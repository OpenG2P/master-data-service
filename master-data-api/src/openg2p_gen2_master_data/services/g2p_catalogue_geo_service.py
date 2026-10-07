"""Versioned geography: levels + units + boundaries as ONE dataset, with lineage.

A boundary change ripples across levels, so geography is versioned as a whole.
Each version records change events (CREATE, RETIRE, RENAME, RECODE, SPLIT,
MERGE, REPARENT, BOUNDARY_CHANGE) against its base version; the crosswalk
follows them across any number of versions to map a unit of one version to its
successors (or predecessors) in another.

Same lifecycle as lists (DRAFT -> SUBMITTED -> PUBLISHED | REJECTED, or
DISCARDED), one open draft at a time, units never deleted from anything
published (RETIRED instead). Version numbers come from
g2p_catalogue_next_geo_version and are never reused, so a draft's boundary
objects (geo/<country>/v<n>/<level>.geojson) can never land on another
version's keys. The rules for change events live in catalogue_geo_rules.py,
shared with the country-pack loader. Publishing runs g2p_catalogue_publish_geo, which stamps valid_from /
valid_to on the units and refreshes g2p_geo_levels / g2p_geo_level_values.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import func, insert, literal, or_, select, text, update

from ..config import Settings
from ..helpers.catalogue_integrations import (
    AweClientError,
    BoundaryStore,
    CatalogueAweHelper,
    approval_mode,
    boundary_object_key,
)
from ..helpers.data_policy_helper import DataPolicyHelper
from ..models import (
    G2PCatalogueRelease,
    G2PCatalogueState,
    G2PGeoChange,
    G2PGeoVersion,
    G2PGeoVersionLevel,
    G2PGeoVersionUnit,
    GeoChangeType,
    ItemStatus,
    VersionStatus,
)
from ..repositories import GeoLevelValueRepository
from ..schemas import GeoLevelData, GeoLevelValueData
from ..schemas.g2p_catalogue import (
    CrosswalkStep,
    GeoChange,
    GeoLevel,
    GeoSettings,
    GeoUnit,
    GeoVersionInfo,
    VersionSelector,
)
from ..catalogue_geo_rules import GeoChangeRuleError, check_geo_change
from .catalogue_common import Actor, CatalogueError, CatalogueUnitOfWork, as_aware, utcnow

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)

GEO_ARTIFACT = "master_data.geo_version"
GEO_SUBJECT = "geography"
# Events after which a unit does not continue as itself (same set as catalogue_geo_rules.TERMINAL).
_TERMINAL = {GeoChangeType.RETIRE, GeoChangeType.SPLIT, GeoChangeType.MERGE, GeoChangeType.RECODE}

# Administrative settings of the geography (not versioned: a PUBLISHED version
# row is immutable), kept in g2p_catalogue_state. The country-pack loader fills
# the licence from the pack manifest when none is set.
GEO_SETTING_KEYS = {
    "visibility": "geo.visibility",
    "licence_uri": "geo.licence_uri",
    "licence_label": "geo.licence_label",
}


async def read_geo_settings(session) -> GeoSettings:
    rows = (
        await session.execute(
            select(G2PCatalogueState.key, G2PCatalogueState.text_value).where(
                G2PCatalogueState.key.in_(list(GEO_SETTING_KEYS.values()))
            )
        )
    ).all()
    stored = {k: v for k, v in rows}
    visibility = (stored.get(GEO_SETTING_KEYS["visibility"]) or "").strip().lower()
    return GeoSettings(
        visibility="public" if visibility == "public" else "private",
        licence_uri=stored.get(GEO_SETTING_KEYS["licence_uri"]) or None,
        licence_label=stored.get(GEO_SETTING_KEYS["licence_label"]) or None,
    )


def _unit(u: G2PGeoVersionUnit) -> GeoUnit:
    return GeoUnit(
        unit_id=u.unit_id,
        level_id=u.level_id,
        name=u.name,
        name_i18n=u.name_i18n,
        parent_unit_id=u.parent_unit_id,
        status=u.status,
        valid_from=u.valid_from,
        valid_to=u.valid_to,
    )


def _level(lv: G2PGeoVersionLevel) -> GeoLevel:
    return GeoLevel(
        level_id=lv.level_id,
        level_mnemonic=lv.level_mnemonic,
        parent_level_id=lv.parent_level_id,
        display=lv.display or lv.level_mnemonic,
        display_i18n=lv.display_i18n,
    )


def _change(c: G2PGeoChange) -> GeoChange:
    return GeoChange(
        change_id=c.change_id,
        version_no=c.version_no,
        change_type=c.change_type,
        from_units=list(c.from_units or []),
        to_units=list(c.to_units or []),
        effective_date=c.effective_date,
        note=c.note,
        is_auto=bool(c.is_auto),
        created_by=c.created_by,
        created_by_name=c.created_by_name,
        created_at=c.created_at,
    )


def geometry_hash(geometry: Any) -> str:
    return hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[
        :16
    ]


def feature_unit_id(feature: Dict[str, Any]) -> Optional[str]:
    props = feature.get("properties") or {}
    return props.get("pcode") or props.get("unit_id") or props.get("level_value_id") or feature.get("id")


class G2PCatalogueGeoService(BaseService):
    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    @staticmethod
    async def current_no(session, at: Optional[datetime] = None) -> Optional[int]:
        return (
            await session.execute(
                select(func.max(G2PGeoVersion.version_no)).where(
                    G2PGeoVersion.status == VersionStatus.PUBLISHED,
                    G2PGeoVersion.effective_from <= (at if at is not None else func.now()),
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _max_published_no(session) -> Optional[int]:
        return (
            await session.execute(
                select(func.max(G2PGeoVersion.version_no)).where(
                    G2PGeoVersion.status == VersionStatus.PUBLISHED
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _open_version(session, *, lock: bool = False) -> Optional[G2PGeoVersion]:
        stmt = select(G2PGeoVersion).where(G2PGeoVersion.status.in_(VersionStatus.OPEN))
        if lock:
            stmt = stmt.with_for_update()
        return (await session.execute(stmt)).scalars().first()

    async def _info(
        self, session, v: G2PGeoVersion, current: Optional[int], with_count: bool = True
    ) -> GeoVersionInfo:
        count = None
        if with_count:
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(G2PGeoVersionUnit)
                    .where(
                        G2PGeoVersionUnit.version_no == v.version_no,
                        G2PGeoVersionUnit.status == ItemStatus.ACTIVE,
                    )
                )
            ).scalar_one()
        return GeoVersionInfo(
            version_no=v.version_no,
            status=v.status,
            base_version_no=v.base_version_no,
            effective_from=v.effective_from,
            published_at=v.published_at,
            is_latest=current is not None and v.version_no == current,
            change_note=v.change_note,
            created_by=v.created_by,
            created_by_name=v.created_by_name,
            created_at=v.created_at,
            updated_by=v.updated_by,
            updated_by_name=v.updated_by_name,
            updated_at=v.updated_at,
            submitted_by=v.submitted_by,
            submitted_by_name=v.submitted_by_name,
            submitted_at=v.submitted_at,
            decided_by=v.decided_by,
            decided_by_name=v.decided_by_name,
            decided_at=v.decided_at,
            decision_note=v.decision_note,
            approval_ref=v.approval_ref,
            country=v.country or (_config.catalogue_country or None),
            owner_org=v.owner_org,
            boundary_objects=v.boundary_objects or {},
            unit_count=count,
        )

    async def resolve_version(
        self, session, sel: Optional[VersionSelector]
    ) -> Tuple[G2PGeoVersion, Optional[int]]:
        sel = sel or VersionSelector()
        given = [x for x in (sel.version, sel.as_of, sel.release) if x is not None]
        if len(given) > 1:
            raise CatalogueError("G2P-CAT-400", "give at most one of version, as_of, release")
        current = await self.current_no(session)
        if sel.release:
            release = await session.get(G2PCatalogueRelease, sel.release)
            if not release or release.geo_version_no is None:
                raise CatalogueError("G2P-CAT-404", f"release {sel.release} does not pin a geography version")
            no = release.geo_version_no
        elif sel.as_of is not None:
            no = await self.current_no(session, as_aware(sel.as_of))
            if no is None:
                raise CatalogueError("G2P-CAT-404", f"no geography version was in effect at {sel.as_of}")
        elif sel.version == "draft":
            draft = await self._open_version(session)
            if not draft:
                raise CatalogueError("G2P-CAT-404", "geography has no open draft")
            return draft, current
        elif isinstance(sel.version, int):
            no = sel.version
        else:
            no = current
            if no is None:
                raise CatalogueError("G2P-CAT-404", "no published geography version is in effect")
        v = await session.get(G2PGeoVersion, no)
        if not v:
            raise CatalogueError("G2P-CAT-404", f"geography version {no} not found")
        return v, current

    @staticmethod
    async def _levels(session, version_no: int) -> Dict[str, G2PGeoVersionLevel]:
        rows = (
            (
                await session.execute(
                    select(G2PGeoVersionLevel).where(G2PGeoVersionLevel.version_no == version_no)
                )
            )
            .scalars()
            .all()
        )
        return {r.level_id: r for r in rows}

    @staticmethod
    async def _units(session, version_no: int) -> Dict[str, G2PGeoVersionUnit]:
        rows = (
            (
                await session.execute(
                    select(G2PGeoVersionUnit).where(G2PGeoVersionUnit.version_no == version_no)
                )
            )
            .scalars()
            .all()
        )
        return {r.unit_id: r for r in rows}

    @staticmethod
    def _find_level(levels: Dict[str, G2PGeoVersionLevel], level: str) -> G2PGeoVersionLevel:
        if level in levels:
            return levels[level]
        for lv in levels.values():
            if lv.level_mnemonic == level:
                return lv
        raise CatalogueError("G2P-CAT-404", f"level not found: {level}")

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_geo_versions(self) -> List[GeoVersionInfo]:
        async with get_async_session_maker()() as s:
            current = await self.current_no(s)
            counts = dict(
                (
                    await s.execute(
                        select(G2PGeoVersionUnit.version_no, func.count())
                        .where(G2PGeoVersionUnit.status == ItemStatus.ACTIVE)
                        .group_by(G2PGeoVersionUnit.version_no)
                    )
                ).all()
            )
            rows = (
                (await s.execute(select(G2PGeoVersion).order_by(G2PGeoVersion.version_no.desc())))
                .scalars()
                .all()
            )
            out = []
            for v in rows:
                info = await self._info(s, v, current, with_count=False)
                info.unit_count = counts.get(v.version_no, 0)
                out.append(info)
            return out

    async def get_geo_levels(self, sel) -> Tuple[GeoVersionInfo, List[GeoLevel]]:
        async with get_async_session_maker()() as s:
            v, current = await self.resolve_version(s, sel)
            levels = await self._levels(s, v.version_no)
            ordered = self._ordered_levels(levels)
            return await self._info(s, v, current), [_level(lv) for lv in ordered]

    @staticmethod
    def _ordered_levels(levels: Dict[str, G2PGeoVersionLevel]) -> List[G2PGeoVersionLevel]:
        out, frontier = [], [
            lv for lv in levels.values() if not lv.parent_level_id or lv.parent_level_id not in levels
        ]
        seen = set()
        while frontier:
            frontier.sort(key=lambda x: x.level_id)
            nxt = []
            for lv in frontier:
                if lv.level_id in seen:
                    continue
                seen.add(lv.level_id)
                out.append(lv)
                nxt.extend(c for c in levels.values() if c.parent_level_id == lv.level_id)
            frontier = nxt
        out.extend(lv for lv in levels.values() if lv.level_id not in seen)
        return out

    async def get_geo_units(
        self,
        sel,
        *,
        level: Optional[str] = None,
        parent_unit_id: Optional[str] = None,
        include_retired: bool = False,
        search: Optional[str] = None,
        page_size: int = 1000,
        page_number: int = 1,
        data_policies: Optional[List[dict]] = None,
    ) -> Tuple[GeoVersionInfo, List[GeoUnit], int]:
        async with get_async_session_maker()() as s:
            v, current = await self.resolve_version(s, sel)
            U = G2PGeoVersionUnit
            conds = [U.version_no == v.version_no]
            level_row = None
            if level:
                level_row = self._find_level(await self._levels(s, v.version_no), level)
                conds.append(U.level_id == level_row.level_id)
            if parent_unit_id is not None:
                conds.append(
                    U.parent_unit_id == parent_unit_id if parent_unit_id else U.parent_unit_id.is_(None)
                )
            if not include_retired:
                conds.append(U.status == ItemStatus.ACTIVE)
            if search:
                like = f"%{search}%"
                conds.append(or_(U.unit_id.ilike(like), U.name.ilike(like)))
            if data_policies:
                expression = DataPolicyHelper.resolve_geo_policy(data_policies)
                if expression:
                    cond = GeoLevelValueRepository(
                        name_column=U.name, level_id_column=U.level_id
                    ).build_policy_condition(
                        expression, level_context=level_row.level_mnemonic if level_row else None
                    )
                    if cond is not None:
                        conds.append(cond)
            total = (await s.execute(select(func.count()).select_from(U).where(*conds))).scalar_one()
            rows = (
                (
                    await s.execute(
                        select(U)
                        .where(*conds)
                        .order_by(U.level_id, U.unit_id)
                        .limit(page_size)
                        .offset(max(0, page_number - 1) * page_size)
                    )
                )
                .scalars()
                .all()
            )
            return await self._info(s, v, current, with_count=False), [_unit(r) for r in rows], total

    async def get_geo_unit(self, unit_id: str, sel) -> Tuple[GeoVersionInfo, GeoUnit, List[GeoUnit]]:
        async with get_async_session_maker()() as s:
            v, current = await self.resolve_version(s, sel)
            row = await s.get(G2PGeoVersionUnit, (v.version_no, unit_id))
            if not row:
                raise CatalogueError("G2P-CAT-404", f"unit {unit_id} not in geography version {v.version_no}")
            ancestors, cur, seen = [], row.parent_unit_id, set()
            while cur and cur not in seen:
                seen.add(cur)
                p = await s.get(G2PGeoVersionUnit, (v.version_no, cur))
                if not p:
                    break
                ancestors.append(_unit(p))
                cur = p.parent_unit_id
            return await self._info(s, v, current, with_count=False), _unit(row), ancestors

    async def get_geo_changes(
        self, from_version: Optional[int], to_version, unit_id: Optional[str], include_draft: bool
    ) -> List[GeoChange]:
        async with get_async_session_maker()() as s:
            to_v, _ = await self.resolve_version(s, VersionSelector(version=to_version))
            lo = from_version or 0
            versions = select(G2PGeoVersion.version_no).where(
                G2PGeoVersion.version_no > lo,
                G2PGeoVersion.version_no <= to_v.version_no,
                G2PGeoVersion.status == VersionStatus.PUBLISHED,
            )
            conds = [G2PGeoChange.version_no.in_(versions)]
            if to_v.status != VersionStatus.PUBLISHED:
                conds = [or_(conds[0], G2PGeoChange.version_no == to_v.version_no)]
            if include_draft:
                draft = await self._open_version(s)
                if draft:
                    conds = [or_(conds[0], G2PGeoChange.version_no == draft.version_no)]
            stmt = select(G2PGeoChange).where(*conds)
            if unit_id:
                stmt = stmt.where(
                    or_(G2PGeoChange.from_units.any(unit_id), G2PGeoChange.to_units.any(unit_id))
                )
            rows = (
                (await s.execute(stmt.order_by(G2PGeoChange.version_no, G2PGeoChange.change_id)))
                .scalars()
                .all()
            )
            return [_change(c) for c in rows]

    async def get_geo_crosswalk(self, unit_id: str, from_version: int, to_version) -> Dict[str, Any]:
        async with get_async_session_maker()() as s:
            to_v, _ = await self.resolve_version(s, VersionSelector(version=to_version))
            from_v = await s.get(G2PGeoVersion, from_version)
            if not from_v:
                raise CatalogueError("G2P-CAT-404", f"geography version {from_version} not found")
            if not await s.get(G2PGeoVersionUnit, (from_version, unit_id)):
                raise CatalogueError("G2P-CAT-404", f"unit {unit_id} not in geography version {from_version}")
            f, t = from_version, to_v.version_no
            path: List[CrosswalkStep] = []
            unmapped: List[str] = []
            current = {unit_id}
            if f == t:
                direction = "none"
            else:
                direction = "forward" if f < t else "backward"
                lo, hi = (f, t) if f < t else (t, f)
                versions = (
                    (
                        await s.execute(
                            select(G2PGeoVersion.version_no)
                            .where(
                                G2PGeoVersion.version_no > lo,
                                G2PGeoVersion.version_no <= hi,
                                or_(
                                    G2PGeoVersion.status == VersionStatus.PUBLISHED,
                                    G2PGeoVersion.version_no == t,
                                ),
                            )
                            .order_by(G2PGeoVersion.version_no)
                        )
                    )
                    .scalars()
                    .all()
                )
                if direction == "backward":
                    versions = list(reversed(versions))
                for vno in versions:
                    events = (
                        (
                            await s.execute(
                                select(G2PGeoChange)
                                .where(G2PGeoChange.version_no == vno)
                                .order_by(G2PGeoChange.change_id)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    nxt: set = set()
                    for u in sorted(current):
                        if direction == "forward":
                            touching = [e for e in events if u in (e.from_units or [])]
                            terminal = [e for e in touching if e.change_type in _TERMINAL]
                            for e in touching:
                                path.append(self._step(e))
                            if terminal:
                                for e in terminal:
                                    if e.to_units:
                                        nxt.update(e.to_units)
                                    else:
                                        unmapped.append(u)
                            else:
                                nxt.add(u)
                        else:
                            touching = [e for e in events if u in (e.to_units or [])]
                            origin = [
                                e for e in touching if e.change_type in (_TERMINAL | {GeoChangeType.CREATE})
                            ]
                            for e in touching:
                                path.append(self._step(e))
                            if origin:
                                for e in origin:
                                    if e.from_units:
                                        nxt.update(e.from_units)
                                    else:
                                        unmapped.append(u)
                            else:
                                nxt.add(u)
                    current = nxt
            units = []
            for u in sorted(current):
                row = await s.get(G2PGeoVersionUnit, (t, u))
                if row:
                    units.append(_unit(row))
                else:
                    unmapped.append(u)
            unique_path = list({(p.version_no, p.change_id): p for p in path}.values())
            return {
                "unit_id": unit_id,
                "from_version": f,
                "to_version": t,
                "direction": direction,
                "unchanged": [x.unit_id for x in units] == [unit_id] and not unique_path,
                "units": units,
                "unmapped": sorted(set(unmapped)),
                "path": unique_path,
            }

    @staticmethod
    def _step(e: G2PGeoChange) -> CrosswalkStep:
        return CrosswalkStep(
            version_no=e.version_no,
            change_id=e.change_id,
            change_type=e.change_type,
            from_units=list(e.from_units or []),
            to_units=list(e.to_units or []),
        )

    async def get_geo_boundary(self, sel, level: str) -> Dict[str, Any]:
        async with get_async_session_maker()() as s:
            v, _ = await self.resolve_version(s, sel)
            lv = self._find_level(await self._levels(s, v.version_no), level)
            key = (v.boundary_objects or {}).get(lv.level_mnemonic)
        store = BoundaryStore.get_component()
        return {
            "version_no": v.version_no,
            "level": lv.level_mnemonic,
            "object_key": key,
            "url": store.public_url(key),
            "presigned_url": await store.presigned_url(key) if key else None,
        }

    async def read_boundary(self, sel, level: str) -> bytes:
        info = await self.get_geo_boundary(sel, level)
        if not info["object_key"]:
            raise CatalogueError(
                "G2P-CAT-404", f"no boundary for level {level} in version {info['version_no']}"
            )
        store = BoundaryStore.get_component()
        if not store.enabled():
            raise CatalogueError("G2P-CAT-409", "the boundary store is not configured")
        return await store.get(info["object_key"])

    # ------------------------------------------------------------------
    # Drafts
    # ------------------------------------------------------------------

    async def _create_draft(
        self,
        uow: CatalogueUnitOfWork,
        *,
        base_version: Optional[int] = None,
        copy_from_version: Optional[int] = None,
        change_note: Optional[str] = None,
        effective_from: Optional[datetime] = None,
        owner_org: Optional[str] = None,
    ) -> G2PGeoVersion:
        s = uow.session
        # Serialise draft creation.
        await s.execute(text("SELECT pg_advisory_xact_lock(hashtext('g2p_geo_draft'))"))
        if await self._open_version(s):
            raise CatalogueError("G2P-CAT-409", "geography already has an open draft")
        max_published = await self._max_published_no(s)
        base_no = base_version if base_version is not None else max_published
        if base_no is not None:
            base = await s.get(G2PGeoVersion, base_no)
            if not base or base.status != VersionStatus.PUBLISHED:
                raise CatalogueError(
                    "G2P-CAT-400", f"base version {base_no} is not a published geography version"
                )
            if base_no != max_published:
                raise CatalogueError(
                    "G2P-CAT-400", f"a draft must start from the highest published version ({max_published})"
                )
        else:
            base = None
        source_no = copy_from_version if copy_from_version is not None else base_no
        source = await s.get(G2PGeoVersion, source_no) if source_no is not None else None
        if source_no is not None and not source:
            raise CatalogueError("G2P-CAT-404", f"geography version {source_no} not found")
        # Never reused, even after a discard (serialised by the advisory lock above).
        next_no = (await s.execute(text("SELECT g2p_catalogue_next_geo_version()"))).scalar_one()
        now = utcnow()
        src = source or base
        draft = G2PGeoVersion(
            version_no=next_no,
            status=VersionStatus.DRAFT,
            base_version_no=base_no,
            country=(src.country if src else None) or (_config.catalogue_country or None),
            owner_org=owner_org
            or (src.owner_org if src else None)
            or (_config.catalogue_default_owner_org or None),
            change_note=change_note,
            effective_from=as_aware(effective_from),
            boundary_objects=dict(src.boundary_objects or {}) if src else {},
            boundary_checksums=dict(src.boundary_checksums or {}) if src else {},
            created_by=uow.actor.id,
            created_by_name=uow.actor.display_name,
            created_at=now,
            updated_by=uow.actor.id,
            updated_by_name=uow.actor.display_name,
            updated_at=now,
        )
        s.add(draft)
        await s.flush()
        if source is not None:
            L, U = G2PGeoVersionLevel, G2PGeoVersionUnit
            await s.execute(
                insert(L).from_select(
                    [
                        "version_no",
                        "level_id",
                        "level_mnemonic",
                        "parent_level_id",
                        "display",
                        "display_i18n",
                    ],
                    select(
                        literal(next_no),
                        L.level_id,
                        L.level_mnemonic,
                        L.parent_level_id,
                        L.display,
                        L.display_i18n,
                    ).where(L.version_no == source.version_no),
                )
            )
            await s.execute(
                insert(U).from_select(
                    [
                        "version_no",
                        "unit_id",
                        "level_id",
                        "name",
                        "name_i18n",
                        "parent_unit_id",
                        "status",
                        "valid_from",
                        "valid_to",
                    ],
                    select(
                        literal(next_no),
                        U.unit_id,
                        U.level_id,
                        U.name,
                        U.name_i18n,
                        U.parent_unit_id,
                        U.status,
                        U.valid_from,
                        U.valid_to,
                    ).where(U.version_no == source.version_no),
                )
            )
        await uow.log(
            "geo.draft.created",
            "geo",
            GEO_SUBJECT,
            next_no,
            {"base_version_no": base_no, "copied_from": source_no},
        )
        return draft

    async def _ensure_draft(self, uow: CatalogueUnitOfWork) -> G2PGeoVersion:
        draft = await self._open_version(uow.session, lock=True)
        if draft is None:
            return await self._create_draft(uow)
        if draft.status != VersionStatus.DRAFT:
            raise CatalogueError(
                "G2P-CAT-409",
                f"geography version {draft.version_no} is {draft.status}; it can no longer be edited",
            )
        return draft

    async def _require_draft(self, s) -> G2PGeoVersion:
        draft = await self._open_version(s, lock=True)
        if draft is None:
            raise CatalogueError("G2P-CAT-404", "geography has no open draft")
        return draft

    @staticmethod
    def _touch(draft, actor: Actor) -> None:
        draft.updated_by = actor.id
        draft.updated_by_name = actor.display_name
        draft.updated_at = utcnow()

    async def _check_effective_from(self, s, effective_from: Optional[datetime]) -> None:
        if effective_from is None:
            return
        last = (
            await s.execute(
                select(G2PGeoVersion.effective_from)
                .where(G2PGeoVersion.status == VersionStatus.PUBLISHED)
                .order_by(G2PGeoVersion.version_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last is not None and as_aware(effective_from) < as_aware(last):
            raise CatalogueError(
                "G2P-CAT-400",
                f"effective_from {effective_from} is earlier than the latest published version's ({last})",
            )

    async def create_geo_draft(self, payload, actor: Actor) -> GeoVersionInfo:
        async with CatalogueUnitOfWork(actor) as uow:
            await self._check_effective_from(uow.session, payload.effective_from)
            draft = await self._create_draft(
                uow,
                base_version=payload.base_version,
                copy_from_version=payload.copy_from_version,
                change_note=payload.change_note,
                effective_from=payload.effective_from,
                owner_org=payload.owner_org,
            )
            info = await self._info(uow.session, draft, await self.current_no(uow.session))
            await uow.commit()
            return info

    async def update_geo_draft(self, payload, actor: Actor) -> GeoVersionInfo:
        async with CatalogueUnitOfWork(actor) as uow:
            draft = await self._require_draft(uow.session)
            if draft.status != VersionStatus.DRAFT:
                raise CatalogueError("G2P-CAT-409", f"geography version {draft.version_no} is {draft.status}")
            fields = payload.model_fields_set
            if "change_note" in fields:
                draft.change_note = payload.change_note
            if "effective_from" in fields:
                await self._check_effective_from(uow.session, payload.effective_from)
                draft.effective_from = as_aware(payload.effective_from)
            if "owner_org" in fields:
                draft.owner_org = payload.owner_org
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.updated", "geo", GEO_SUBJECT, draft.version_no, {"fields": sorted(fields)}
            )
            info = await self._info(uow.session, draft, await self.current_no(uow.session))
            await uow.commit()
            return info

    # ------------------------------------------------------------------
    # Settings (visibility, licence)
    # ------------------------------------------------------------------

    async def get_geo_settings(self) -> GeoSettings:
        async with get_async_session_maker()() as s:
            return await read_geo_settings(s)

    async def update_geo_settings(self, payload, actor: Actor) -> GeoSettings:
        fields = payload.model_fields_set & set(GEO_SETTING_KEYS)
        if not fields:
            raise CatalogueError("G2P-CAT-400", "at least one field must be provided to update")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            changed: Dict[str, Any] = {}
            for field in sorted(fields):
                value = getattr(payload, field)
                if field == "visibility":
                    if value is None:
                        continue
                    value = "public" if value == "public" else "private"
                else:
                    value = (value or "").strip() or None
                key = GEO_SETTING_KEYS[field]
                row = await s.get(G2PCatalogueState, key, with_for_update=True)
                if row is None:
                    s.add(G2PCatalogueState(key=key, text_value=value))
                else:
                    row.text_value = value
                    row.updated_at = utcnow()
                changed[field] = value
            await s.flush()
            if changed:
                await uow.log("geo.settings.updated", "geo", GEO_SUBJECT, None, changed)
            result = await read_geo_settings(s)
            await uow.commit()
            return result

    async def upsert_draft_levels(self, levels, actor: Actor) -> Tuple[GeoVersionInfo, List[GeoLevel]]:
        if not levels:
            raise CatalogueError("G2P-CAT-400", "levels is empty")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            existing = await self._levels(s, draft.version_no)
            out = []
            for item in levels:
                lid = (item.level_id or "").strip()
                mnemonic = (item.level_mnemonic or "").strip()
                if not lid or not mnemonic:
                    raise CatalogueError("G2P-CAT-400", "level_id and level_mnemonic are required")
                row = existing.get(lid)
                if row is None:
                    row = G2PGeoVersionLevel(
                        version_no=draft.version_no, level_id=lid, level_mnemonic=mnemonic
                    )
                    s.add(row)
                    existing[lid] = row
                row.level_mnemonic = mnemonic
                row.parent_level_id = (item.parent_level_id or "").strip() or None
                if "display" in item.model_fields_set:
                    row.display = item.display
                if "display_i18n" in item.model_fields_set:
                    row.display_i18n = item.display_i18n
                out.append(row)
            self._validate_levels(existing)
            await s.flush()
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.levels_changed",
                "geo",
                GEO_SUBJECT,
                draft.version_no,
                {"levels": [r.level_id for r in out]},
            )
            info = await self._info(s, draft, await self.current_no(s))
            result = [_level(r) for r in out]
            await uow.commit()
            return info, result

    @staticmethod
    def _validate_levels(levels: Dict[str, G2PGeoVersionLevel]) -> None:
        seen_pairs = set()
        for lv in levels.values():
            if lv.parent_level_id and lv.parent_level_id not in levels:
                raise CatalogueError(
                    "G2P-CAT-400", f"level {lv.level_id}: parent level {lv.parent_level_id} not found"
                )
            if lv.parent_level_id == lv.level_id:
                raise CatalogueError("G2P-CAT-400", "a level cannot be its own parent")
            key = (lv.level_mnemonic, lv.parent_level_id)
            if key in seen_pairs:
                raise CatalogueError(
                    "G2P-CAT-409", f"level_mnemonic already exists with this parent: {lv.level_mnemonic}"
                )
            seen_pairs.add(key)
        for lv in levels.values():
            cur, seen = lv.level_id, set()
            while cur:
                if cur in seen:
                    raise CatalogueError("G2P-CAT-400", f"level {lv.level_id}: parent chain has a cycle")
                seen.add(cur)
                cur = levels[cur].parent_level_id if cur in levels else None

    async def upsert_draft_units(self, units, actor: Actor) -> Tuple[GeoVersionInfo, List[GeoUnit]]:
        if not units:
            raise CatalogueError("G2P-CAT-400", "units is empty")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            out = await self._upsert_units(s, draft, units)
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.units_changed",
                "geo",
                GEO_SUBJECT,
                draft.version_no,
                {"units": [u.unit_id for u in out][:200], "count": len(out)},
            )
            info = await self._info(s, draft, await self.current_no(s))
            result = [_unit(u) for u in out]
            await uow.commit()
            return info, result

    async def _upsert_units(self, s, draft, units) -> List[G2PGeoVersionUnit]:
        levels = await self._levels(s, draft.version_no)
        existing = await self._units(s, draft.version_no)
        out = []
        for item in units:
            uid = (item.unit_id or "").strip()
            name = (item.name or "").strip()
            if not uid or not name:
                raise CatalogueError("G2P-CAT-400", "unit_id and name are required")
            level = self._find_level(levels, item.level_id)
            row = existing.get(uid)
            if row is None:
                row = G2PGeoVersionUnit(
                    version_no=draft.version_no,
                    unit_id=uid,
                    level_id=level.level_id,
                    name=name,
                    status=ItemStatus.ACTIVE,
                )
                s.add(row)
                existing[uid] = row
            row.level_id = level.level_id
            row.name = name
            fs = item.model_fields_set
            if "name_i18n" in fs:
                row.name_i18n = item.name_i18n
            if "parent_unit_id" in fs:
                row.parent_unit_id = (item.parent_unit_id or "").strip() or None
            if item.status:
                row.status = item.status
            elif row.status == ItemStatus.RETIRED:
                row.status = ItemStatus.ACTIVE
            out.append(row)
        self._validate_units(levels, existing, only={r.unit_id for r in out})
        await s.flush()
        return out

    @staticmethod
    def _validate_units(levels, units: Dict[str, G2PGeoVersionUnit], only: Optional[set] = None) -> None:
        names = {}
        for u in units.values():
            if u.status != ItemStatus.ACTIVE:
                continue
            key = (u.level_id, u.parent_unit_id, u.name)
            if key in names and names[key] != u.unit_id:
                if only is None or u.unit_id in only or names[key] in only:
                    raise CatalogueError(
                        "G2P-CAT-409",
                        f"units {names[key]} and {u.unit_id} have the same name '{u.name}' under the same parent",
                    )
            names[key] = u.unit_id
        for u in units.values():
            if only is not None and u.unit_id not in only:
                continue
            if u.level_id not in levels:
                raise CatalogueError("G2P-CAT-400", f"unit {u.unit_id}: level {u.level_id} not found")
            if u.status != ItemStatus.ACTIVE:
                continue
            if u.parent_unit_id:
                if u.parent_unit_id == u.unit_id:
                    raise CatalogueError("G2P-CAT-400", "a unit cannot be its own parent")
                parent = units.get(u.parent_unit_id)
                if not parent or parent.status != ItemStatus.ACTIVE:
                    raise CatalogueError(
                        "G2P-CAT-400", f"unit {u.unit_id}: parent {u.parent_unit_id} is not an active unit"
                    )
                expected = levels[u.level_id].parent_level_id
                if expected and parent.level_id != expected:
                    raise CatalogueError(
                        "G2P-CAT-400",
                        f"unit {u.unit_id}: parent {parent.unit_id} is at level {parent.level_id}, "
                        f"expected {expected}",
                    )

    async def retire_draft_units(self, unit_ids: List[str], cascade: bool, actor: Actor):
        if not unit_ids:
            raise CatalogueError("G2P-CAT-400", "unit_ids is empty")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            retired, removed = await self._retire_units(s, draft, unit_ids, cascade)
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.units_retired",
                "geo",
                GEO_SUBJECT,
                draft.version_no,
                {"retired": retired[:200], "removed": removed[:200]},
            )
            info = await self._info(s, draft, await self.current_no(s))
            await uow.commit()
            return info, retired, removed

    async def _retire_units(self, s, draft, unit_ids, cascade) -> Tuple[List[str], List[str]]:
        units = await self._units(s, draft.version_no)
        base_ids = (
            set((await self._units(s, draft.base_version_no)).keys()) if draft.base_version_no else set()
        )
        targets = []
        for uid in unit_ids:
            if uid not in units:
                raise CatalogueError("G2P-CAT-404", f"unit {uid} not in the geography draft")
            targets.append(units[uid])
        frontier, seen = {t.unit_id for t in targets}, {t.unit_id for t in targets}
        while frontier:
            kids = [
                u
                for u in units.values()
                if u.parent_unit_id in frontier and u.status == ItemStatus.ACTIVE and u.unit_id not in seen
            ]
            if kids and not cascade:
                raise CatalogueError(
                    "G2P-CAT-409",
                    f"cannot retire {sorted(frontier)[:5]}: {len(kids)} active descendant unit(s); pass cascade=true",
                )
            targets.extend(kids)
            frontier = {k.unit_id for k in kids}
            seen |= frontier
        retired, removed = [], []
        for u in targets:
            if u.unit_id in base_ids:
                u.status = ItemStatus.RETIRED
                retired.append(u.unit_id)
            else:
                await s.delete(u)
                removed.append(u.unit_id)
        await s.flush()
        return retired, removed

    # ---- change events ---------------------------------------------------

    async def _validate_change(
        self,
        s,
        draft: G2PGeoVersion,
        change_type: str,
        from_units: List[str],
        to_units: List[str],
        *,
        exclude_change_id: Optional[int] = None,
    ) -> Tuple[List[str], List[str]]:
        """Check one event against the draft and its base (catalogue_geo_rules.py)."""
        D = await self._units(s, draft.version_no)
        B = await self._units(s, draft.base_version_no) if draft.base_version_no is not None else {}
        others = []
        if change_type in _TERMINAL:
            others = [
                (e.change_id, e.change_type, list(e.from_units or []))
                for e in (
                    await s.execute(
                        select(G2PGeoChange).where(
                            G2PGeoChange.version_no == draft.version_no,
                            G2PGeoChange.change_type.in_(list(_TERMINAL)),
                            G2PGeoChange.is_auto.is_(False),
                        )
                    )
                ).scalars()
                if exclude_change_id is None or e.change_id != exclude_change_id
            ]
        try:
            return check_geo_change(
                change_type,
                from_units,
                to_units,
                base_version_no=draft.base_version_no,
                base_units=B,
                draft_units=D,
                other_terminal_events=others,
            )
        except GeoChangeRuleError as exc:
            raise CatalogueError(exc.code, exc.message) from exc

    async def record_geo_change(self, payload, actor: Actor) -> Tuple[GeoVersionInfo, GeoChange]:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._require_draft(s)
            if draft.status != VersionStatus.DRAFT:
                raise CatalogueError("G2P-CAT-409", f"geography version {draft.version_no} is {draft.status}")
            frm, to = await self._validate_change(
                s, draft, payload.change_type, payload.from_units, payload.to_units
            )
            row = G2PGeoChange(
                version_no=draft.version_no,
                change_type=payload.change_type,
                from_units=frm,
                to_units=to,
                effective_date=payload.effective_date,
                note=payload.note,
                is_auto=False,
                created_by=actor.id,
                created_by_name=actor.display_name,
                created_at=utcnow(),
            )
            s.add(row)
            await s.flush()
            self._touch(draft, actor)
            await uow.log(
                "geo.change.recorded",
                "geo",
                GEO_SUBJECT,
                draft.version_no,
                {"change_id": row.change_id, "change_type": row.change_type, "from": frm, "to": to},
            )
            info = await self._info(s, draft, await self.current_no(s))
            change = _change(row)
            await uow.commit()
            return info, change

    async def delete_geo_change(self, change_id: int, actor: Actor) -> int:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._require_draft(s)
            row = await s.get(G2PGeoChange, change_id)
            if not row or row.version_no != draft.version_no:
                raise CatalogueError("G2P-CAT-404", f"change {change_id} is not in the open geography draft")
            if draft.status != VersionStatus.DRAFT:
                raise CatalogueError("G2P-CAT-409", f"geography version {draft.version_no} is {draft.status}")
            await s.delete(row)
            await uow.log(
                "geo.change.deleted", "geo", GEO_SUBJECT, draft.version_no, {"change_id": change_id}
            )
            await uow.commit()
            return change_id

    # ---- boundaries ------------------------------------------------------

    async def upload_draft_boundary(
        self, level: str, geojson: Dict[str, Any], actor: Actor
    ) -> Dict[str, Any]:
        if not isinstance(geojson, dict) or geojson.get("type") != "FeatureCollection":
            raise CatalogueError("G2P-CAT-400", "geojson must be a GeoJSON FeatureCollection")
        features = geojson.get("features") or []
        store = BoundaryStore.get_component()
        if not store.enabled():
            raise CatalogueError("G2P-CAT-409", "the boundary store (S3/MinIO) is not configured")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            lv = self._find_level(await self._levels(s, draft.version_no), level)
            country = draft.country or (_config.catalogue_country or "").strip()
            if not country:
                raise CatalogueError(
                    "G2P-CAT-400", "no country is recorded for geography; set catalogue_country"
                )
            # The key carries this draft's version number, which is never reused,
            # so it cannot be another version's object. Belt and braces (data
            # written before numbers were protected): refuse a key that any OTHER
            # version — published, rejected or discarded — records.
            key = boundary_object_key(country, draft.version_no, lv.level_mnemonic)
            used = (
                await s.execute(
                    select(func.count())
                    .select_from(G2PGeoVersion)
                    .where(
                        G2PGeoVersion.version_no != draft.version_no,
                        G2PGeoVersion.boundary_objects[lv.level_mnemonic].astext == key,
                    )
                )
            ).scalar_one()
            if used:
                raise CatalogueError(
                    "G2P-CAT-409", f"object {key} belongs to another geography version and is immutable"
                )
            body = json.dumps(geojson, separators=(",", ":")).encode()
            unit_hashes = {}
            for f in features:
                uid = feature_unit_id(f)
                if uid:
                    unit_hashes[str(uid)] = geometry_hash(f.get("geometry"))
            await store.put(key, body)
            objects = dict(draft.boundary_objects or {})
            objects[lv.level_mnemonic] = key
            draft.boundary_objects = objects
            sums = dict(draft.boundary_checksums or {})
            sums[lv.level_mnemonic] = {
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "units": unit_hashes,
            }
            draft.boundary_checksums = sums
            draft.country = country
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.boundary_uploaded",
                "geo",
                GEO_SUBJECT,
                draft.version_no,
                {"level": lv.level_mnemonic, "object_key": key, "features": len(features)},
            )
            info = await self._info(s, draft, await self.current_no(s))
            await uow.commit()
            return {"draft": info, "level": lv.level_mnemonic, "object_key": key, "features": len(features)}

    # ---- submit / approve / reject / discard -----------------------------

    async def validate_version(self, s, draft: G2PGeoVersion) -> None:
        levels = await self._levels(s, draft.version_no)
        if not levels:
            raise CatalogueError("G2P-CAT-400", "the geography draft has no levels")
        self._validate_levels(levels)
        units = await self._units(s, draft.version_no)
        self._validate_units(levels, units)
        explicit = (
            (
                await s.execute(
                    select(G2PGeoChange).where(
                        G2PGeoChange.version_no == draft.version_no, G2PGeoChange.is_auto.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
        for e in explicit:
            await self._validate_change(
                s,
                draft,
                e.change_type,
                list(e.from_units or []),
                list(e.to_units or []),
                exclude_change_id=e.change_id,
            )

    async def _auto_boundary_changes(self, uow, draft: G2PGeoVersion) -> int:
        """BOUNDARY_CHANGE events for units whose geometry changed and that no event covers."""
        if draft.base_version_no is None:
            return 0
        s = uow.session
        base = await s.get(G2PGeoVersion, draft.base_version_no)
        before = (base.boundary_checksums or {}) if base else {}
        after = draft.boundary_checksums or {}
        units = await self._units(s, draft.version_no)
        covered = set()
        # A rename or a move says nothing about geometry; every other event already covers it.
        for e in (
            await s.execute(
                select(G2PGeoChange).where(
                    G2PGeoChange.version_no == draft.version_no,
                    G2PGeoChange.change_type.not_in([GeoChangeType.RENAME, GeoChangeType.REPARENT]),
                )
            )
        ).scalars():
            covered.update(e.from_units or [])
            covered.update(e.to_units or [])
        n = 0
        for level, meta in after.items():
            old = (before.get(level) or {}).get("units") or {}
            new = (meta or {}).get("units") or {}
            if (before.get(level) or {}).get("sha256") == (meta or {}).get("sha256"):
                continue
            changed = sorted(
                u
                for u, h in new.items()
                if u in old
                and old[u] != h
                and u not in covered
                and u in units
                and units[u].status == ItemStatus.ACTIVE
            )
            if changed:
                s.add(
                    G2PGeoChange(
                        version_no=draft.version_no,
                        change_type=GeoChangeType.BOUNDARY_CHANGE,
                        from_units=changed,
                        to_units=changed,
                        note=f"auto: {level} boundary changed",
                        is_auto=True,
                        created_by=uow.actor.id,
                        created_by_name=uow.actor.display_name,
                        created_at=utcnow(),
                    )
                )
                n += 1
        await s.flush()
        return n

    async def submit_geo_draft(self, payload, actor: Actor) -> GeoVersionInfo:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._require_draft(s)
            if draft.status != VersionStatus.DRAFT:
                raise CatalogueError(
                    "G2P-CAT-409", f"geography version {draft.version_no} is already {draft.status}"
                )
            fields = payload.model_fields_set
            if "change_note" in fields and payload.change_note is not None:
                draft.change_note = payload.change_note
            if "effective_from" in fields:
                await self._check_effective_from(s, payload.effective_from)
                draft.effective_from = as_aware(payload.effective_from)
            await self.validate_version(s, draft)
            await self._complete_lineage(uow, draft)
            if draft.base_version_no is not None and not await self._has_changes(s, draft):
                raise CatalogueError(
                    "G2P-CAT-400", "the geography draft has no changes from its base version"
                )
            draft.status = VersionStatus.SUBMITTED
            draft.submitted_by = actor.id
            draft.submitted_by_name = actor.display_name
            draft.submitted_at = utcnow()
            await s.flush()
            await uow.log(
                "geo.draft.submitted",
                "geo",
                GEO_SUBJECT,
                draft.version_no,
                {"approval_mode": approval_mode(), "owner_org": draft.owner_org},
            )
            if approval_mode() == "awe":
                await self._start_awe(uow, draft)
            info = await self._info(s, draft, await self.current_no(s))
            await uow.commit()
            return info

    async def _complete_lineage(self, uow, draft) -> None:
        s = uow.session
        await s.flush()
        await s.execute(
            text("SELECT g2p_catalogue_geo_autolineage(:v, :a)"), {"v": draft.version_no, "a": uow.actor.id}
        )
        # The database function knows only the id; name the events it just added.
        await s.execute(
            update(G2PGeoChange)
            .where(
                G2PGeoChange.version_no == draft.version_no,
                G2PGeoChange.created_by == uow.actor.id,
                G2PGeoChange.created_by_name.is_(None),
            )
            .values(created_by_name=uow.actor.display_name)
        )
        await self._auto_boundary_changes(uow, draft)

    async def _has_changes(self, s, draft) -> bool:
        n_events = (
            await s.execute(
                select(func.count())
                .select_from(G2PGeoChange)
                .where(G2PGeoChange.version_no == draft.version_no)
            )
        ).scalar_one()
        if n_events:
            return True
        base = await s.get(G2PGeoVersion, draft.base_version_no)
        if (base.boundary_objects or {}) != (draft.boundary_objects or {}):
            return True
        bl = {
            k: (v.level_mnemonic, v.parent_level_id, v.display, v.display_i18n)
            for k, v in (await self._levels(s, base.version_no)).items()
        }
        dl = {
            k: (v.level_mnemonic, v.parent_level_id, v.display, v.display_i18n)
            for k, v in (await self._levels(s, draft.version_no)).items()
        }
        if bl != dl:
            return True
        bu = {
            k: (v.level_id, v.name_i18n or None, v.status)
            for k, v in (await self._units(s, base.version_no)).items()
        }
        du = {
            k: (v.level_id, v.name_i18n or None, v.status)
            for k, v in (await self._units(s, draft.version_no)).items()
        }
        return bu != du

    async def _start_awe(self, uow, draft) -> None:
        if not uow.actor.token:
            raise CatalogueError("G2P-CAT-403", "a bearer token is required to open an AWE approval request")
        artifact_id = f"{GEO_SUBJECT}:{draft.version_no}"
        try:
            result = await CatalogueAweHelper.get_component().create_request(
                uow.actor.token,
                policy_key=_config.awe_policy_key_geo,
                artifact_type=GEO_ARTIFACT,
                artifact_id=artifact_id,
                context={
                    "version_no": draft.version_no,
                    "owner_org": draft.owner_org,
                    "country": draft.country,
                    "change_note": draft.change_note,
                },
                requester=uow.actor.id,
                idempotency_key=f"mds-geo-{draft.version_no}",
            )
        except AweClientError as exc:
            raise CatalogueError("G2P-CAT-502", f"AWE request failed: {exc.message}") from exc
        draft.approval_ref = result.get("request_id")
        await uow.log(
            "geo.approval.requested",
            "geo",
            GEO_SUBJECT,
            draft.version_no,
            {"awe_request_id": draft.approval_ref, "status": result.get("status")},
        )

    async def _submitted(self, s, version_no: Optional[int]) -> G2PGeoVersion:
        draft = await self._require_draft(s)
        if draft.status != VersionStatus.SUBMITTED:
            raise CatalogueError(
                "G2P-CAT-409", f"geography version {draft.version_no} is {draft.status}, not SUBMITTED"
            )
        if version_no is not None and version_no != draft.version_no:
            raise CatalogueError(
                "G2P-CAT-409", f"version {version_no} is not the submitted version ({draft.version_no})"
            )
        return draft

    async def approve_geo_draft(self, payload, actor: Actor) -> GeoVersionInfo:
        if approval_mode() == "awe":
            raise CatalogueError("G2P-CAT-409", "approval runs through AWE in this deployment")
        from .g2p_catalogue_list_service import G2PCatalogueListService

        async with CatalogueUnitOfWork(actor) as uow:
            draft = await self._submitted(uow.session, payload.version_no)
            G2PCatalogueListService._check_maker_checker(draft, actor)
            info = await self.publish(uow, draft, payload.effective_from, payload.decision_note)
            await uow.commit()
            return info

    async def publish(
        self, uow, draft: G2PGeoVersion, effective_from, note, *, allow_draft: bool = False
    ) -> GeoVersionInfo:
        s = uow.session
        if effective_from is not None:
            await self._check_effective_from(s, effective_from)
        # g2p_catalogue_publish_geo stamps decided_by with the same id.
        draft.decided_by = uow.actor.id
        draft.decided_by_name = uow.actor.display_name
        await s.flush()
        eff = (
            await s.execute(
                text("SELECT g2p_catalogue_publish_geo(:v, :a, :eff, :note, :allow)"),
                {
                    "v": draft.version_no,
                    "a": uow.actor.id,
                    "eff": as_aware(effective_from),
                    "note": note,
                    "allow": allow_draft,
                },
            )
        ).scalar_one()
        await s.refresh(draft)
        await uow.log("geo.draft.approved", "geo", GEO_SUBJECT, draft.version_no, {"decision_note": note})
        current = await self.current_no(s)
        details = {
            "effective_from": eff.isoformat() if eff else None,
            "base_version_no": draft.base_version_no,
            "current_version_no": current,
            "boundary_objects": draft.boundary_objects or {},
        }
        await uow.log("geo.version.published", "geo", GEO_SUBJECT, draft.version_no, details)
        return await self._info(s, draft, current)

    async def reject_geo_draft(self, payload, actor: Actor) -> GeoVersionInfo:
        if approval_mode() == "awe":
            raise CatalogueError("G2P-CAT-409", "approval runs through AWE in this deployment")
        if not (payload.decision_note or "").strip():
            raise CatalogueError("G2P-CAT-400", "decision_note is required to reject")
        from .g2p_catalogue_list_service import G2PCatalogueListService

        async with CatalogueUnitOfWork(actor) as uow:
            draft = await self._submitted(uow.session, payload.version_no)
            G2PCatalogueListService._check_maker_checker(draft, actor)
            await self.reject(uow, draft, payload.decision_note)
            info = await self._info(uow.session, draft, await self.current_no(uow.session))
            await uow.commit()
            return info

    async def reject(self, uow, draft, note) -> None:
        draft.status = VersionStatus.REJECTED
        draft.decided_by = uow.actor.id
        draft.decided_by_name = uow.actor.display_name
        draft.decided_at = utcnow()
        draft.decision_note = note
        await uow.session.flush()
        await uow.log("geo.draft.rejected", "geo", GEO_SUBJECT, draft.version_no, {"decision_note": note})

    async def discard_geo_draft(self, actor: Actor) -> int:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._require_draft(s)
            if draft.status == VersionStatus.SUBMITTED and approval_mode() == "awe":
                raise CatalogueError("G2P-CAT-409", "the draft is awaiting approval in AWE")
            no = draft.version_no
            # Kept as a tombstone: the number (and its boundary keys) stay taken.
            draft.status = VersionStatus.DISCARDED
            draft.decided_by = actor.id
            draft.decided_by_name = actor.display_name
            draft.decided_at = utcnow()
            await s.flush()
            await uow.log("geo.draft.discarded", "geo", GEO_SUBJECT, no, {})
            await uow.commit()
            return no

    # ------------------------------------------------------------------
    # Legacy write endpoints (/geo/*) — they now edit the geography draft
    # ------------------------------------------------------------------

    @staticmethod
    def _legacy_level(lv: G2PGeoVersionLevel) -> GeoLevelData:
        return GeoLevelData(
            level_id=lv.level_id, level_mnemonic=lv.level_mnemonic, parent_level_id=lv.parent_level_id
        )

    @staticmethod
    def _legacy_unit(u: G2PGeoVersionUnit) -> GeoLevelValueData:
        return GeoLevelValueData(
            level_value_id=u.unit_id,
            level_id=u.level_id,
            level_value_mnemonic=u.name,
            parent_level_value_id=u.parent_unit_id,
        )

    async def legacy_add_level(
        self, level_mnemonic: str, parent_level_id: Optional[str], actor
    ) -> GeoLevelData:
        mnemonic = (level_mnemonic or "").strip()
        if not mnemonic:
            raise CatalogueError("G2P-GEO-400", "level_mnemonic is required")
        parent = (parent_level_id or "").strip() or None
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            levels = await self._levels(s, draft.version_no)
            if parent and parent not in levels:
                raise CatalogueError("G2P-GEO-404", f"parent_level_id not found: {parent}")
            row = G2PGeoVersionLevel(
                version_no=draft.version_no,
                level_id=str(uuid.uuid4()),
                level_mnemonic=mnemonic,
                parent_level_id=parent,
            )
            levels[row.level_id] = row
            self._validate_levels(levels)
            s.add(row)
            await s.flush()
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.levels_changed", "geo", GEO_SUBJECT, draft.version_no, {"levels": [row.level_id]}
            )
            out = self._legacy_level(row)
            await uow.commit()
            return out

    async def legacy_update_level(self, payload, actor) -> GeoLevelData:
        fields = payload.model_fields_set - {"level_id"}
        if not fields:
            raise CatalogueError("G2P-GEO-400", "At least one field must be provided to update")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            levels = await self._levels(s, draft.version_no)
            row = levels.get(payload.level_id)
            if not row:
                raise CatalogueError("G2P-GEO-404", f"level_id not found: {payload.level_id}")
            if "level_mnemonic" in fields:
                m = (payload.level_mnemonic or "").strip()
                if not m:
                    raise CatalogueError("G2P-GEO-400", "level_mnemonic cannot be empty")
                row.level_mnemonic = m
            if "parent_level_id" in fields:
                p = (payload.parent_level_id or "").strip() or None
                if p and p not in levels:
                    raise CatalogueError("G2P-GEO-404", f"parent_level_id not found: {p}")
                row.parent_level_id = p
            self._validate_levels(levels)
            await s.flush()
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.levels_changed", "geo", GEO_SUBJECT, draft.version_no, {"levels": [row.level_id]}
            )
            out = self._legacy_level(row)
            await uow.commit()
            return out

    async def legacy_delete_level(self, level_id: str, actor) -> str:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            levels = await self._levels(s, draft.version_no)
            row = levels.get(level_id)
            if not row:
                raise CatalogueError("G2P-GEO-404", f"level_id not found: {level_id}")
            kids = [lv for lv in levels.values() if lv.parent_level_id == level_id]
            if kids:
                raise CatalogueError("G2P-GEO-409", f"Cannot delete level with {len(kids)} child level(s)")
            n = (
                await s.execute(
                    select(func.count())
                    .select_from(G2PGeoVersionUnit)
                    .where(
                        G2PGeoVersionUnit.version_no == draft.version_no,
                        G2PGeoVersionUnit.level_id == level_id,
                    )
                )
            ).scalar_one()
            if n:
                raise CatalogueError("G2P-GEO-409", f"Cannot delete level with {n} level value(s)")
            await s.delete(row)
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.level_removed", "geo", GEO_SUBJECT, draft.version_no, {"level_id": level_id}
            )
            await uow.commit()
            return level_id

    async def legacy_add_unit(
        self, level_id, level_value_mnemonic, parent_level_value_id, actor
    ) -> GeoLevelValueData:
        from ..schemas.g2p_catalogue import DraftUnitInput

        name = (level_value_mnemonic or "").strip()
        if not (level_id or "").strip():
            raise CatalogueError("G2P-GEO-400", "level_id is required")
        if not name:
            raise CatalogueError("G2P-GEO-400", "level_value_mnemonic is required")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            if level_id not in await self._levels(s, draft.version_no):
                raise CatalogueError("G2P-GEO-404", f"level_id not found: {level_id}")
            parent = (parent_level_value_id or "").strip() or None
            if parent and not await s.get(G2PGeoVersionUnit, (draft.version_no, parent)):
                raise CatalogueError("G2P-GEO-404", f"parent_level_value_id not found: {parent}")
            item = DraftUnitInput(
                unit_id=str(uuid.uuid4()), level_id=level_id, name=name, parent_unit_id=parent
            )
            (row,) = await self._upsert_units(s, draft, [item])
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.units_changed", "geo", GEO_SUBJECT, draft.version_no, {"units": [row.unit_id]}
            )
            out = self._legacy_unit(row)
            await uow.commit()
            return out

    async def legacy_update_unit(self, payload, actor) -> GeoLevelValueData:
        from ..schemas.g2p_catalogue import DraftUnitInput

        fields = payload.model_fields_set - {"level_value_id"}
        if not fields:
            raise CatalogueError("G2P-GEO-400", "At least one field must be provided to update")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            row = await s.get(G2PGeoVersionUnit, (draft.version_no, payload.level_value_id))
            if not row:
                raise CatalogueError("G2P-GEO-404", f"level_value_id not found: {payload.level_value_id}")
            data = {"unit_id": row.unit_id, "level_id": row.level_id, "name": row.name}
            if "level_id" in fields:
                if not (payload.level_id or "").strip():
                    raise CatalogueError("G2P-GEO-400", "level_id cannot be empty")
                data["level_id"] = payload.level_id
            if "level_value_mnemonic" in fields:
                if not (payload.level_value_mnemonic or "").strip():
                    raise CatalogueError("G2P-GEO-400", "level_value_mnemonic cannot be empty")
                data["name"] = payload.level_value_mnemonic
            if "parent_level_value_id" in fields:
                p = (payload.parent_level_value_id or "").strip() or None
                if p == row.unit_id:
                    raise CatalogueError("G2P-GEO-400", "level value cannot be its own parent")
                data["parent_unit_id"] = p
            (row,) = await self._upsert_units(s, draft, [DraftUnitInput(**data)])
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.units_changed", "geo", GEO_SUBJECT, draft.version_no, {"units": [row.unit_id]}
            )
            out = self._legacy_unit(row)
            await uow.commit()
            return out

    async def legacy_delete_unit(self, level_value_id: str, cascade: bool, actor) -> str:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            draft = await self._ensure_draft(uow)
            if not await s.get(G2PGeoVersionUnit, (draft.version_no, level_value_id)):
                raise CatalogueError("G2P-GEO-404", f"level_value_id not found: {level_value_id}")
            try:
                retired, removed = await self._retire_units(s, draft, [level_value_id], cascade)
            except CatalogueError as exc:
                if exc.code == "G2P-CAT-409":
                    raise CatalogueError("G2P-GEO-409", exc.message) from exc
                raise
            self._touch(draft, actor)
            await uow.log(
                "geo.draft.units_retired",
                "geo",
                GEO_SUBJECT,
                draft.version_no,
                {"retired": retired[:200], "removed": removed[:200], "via": "delete_geo_level_value"},
            )
            await uow.commit()
            return level_value_id
