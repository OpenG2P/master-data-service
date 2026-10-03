"""Uniform delivery of catalogue events, and the per-worker background loop.

Outbox
------
Every row of ``g2p_catalogue_change_log`` is an outbox entry. Whoever wrote it
— the API, the database itself (``*.version.effective`` when a future-effective
version comes into effect, ``*.version.migrated`` at migration) or the
country-pack loader — it is delivered the same way:

* to the Audit Manager as a CloudEvent (every event), and
* to WebSub (``*.version.published``, ``*.version.effective``,
  ``release.published``),

and ``forwarded_at`` is set only once both have accepted it (or there was
nowhere to send it). Delivery is at-least-once; the CloudEvent id is derived
from the change-log event id, so a receiver can de-duplicate a retry.

Two paths deliver:

* right after an API transaction commits, its own events are delivered
  fire-and-forget (``deliver_after_commit``) — the request never waits;
* the relay (``relay_pending``), run by every worker's background loop, picks
  up everything still pending: DB- and loader-written events, and API events
  whose immediate delivery failed. A Postgres advisory lock lets only one
  worker in the deployment relay at a time; rows are claimed with
  ``FOR UPDATE SKIP LOCKED`` so the two paths never send the same row at once.

Delivery stops at the first event that could not be delivered (5xx, timeout,
408/429) and the rest are retried on the next run. Order: the relay sends in
event-id order; a worker's immediate deliveries are serialised in commit order
(one asyncio lock per worker); across workers only the relay orders events, and
every CloudEvent carries the change-log time and event id.

Why an asyncio task and not a CronJob: the API already runs a periodic loop for
effective dates, it has the configuration and the HTTP clients, and the
advisory lock makes running it in every worker safe. No extra deployment unit.

Legacy read cache
-----------------
Legacy reads are cached in memory per worker (fastapi-cache). The worker that
publishes drops its cache after commit; every worker's loop polls
``g2p_catalogue_state['legacy.generation']`` (bumped by the database whenever
the legacy tables are re-materialised — by a publish on any worker or pod, by a
future-effective version coming into effect, or by the loader) and drops its
cache when it moved. A legacy read is thus stale for at most
``catalogue_outbox_relay_seconds`` (and never longer than
``cache_expire_seconds``, when cache entries expire anyway).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

import httpx
from openg2p_fastapi_common.context import get_async_session_maker
from sqlalchemy import text

from ..config import Settings
from ..helpers.catalogue_integrations import (
    CatalogueAuditHelper,
    CatalogueWebSubHelper,
    spawn_background,
)

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)

_RELAY_LOCK = "g2p_catalogue_outbox"

# Events that change which version of a subject exists or is in effect: they go
# to WebSub, and (published/effective/migrated) re-materialise the legacy tables.
_WEBSUB_SUFFIXES = (".version.published", ".version.effective")
_WEBSUB_EXACT = ("release.published",)


def is_websub_event(event_type: str) -> bool:
    return event_type in _WEBSUB_EXACT or event_type.endswith(_WEBSUB_SUFFIXES)


def changes_legacy_state(event_type: str) -> bool:
    return event_type.endswith((".version.published", ".version.effective", ".version.migrated"))


def websub_topic(change: Dict[str, Any]) -> str:
    kind = "effective" if change["event_type"].endswith(".effective") else "published"
    return CatalogueWebSubHelper.topic_for(change["subject_type"], kind)


def websub_payload(change: Dict[str, Any]) -> Dict[str, Any]:
    """The notification body: the event's details plus who/what/which version."""
    subject_type = change["subject_type"]
    payload: Dict[str, Any] = dict(change.get("details") or {})
    payload.update(
        {
            "event_id": change.get("event_id"),
            "event_type": change["event_type"],
            "subject_type": subject_type,
            "subject_id": change.get("subject_id"),
        }
    )
    if change.get("version_no") is not None:
        payload["version_no"] = change["version_no"]
    if subject_type == "list":
        payload["list_id"] = change.get("subject_id")
    elif subject_type == "release":
        payload["release_code"] = change.get("subject_id")
    return payload


def _enabled() -> bool:
    return CatalogueAuditHelper.enabled() or CatalogueWebSubHelper.enabled()


async def _deliver(rows: List[Dict[str, Any]]) -> List[int]:
    """Send rows in order; return the event ids that need no retry (a prefix)."""
    if not _enabled():
        return [r["event_id"] for r in rows]
    audit = CatalogueAuditHelper.get_component() or CatalogueAuditHelper()
    websub = CatalogueWebSubHelper.get_component() or CatalogueWebSubHelper()
    done: List[int] = []
    async with httpx.AsyncClient(timeout=max(_config.audit_timeout_seconds, 10.0)) as client:
        for row in rows:
            try:
                ok = await audit.send(client, row)
                if ok and is_websub_event(row["event_type"]):
                    ok = await websub.send(client, websub_topic(row), websub_payload(row))
            except Exception:
                _logger.exception("Delivering catalogue event %s failed", row.get("event_id"))
                ok = False
            if not ok:
                break
            done.append(row["event_id"])
    return done


_SELECT = """
SELECT event_id, event_type, subject_type, subject_id, version_no, actor, actor_name, at, details
  FROM g2p_catalogue_change_log
 WHERE forwarded_at IS NULL {extra}
 ORDER BY event_id
 LIMIT :limit
 FOR UPDATE SKIP LOCKED
"""


async def _forward(event_ids: Optional[Iterable[int]] = None, *, limit: Optional[int] = None) -> int:
    """Claim pending rows (all, or only ``event_ids``), deliver, mark. Returns rows marked."""
    limit = limit or _config.catalogue_outbox_batch_size
    async with get_async_session_maker()() as s:
        async with s.begin():
            params: Dict[str, Any] = {"limit": limit}
            if event_ids is None:
                got = (
                    await s.execute(
                        text("SELECT pg_try_advisory_xact_lock(hashtext(:k))"), {"k": _RELAY_LOCK}
                    )
                ).scalar_one()
                if not got:
                    return 0
                extra = ""
            else:
                ids = list(event_ids)
                if not ids:
                    return 0
                extra = "AND event_id = ANY(:ids)"
                params["ids"] = ids
            rows = [dict(r._mapping) for r in (await s.execute(text(_SELECT.format(extra=extra)), params))]
            if not rows:
                return 0
            done = await _deliver(rows)
            if done:
                await s.execute(
                    text(
                        "UPDATE g2p_catalogue_change_log SET forwarded_at = now() "
                        "WHERE event_id = ANY(:ids) AND forwarded_at IS NULL"
                    ),
                    {"ids": done},
                )
            if len(done) < len(rows):
                _logger.info(
                    "Catalogue outbox: %s event(s) left for the next relay run", len(rows) - len(done)
                )
            return len(done)


async def relay_pending(max_batches: int = 50) -> int:
    """Forward every pending event (one worker at a time). Returns how many were forwarded."""
    total = 0
    for _ in range(max_batches):
        n = await _forward(limit=_config.catalogue_outbox_batch_size)
        total += n
        if n < _config.catalogue_outbox_batch_size:
            break
    return total


_immediate_lock: Dict[int, asyncio.Lock] = {}


def _lock_for_loop() -> asyncio.Lock:
    loop_id = id(asyncio.get_running_loop())
    lock = _immediate_lock.get(loop_id)
    if lock is None:
        _immediate_lock.clear()
        lock = _immediate_lock[loop_id] = asyncio.Lock()
    return lock


async def _deliver_quietly(event_ids: List[int]) -> None:
    try:
        # FIFO: this worker's transactions are delivered in the order they committed.
        async with _lock_for_loop():
            await _forward(event_ids, limit=len(event_ids))
    except Exception:
        _logger.exception("Immediate delivery of catalogue events failed; the relay will retry")


def deliver_after_commit(event_ids: List[int]) -> None:
    """Fire-and-forget delivery of a just-committed transaction's events.

    Without an Audit Manager or WebSub configured there is nothing to wait for:
    the relay marks the rows on its next run.
    """
    if event_ids and _enabled():
        spawn_background(_deliver_quietly(list(event_ids)))


async def refresh_current() -> int:
    """Bring future-effective versions into effect (DB function; one caller at a time)."""
    async with get_async_session_maker()() as s:
        async with s.begin():
            return (await s.execute(text("SELECT g2p_catalogue_refresh_current()"))).scalar_one()


# ---------------------------------------------------------------------------
# Legacy read cache (per worker)
# ---------------------------------------------------------------------------

_seen_generation: Dict[str, Optional[int]] = {"value": None}


async def clear_read_cache() -> None:
    """Drop this worker's cached legacy reads."""
    try:
        from fastapi_cache import FastAPICache

        await FastAPICache.clear()
    except Exception:
        pass


async def legacy_generation() -> Optional[int]:
    async with get_async_session_maker()() as s:
        return (
            await s.execute(text("SELECT int_value FROM g2p_catalogue_state WHERE key = 'legacy.generation'"))
        ).scalar_one_or_none()


async def sync_read_cache() -> bool:
    """Drop this worker's cache if the legacy tables changed since it last looked."""
    gen = await legacy_generation()
    changed = gen != _seen_generation["value"]
    _seen_generation["value"] = gen
    if changed:
        await clear_read_cache()
    return changed


def note_generation(gen: Optional[int]) -> None:
    _seen_generation["value"] = gen


# ---------------------------------------------------------------------------
# The background loop (one per worker)
# ---------------------------------------------------------------------------


class BackgroundCycle:
    """One iteration of the per-worker loop; kept separate so tests can drive it."""

    def __init__(self) -> None:
        self._last_refresh = 0.0

    async def run_once(self, *, force_refresh: bool = False) -> Dict[str, int]:
        out = {"effective": 0, "forwarded": 0, "cache_cleared": 0}
        refresh_every = _config.catalogue_effective_refresh_seconds
        now = time.monotonic()
        if force_refresh or (refresh_every and now - self._last_refresh >= refresh_every):
            self._last_refresh = now
            out["effective"] = await refresh_current()
            if out["effective"]:
                _logger.info(
                    "Catalogue: %s version(s) came into effect; legacy tables refreshed", out["effective"]
                )
        if _config.catalogue_outbox_relay_seconds or out["effective"]:
            out["forwarded"] = await relay_pending()
        if await sync_read_cache():
            out["cache_cleared"] = 1
        return out

    async def loop(self) -> None:
        intervals = [
            x
            for x in (_config.catalogue_outbox_relay_seconds, _config.catalogue_effective_refresh_seconds)
            if x and x > 0
        ]
        if not intervals:
            return
        tick = min(intervals)
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("Catalogue background cycle failed")
            await asyncio.sleep(tick)
