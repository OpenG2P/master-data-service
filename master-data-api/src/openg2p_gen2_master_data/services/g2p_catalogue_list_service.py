"""Versioned code lists: read any version, edit only a draft, publish on approval.

Lifecycle of a list version::

    DRAFT --submit--> SUBMITTED --approve--> PUBLISHED   (immutable, DB-enforced)
      |                    \\--reject---> REJECTED
      \\--discard--> DISCARDED  (kept, so its number is never reused)

Version numbers are allocated by g2p_catalogue_next_list_version and are never
reused (a discarded or rejected version keeps its number for good).

One open (DRAFT or SUBMITTED) version per list. A draft starts as a copy of the
highest published version (its base). Values are never deleted from anything
published: a value removed in a draft is RETIRED there (a value that was only
ever in the draft is simply removed). Publishing refreshes the legacy tables
(g2p_attributes / g2p_attribute_values) in the same transaction, through the
database function g2p_catalogue_publish_list.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import delete, func, insert, literal, or_, select, text, update

from ..config import Settings
from ..helpers.catalogue_integrations import (
    AweClientError,
    CatalogueAweHelper,
    approval_mode,
)
from ..helpers.data_policy_helper import DataPolicyHelper
from ..models import (
    G2PAttribute,
    G2PCatalogueReleaseMember,
    G2PListVersion,
    G2PListVersionValue,
    ItemStatus,
    VersionStatus,
)
from ..repositories import AttributeValueRepository
from ..schemas import AttributeData, AttributeValueData
from ..schemas.g2p_catalogue import (
    ListSummary,
    ListValue,
    ValueChange,
    VersionInfo,
    VersionSelector,
)
from .catalogue_common import (
    Actor,
    CatalogueError,
    CatalogueUnitOfWork,
    as_aware,
    check_attribute_schema,
    merge_refs,
    schema_summary,
    utcnow,
    validate_value_attributes,
)

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)

LIST_ARTIFACT = "master_data.list_version"
_VALUE_FIELDS = (
    "value_code",
    "display",
    "display_i18n",
    "parent_value_code",
    "sort_order",
    "attributes",
    "roles",
)
_LIST_META_FIELDS = ("list_code", "display", "display_i18n", "is_hierarchical", "attribute_schema")


# The country-pack loader's change note of a list's first version:
# "Initial load from country pack ETH (1.2)" for a core list, with " (agriculture)"
# appended for a domain list (docker/db-seed/load_geo_pack.py, load_list).
_PACK_NOTE = re.compile(r"^(?:Initial load|Update) from country pack \S+ \([^)]*\)(?: \(([^)]+)\))?$")


def normalise_domain(value: Optional[str]) -> Optional[str]:
    """A list's domain as stored: trimmed, lower-case; empty means none."""
    value = (value or "").strip().lower()
    return value or None


def visibility_of(value: Optional[str]) -> str:
    """Stored visibility as shown: only an explicit "public" is public."""
    return "public" if (value or "").strip().lower() == "public" else "private"


def blank_to_none(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def domain_from_note(note: Optional[str]) -> Optional[str]:
    """The domain a pack-loaded list was loaded under, from its first version's
    change note ("core" when the note has no domain suffix); None otherwise."""
    m = _PACK_NOTE.match((note or "").strip())
    if not m:
        return None
    return normalise_domain(m.group(1)) or "core"


async def _derived_domains(session, list_ids: List[str]) -> Dict[str, str]:
    """Fallback domain of lists whose ``domain`` column is empty (pack lists loaded
    before the column existed): read from each list's first version's change note.
    One query for all of them."""
    if not list_ids:
        return {}
    rows = (
        await session.execute(
            select(G2PListVersion.list_id, G2PListVersion.change_note)
            .where(G2PListVersion.list_id.in_(list_ids))
            .distinct(G2PListVersion.list_id)
            .order_by(G2PListVersion.list_id, G2PListVersion.version_no)
        )
    ).all()
    out = {}
    for list_id, note in rows:
        domain = domain_from_note(note)
        if domain:
            out[list_id] = domain
    return out


def _version_info(v: G2PListVersion, current_no: Optional[int]) -> VersionInfo:
    return VersionInfo(
        version_no=v.version_no,
        status=v.status,
        base_version_no=v.base_version_no,
        effective_from=v.effective_from,
        published_at=v.published_at,
        is_latest=current_no is not None and v.version_no == current_no,
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
    )


def _value(row: G2PListVersionValue) -> ListValue:
    return ListValue(
        value_id=row.value_id,
        value_code=row.value_code,
        display=row.display,
        display_i18n=row.display_i18n,
        parent_code=row.parent_value_code,
        sort_order=row.sort_order,
        attributes=row.attributes,
        roles=row.roles,
        status=row.status,
    )


def _same(a: Any, b: Any) -> bool:
    return (a if a not in ("", {}, []) else None) == (b if b not in ("", {}, []) else None)


class G2PCatalogueListService(BaseService):
    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_list(session, list_code: str, *, lock: bool = False) -> G2PAttribute:
        code = (list_code or "").strip()
        if not code:
            raise CatalogueError("G2P-CAT-400", "list_code is required")
        stmt = select(G2PAttribute).where(
            or_(G2PAttribute.attribute_code == code, G2PAttribute.attribute_id == code)
        )
        stmt = stmt.order_by((G2PAttribute.attribute_code == code).desc()).limit(1)
        if lock:
            stmt = stmt.with_for_update()
        row = (await session.execute(stmt)).scalars().first()
        if not row:
            raise CatalogueError("G2P-CAT-404", f"list not found: {code}")
        return row

    @staticmethod
    async def _current_no(session, list_id: str, at: Optional[datetime] = None) -> Optional[int]:
        stmt = select(func.max(G2PListVersion.version_no)).where(
            G2PListVersion.list_id == list_id,
            G2PListVersion.status == VersionStatus.PUBLISHED,
            G2PListVersion.effective_from <= (at if at is not None else func.now()),
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def _max_published_no(session, list_id: str) -> Optional[int]:
        stmt = select(func.max(G2PListVersion.version_no)).where(
            G2PListVersion.list_id == list_id, G2PListVersion.status == VersionStatus.PUBLISHED
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def _open_version(session, list_id: str, *, lock: bool = False) -> Optional[G2PListVersion]:
        stmt = select(G2PListVersion).where(
            G2PListVersion.list_id == list_id, G2PListVersion.status.in_(VersionStatus.OPEN)
        )
        if lock:
            stmt = stmt.with_for_update()
        return (await session.execute(stmt)).scalars().first()

    @staticmethod
    async def _get_version(session, list_id: str, version_no: int) -> Optional[G2PListVersion]:
        return await session.get(G2PListVersion, (list_id, version_no))

    async def resolve_version(
        self, session, attr: G2PAttribute, sel: Optional[VersionSelector]
    ) -> Tuple[G2PListVersion, Optional[int]]:
        """(version row, current version no) for a version selector."""
        sel = sel or VersionSelector()
        given = [x for x in (sel.version, sel.as_of, sel.release) if x is not None]
        if len(given) > 1:
            raise CatalogueError("G2P-CAT-400", "give at most one of version, as_of, release")
        current = await self._current_no(session, attr.attribute_id)
        if sel.release:
            member = await session.get(G2PCatalogueReleaseMember, (sel.release, attr.attribute_id))
            if not member:
                raise CatalogueError(
                    "G2P-CAT-404", f"release {sel.release} does not pin list {attr.attribute_code}"
                )
            version_no = member.version_no
        elif sel.as_of is not None:
            version_no = await self._current_no(session, attr.attribute_id, as_aware(sel.as_of))
            if version_no is None:
                raise CatalogueError(
                    "G2P-CAT-404",
                    f"list {attr.attribute_code} had no published version in effect at {sel.as_of}",
                )
        elif sel.version == "draft":
            draft = await self._open_version(session, attr.attribute_id)
            if not draft:
                raise CatalogueError("G2P-CAT-404", f"list {attr.attribute_code} has no open draft")
            return draft, current
        elif isinstance(sel.version, int):
            version_no = sel.version
        else:
            version_no = current
            if version_no is None:
                raise CatalogueError(
                    "G2P-CAT-404", f"list {attr.attribute_code} has no published version in effect"
                )
        version = await self._get_version(session, attr.attribute_id, version_no)
        if not version:
            raise CatalogueError(
                "G2P-CAT-404", f"version {version_no} of list {attr.attribute_code} not found"
            )
        return version, current

    async def _summary(self, session, attr: G2PAttribute) -> ListSummary:
        open_v = await self._open_version(session, attr.attribute_id)
        domain = normalise_domain(attr.domain)
        if domain is None:
            domain = (await _derived_domains(session, [attr.attribute_id])).get(attr.attribute_id)
        return ListSummary(
            list_id=attr.attribute_id,
            list_code=attr.attribute_code,
            display=attr.attribute_display,
            display_i18n=attr.display_i18n,
            description=attr.description,
            owner_org=attr.owner_org,
            domain=domain,
            visibility=visibility_of(attr.visibility),
            licence_uri=attr.licence_uri,
            licence_label=attr.licence_label,
            is_hierarchical=bool(attr.is_hierarchical),
            attribute_schema=attr.attribute_schema,
            attribute_schema_summary=schema_summary(attr.attribute_schema),
            current_version_no=attr.current_version_no,
            latest_published_version_no=await self._max_published_no(session, attr.attribute_id),
            open_draft_version_no=open_v.version_no if open_v else None,
            open_draft_status=open_v.status if open_v else None,
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_lists(self, include_unpublished: bool = True) -> List[ListSummary]:
        async with get_async_session_maker()() as session:
            published = (
                select(G2PListVersion.list_id, func.max(G2PListVersion.version_no).label("maxv"))
                .where(G2PListVersion.status == VersionStatus.PUBLISHED)
                .group_by(G2PListVersion.list_id)
                .subquery()
            )
            opened = (
                select(G2PListVersion.list_id, G2PListVersion.version_no, G2PListVersion.status)
                .where(G2PListVersion.status.in_(VersionStatus.OPEN))
                .subquery()
            )
            stmt = (
                select(G2PAttribute, published.c.maxv, opened.c.version_no, opened.c.status)
                .outerjoin(published, published.c.list_id == G2PAttribute.attribute_id)
                .outerjoin(opened, opened.c.list_id == G2PAttribute.attribute_id)
                .order_by(G2PAttribute.attribute_code, G2PAttribute.attribute_id)
            )
            if not include_unpublished:
                stmt = stmt.where(published.c.maxv.is_not(None))
            rows = (await session.execute(stmt)).all()
            derived = await _derived_domains(
                session, [attr.attribute_id for attr, *_ in rows if normalise_domain(attr.domain) is None]
            )
        out = []
        for attr, maxv, open_no, open_status in rows:
            out.append(
                ListSummary(
                    list_id=attr.attribute_id,
                    list_code=attr.attribute_code,
                    display=attr.attribute_display,
                    display_i18n=attr.display_i18n,
                    description=attr.description,
                    owner_org=attr.owner_org,
                    domain=normalise_domain(attr.domain) or derived.get(attr.attribute_id),
                    visibility=visibility_of(attr.visibility),
                    licence_uri=attr.licence_uri,
                    licence_label=attr.licence_label,
                    is_hierarchical=bool(attr.is_hierarchical),
                    attribute_schema=attr.attribute_schema,
                    attribute_schema_summary=schema_summary(attr.attribute_schema),
                    current_version_no=attr.current_version_no,
                    latest_published_version_no=maxv,
                    open_draft_version_no=open_no,
                    open_draft_status=open_status,
                )
            )
        return out

    async def get_list(
        self, list_code: str, sel: Optional[VersionSelector]
    ) -> Tuple[ListSummary, Optional[VersionInfo]]:
        async with get_async_session_maker()() as session:
            attr = await self._get_list(session, list_code)
            summary = await self._summary(session, attr)
            try:
                version, current = await self.resolve_version(session, attr, sel)
            except CatalogueError:
                if sel and (sel.version is not None or sel.as_of or sel.release):
                    raise
                return summary, None
            # The list as it is in that version.
            summary.list_code = version.list_code or summary.list_code
            summary.display = version.display
            summary.display_i18n = version.display_i18n
            summary.is_hierarchical = bool(version.is_hierarchical)
            summary.attribute_schema = version.attribute_schema
            summary.attribute_schema_summary = schema_summary(version.attribute_schema)
            return summary, _version_info(version, current)

    async def get_list_values(
        self,
        list_code: str,
        sel: Optional[VersionSelector],
        *,
        include_retired: bool = False,
        parent_code: Optional[str] = None,
        attribute_filters: Optional[Dict[str, Any]] = None,
        search: Optional[str] = None,
        page_size: int = 1000,
        page_number: int = 1,
        data_policies: Optional[List[dict]] = None,
    ) -> Tuple[str, VersionInfo, List[ListValue], int]:
        async with get_async_session_maker()() as session:
            attr = await self._get_list(session, list_code)
            version, current = await self.resolve_version(session, attr, sel)
            V = G2PListVersionValue
            conds = [V.list_id == attr.attribute_id, V.version_no == version.version_no]
            if not include_retired:
                conds.append(V.status == ItemStatus.ACTIVE)
            if parent_code is not None:
                # "" asks for the top level.
                conds.append(
                    V.parent_value_code == parent_code if parent_code else V.parent_value_code.is_(None)
                )
            if attribute_filters:
                conds.append(V.attributes.contains(attribute_filters))
            if search:
                like = f"%{search}%"
                conds.append(or_(V.value_code.ilike(like), V.display.ilike(like)))
            if data_policies:
                expression = DataPolicyHelper.resolve_attribute_policy(data_policies)
                if expression:
                    cond = AttributeValueRepository(
                        value_code_column=V.value_code, attribute_id_column=V.list_id
                    ).build_policy_condition(expression, attribute_context=attr.attribute_code)
                    if cond is not None:
                        conds.append(cond)
            total = (await session.execute(select(func.count()).select_from(V).where(*conds))).scalar_one()
            stmt = (
                select(V)
                .where(*conds)
                .order_by(V.sort_order.asc().nulls_last(), V.value_code)
                .limit(page_size)
                .offset(max(0, page_number - 1) * page_size)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return (
                version.list_code or attr.attribute_code,
                _version_info(version, current),
                [_value(r) for r in rows],
                total,
            )

    async def get_list_value(
        self, list_code: str, value_code: str, sel: Optional[VersionSelector]
    ) -> Tuple[str, VersionInfo, ListValue]:
        async with get_async_session_maker()() as session:
            attr = await self._get_list(session, list_code)
            version, current = await self.resolve_version(session, attr, sel)
            row = (
                (
                    await session.execute(
                        select(G2PListVersionValue).where(
                            G2PListVersionValue.list_id == attr.attribute_id,
                            G2PListVersionValue.version_no == version.version_no,
                            G2PListVersionValue.value_code == value_code,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not row:
                raise CatalogueError(
                    "G2P-CAT-404",
                    f"value {value_code} not in version {version.version_no} of list {attr.attribute_code}",
                )
            return version.list_code or attr.attribute_code, _version_info(version, current), _value(row)

    async def get_list_versions(self, list_code: str) -> Tuple[str, List[VersionInfo]]:
        async with get_async_session_maker()() as session:
            attr = await self._get_list(session, list_code)
            current = await self._current_no(session, attr.attribute_id)
            rows = (
                (
                    await session.execute(
                        select(G2PListVersion)
                        .where(G2PListVersion.list_id == attr.attribute_id)
                        .order_by(G2PListVersion.version_no.desc())
                    )
                )
                .scalars()
                .all()
            )
            return attr.attribute_code, [_version_info(v, current) for v in rows]

    async def _values_map(self, session, list_id: str, version_no: int) -> Dict[str, G2PListVersionValue]:
        rows = (
            (
                await session.execute(
                    select(G2PListVersionValue).where(
                        G2PListVersionValue.list_id == list_id, G2PListVersionValue.version_no == version_no
                    )
                )
            )
            .scalars()
            .all()
        )
        return {r.value_id: r for r in rows}

    async def get_list_diff(self, list_code: str, from_version: Optional[int], to_version) -> Dict[str, Any]:
        async with get_async_session_maker()() as session:
            attr = await self._get_list(session, list_code)
            to_v, _ = await self.resolve_version(session, attr, VersionSelector(version=to_version))
            from_no = from_version if from_version is not None else to_v.base_version_no
            from_v = (
                await self._get_version(session, attr.attribute_id, from_no) if from_no is not None else None
            )
            if from_no is not None and not from_v:
                raise CatalogueError(
                    "G2P-CAT-404", f"version {from_no} of list {attr.attribute_code} not found"
                )
            return await self._diff(session, attr, from_v, to_v)

    async def _diff(
        self, session, attr, from_v: Optional[G2PListVersion], to_v: G2PListVersion
    ) -> Dict[str, Any]:
        before = await self._values_map(session, attr.attribute_id, from_v.version_no) if from_v else {}
        after = await self._values_map(session, attr.attribute_id, to_v.version_no)
        meta = {}
        for f in _LIST_META_FIELDS:
            b = getattr(from_v, f, None) if from_v else None
            a = getattr(to_v, f, None)
            if not _same(b, a):
                meta[f] = {"before": b, "after": a}
        added, changed, retired, reactivated = [], [], [], []
        for vid, row in after.items():
            old = before.get(vid)
            if old is None:
                if row.status == ItemStatus.ACTIVE:
                    added.append(_value(row))
                continue
            if old.status == ItemStatus.ACTIVE and row.status == ItemStatus.RETIRED:
                retired.append(_value(row))
                continue
            if old.status == ItemStatus.RETIRED and row.status == ItemStatus.ACTIVE:
                reactivated.append(_value(row))
                continue
            changes = {
                f: {"before": getattr(old, f), "after": getattr(row, f)}
                for f in _VALUE_FIELDS
                if not _same(getattr(old, f), getattr(row, f))
            }
            if changes:
                changed.append(ValueChange(value_id=vid, value_code=row.value_code, changes=changes))
        for vid, old in before.items():
            if vid not in after and old.status == ItemStatus.ACTIVE:
                retired.append(_value(old))
        return {
            "list_code": to_v.list_code or attr.attribute_code,
            "from_version": from_v.version_no if from_v else None,
            "to_version": to_v.version_no,
            "metadata_changes": meta,
            "added": added,
            "changed": changed,
            "retired": retired,
            "reactivated": reactivated,
        }

    # ------------------------------------------------------------------
    # Drafts
    # ------------------------------------------------------------------

    async def _create_draft(
        self,
        uow: CatalogueUnitOfWork,
        attr: G2PAttribute,
        *,
        base_version: Optional[int] = None,
        copy_from_version: Optional[int] = None,
        change_note: Optional[str] = None,
        effective_from: Optional[datetime] = None,
    ) -> G2PListVersion:
        session = uow.session
        if await self._open_version(session, attr.attribute_id):
            raise CatalogueError("G2P-CAT-409", f"list {attr.attribute_code} already has an open draft")
        max_published = await self._max_published_no(session, attr.attribute_id)
        base_no = base_version if base_version is not None else max_published
        if base_no is not None:
            base = await self._get_version(session, attr.attribute_id, base_no)
            if not base or base.status != VersionStatus.PUBLISHED:
                raise CatalogueError("G2P-CAT-400", f"base version {base_no} is not a published version")
            if max_published is not None and base_no != max_published:
                raise CatalogueError(
                    "G2P-CAT-400",
                    f"a draft must start from the highest published version ({max_published}); "
                    "use copy_from_version to bring older content forward",
                )
        else:
            base = None
        source_no = copy_from_version if copy_from_version is not None else base_no
        source = (
            await self._get_version(session, attr.attribute_id, source_no) if source_no is not None else None
        )
        if source_no is not None and not source:
            raise CatalogueError(
                "G2P-CAT-404", f"version {source_no} of list {attr.attribute_code} not found"
            )
        # Never reused, even after a discard (the caller holds the list row lock).
        next_no = (
            await session.execute(
                text("SELECT g2p_catalogue_next_list_version(:list_id)"), {"list_id": attr.attribute_id}
            )
        ).scalar_one()
        now = utcnow()
        meta_src = source or base
        draft = G2PListVersion(
            list_id=attr.attribute_id,
            version_no=next_no,
            status=VersionStatus.DRAFT,
            base_version_no=base_no,
            list_code=meta_src.list_code if meta_src else attr.attribute_code,
            display=meta_src.display if meta_src else attr.attribute_display,
            display_i18n=meta_src.display_i18n if meta_src else attr.display_i18n,
            is_hierarchical=bool(meta_src.is_hierarchical) if meta_src else bool(attr.is_hierarchical),
            attribute_schema=meta_src.attribute_schema if meta_src else attr.attribute_schema,
            change_note=change_note,
            effective_from=as_aware(effective_from),
            created_by=uow.actor.id,
            created_by_name=uow.actor.display_name,
            created_at=now,
            updated_by=uow.actor.id,
            updated_by_name=uow.actor.display_name,
            updated_at=now,
        )
        session.add(draft)
        await session.flush()
        if source is not None:
            V = G2PListVersionValue
            await session.execute(
                insert(V).from_select(
                    [
                        "list_id",
                        "version_no",
                        "value_id",
                        "value_code",
                        "display",
                        "display_i18n",
                        "parent_value_code",
                        "sort_order",
                        "attributes",
                        "roles",
                        "status",
                    ],
                    select(
                        V.list_id,
                        literal(next_no),
                        V.value_id,
                        V.value_code,
                        V.display,
                        V.display_i18n,
                        V.parent_value_code,
                        V.sort_order,
                        V.attributes,
                        V.roles,
                        V.status,
                    ).where(V.list_id == attr.attribute_id, V.version_no == source.version_no),
                )
            )
        await uow.log(
            "list.draft.created",
            "list",
            attr.attribute_id,
            next_no,
            {"list_code": attr.attribute_code, "base_version_no": base_no, "copied_from": source_no},
        )
        return draft

    async def _ensure_draft(self, uow: CatalogueUnitOfWork, attr: G2PAttribute) -> G2PListVersion:
        """The open DRAFT, created from the latest published version if there is none."""
        draft = await self._open_version(uow.session, attr.attribute_id, lock=True)
        if draft is None:
            return await self._create_draft(uow, attr)
        if draft.status != VersionStatus.DRAFT:
            raise CatalogueError(
                "G2P-CAT-409",
                f"version {draft.version_no} of list {attr.attribute_code} is {draft.status}; "
                "it can no longer be edited (approve, reject or discard it first)",
            )
        return draft

    async def _require_draft(self, session, attr: G2PAttribute) -> G2PListVersion:
        draft = await self._open_version(session, attr.attribute_id, lock=True)
        if draft is None:
            raise CatalogueError("G2P-CAT-404", f"list {attr.attribute_code} has no open draft")
        return draft

    @staticmethod
    def _touch(draft: G2PListVersion, actor: Actor) -> None:
        draft.updated_by = actor.id
        draft.updated_by_name = actor.display_name
        draft.updated_at = utcnow()

    async def create_list(self, payload, actor: Actor) -> Tuple[ListSummary, VersionInfo]:
        code = (payload.list_code or "").strip()
        display = (payload.display or "").strip()
        if not code or not display:
            raise CatalogueError("G2P-CAT-400", "list_code and display are required")
        check_attribute_schema(payload.attribute_schema)
        list_id = (payload.list_id or code).strip()
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            exists = (
                await s.execute(
                    select(func.count())
                    .select_from(G2PAttribute)
                    .where(or_(G2PAttribute.attribute_code == code, G2PAttribute.attribute_id == list_id))
                )
            ).scalar_one()
            if exists:
                raise CatalogueError("G2P-CAT-409", f"list already exists: {code}")
            attr = G2PAttribute(
                attribute_id=list_id,
                attribute_code=code,
                attribute_display=display,
                is_hierarchical=bool(payload.is_hierarchical),
                display_i18n=payload.display_i18n,
                attribute_schema=payload.attribute_schema,
                description=payload.description,
                owner_org=payload.owner_org or (_config.catalogue_default_owner_org or None),
                domain=normalise_domain(payload.domain),
                visibility=visibility_of(payload.visibility),
                licence_uri=blank_to_none(payload.licence_uri),
                licence_label=blank_to_none(payload.licence_label),
                current_version_no=None,
            )
            s.add(attr)
            await s.flush()
            await uow.log(
                "list.created",
                "list",
                list_id,
                None,
                {
                    "list_code": code,
                    "owner_org": attr.owner_org,
                    "domain": attr.domain,
                    "visibility": attr.visibility,
                    "licence_uri": attr.licence_uri,
                },
            )
            draft = await self._create_draft(uow, attr, change_note=payload.change_note)
            summary = await self._summary(s, attr)
            info = _version_info(draft, None)
            await uow.commit()
            return summary, info

    async def update_list(self, payload, actor: Actor) -> Tuple[ListSummary, Optional[VersionInfo]]:
        fields = payload.model_fields_set - {"list_code"}
        if not fields:
            raise CatalogueError("G2P-CAT-400", "at least one field must be provided to update")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, payload.list_code, lock=True)
            direct = {}
            if "description" in fields:
                attr.description = payload.description
                direct["description"] = payload.description
            if "owner_org" in fields:
                attr.owner_org = payload.owner_org
                direct["owner_org"] = payload.owner_org
            if "domain" in fields:
                attr.domain = normalise_domain(payload.domain)
                direct["domain"] = attr.domain
            if "visibility" in fields and payload.visibility is not None:
                attr.visibility = visibility_of(payload.visibility)
                direct["visibility"] = attr.visibility
            if "licence_uri" in fields:
                attr.licence_uri = blank_to_none(payload.licence_uri)
                direct["licence_uri"] = attr.licence_uri
            if "licence_label" in fields:
                attr.licence_label = blank_to_none(payload.licence_label)
                direct["licence_label"] = attr.licence_label
            if direct:
                await uow.log("list.updated", "list", attr.attribute_id, None, direct)
            draft = None
            versioned = fields & {
                "new_list_code",
                "display",
                "display_i18n",
                "is_hierarchical",
                "attribute_schema",
            }
            if versioned:
                draft = await self._ensure_draft(uow, attr)
                changed = await self._apply_draft_meta(s, attr, draft, payload, versioned)
                self._touch(draft, actor)
                await uow.log(
                    "list.draft.metadata_changed", "list", attr.attribute_id, draft.version_no, changed
                )
            await s.flush()
            summary = await self._summary(s, attr)
            info = _version_info(draft, attr.current_version_no) if draft else None
            await uow.commit()
            return summary, info

    async def _apply_draft_meta(self, s, attr, draft: G2PListVersion, payload, fields) -> Dict[str, Any]:
        changed: Dict[str, Any] = {}
        if "new_list_code" in fields:
            new_code = (payload.new_list_code or "").strip()
            if not new_code:
                raise CatalogueError("G2P-CAT-400", "list code cannot be empty")
            clash = (
                await s.execute(
                    select(func.count())
                    .select_from(G2PAttribute)
                    .where(
                        G2PAttribute.attribute_code == new_code,
                        G2PAttribute.attribute_id != attr.attribute_id,
                    )
                )
            ).scalar_one()
            if clash:
                raise CatalogueError("G2P-CAT-409", f"list code already exists: {new_code}")
            draft.list_code = new_code
            changed["list_code"] = new_code
        if "display" in fields:
            display = (payload.display or "").strip()
            if not display:
                raise CatalogueError("G2P-CAT-400", "display cannot be empty")
            draft.display = display
            changed["display"] = display
        if "display_i18n" in fields:
            draft.display_i18n = payload.display_i18n
            changed["display_i18n"] = payload.display_i18n
        if "is_hierarchical" in fields:
            if not payload.is_hierarchical:
                n = (
                    await s.execute(
                        select(func.count())
                        .select_from(G2PListVersionValue)
                        .where(
                            G2PListVersionValue.list_id == attr.attribute_id,
                            G2PListVersionValue.version_no == draft.version_no,
                            G2PListVersionValue.parent_value_code.is_not(None),
                            G2PListVersionValue.status == ItemStatus.ACTIVE,
                        )
                    )
                ).scalar_one()
                if n:
                    raise CatalogueError(
                        "G2P-CAT-409",
                        f"cannot set is_hierarchical=false for list {attr.attribute_code} "
                        "while active values have a parent",
                    )
            draft.is_hierarchical = bool(payload.is_hierarchical)
            changed["is_hierarchical"] = draft.is_hierarchical
        if "attribute_schema" in fields:
            check_attribute_schema(payload.attribute_schema)
            draft.attribute_schema = payload.attribute_schema
            changed["attribute_schema"] = True
        return changed

    async def create_list_draft(self, payload, actor: Actor) -> Tuple[str, VersionInfo]:
        async with CatalogueUnitOfWork(actor) as uow:
            attr = await self._get_list(uow.session, payload.list_code, lock=True)
            await self._check_effective_from(uow.session, attr, payload.effective_from)
            draft = await self._create_draft(
                uow,
                attr,
                base_version=payload.base_version,
                copy_from_version=payload.copy_from_version,
                change_note=payload.change_note,
                effective_from=payload.effective_from,
            )
            info = _version_info(draft, attr.current_version_no)
            await uow.commit()
            return attr.attribute_code, info

    async def _check_effective_from(self, s, attr, effective_from: Optional[datetime]) -> None:
        if effective_from is None:
            return
        last = (
            await s.execute(
                select(G2PListVersion.effective_from)
                .where(
                    G2PListVersion.list_id == attr.attribute_id,
                    G2PListVersion.status == VersionStatus.PUBLISHED,
                )
                .order_by(G2PListVersion.version_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last is not None and as_aware(effective_from) < as_aware(last):
            raise CatalogueError(
                "G2P-CAT-400",
                f"effective_from {effective_from} is earlier than the latest published version's ({last})",
            )

    async def update_list_draft(self, payload, actor: Actor) -> Tuple[str, VersionInfo]:
        async with CatalogueUnitOfWork(actor) as uow:
            attr = await self._get_list(uow.session, payload.list_code, lock=True)
            draft = await self._require_draft(uow.session, attr)
            if draft.status != VersionStatus.DRAFT:
                raise CatalogueError("G2P-CAT-409", f"version {draft.version_no} is {draft.status}")
            fields = payload.model_fields_set
            if "change_note" in fields:
                draft.change_note = payload.change_note
            if "effective_from" in fields:
                await self._check_effective_from(uow.session, attr, payload.effective_from)
                draft.effective_from = as_aware(payload.effective_from)
            self._touch(draft, actor)
            await uow.log(
                "list.draft.updated",
                "list",
                attr.attribute_id,
                draft.version_no,
                {"change_note": draft.change_note, "effective_from": str(draft.effective_from or "")},
            )
            info = _version_info(draft, attr.current_version_no)
            await uow.commit()
            return attr.attribute_code, info

    async def upsert_draft_values(
        self, list_code: str, values, actor: Actor
    ) -> Tuple[str, VersionInfo, List[ListValue]]:
        if not values:
            raise CatalogueError("G2P-CAT-400", "values is empty")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, list_code, lock=True)
            draft = await self._ensure_draft(uow, attr)
            rows = await self._values_map(s, attr.attribute_id, draft.version_no)
            by_code = {r.value_code: r for r in rows.values()}
            out, created, updated = [], [], []
            for item in values:
                code = (item.value_code or "").strip()
                if not code:
                    raise CatalogueError("G2P-CAT-400", "value_code is required")
                row = rows.get(item.value_id) if item.value_id else None
                if row is None:
                    row = by_code.get(code)
                    if row is not None and item.value_id and row.value_id != item.value_id:
                        raise CatalogueError(
                            "G2P-CAT-409", f"value_code {code} is already used by value {row.value_id}"
                        )
                if row is None:
                    display = (item.display or "").strip()
                    if not display:
                        raise CatalogueError("G2P-CAT-400", f"display is required for new value {code}")
                    row = G2PListVersionValue(
                        list_id=attr.attribute_id,
                        version_no=draft.version_no,
                        value_id=item.value_id or code,
                        value_code=code,
                        status=ItemStatus.ACTIVE,
                    )
                    if row.value_id in rows:
                        row.value_id = str(uuid.uuid4())
                    s.add(row)
                    rows[row.value_id] = row
                    created.append(code)
                else:
                    if row.value_code != code:
                        clash = by_code.get(code)
                        if clash is not None and clash.value_id != row.value_id:
                            raise CatalogueError(
                                "G2P-CAT-409", f"value_code {code} is already used in this list"
                            )
                        by_code.pop(row.value_code, None)
                        row.value_code = code
                    updated.append(code)
                by_code[code] = row
                fs = item.model_fields_set
                if item.display is not None:
                    row.display = item.display.strip()
                if row.status == ItemStatus.RETIRED and "status" not in fs:
                    # Upserting a retired code brings it back.
                    row.status = ItemStatus.ACTIVE
                if "display_i18n" in fs:
                    row.display_i18n = item.display_i18n
                if "parent_code" in fs:
                    row.parent_value_code = (item.parent_code or "").strip() or None
                if "sort_order" in fs:
                    row.sort_order = item.sort_order
                if "attributes" in fs:
                    row.attributes = item.attributes
                if "roles" in fs:
                    row.roles = item.roles
                if "status" in fs and item.status:
                    row.status = item.status
                if row.parent_value_code and not draft.is_hierarchical:
                    raise CatalogueError(
                        "G2P-CAT-400",
                        f"list {attr.attribute_code} is not hierarchical; parent_code is not allowed",
                    )
                if row.parent_value_code == row.value_code:
                    raise CatalogueError("G2P-CAT-400", "a value cannot be its own parent")
                # Typed attributes are checked as they are edited, and again on submit.
                refs = validate_value_attributes(draft.attribute_schema, code, row.attributes)
                if refs:
                    await self._check_list_refs(
                        s, refs, context=f"value '{code}'", at=self.refs_resolved_at(draft)
                    )
                out.append(row)
            await s.flush()
            self._touch(draft, actor)
            await uow.log(
                "list.draft.values_changed",
                "list",
                attr.attribute_id,
                draft.version_no,
                {"created": created[:200], "updated": updated[:200], "count": len(out)},
            )
            result = [_value(r) for r in out]
            info = _version_info(draft, attr.current_version_no)
            await uow.commit()
            return attr.attribute_code, info, result

    async def retire_draft_values(
        self, list_code: str, value_codes: List[str], cascade: bool, actor: Actor
    ) -> Tuple[str, VersionInfo, List[str], List[str]]:
        if not value_codes:
            raise CatalogueError("G2P-CAT-400", "value_codes is empty")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, list_code, lock=True)
            draft = await self._ensure_draft(uow, attr)
            retired, removed = await self._retire_in_draft(s, attr, draft, value_codes, cascade)
            self._touch(draft, actor)
            await uow.log(
                "list.draft.values_retired",
                "list",
                attr.attribute_id,
                draft.version_no,
                {"retired": retired[:200], "removed": removed[:200]},
            )
            info = _version_info(draft, attr.current_version_no)
            await uow.commit()
            return attr.attribute_code, info, retired, removed

    async def _retire_in_draft(self, s, attr, draft, value_codes, cascade) -> Tuple[List[str], List[str]]:
        rows = await self._values_map(s, attr.attribute_id, draft.version_no)
        by_code = {r.value_code: r for r in rows.values()}
        base_ids = set()
        if draft.base_version_no is not None:
            base_ids = set((await self._values_map(s, attr.attribute_id, draft.base_version_no)).keys())
        targets: List[G2PListVersionValue] = []
        for code in value_codes:
            row = by_code.get(code)
            if row is None:
                raise CatalogueError(
                    "G2P-CAT-404", f"value {code} not in the draft of list {attr.attribute_code}"
                )
            targets.append(row)
        # Children of a value being retired.
        frontier = {t.value_code for t in targets}
        seen = set(frontier)
        while frontier:
            kids = [
                r
                for r in rows.values()
                if r.parent_value_code in frontier
                and r.status == ItemStatus.ACTIVE
                and r.value_code not in seen
            ]
            if kids and not cascade:
                raise CatalogueError(
                    "G2P-CAT-409",
                    f"cannot retire {sorted(frontier)}: {len(kids)} active child value(s); pass cascade=true",
                )
            targets.extend(kids)
            frontier = {k.value_code for k in kids}
            seen |= frontier
        retired, removed = [], []
        for row in targets:
            if row.value_id in base_ids:
                row.status = ItemStatus.RETIRED
                retired.append(row.value_code)
            else:
                await s.delete(row)
                removed.append(row.value_code)
        await s.flush()
        return retired, removed

    async def discard_draft(self, list_code: str, actor: Actor) -> Tuple[str, int]:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, list_code, lock=True)
            draft = await self._require_draft(s, attr)
            if draft.status == VersionStatus.SUBMITTED and approval_mode() == "awe":
                raise CatalogueError(
                    "G2P-CAT-409", "the draft is awaiting approval in AWE; cancel the AWE request instead"
                )
            no = draft.version_no
            # Kept as a tombstone (with its content, like a REJECTED version): the
            # number stays taken, so the next draft is no + 1, not no again.
            draft.status = VersionStatus.DISCARDED
            draft.decided_by = actor.id
            draft.decided_by_name = actor.display_name
            draft.decided_at = utcnow()
            await s.flush()
            await uow.log(
                "list.draft.discarded", "list", attr.attribute_id, no, {"list_code": attr.attribute_code}
            )
            await uow.commit()
            return attr.attribute_code, no

    # ------------------------------------------------------------------
    # Submit / approve / reject / publish
    # ------------------------------------------------------------------

    @staticmethod
    def refs_resolved_at(
        version: G2PListVersion, effective_from: Optional[datetime] = None
    ) -> Optional[datetime]:
        """The moment a version's ``x-list-ref`` references are resolved at.

        The version's effective date when it is in the future — a version that
        takes effect on 2027-01-01 may reference values of a referenced list's
        version that is published and takes effect by then — else None, meaning
        now (by the database clock, the one effective dates are stamped with).
        """
        eff = as_aware(effective_from if effective_from is not None else version.effective_from)
        return eff if eff is not None and eff > utcnow() else None

    async def _check_list_refs(
        self,
        s,
        refs: Dict[str, set],
        context: str,
        *,
        at: Optional[datetime] = None,
        release_versions: Optional[Dict[str, int]] = None,
    ) -> None:
        """Every referenced code must be an ACTIVE value of the referenced list's
        version IN EFFECT at ``at`` (None: now): its latest published version
        with effective_from <= at. When validating a release, a referenced list
        the release pins is checked at its pinned version instead.

        Never a draft. A list's draft can therefore only reference values that
        are already published; when a referenced list and the list referencing
        it change together (e.g. a new crop and its varieties), publish the
        referenced list first — with the same or an earlier effective date —
        then submit the referencing list. The error says so when the code is
        only in the referenced list's open draft.
        """
        for ref_code, codes in refs.items():
            ref = (
                (
                    await s.execute(
                        select(G2PAttribute).where(
                            or_(
                                G2PAttribute.attribute_code == ref_code, G2PAttribute.attribute_id == ref_code
                            )
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not ref:
                raise CatalogueError("G2P-CAT-400", f"{context}: referenced list {ref_code} does not exist")
            when = f"at {at.strftime('%Y-%m-%d %H:%M:%S UTC')}" if at is not None else "now"
            if release_versions is not None and ref.attribute_id in release_versions:
                version_no = release_versions[ref.attribute_id]
                where = f"version {version_no}, pinned in the release"
            else:
                version_no = await self._current_no(s, ref.attribute_id, at)
                if version_no is None:
                    raise CatalogueError(
                        "G2P-CAT-400",
                        f"{context}: referenced list {ref_code} has no published version in effect {when}",
                    )
                where = f"version {version_no}, in effect {when}"
            found = set(
                (
                    await s.execute(
                        select(G2PListVersionValue.value_code).where(
                            G2PListVersionValue.list_id == ref.attribute_id,
                            G2PListVersionValue.version_no == version_no,
                            G2PListVersionValue.status == ItemStatus.ACTIVE,
                            G2PListVersionValue.value_code.in_(list(codes)),
                        )
                    )
                ).scalars()
            )
            missing = sorted(set(codes) - found)
            if not missing:
                continue
            hint = ""
            open_v = await self._open_version(s, ref.attribute_id)
            if open_v is not None:
                in_draft = sorted(
                    (
                        await s.execute(
                            select(G2PListVersionValue.value_code).where(
                                G2PListVersionValue.list_id == ref.attribute_id,
                                G2PListVersionValue.version_no == open_v.version_no,
                                G2PListVersionValue.status == ItemStatus.ACTIVE,
                                G2PListVersionValue.value_code.in_(missing),
                            )
                        )
                    ).scalars()
                )
                if in_draft:
                    hint = (
                        f"; {in_draft} exist only in the unpublished draft (version {open_v.version_no}) "
                        f"of {ref_code} — publish {ref_code} first"
                    )
            raise CatalogueError(
                "G2P-CAT-400",
                f"{context}: {missing} are not values of list {ref_code} ({where}){hint}",
            )

    async def validate_version(
        self,
        s,
        attr,
        version: G2PListVersion,
        release_versions=None,
        *,
        effective_from: Optional[datetime] = None,
    ) -> None:
        """Everything a version must satisfy before it can be published.

        ``x-list-ref`` references resolve against the referenced lists' versions
        in effect when this version takes effect (``effective_from`` if given,
        else the version's own; now if that is unset or past), or against the
        pinned versions when validating a release.
        """
        check_attribute_schema(version.attribute_schema)
        rows = await self._values_map(s, attr.attribute_id, version.version_no)
        active = {r.value_code: r for r in rows.values() if r.status == ItemStatus.ACTIVE}
        refs: Dict[str, set] = {}
        for code, row in active.items():
            if not (row.display or "").strip():
                raise CatalogueError("G2P-CAT-400", f"value {code} has no display label")
            if row.parent_value_code:
                if not version.is_hierarchical:
                    raise CatalogueError(
                        "G2P-CAT-400", f"value {code} has a parent but the list is not hierarchical"
                    )
                if row.parent_value_code not in active:
                    raise CatalogueError(
                        "G2P-CAT-400", f"value {code}: parent {row.parent_value_code} is not an active value"
                    )
            merge_refs(refs, validate_value_attributes(version.attribute_schema, code, row.attributes))
        # No cycles.
        for code in active:
            seen, cur = set(), code
            while cur:
                if cur in seen:
                    raise CatalogueError("G2P-CAT-400", f"value {code}: parent chain has a cycle")
                seen.add(cur)
                cur = active[cur].parent_value_code if cur in active else None
        if refs:
            await self._check_list_refs(
                s,
                refs,
                context=f"list {attr.attribute_code} v{version.version_no}",
                at=self.refs_resolved_at(version, effective_from),
                release_versions=release_versions,
            )

    async def submit_draft(self, payload, actor: Actor) -> Tuple[str, VersionInfo]:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, payload.list_code, lock=True)
            draft = await self._require_draft(s, attr)
            if draft.status != VersionStatus.DRAFT:
                raise CatalogueError("G2P-CAT-409", f"version {draft.version_no} is already {draft.status}")
            fields = payload.model_fields_set
            if "change_note" in fields and payload.change_note is not None:
                draft.change_note = payload.change_note
            if "effective_from" in fields:
                await self._check_effective_from(s, attr, payload.effective_from)
                draft.effective_from = as_aware(payload.effective_from)
            await self.validate_version(s, attr, draft)
            if draft.base_version_no is not None:
                base = await self._get_version(s, attr.attribute_id, draft.base_version_no)
                diff = await self._diff(s, attr, base, draft)
                if not any(
                    diff[k] for k in ("metadata_changes", "added", "changed", "retired", "reactivated")
                ):
                    raise CatalogueError("G2P-CAT-400", "the draft has no changes from its base version")
            draft.status = VersionStatus.SUBMITTED
            draft.submitted_by = actor.id
            draft.submitted_by_name = actor.display_name
            draft.submitted_at = utcnow()
            await s.flush()
            await uow.log(
                "list.draft.submitted",
                "list",
                attr.attribute_id,
                draft.version_no,
                {
                    "list_code": attr.attribute_code,
                    "approval_mode": approval_mode(),
                    "owner_org": attr.owner_org,
                },
            )
            if approval_mode() == "awe":
                await self._start_awe(uow, attr, draft)
            info = _version_info(draft, attr.current_version_no)
            await uow.commit()
            return attr.attribute_code, info

    async def _start_awe(self, uow: CatalogueUnitOfWork, attr, draft: G2PListVersion) -> None:
        if not uow.actor.token:
            raise CatalogueError("G2P-CAT-403", "a bearer token is required to open an AWE approval request")
        artifact_id = f"{attr.attribute_id}:{draft.version_no}"
        try:
            result = await CatalogueAweHelper.get_component().create_request(
                uow.actor.token,
                policy_key=_config.awe_policy_key_list,
                artifact_type=LIST_ARTIFACT,
                artifact_id=artifact_id,
                context={
                    "list_code": attr.attribute_code,
                    "list_id": attr.attribute_id,
                    "version_no": draft.version_no,
                    "owner_org": attr.owner_org,
                    "change_note": draft.change_note,
                },
                requester=uow.actor.id,
                idempotency_key=f"mds-list-{artifact_id}",
            )
        except AweClientError as exc:
            raise CatalogueError("G2P-CAT-502", f"AWE request failed: {exc.message}") from exc
        draft.approval_ref = result.get("request_id")
        await uow.log(
            "list.approval.requested",
            "list",
            attr.attribute_id,
            draft.version_no,
            {"awe_request_id": draft.approval_ref, "status": result.get("status")},
        )

    @staticmethod
    def _check_maker_checker(version, actor: Actor) -> None:
        # Stable user ids (token ``sub``), never display names: see Actor.
        makers = {m for m in (version.created_by, version.updated_by, version.submitted_by) if m}
        if actor.id in makers:
            raise CatalogueError(
                "G2P-CAT-403",
                "maker-checker: the approver must not be the person who created, edited or submitted the draft",
            )

    async def _submitted(self, s, attr, version_no: Optional[int]) -> G2PListVersion:
        draft = await self._require_draft(s, attr)
        if draft.status != VersionStatus.SUBMITTED:
            raise CatalogueError(
                "G2P-CAT-409", f"version {draft.version_no} is {draft.status}, not SUBMITTED"
            )
        if version_no is not None and version_no != draft.version_no:
            raise CatalogueError(
                "G2P-CAT-409", f"version {version_no} is not the submitted version ({draft.version_no})"
            )
        return draft

    async def approve_draft(self, payload, actor: Actor) -> Tuple[str, VersionInfo]:
        if approval_mode() == "awe":
            raise CatalogueError("G2P-CAT-409", "approval runs through AWE in this deployment")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, payload.list_code, lock=True)
            draft = await self._submitted(s, attr, payload.version_no)
            self._check_maker_checker(draft, actor)
            version = await self.publish(uow, attr, draft, payload.effective_from, payload.decision_note)
            await uow.commit()
            return attr.attribute_code, version

    async def publish(
        self,
        uow: CatalogueUnitOfWork,
        attr,
        draft: G2PListVersion,
        effective_from: Optional[datetime],
        note: Optional[str],
        *,
        allow_draft: bool = False,
    ) -> VersionInfo:
        """Publish in the caller's transaction (also used by the AWE callback)."""
        s = uow.session
        await self.validate_version(s, attr, draft, effective_from=effective_from)
        if effective_from is not None:
            await self._check_effective_from(s, attr, effective_from)
        # g2p_catalogue_publish_list stamps decided_by with the same id.
        draft.decided_by = uow.actor.id
        draft.decided_by_name = uow.actor.display_name
        await s.flush()
        eff = (
            await s.execute(
                text(
                    "SELECT g2p_catalogue_publish_list(:list_id, :version_no, :actor, :eff, :note, :allow_draft)"
                ),
                {
                    "list_id": attr.attribute_id,
                    "version_no": draft.version_no,
                    "actor": uow.actor.id,
                    "eff": as_aware(effective_from),
                    "note": note,
                    "allow_draft": allow_draft,
                },
            )
        ).scalar_one()
        await s.refresh(draft)
        await s.refresh(attr)
        await uow.log(
            "list.draft.approved",
            "list",
            attr.attribute_id,
            draft.version_no,
            {"decision_note": note},
        )
        details = {
            "list_code": draft.list_code or attr.attribute_code,
            "effective_from": eff.isoformat() if eff else None,
            "base_version_no": draft.base_version_no,
            "current_version_no": attr.current_version_no,
        }
        await uow.log("list.version.published", "list", attr.attribute_id, draft.version_no, details)
        return _version_info(draft, attr.current_version_no)

    async def reject_draft(self, payload, actor: Actor) -> Tuple[str, VersionInfo]:
        if approval_mode() == "awe":
            raise CatalogueError("G2P-CAT-409", "approval runs through AWE in this deployment")
        if not (payload.decision_note or "").strip():
            raise CatalogueError("G2P-CAT-400", "decision_note is required to reject")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, payload.list_code, lock=True)
            draft = await self._submitted(s, attr, payload.version_no)
            self._check_maker_checker(draft, actor)
            await self.reject(uow, attr, draft, payload.decision_note)
            info = _version_info(draft, attr.current_version_no)
            await uow.commit()
            return attr.attribute_code, info

    async def reject(self, uow, attr, draft: G2PListVersion, note: Optional[str]) -> None:
        draft.status = VersionStatus.REJECTED
        draft.decided_by = uow.actor.id
        draft.decided_by_name = uow.actor.display_name
        draft.decided_at = utcnow()
        draft.decision_note = note
        await uow.session.flush()
        await uow.log(
            "list.draft.rejected", "list", attr.attribute_id, draft.version_no, {"decision_note": note}
        )

    # ------------------------------------------------------------------
    # Legacy write endpoints (/attributes/*) — they now edit the open draft
    # ------------------------------------------------------------------

    @staticmethod
    def _legacy_attr(attr: G2PAttribute, draft: Optional[G2PListVersion]) -> AttributeData:
        src = draft
        return AttributeData(
            attribute_id=attr.attribute_id,
            attribute_code=(src.list_code if src and src.list_code else attr.attribute_code),
            attribute_display=(src.display if src and src.display else attr.attribute_display),
            is_hierarchical=bool(src.is_hierarchical if src is not None else attr.is_hierarchical),
            current_version_no=attr.current_version_no,
        )

    async def legacy_add_attribute(
        self, *, attribute_code, attribute_display, is_hierarchical, actor
    ) -> AttributeData:
        from ..schemas.g2p_catalogue import CreateListPayload

        code = (attribute_code or "").strip()
        display = (attribute_display or "").strip()
        if not code or not display:
            raise CatalogueError("G2P-ATTR-400", "attribute_code and attribute_display are required")
        await self.create_list(
            CreateListPayload(
                list_code=code,
                display=display,
                is_hierarchical=bool(is_hierarchical),
                list_id=str(uuid.uuid4()),
            ),
            actor,
        )
        async with get_async_session_maker()() as s:
            attr = await self._get_list(s, code)
            return self._legacy_attr(attr, await self._open_version(s, attr.attribute_id))

    async def legacy_update_attribute(self, payload, actor) -> AttributeData:
        from ..schemas.g2p_catalogue import UpdateListPayload

        fields = payload.model_fields_set - {"attribute_id"}
        if not fields:
            raise CatalogueError("G2P-ATTR-400", "At least one field must be provided to update")
        data: Dict[str, Any] = {"list_code": payload.attribute_id}
        if "attribute_code" in fields:
            data["new_list_code"] = payload.attribute_code
        if "attribute_display" in fields:
            data["display"] = payload.attribute_display
        if "is_hierarchical" in fields:
            data["is_hierarchical"] = bool(payload.is_hierarchical)
        await self.update_list(UpdateListPayload(**data), actor)
        async with get_async_session_maker()() as s:
            attr = await self._get_list(s, payload.attribute_id)
            return self._legacy_attr(attr, await self._open_version(s, attr.attribute_id))

    async def legacy_delete_attribute(self, attribute_id: str, cascade: bool, actor: Actor) -> str:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, attribute_id, lock=True)
            ever_published = await self._max_published_no(s, attr.attribute_id)
            if ever_published is None:
                n = (
                    await s.execute(
                        select(func.count())
                        .select_from(G2PListVersionValue)
                        .where(G2PListVersionValue.list_id == attr.attribute_id)
                    )
                ).scalar_one()
                if n and not cascade:
                    raise CatalogueError(
                        "G2P-ATTR-409",
                        f"Cannot delete attribute '{attribute_id}' while attribute values exist",
                    )
                # Never published: nothing anyone could have referenced.
                await s.execute(delete(G2PAttribute).where(G2PAttribute.attribute_id == attr.attribute_id))
                await uow.log(
                    "list.deleted", "list", attr.attribute_id, None, {"list_code": attr.attribute_code}
                )
                await uow.commit()
                return attr.attribute_id
            draft = await self._ensure_draft(uow, attr)
            rows = await self._values_map(s, attr.attribute_id, draft.version_no)
            active = [r.value_code for r in rows.values() if r.status == ItemStatus.ACTIVE]
            if active and not cascade:
                raise CatalogueError(
                    "G2P-ATTR-409", f"Cannot delete attribute '{attribute_id}' while attribute values exist"
                )
            # Published lists are never deleted: every value is retired in the draft.
            retired, removed = (
                (await self._retire_in_draft(s, attr, draft, active, True)) if active else ([], [])
            )
            self._touch(draft, actor)
            await uow.log(
                "list.draft.values_retired",
                "list",
                attr.attribute_id,
                draft.version_no,
                {"retired": retired[:200], "removed": removed[:200], "reason": "delete_attribute"},
            )
            await uow.commit()
            return attr.attribute_id

    async def _find_list_of_value(self, s, value_id: str, attribute_id: Optional[str]) -> G2PAttribute:
        if attribute_id:
            return await self._get_list(s, attribute_id)
        list_id = (
            await s.execute(
                select(G2PListVersionValue.list_id)
                .where(G2PListVersionValue.value_id == value_id)
                .order_by(G2PListVersionValue.version_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not list_id:
            raise CatalogueError("G2P-ATTR-404", f"value_id not found: {value_id}")
        return await self._get_list(s, list_id)

    def _legacy_value(self, attr, row: G2PListVersionValue, parent_id: Optional[str]) -> AttributeValueData:
        return AttributeValueData(
            attribute_id=attr.attribute_id,
            value_id=row.value_id,
            value_code=row.value_code,
            value_display=row.display,
            parent_value_id=parent_id,
            sort_order=row.sort_order,
        )

    async def _code_of(self, s, list_id: str, version_no: int, value_id: Optional[str]) -> Optional[str]:
        if not value_id:
            return None
        row = await s.get(G2PListVersionValue, (list_id, version_no, value_id))
        if not row:
            raise CatalogueError(
                "G2P-ATTR-404", f"parent_value_id not found for attribute '{list_id}': {value_id}"
            )
        return row.value_code

    async def legacy_add_value(
        self, *, attribute_id, value_code, value_display, parent_value_id, sort_order, actor
    ):
        value_code = (value_code or "").strip()
        value_display = (value_display or "").strip()
        if not value_code or not value_display:
            raise CatalogueError("G2P-ATTR-400", "value_code and value_display are required")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._get_list(s, attribute_id, lock=True)
            draft = await self._ensure_draft(uow, attr)
            parent_code = await self._code_of(
                s, attr.attribute_id, draft.version_no, (parent_value_id or "").strip() or None
            )
            if parent_code and not draft.is_hierarchical:
                raise CatalogueError(
                    "G2P-ATTR-400",
                    f"attribute '{attribute_id}' is not hierarchical; parent_value_id is not allowed",
                )
            clash = (
                (
                    await s.execute(
                        select(G2PListVersionValue).where(
                            G2PListVersionValue.list_id == attr.attribute_id,
                            G2PListVersionValue.version_no == draft.version_no,
                            G2PListVersionValue.value_code == value_code,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if clash:
                raise CatalogueError(
                    "G2P-ATTR-409", f"value_code already exists for attribute '{attribute_id}': {value_code}"
                )
            row = G2PListVersionValue(
                list_id=attr.attribute_id,
                version_no=draft.version_no,
                value_id=str(uuid.uuid4()),
                value_code=value_code,
                display=value_display,
                parent_value_code=parent_code,
                sort_order=0 if sort_order is None else sort_order,
                status=ItemStatus.ACTIVE,
            )
            s.add(row)
            await s.flush()
            self._touch(draft, actor)
            await uow.log(
                "list.draft.values_changed",
                "list",
                attr.attribute_id,
                draft.version_no,
                {"created": [value_code], "count": 1, "via": "add_attribute_value"},
            )
            out = self._legacy_value(attr, row, (parent_value_id or "").strip() or None)
            await uow.commit()
            return out

    async def legacy_update_value(self, payload, actor) -> AttributeValueData:
        fields = payload.model_fields_set - {"value_id", "attribute_id"}
        if not fields:
            raise CatalogueError("G2P-ATTR-400", "At least one field must be provided to update")
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._find_list_of_value(
                s, payload.value_id, (payload.attribute_id or "").strip() or None
            )
            attr = await self._get_list(s, attr.attribute_id, lock=True)
            draft = await self._ensure_draft(uow, attr)
            row = await s.get(G2PListVersionValue, (attr.attribute_id, draft.version_no, payload.value_id))
            if not row:
                raise CatalogueError("G2P-ATTR-404", f"value_id not found: {payload.value_id}")
            if "value_code" in fields:
                code = (payload.value_code or "").strip()
                if not code:
                    raise CatalogueError("G2P-ATTR-400", "value_code cannot be empty")
                clash = (
                    await s.execute(
                        select(func.count())
                        .select_from(G2PListVersionValue)
                        .where(
                            G2PListVersionValue.list_id == attr.attribute_id,
                            G2PListVersionValue.version_no == draft.version_no,
                            G2PListVersionValue.value_code == code,
                            G2PListVersionValue.value_id != row.value_id,
                        )
                    )
                ).scalar_one()
                if clash:
                    raise CatalogueError(
                        "G2P-ATTR-409",
                        f"value_code already exists for attribute '{attr.attribute_id}': {code}",
                    )
                # Children follow a recoded parent.
                await s.execute(
                    update(G2PListVersionValue)
                    .where(
                        G2PListVersionValue.list_id == attr.attribute_id,
                        G2PListVersionValue.version_no == draft.version_no,
                        G2PListVersionValue.parent_value_code == row.value_code,
                    )
                    .values(parent_value_code=code)
                )
                row.value_code = code
            if "value_display" in fields:
                display = (payload.value_display or "").strip()
                if not display:
                    raise CatalogueError("G2P-ATTR-400", "value_display cannot be empty")
                row.display = display
            parent_id = None
            if "parent_value_id" in fields:
                parent_id = (payload.parent_value_id or "").strip() or None
                if parent_id == row.value_id:
                    raise CatalogueError("G2P-ATTR-400", "attribute value cannot be its own parent")
                parent_code = await self._code_of(s, attr.attribute_id, draft.version_no, parent_id)
                if parent_code and not draft.is_hierarchical:
                    raise CatalogueError(
                        "G2P-ATTR-400",
                        f"attribute '{attr.attribute_id}' is not hierarchical; parent_value_id is not allowed",
                    )
                row.parent_value_code = parent_code
            elif row.parent_value_code:
                parent_id = (
                    await s.execute(
                        select(G2PListVersionValue.value_id).where(
                            G2PListVersionValue.list_id == attr.attribute_id,
                            G2PListVersionValue.version_no == draft.version_no,
                            G2PListVersionValue.value_code == row.parent_value_code,
                        )
                    )
                ).scalar_one_or_none()
            if "sort_order" in fields:
                row.sort_order = payload.sort_order
            await s.flush()
            self._touch(draft, actor)
            await uow.log(
                "list.draft.values_changed",
                "list",
                attr.attribute_id,
                draft.version_no,
                {"updated": [row.value_code], "count": 1, "via": "update_attribute_value"},
            )
            out = self._legacy_value(attr, row, parent_id)
            await uow.commit()
            return out

    async def legacy_delete_value(self, value_id: str, attribute_id: Optional[str], actor) -> Tuple[str, str]:
        async with CatalogueUnitOfWork(actor) as uow:
            s = uow.session
            attr = await self._find_list_of_value(s, value_id, (attribute_id or "").strip() or None)
            attr = await self._get_list(s, attr.attribute_id, lock=True)
            draft = await self._ensure_draft(uow, attr)
            row = await s.get(G2PListVersionValue, (attr.attribute_id, draft.version_no, value_id))
            if not row:
                raise CatalogueError("G2P-ATTR-404", f"value_id not found: {value_id}")
            children = (
                await s.execute(
                    select(func.count())
                    .select_from(G2PListVersionValue)
                    .where(
                        G2PListVersionValue.list_id == attr.attribute_id,
                        G2PListVersionValue.version_no == draft.version_no,
                        G2PListVersionValue.parent_value_code == row.value_code,
                        G2PListVersionValue.status == ItemStatus.ACTIVE,
                    )
                )
            ).scalar_one()
            if children:
                raise CatalogueError(
                    "G2P-ATTR-409", f"Cannot delete attribute value with {children} child value(s)"
                )
            retired, removed = await self._retire_in_draft(s, attr, draft, [row.value_code], False)
            self._touch(draft, actor)
            await uow.log(
                "list.draft.values_retired",
                "list",
                attr.attribute_id,
                draft.version_no,
                {"retired": retired, "removed": removed, "via": "delete_attribute_value"},
            )
            await uow.commit()
            return value_id, attr.attribute_id
