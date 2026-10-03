"""Shared plumbing for the catalogue services.

- ``CatalogueError``: the error every catalogue operation raises (``G2P-CAT-*``).
- ``Actor``: who is acting (and their bearer token, forwarded to AWE).
- ``CatalogueUnitOfWork``: one transaction; writes change-log events inside it
  and, after commit, hands them to the outbox (services/catalogue_outbox.py)
  for delivery to the Audit Manager and WebSub. The change log is the outbox,
  so the local log is exact and delivery is retried when the outbound calls
  fail.
- typed attribute validation (JSON Schema + ``x-list-ref``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from openg2p_fastapi_common.context import get_async_session_maker
from sqlalchemy import insert
from sqlalchemy.exc import DBAPIError

from ..config import Settings
from ..models import G2PCatalogueChangeLog

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class CatalogueError(Exception):
    """``code`` is G2P-CAT-400 (bad request), -403 (not allowed), -404, -409 (state conflict)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class Actor:
    """Who is acting.

    ``id`` is the STABLE identifier of the user — the token's ``sub`` claim
    (Keycloak's user id), the same id the registry platform's audit middleware
    records as the actor. It is what lands in created_by / updated_by /
    submitted_by / decided_by / published_by / members_set_by and in the change
    log, and what maker != checker compares: a display name is neither unique
    nor stable (two "Abebe Kebede"s; a renamed user), so it must never decide
    who may approve. ``name`` is the display name (``name`` claim, else
    ``preferred_username``), kept for people to read (change log
    ``actor_name``, audit ``actor.name``).
    """

    id: str
    token: Optional[str] = None
    name: Optional[str] = None
    is_system: bool = False

    @property
    def display_name(self) -> Optional[str]:
        """What the change log records as actor_name: None marks a system actor."""
        return None if self.is_system else (self.name or self.id)

    @classmethod
    def system(cls, name: str = "system") -> "Actor":
        return cls(id=name, is_system=True)


def _jwt_claims(token: Optional[str]) -> Dict[str, Any]:
    """Payload of an already-validated JWT (no verification here: iam-core did it)."""
    if not token or token.count(".") != 2:
        return {}
    try:
        import base64
        import json

        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        claims = json.loads(base64.urlsafe_b64decode(part.encode()))
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def actor_from_request(request) -> Actor:
    """The validated principal (``request.state.auth``, set by iam-core) as an Actor.

    id = ``sub`` (fallback: ``preferred_username``, then ``name``, for an IdP
    that leaves ``sub`` out); name = ``name`` (fallback ``preferred_username``).
    The bearer token is kept for AWE.
    """
    auth = getattr(getattr(request, "state", None), "auth", None) if request is not None else None
    name = getattr(auth, "name", None) if auth else None
    sub = getattr(auth, "sub", None) if auth else None
    token = getattr(auth, "credentials", None) if auth else None
    if not token and request is not None:
        header = request.headers.get("authorization", "")
        parts = header.split(maxsplit=1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    username = None
    if auth is not None and (not sub or not name):
        username = getattr(auth, "preferred_username", None) or _jwt_claims(token).get("preferred_username")
    actor_id = sub or username or name or "anonymous"
    return Actor(id=str(actor_id), token=token, name=name or username or (str(actor_id) if auth else None))


_DB_CODE = re.compile(r"(G2P-CAT-(?:IMMUTABLE|\d{3}))[: ]\s*(.*)", re.S)


def translate_db_error(exc: Exception) -> Exception:
    """Map a trigger / function RAISE to a CatalogueError; leave anything else alone."""
    if not isinstance(exc, DBAPIError):
        return exc
    text = str(getattr(exc, "orig", None) or exc)
    m = _DB_CODE.search(text)
    if not m:
        return exc
    code, message = m.group(1), m.group(2).split("\n")[0].strip()
    if code == "G2P-CAT-IMMUTABLE":
        return CatalogueError("G2P-CAT-409", f"immutable: {message}")
    return CatalogueError(code, message)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class CatalogueUnitOfWork:
    """``async with CatalogueUnitOfWork(actor) as uow:`` … ``await uow.commit()``."""

    def __init__(self, actor: Actor):
        self.actor = actor
        self.session = None
        self._changes: List[Dict[str, Any]] = []
        self._after_commit: List[Callable[[], Any]] = []

    async def __aenter__(self) -> "CatalogueUnitOfWork":
        self.session = get_async_session_maker()()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if exc_type is not None:
                await self.session.rollback()
        finally:
            await self.session.close()
        if exc is not None:
            translated = translate_db_error(exc)
            if translated is not exc:
                raise translated from exc
        return False

    async def log(
        self,
        event_type: str,
        subject_type: str,
        subject_id: Optional[str],
        version_no: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        actor: Optional[str] = None,
    ) -> int:
        actor_id = actor or self.actor.id
        actor_name = self.actor.display_name if actor is None else None
        event_id = (
            await self.session.execute(
                insert(G2PCatalogueChangeLog)
                .values(
                    event_type=event_type,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    version_no=version_no,
                    actor=actor_id,
                    actor_name=actor_name,
                    at=utcnow(),
                    details=details or {},
                )
                .returning(G2PCatalogueChangeLog.event_id)
            )
        ).scalar_one()
        self._changes.append({"event_id": event_id, "event_type": event_type})
        return event_id

    def after_commit(self, fn: Callable[[], Any]) -> None:
        self._after_commit.append(fn)

    async def commit(self) -> None:
        from .catalogue_outbox import changes_legacy_state, clear_read_cache, deliver_after_commit

        try:
            await self.session.commit()
        except Exception as exc:
            translated = translate_db_error(exc)
            if translated is not exc:
                raise translated from exc
            raise
        if self._changes:
            # Fire-and-forget; marked forwarded only on success, else the relay retries.
            deliver_after_commit([c["event_id"] for c in self._changes])
        if any(changes_legacy_state(c["event_type"]) for c in self._changes):
            # This worker's cache now; other workers within catalogue_outbox_relay_seconds.
            await clear_read_cache()
        for fn in self._after_commit:
            try:
                result = fn()
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                _logger.exception("after-commit hook failed")
        self._changes, self._after_commit = [], []


# ---------------------------------------------------------------------------
# Typed attributes
# ---------------------------------------------------------------------------


def check_attribute_schema(schema: Optional[Dict[str, Any]]) -> None:
    if schema is None:
        return
    if not isinstance(schema, dict):
        raise CatalogueError("G2P-CAT-400", "attribute_schema must be a JSON object")
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise CatalogueError(
            "G2P-CAT-400", f"attribute_schema is not a valid JSON Schema: {exc.message}"
        ) from exc


def schema_list_refs(schema: Optional[Dict[str, Any]], path: str = "") -> List[Tuple[str, str]]:
    """[(json path, referenced list code)] for every ``x-list-ref`` in the schema."""
    out: List[Tuple[str, str]] = []
    if not isinstance(schema, dict):
        return out
    ref = schema.get("x-list-ref")
    if isinstance(ref, str) and ref:
        out.append((path or "$", ref))
    for name, sub in (schema.get("properties") or {}).items():
        out.extend(schema_list_refs(sub, f"{path}.{name}" if path else name))
    items = schema.get("items")
    if isinstance(items, dict):
        out.extend(schema_list_refs(items, f"{path}[]"))
    return out


def schema_summary(schema: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not schema:
        return None
    return {
        "properties": sorted((schema.get("properties") or {}).keys()),
        "required": list(schema.get("required") or []),
        "list_refs": {p: r for p, r in schema_list_refs(schema)},
    }


def _collect_ref_values(schema: Any, instance: Any, out: Dict[str, set], path: str = "") -> None:
    if not isinstance(schema, dict):
        return
    ref = schema.get("x-list-ref")
    if isinstance(ref, str) and ref and instance is not None:
        values = instance if isinstance(instance, list) else [instance]
        for v in values:
            if isinstance(v, str):
                out.setdefault(ref, set()).add(v)
    if isinstance(instance, dict):
        for name, sub in (schema.get("properties") or {}).items():
            if name in instance:
                _collect_ref_values(sub, instance[name], out, f"{path}.{name}")
    items = schema.get("items")
    if isinstance(items, dict) and isinstance(instance, list):
        for item in instance:
            _collect_ref_values(items, item, out, f"{path}[]")


def validate_value_attributes(
    schema: Optional[Dict[str, Any]], value_code: str, attributes: Optional[Dict[str, Any]]
) -> Dict[str, set]:
    """Validate one value's attributes; return {referenced list code: {codes}} to check."""
    if not schema:
        return {}
    from jsonschema import Draft202012Validator

    instance = attributes if attributes is not None else {}
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "(root)"
        raise CatalogueError(
            "G2P-CAT-400",
            f"value '{value_code}': attributes invalid at {where}: {first.message}",
        )
    refs: Dict[str, set] = {}
    _collect_ref_values(schema, instance, refs)
    return refs


def merge_refs(target: Dict[str, set], extra: Dict[str, set]) -> Dict[str, set]:
    for k, v in extra.items():
        target.setdefault(k, set()).update(v)
    return target


def diff_fields(before: Any, after: Any, fields: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for f in fields:
        b = getattr(before, f, None) if before is not None else None
        a = getattr(after, f, None) if after is not None else None
        if (b or None) != (a or None) and b != a:
            out[f] = {"before": b, "after": a}
    return out
