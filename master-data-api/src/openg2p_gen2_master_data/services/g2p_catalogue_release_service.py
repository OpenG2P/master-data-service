"""Catalogue releases, the change feed, and the AWE approval callback.

A release is a named, immutable set of list versions plus one geography
version, for consumers that pin everything at once ("the catalogue as of
release 2027.1"). Only published versions can be members. Publishing a release
needs referenceData:publish and a different person from its makers: whoever
created it and whoever last set its members (compared by stable user id).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import delete, func, select

from ..config import Settings
from ..helpers.catalogue_integrations import verify_awe_webhook_signature
from ..models import (
    G2PAttribute,
    G2PCatalogueAweEvent,
    G2PCatalogueChangeLog,
    G2PCatalogueRelease,
    G2PCatalogueReleaseMember,
    G2PCatalogueState,
    G2PGeoVersion,
    G2PListVersion,
    VersionStatus,
)
from ..schemas.g2p_catalogue import AweWebhookEvent, ChangeEvent, ReleaseInfo, ReleaseMember
from .catalogue_common import Actor, CatalogueError, CatalogueUnitOfWork, utcnow
from .g2p_catalogue_geo_service import GEO_ARTIFACT, GEO_SUBJECT, G2PCatalogueGeoService
from .g2p_catalogue_list_service import LIST_ARTIFACT, G2PCatalogueListService

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class G2PCatalogueReleaseService(BaseService):
    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    @staticmethod
    async def _members(s, release_code: str) -> List[ReleaseMember]:
        rows = (
            await s.execute(
                select(G2PCatalogueReleaseMember, G2PAttribute.attribute_code)
                .outerjoin(G2PAttribute, G2PAttribute.attribute_id == G2PCatalogueReleaseMember.list_id)
                .where(G2PCatalogueReleaseMember.release_code == release_code)
                .order_by(G2PAttribute.attribute_code)
            )
        ).all()
        return [
            ReleaseMember(list_id=m.list_id, list_code=code or m.list_id, version_no=m.version_no)
            for m, code in rows
        ]

    @staticmethod
    def _info(r: G2PCatalogueRelease, count: int) -> ReleaseInfo:
        return ReleaseInfo(
            release_code=r.release_code,
            title=r.title,
            note=r.note,
            status=r.status,
            geo_version_no=r.geo_version_no,
            created_by=r.created_by,
            created_by_name=r.created_by_name,
            created_at=r.created_at,
            members_set_by=r.members_set_by,
            members_set_by_name=r.members_set_by_name,
            members_set_at=r.members_set_at,
            published_by=r.published_by,
            published_by_name=r.published_by_name,
            published_at=r.published_at,
            member_count=count,
        )

    async def get_releases(self) -> List[ReleaseInfo]:
        async with get_async_session_maker()() as s:
            counts = dict(
                (
                    await s.execute(
                        select(G2PCatalogueReleaseMember.release_code, func.count()).group_by(
                            G2PCatalogueReleaseMember.release_code
                        )
                    )
                ).all()
            )
            rows = (
                (
                    await s.execute(
                        select(G2PCatalogueRelease).order_by(
                            G2PCatalogueRelease.created_at.desc(), G2PCatalogueRelease.release_code
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [self._info(r, counts.get(r.release_code, 0)) for r in rows]

    async def get_release(self, release_code: str) -> Tuple[ReleaseInfo, List[ReleaseMember]]:
        async with get_async_session_maker()() as s:
            r = await s.get(G2PCatalogueRelease, release_code)
            if not r:
                raise CatalogueError("G2P-CAT-404", f"release not found: {release_code}")
            members = await self._members(s, release_code)
            return self._info(r, len(members)), members

    async def create_release(self, payload, actor: Actor) -> Tuple[ReleaseInfo, List[ReleaseMember]]:
        code = (payload.release_code or "").strip()
        if not code:
            raise CatalogueError("G2P-CAT-400", "release_code is required")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            if await s.get(G2PCatalogueRelease, code):
                raise CatalogueError("G2P-CAT-409", f"release already exists: {code}")
            r = G2PCatalogueRelease(
                release_code=code,
                title=payload.title,
                note=payload.note,
                status=VersionStatus.DRAFT,
                created_by=actor.id,
                created_by_name=actor.display_name,
                created_at=utcnow(),
            )
            s.add(r)
            await s.flush()
            await uow.log("release.created", "release", code, None, {"title": payload.title})
            info = self._info(r, 0)
            await uow.commit()
            return info, []

    async def _draft_release(self, s, code: str) -> G2PCatalogueRelease:
        r = await s.get(G2PCatalogueRelease, code, with_for_update=True)
        if not r:
            raise CatalogueError("G2P-CAT-404", f"release not found: {code}")
        if r.status != VersionStatus.DRAFT:
            raise CatalogueError("G2P-CAT-409", f"release {code} is {r.status} and cannot be changed")
        return r

    async def set_release_members(self, payload, actor: Actor) -> Tuple[ReleaseInfo, List[ReleaseMember]]:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            r = await self._draft_release(s, payload.release_code)
            resolved: Dict[str, int] = {}
            for m in payload.members:
                attr = (
                    (
                        await s.execute(
                            select(G2PAttribute).where(
                                (G2PAttribute.attribute_code == m.list_code)
                                | (G2PAttribute.attribute_id == m.list_code)
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if not attr:
                    raise CatalogueError("G2P-CAT-404", f"list not found: {m.list_code}")
                v = await s.get(G2PListVersion, (attr.attribute_id, m.version_no))
                if not v or v.status != VersionStatus.PUBLISHED:
                    raise CatalogueError(
                        "G2P-CAT-400", f"version {m.version_no} of list {m.list_code} is not published"
                    )
                resolved[attr.attribute_id] = m.version_no
            if "geo_version_no" in payload.model_fields_set:
                if payload.geo_version_no is not None:
                    g = await s.get(G2PGeoVersion, payload.geo_version_no)
                    if not g or g.status != VersionStatus.PUBLISHED:
                        raise CatalogueError(
                            "G2P-CAT-400", f"geography version {payload.geo_version_no} is not published"
                        )
                r.geo_version_no = payload.geo_version_no
            # Choosing the members is making the release: this person may not publish it.
            r.members_set_by = actor.id
            r.members_set_by_name = actor.display_name
            r.members_set_at = utcnow()
            if payload.replace:
                await s.execute(
                    delete(G2PCatalogueReleaseMember).where(
                        G2PCatalogueReleaseMember.release_code == r.release_code
                    )
                )
                await s.flush()
            for list_id, version_no in resolved.items():
                existing = await s.get(G2PCatalogueReleaseMember, (r.release_code, list_id))
                if existing:
                    existing.version_no = version_no
                else:
                    s.add(
                        G2PCatalogueReleaseMember(
                            release_code=r.release_code, list_id=list_id, version_no=version_no
                        )
                    )
            await s.flush()
            await uow.log(
                "release.members_set",
                "release",
                r.release_code,
                None,
                {"members": resolved, "geo_version_no": r.geo_version_no, "replace": payload.replace},
            )
            members = await self._members(s, r.release_code)
            info = self._info(r, len(members))
            await uow.commit()
            return info, members

    async def publish_release(
        self, release_code: str, actor: Actor
    ) -> Tuple[ReleaseInfo, List[ReleaseMember]]:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            r = await self._draft_release(s, release_code)
            makers = {m for m in (r.created_by, r.members_set_by) if m}
            if actor.id in makers:
                raise CatalogueError(
                    "G2P-CAT-403",
                    "maker-checker: the publisher must not be the person who created the release "
                    "or last set its members",
                )
            members = await self._members(s, release_code)
            if not members and r.geo_version_no is None:
                raise CatalogueError(
                    "G2P-CAT-400", "a release must pin at least one list or a geography version"
                )
            pinned = {m.list_id: m.version_no for m in members}
            list_service = G2PCatalogueListService.get_component()
            for m in members:
                v = await s.get(G2PListVersion, (m.list_id, m.version_no))
                if not v or v.status != VersionStatus.PUBLISHED:
                    raise CatalogueError(
                        "G2P-CAT-400", f"version {m.version_no} of {m.list_code} is not published"
                    )
                # References between lists must resolve inside the release where possible.
                attr = await s.get(G2PAttribute, m.list_id)
                await list_service.validate_version(s, attr, v, release_versions=pinned)
            r.status = VersionStatus.PUBLISHED
            r.published_by = actor.id
            r.published_by_name = actor.display_name
            r.published_at = utcnow()
            await s.flush()
            details = {
                "members": {m.list_code: m.version_no for m in members},
                "geo_version_no": r.geo_version_no,
            }
            await uow.log("release.published", "release", release_code, None, details)
            info = self._info(r, len(members))
            await uow.commit()
            return info, members

    async def delete_release(self, release_code: str, actor: Actor) -> str:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            await self._draft_release(s, release_code)
            await s.execute(
                delete(G2PCatalogueRelease).where(G2PCatalogueRelease.release_code == release_code)
            )
            await uow.log("release.deleted", "release", release_code, None, {})
            await uow.commit()
            return release_code


class G2PCatalogueFeedService(BaseService):
    """The change feed: the append-only change log read with a cursor."""

    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    async def get_changes(
        self,
        cursor: int,
        limit: int,
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        event_types: Optional[List[str]] = None,
    ) -> Tuple[List[ChangeEvent], int, bool]:
        C = G2PCatalogueChangeLog
        async with get_async_session_maker()() as s:
            stmt = select(C).where(C.event_id > cursor)
            if subject_type:
                stmt = stmt.where(C.subject_type == subject_type)
            if subject_id:
                stmt = stmt.where(C.subject_id == subject_id)
            if event_types:
                stmt = stmt.where(C.event_type.in_(event_types))
            rows = (await s.execute(stmt.order_by(C.event_id).limit(limit + 1))).scalars().all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        events = [
            ChangeEvent(
                event_id=r.event_id,
                event_type=r.event_type,
                subject_type=r.subject_type,
                subject_id=r.subject_id,
                version_no=r.version_no,
                actor=r.actor,
                actor_name=r.actor_name,
                at=r.at,
                details=r.details,
            )
            for r in rows
        ]
        return events, (rows[-1].event_id if rows else cursor), has_more

    async def config_state(self) -> Dict[str, Any]:
        async with get_async_session_maker()() as s:
            st = await s.get(G2PCatalogueState, "geo.current_version_no")
            latest_geo = (
                (
                    await s.execute(
                        select(G2PGeoVersion.country)
                        .where(G2PGeoVersion.country.is_not(None))
                        .order_by(G2PGeoVersion.version_no.desc())
                    )
                )
                .scalars()
                .first()
            )
        return {
            "geo_current_version_no": st.int_value if st else None,
            "country": latest_geo or (_config.catalogue_country or None),
        }


class G2PCatalogueAweCallbackService(BaseService):
    """Applies AWE terminal decisions: request_approved -> publish, rejected/cancelled -> REJECTED.

    Authenticated by the HMAC signature (no JWT), idempotent on event_id.
    """

    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    async def handle(
        self,
        *,
        raw_body: bytes,
        signature_header: Optional[str],
        timestamp_header: Optional[str],
        header_event_id: Optional[str],
    ) -> Dict[str, Any]:
        verify_awe_webhook_signature(
            secret=(_config.awe_callback_hmac_secret or "").strip(),
            body=raw_body,
            signature_header=signature_header,
            timestamp_header=timestamp_header,
            tolerance_seconds=_config.awe_webhook_timestamp_tolerance_seconds,
        )
        event = AweWebhookEvent.model_validate(json.loads(raw_body))
        if header_event_id and header_event_id != event.event_id:
            raise CatalogueError("G2P-CAT-400", "X-Approval-Event-Id does not match the body")

        # AWE's approver id as AWE reports it; without one the decision is AWE's own.
        actor = Actor(id=event.actor, name=event.actor) if event.actor else Actor.system("awe")
        try:
            return await self._handle(event, actor)
        except Exception as exc:
            await self._record_failure(event, exc)
            raise

    async def _record_failure(self, event: AweWebhookEvent, exc: Exception) -> None:
        try:
            async with get_async_session_maker()() as s:
                row = await s.get(G2PCatalogueAweEvent, event.event_id)
                if row is None:
                    row = G2PCatalogueAweEvent(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        request_id=event.request_id,
                        artifact_type=event.artifact_type,
                        artifact_id=event.artifact_id,
                        status=event.status,
                        actor=event.actor,
                        occurred_at=event.occurred_at,
                        received_at=utcnow(),
                    )
                    s.add(row)
                row.applied = False
                row.error = str(getattr(exc, "message", exc))[:2000]
                await s.commit()
        except Exception:
            _logger.exception("could not record the failed AWE event %s", event.event_id)

    async def _handle(self, event: AweWebhookEvent, actor: Actor) -> Dict[str, Any]:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            row = await s.get(G2PCatalogueAweEvent, event.event_id)
            if row and row.applied:
                return {"event_id": event.event_id, "applied": True, "message": "duplicate"}
            if row is None:
                row = G2PCatalogueAweEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    request_id=event.request_id,
                    artifact_type=event.artifact_type,
                    artifact_id=event.artifact_id,
                    status=event.status,
                    actor=event.actor,
                    occurred_at=event.occurred_at,
                    received_at=utcnow(),
                    applied=False,
                )
                s.add(row)
            message = "ok"
            if event.event_type in ("request_approved", "request_rejected", "request_cancelled"):
                message = await self._apply(uow, event)
            row.applied = True
            await s.flush()
            await uow.commit()
            return {"event_id": event.event_id, "applied": True, "message": message}

    async def _apply(self, uow: CatalogueUnitOfWork, event: AweWebhookEvent) -> str:
        s = uow.session
        subject, _, version = event.artifact_id.rpartition(":")
        try:
            version_no = int(version)
        except ValueError as exc:
            raise CatalogueError("G2P-CAT-400", f"unrecognised artifact_id {event.artifact_id}") from exc
        approved = event.event_type == "request_approved"
        note = {
            "request_approved": "Approved via AWE",
            "request_rejected": "Rejected via AWE",
            "request_cancelled": "AWE request cancelled",
        }[event.event_type]

        if event.artifact_type == LIST_ARTIFACT:
            svc = G2PCatalogueListService.get_component()
            attr = await s.get(G2PAttribute, subject, with_for_update=True)
            if not attr:
                raise CatalogueError("G2P-CAT-404", f"list {subject} not found")
            v = await s.get(G2PListVersion, (subject, version_no))
            if not v:
                raise CatalogueError("G2P-CAT-404", f"version {version_no} of list {subject} not found")
            if v.approval_ref and v.approval_ref != event.request_id:
                raise CatalogueError("G2P-CAT-409", "AWE request id does not match the version")
            if v.status != VersionStatus.SUBMITTED:
                return f"already {v.status}"
            if approved:
                await svc.publish(uow, attr, v, None, note)
            else:
                await svc.reject(uow, attr, v, note)
            return "published" if approved else "rejected"

        if event.artifact_type == GEO_ARTIFACT and subject == GEO_SUBJECT:
            svc = G2PCatalogueGeoService.get_component()
            v = await s.get(G2PGeoVersion, version_no, with_for_update=True)
            if not v:
                raise CatalogueError("G2P-CAT-404", f"geography version {version_no} not found")
            if v.approval_ref and v.approval_ref != event.request_id:
                raise CatalogueError("G2P-CAT-409", "AWE request id does not match the version")
            if v.status != VersionStatus.SUBMITTED:
                return f"already {v.status}"
            if approved:
                await svc.publish(uow, v, None, note)
            else:
                await svc.reject(uow, v, note)
            return "published" if approved else "rejected"

        raise CatalogueError("G2P-CAT-400", f"unsupported artifact_type {event.artifact_type}")
