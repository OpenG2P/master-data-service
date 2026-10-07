"""The public (anonymous, read-only) catalogue: what /public/... serves.

Opt-in twice over: the deployment turns the public catalogue on
(``public_catalogue_enabled``, off by default) and an administrator marks each
dataset, and the geography, ``public`` (private by default). Whatever the
settings, only PUBLISHED versions are ever read here — never a draft, a
submitted, rejected or discarded version — and nothing else (sample people,
the change feed, who approved what) is reachable. Every query below filters on
``status = PUBLISHED`` itself rather than going through the authenticated
services' version resolution, which also serves drafts.

A dataset or geography that is private, or a version that is not published,
is answered exactly like one that does not exist (404), so the public API does
not reveal what exists behind it.

Standards: DCAT (DCAT-AP style) catalogue metadata and SKOS concept schemes,
both as JSON-LD, built here; see ``catalog_jsonld`` and ``skos_jsonld``.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import func, or_, select

from ..config import Settings
from ..models import (
    G2PAttribute,
    G2PCatalogueRelease,
    G2PCatalogueReleaseMember,
    G2PGeoVersion,
    G2PGeoVersionLevel,
    G2PGeoVersionUnit,
    G2PListVersion,
    G2PListVersionValue,
    ItemStatus,
    VersionStatus,
)
from ..schemas.g2p_catalogue import GeoSettings
from .catalogue_common import as_aware
from .g2p_catalogue_geo_service import read_geo_settings
from .g2p_catalogue_list_service import normalise_domain

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)

PUBLIC = "public"

JSONLD_CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

_IANA = "https://www.iana.org/assignments/media-types/"
_EU_FILE_TYPE = "http://publications.europa.eu/resource/authority/file-type/"
# (media type, EU file-type authority code) per download format.
FORMATS = {
    "csv": ("text/csv", "CSV"),
    "json": ("application/json", "JSON"),
    "skos": ("application/ld+json", "JSON_LD"),
    "geojson": ("application/geo+json", "GEOJSON"),
}


class PublicNotFound(Exception):
    """Anything the public catalogue does not serve (missing, private or unpublished)."""

    def __init__(self, message: str = "not found"):
        super().__init__(message)
        self.message = message


class PublicBadRequest(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class PublicSelector:
    """``version`` (number or "latest") or ``as_of``; at most one. Published versions only."""

    version: Optional[int] = None
    as_of: Optional[datetime] = None

    @classmethod
    def parse(cls, version: Optional[str], as_of: Optional[datetime]) -> PublicSelector:
        v = (version or "").strip().lower()
        if v and as_of is not None:
            raise PublicBadRequest("give at most one of version, as_of")
        if v in ("", "latest"):
            return cls(None, as_aware(as_of) if as_of is not None else None)
        if not v.isdigit():
            raise PublicBadRequest('version must be a number or "latest"')
        return cls(int(v), None)


def iso(value: Optional[datetime]) -> Optional[str]:
    return as_aware(value).isoformat() if value is not None else None


def _dt(value: Optional[datetime]) -> Optional[Dict[str, str]]:
    return {"@value": iso(value), "@type": "xsd:dateTime"} if value is not None else None


def _licence(uri: Optional[str], label: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    if not uri and not label:
        return None
    return {"uri": uri or None, "label": label or None}


def _licence_ld(licence: Optional[Dict[str, Optional[str]]]) -> Optional[Dict[str, Any]]:
    if not licence:
        return None
    node: Dict[str, Any] = {"@type": "dct:LicenseDocument"}
    if licence.get("uri"):
        node["@id"] = licence["uri"]
    if licence.get("label"):
        node["rdfs:label"] = licence["label"]
    return node


def _labels(display: Optional[str], i18n: Optional[Dict[str, str]]) -> List[Dict[str, str]]:
    """Language-tagged labels: display_i18n per locale, plus the plain label in the
    default language when display_i18n does not already carry that language."""
    out: List[Dict[str, str]] = []
    i18n = {k: v for k, v in (i18n or {}).items() if k and v}
    default = (_config.public_catalogue_default_language or "").strip()
    if display and (not default or default not in i18n):
        out.append({"@value": display, "@language": default} if default else {"@value": display})
    for lang in sorted(i18n):
        out.append({"@value": i18n[lang], "@language": lang})
    return out


def _compact(node: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in node.items() if v not in (None, [], {})}


class G2PCataloguePublicService(BaseService):
    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    # ------------------------------------------------------------------
    # Lists (datasets)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_public(attr: G2PAttribute) -> bool:
        return (attr.visibility or "").strip().lower() == PUBLIC

    @staticmethod
    async def _public_list(s, code: str) -> G2PAttribute:
        code = (code or "").strip()
        if not code:
            raise PublicNotFound("dataset not found")
        attr = (
            (
                await s.execute(
                    select(G2PAttribute)
                    .where(or_(G2PAttribute.attribute_code == code, G2PAttribute.attribute_id == code))
                    .order_by((G2PAttribute.attribute_code == code).desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if attr is None or (attr.visibility or "").strip().lower() != PUBLIC:
            raise PublicNotFound(f"dataset not found: {code}")
        return attr

    @staticmethod
    async def _published(s, list_id: str) -> List[G2PListVersion]:
        """PUBLISHED versions of a list, newest first."""
        return list(
            (
                await s.execute(
                    select(G2PListVersion)
                    .where(
                        G2PListVersion.list_id == list_id, G2PListVersion.status == VersionStatus.PUBLISHED
                    )
                    .order_by(G2PListVersion.version_no.desc())
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _in_effect(versions: List[G2PListVersion], at: Optional[datetime] = None) -> Optional[Any]:
        at = as_aware(at) if at is not None else datetime.now().astimezone()
        for v in versions:  # newest first
            if v.effective_from is not None and as_aware(v.effective_from) <= at:
                return v
        return None

    def _pick(self, versions, sel: PublicSelector, what: str):
        if sel.version is not None:
            for v in versions:
                if v.version_no == sel.version:
                    return v
            raise PublicNotFound(f"{what}: no published version {sel.version}")
        v = self._in_effect(versions, sel.as_of)
        if v is None:
            raise PublicNotFound(
                f"{what}: no published version in effect" + (f" at {iso(sel.as_of)}" if sel.as_of else "")
            )
        return v

    def _dataset(self, attr, versions, current, base: str, *, with_versions: bool = False) -> Dict[str, Any]:
        code = attr.attribute_code or attr.attribute_id
        url = f"{base}/public/datasets/{quote(code, safe='')}"
        out = {
            "code": code,
            "title": current.display or attr.attribute_display or code,
            "title_i18n": current.display_i18n or None,
            "description": attr.description,
            "theme": normalise_domain(attr.domain),
            "publisher": attr.owner_org,
            "licence": _licence(attr.licence_uri, attr.licence_label),
            "hierarchical": bool(current.is_hierarchical),
            "version": current.version_no,
            "effective_from": iso(current.effective_from),
            "issued": iso(min((v.published_at for v in versions if v.published_at), default=None)),
            "modified": iso(current.published_at),
            "links": {
                "self": url,
                "entries": f"{url}/entries",
                "csv": f"{url}/download.csv?version={current.version_no}",
                "json": f"{url}/download.json?version={current.version_no}",
                "skos": f"{url}/skos?version={current.version_no}",
            },
        }
        if with_versions:
            out["versions"] = [
                {
                    "version": v.version_no,
                    "effective_from": iso(v.effective_from),
                    "published_at": iso(v.published_at),
                    "change_note": v.change_note,
                    "is_current": v.version_no == current.version_no,
                }
                for v in versions
            ]
        return out

    async def _public_lists(self, s) -> List[Tuple[G2PAttribute, List[G2PListVersion], G2PListVersion]]:
        attrs = (
            (
                await s.execute(
                    select(G2PAttribute)
                    .where(func.lower(func.trim(G2PAttribute.visibility)) == PUBLIC)
                    .order_by(G2PAttribute.attribute_code, G2PAttribute.attribute_id)
                )
            )
            .scalars()
            .all()
        )
        if not attrs:
            return []
        rows = (
            (
                await s.execute(
                    select(G2PListVersion)
                    .where(
                        G2PListVersion.list_id.in_([a.attribute_id for a in attrs]),
                        G2PListVersion.status == VersionStatus.PUBLISHED,
                    )
                    .order_by(G2PListVersion.list_id, G2PListVersion.version_no.desc())
                )
            )
            .scalars()
            .all()
        )
        by_list: Dict[str, List[G2PListVersion]] = {}
        for v in rows:
            by_list.setdefault(v.list_id, []).append(v)
        out = []
        for a in attrs:
            versions = by_list.get(a.attribute_id, [])
            current = self._in_effect(versions)
            if current is not None:  # public but nothing in effect yet: not listed
                out.append((a, versions, current))
        return out

    async def list_datasets(self, base: str) -> Tuple[List[Dict[str, Any]], Optional[datetime]]:
        async with get_async_session_maker()() as s:
            items = await self._public_lists(s)
        datasets = [self._dataset(a, vs, cur, base) for a, vs, cur in items]
        modified = max((cur.published_at for _, _, cur in items if cur.published_at), default=None)
        return datasets, modified

    async def get_dataset(self, code: str, base: str) -> Tuple[Dict[str, Any], Optional[datetime]]:
        async with get_async_session_maker()() as s:
            attr = await self._public_list(s, code)
            versions = await self._published(s, attr.attribute_id)
        current = self._in_effect(versions)
        if current is None:
            raise PublicNotFound(f"dataset not found: {code}")
        return self._dataset(attr, versions, current, base, with_versions=True), current.published_at

    async def _version_and_values(
        self, code: str, sel: PublicSelector, *, include_retired: bool = False
    ) -> Tuple[G2PAttribute, G2PListVersion, List[G2PListVersionValue]]:
        async with get_async_session_maker()() as s:
            attr = await self._public_list(s, code)
            version = self._pick(await self._published(s, attr.attribute_id), sel, f"dataset {code}")
            V = G2PListVersionValue
            conds = [V.list_id == attr.attribute_id, V.version_no == version.version_no]
            if not include_retired:
                conds.append(V.status == ItemStatus.ACTIVE)
            rows = (
                (
                    await s.execute(
                        select(V).where(*conds).order_by(V.sort_order.asc().nulls_last(), V.value_code)
                    )
                )
                .scalars()
                .all()
            )
        return attr, version, list(rows)

    @staticmethod
    def _entry(row: G2PListVersionValue) -> Dict[str, Any]:
        return {
            "code": row.value_code,
            "label": row.display,
            "labels": row.display_i18n or None,
            "parent_code": row.parent_value_code,
            "sort_order": row.sort_order,
            "attributes": row.attributes or None,
            "roles": row.roles or None,
            "status": row.status,
        }

    @staticmethod
    def _version_ref(attr, version) -> Dict[str, Any]:
        return {
            "dataset": attr.attribute_code or attr.attribute_id,
            "version": version.version_no,
            "effective_from": iso(version.effective_from),
            "published_at": iso(version.published_at),
        }

    async def get_entries(
        self,
        code: str,
        sel: PublicSelector,
        *,
        parent_code: Optional[str],
        include_retired: bool,
        page: int,
        page_size: int,
    ) -> Tuple[Dict[str, Any], Optional[datetime]]:
        attr, version, rows = await self._version_and_values(code, sel, include_retired=include_retired)
        if parent_code is not None:
            rows = [r for r in rows if (r.parent_value_code or "") == parent_code]
        total = len(rows)
        start = (page - 1) * page_size
        return (
            {
                **self._version_ref(attr, version),
                "total": total,
                "page": page,
                "page_size": page_size,
                "entries": [self._entry(r) for r in rows[start : start + page_size]],
            },
            version.published_at,
        )

    async def get_entry(self, code: str, entry_code: str, sel: PublicSelector):
        attr, version, rows = await self._version_and_values(code, sel, include_retired=True)
        for r in rows:
            if r.value_code == entry_code:
                return {**self._version_ref(attr, version), "entry": self._entry(r)}, version.published_at
        raise PublicNotFound(f"entry {entry_code} not in version {version.version_no} of {code}")

    async def download_json(self, code: str, sel: PublicSelector, include_retired: bool):
        attr, version, rows = await self._version_and_values(code, sel, include_retired=include_retired)
        body = {
            **self._version_ref(attr, version),
            "title": version.display,
            "title_i18n": version.display_i18n or None,
            "entries": [self._entry(r) for r in rows],
        }
        name = f"{attr.attribute_code or attr.attribute_id}-v{version.version_no}.json"
        return json.dumps(body, ensure_ascii=False, default=str).encode(), version.published_at, name

    async def download_csv(self, code: str, sel: PublicSelector, include_retired: bool):
        attr, version, rows = await self._version_and_values(code, sel, include_retired=include_retired)
        langs = sorted({lang for r in rows for lang in (r.display_i18n or {})})
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            ["code", "label", *[f"label_{lang}" for lang in langs], "parent_code", "sort_order", "status"]
            + ["attributes", "roles"]
        )
        for r in rows:
            i18n = r.display_i18n or {}
            w.writerow(
                [r.value_code, r.display or "", *[i18n.get(lang, "") for lang in langs]]
                + [r.parent_value_code or "", "" if r.sort_order is None else r.sort_order, r.status]
                + [
                    json.dumps(r.attributes, ensure_ascii=False) if r.attributes else "",
                    json.dumps(r.roles, ensure_ascii=False) if r.roles else "",
                ]
            )
        name = f"{attr.attribute_code or attr.attribute_id}-v{version.version_no}.csv"
        return buf.getvalue().encode(), version.published_at, name

    async def skos_jsonld(self, code: str, sel: PublicSelector, base: str):
        """SKOS concept scheme of one dataset version: one skos:Concept per active entry."""
        attr, version, rows = await self._version_and_values(code, sel)
        code = attr.attribute_code or attr.attribute_id
        ds = f"{base}/public/datasets/{quote(code, safe='')}"
        scheme_id = f"{ds}/skos"

        def concept_id(c: str) -> str:
            return f"{ds}/entries/{quote(c, safe='')}"

        codes = {r.value_code for r in rows}
        top = [r.value_code for r in rows if not r.parent_value_code or r.parent_value_code not in codes]
        scheme = _compact(
            {
                "@id": scheme_id,
                "@type": "skos:ConceptScheme",
                "skos:prefLabel": _labels(version.display or code, version.display_i18n),
                "dct:title": version.display or code,
                "dct:description": attr.description,
                "dct:identifier": code,
                "skos:notation": code,
                "owl:versionInfo": str(version.version_no),
                "dcat:version": str(version.version_no),
                "dct:issued": _dt(version.published_at),
                "dct:license": _licence_ld(_licence(attr.licence_uri, attr.licence_label)),
                "dct:publisher": (
                    {"@type": "foaf:Agent", "foaf:name": attr.owner_org} if attr.owner_org else None
                ),
                "rdfs:seeAlso": {"@id": ds},
                "skos:hasTopConcept": [{"@id": concept_id(c)} for c in top],
            }
        )
        concepts = []
        for r in rows:
            node = {
                "@id": concept_id(r.value_code),
                "@type": "skos:Concept",
                "skos:notation": r.value_code,
                "skos:prefLabel": _labels(r.display or r.value_code, r.display_i18n),
                "skos:inScheme": {"@id": scheme_id},
            }
            if r.parent_value_code and r.parent_value_code in codes:
                node["skos:broader"] = {"@id": concept_id(r.parent_value_code)}
            else:
                node["skos:topConceptOf"] = {"@id": scheme_id}
            concepts.append(node)
        doc = {"@context": JSONLD_CONTEXT, "@graph": [scheme, *concepts]}
        return doc, version.published_at

    # ------------------------------------------------------------------
    # Geography
    # ------------------------------------------------------------------

    @staticmethod
    async def _geo_settings_public(s) -> GeoSettings:
        settings = await read_geo_settings(s)
        if settings.visibility != PUBLIC:
            raise PublicNotFound("geography not found")
        return settings

    @staticmethod
    async def _geo_published(s) -> List[G2PGeoVersion]:
        return list(
            (
                await s.execute(
                    select(G2PGeoVersion)
                    .where(G2PGeoVersion.status == VersionStatus.PUBLISHED)
                    .order_by(G2PGeoVersion.version_no.desc())
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def _geo_levels(s, version_no: int) -> List[G2PGeoVersionLevel]:
        rows = (
            (await s.execute(select(G2PGeoVersionLevel).where(G2PGeoVersionLevel.version_no == version_no)))
            .scalars()
            .all()
        )
        # Root first, then children (by parent chain), as the authenticated API orders them.
        by_parent: Dict[Optional[str], List[G2PGeoVersionLevel]] = {}
        for lv in rows:
            by_parent.setdefault(lv.parent_level_id, []).append(lv)
        ordered, queue = [], sorted(by_parent.get(None, []), key=lambda x: x.level_id)
        seen = set()
        while queue:
            lv = queue.pop(0)
            if lv.level_id in seen:
                continue
            seen.add(lv.level_id)
            ordered.append(lv)
            queue.extend(sorted(by_parent.get(lv.level_id, []), key=lambda x: x.level_id))
        ordered.extend(sorted((lv for lv in rows if lv.level_id not in seen), key=lambda x: x.level_id))
        return ordered

    @staticmethod
    def _find_level(levels: List[G2PGeoVersionLevel], level: str) -> G2PGeoVersionLevel:
        for lv in levels:
            if lv.level_id == level or lv.level_mnemonic == level:
                return lv
        raise PublicNotFound(f"level not found: {level}")

    async def _geo_context(self, sel: PublicSelector):
        async with get_async_session_maker()() as s:
            settings = await self._geo_settings_public(s)
            versions = await self._geo_published(s)
            version = self._pick(versions, sel, "geography")
            levels = await self._geo_levels(s, version.version_no)
            counts = dict(
                (
                    await s.execute(
                        select(G2PGeoVersionUnit.level_id, func.count())
                        .where(
                            G2PGeoVersionUnit.version_no == version.version_no,
                            G2PGeoVersionUnit.status == ItemStatus.ACTIVE,
                        )
                        .group_by(G2PGeoVersionUnit.level_id)
                    )
                ).all()
            )
        return settings, versions, version, levels, counts

    def _geo_level(self, lv, version, counts, base: str) -> Dict[str, Any]:
        url = f"{base}/public/geography/levels/{quote(lv.level_mnemonic, safe='')}"
        links = {"units": f"{url}/units.csv?version={version.version_no}"}
        if (version.boundary_objects or {}).get(lv.level_mnemonic):
            links["geojson"] = f"{url}/boundaries.geojson?version={version.version_no}"
        return {
            "level": lv.level_mnemonic,
            "level_id": lv.level_id,
            "parent_level_id": lv.parent_level_id,
            "label": lv.display,
            "labels": lv.display_i18n or None,
            "unit_count": counts.get(lv.level_id, 0),
            "links": links,
        }

    def _geography(self, settings, versions, version, levels, counts, base) -> Dict[str, Any]:
        return {
            "title": "Geography",
            "country": version.country or (_config.catalogue_country or None),
            "publisher": version.owner_org,
            "licence": _licence(settings.licence_uri, settings.licence_label),
            "version": version.version_no,
            "effective_from": iso(version.effective_from),
            "issued": iso(min((v.published_at for v in versions if v.published_at), default=None)),
            "modified": iso(version.published_at),
            "levels": [self._geo_level(lv, version, counts, base) for lv in levels],
            "versions": [
                {
                    "version": v.version_no,
                    "effective_from": iso(v.effective_from),
                    "published_at": iso(v.published_at),
                    "change_note": v.change_note,
                }
                for v in versions
            ],
            "links": {
                "self": f"{base}/public/geography",
                "levels": f"{base}/public/geography/levels",
                "units": f"{base}/public/geography/units",
            },
        }

    async def get_geography(self, sel: PublicSelector, base: str):
        settings, versions, version, levels, counts = await self._geo_context(sel)
        return self._geography(settings, versions, version, levels, counts, base), version.published_at

    async def get_geo_levels(self, sel: PublicSelector, base: str):
        _, _, version, levels, counts = await self._geo_context(sel)
        return (
            {
                "version": version.version_no,
                "effective_from": iso(version.effective_from),
                "levels": [self._geo_level(lv, version, counts, base) for lv in levels],
            },
            version.published_at,
        )

    @staticmethod
    def _unit(u: G2PGeoVersionUnit, level: Optional[G2PGeoVersionLevel]) -> Dict[str, Any]:
        return {
            "unit_id": u.unit_id,
            "name": u.name,
            "names": u.name_i18n or None,
            "level": level.level_mnemonic if level else u.level_id,
            "parent_unit_id": u.parent_unit_id,
            "status": u.status,
            "valid_from": iso(u.valid_from),
            "valid_to": iso(u.valid_to),
        }

    async def _units(self, sel, level: Optional[str], parent: Optional[str], include_retired: bool):
        _, _, version, levels, _ = await self._geo_context(sel)
        lv = self._find_level(levels, level) if level else None
        U = G2PGeoVersionUnit
        conds = [U.version_no == version.version_no]
        if lv is not None:
            conds.append(U.level_id == lv.level_id)
        if parent is not None:
            conds.append(U.parent_unit_id == parent if parent else U.parent_unit_id.is_(None))
        if not include_retired:
            conds.append(U.status == ItemStatus.ACTIVE)
        async with get_async_session_maker()() as s:
            rows = (await s.execute(select(U).where(*conds).order_by(U.level_id, U.unit_id))).scalars().all()
        return version, {x.level_id: x for x in levels}, lv, list(rows)

    async def get_geo_units(self, sel, *, level, parent, include_retired, page, page_size):
        version, by_id, _, rows = await self._units(sel, level, parent, include_retired)
        start = (page - 1) * page_size
        return (
            {
                "version": version.version_no,
                "effective_from": iso(version.effective_from),
                "total": len(rows),
                "page": page,
                "page_size": page_size,
                "units": [self._unit(u, by_id.get(u.level_id)) for u in rows[start : start + page_size]],
            },
            version.published_at,
        )

    async def units_csv(self, sel, level: str, include_retired: bool):
        version, by_id, lv, rows = await self._units(sel, level, None, include_retired)
        langs = sorted({lang for u in rows for lang in (u.name_i18n or {})})
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            ["unit_id", "name", *[f"name_{lang}" for lang in langs], "level", "parent_unit_id", "status"]
            + ["valid_from", "valid_to"]
        )
        for u in rows:
            i18n = u.name_i18n or {}
            w.writerow(
                [u.unit_id, u.name, *[i18n.get(lang, "") for lang in langs], lv.level_mnemonic]
                + [u.parent_unit_id or "", u.status, iso(u.valid_from) or "", iso(u.valid_to) or ""]
            )
        name = f"geography-v{version.version_no}-{lv.level_mnemonic}.csv"
        return buf.getvalue().encode(), version.published_at, name

    async def boundary_object(self, sel, level: str) -> Tuple[str, str, G2PGeoVersion, str]:
        """(object key, ETag seed, version, file name) of a public level's boundary GeoJSON."""
        _, _, version, levels, _ = await self._geo_context(sel)
        lv = self._find_level(levels, level)
        key = (version.boundary_objects or {}).get(lv.level_mnemonic)
        if not key:
            raise PublicNotFound(f"no boundary for level {level} in version {version.version_no}")
        checksum = (version.boundary_checksums or {}).get(lv.level_mnemonic)
        seed = f"{key}:{json.dumps(checksum, sort_keys=True, default=str) if checksum else ''}"
        return key, seed, version, f"geography-v{version.version_no}-{lv.level_mnemonic}.geojson"

    # ------------------------------------------------------------------
    # Releases (public members only)
    # ------------------------------------------------------------------

    async def _release_view(self, s, releases, base: str) -> List[Dict[str, Any]]:
        if not releases:
            return []
        geo_public = (await read_geo_settings(s)).visibility == PUBLIC
        codes = [r.release_code for r in releases]
        rows = (
            await s.execute(
                select(G2PCatalogueReleaseMember, G2PAttribute)
                .join(G2PAttribute, G2PAttribute.attribute_id == G2PCatalogueReleaseMember.list_id)
                .where(G2PCatalogueReleaseMember.release_code.in_(codes))
                .order_by(G2PAttribute.attribute_code)
            )
        ).all()
        members: Dict[str, List[Dict[str, Any]]] = {}
        for m, attr in rows:
            if not self._is_public(attr):
                continue
            code = attr.attribute_code or attr.attribute_id
            members.setdefault(m.release_code, []).append(
                {
                    "dataset": code,
                    "version": m.version_no,
                    "links": {
                        "entries": f"{base}/public/datasets/{quote(code, safe='')}/entries?version={m.version_no}"
                    },
                }
            )
        out = []
        for r in releases:
            geo_no = r.geo_version_no if geo_public else None
            ms = members.get(r.release_code, [])
            if not ms and geo_no is None:
                continue  # nothing public in it
            out.append(
                {
                    "code": r.release_code,
                    "title": r.title,
                    "note": r.note,
                    "published_at": iso(r.published_at),
                    "geography_version": geo_no,
                    "members": ms,
                    "links": {"self": f"{base}/public/releases/{quote(r.release_code, safe='')}"},
                }
            )
        return out

    async def list_releases(self, base: str):
        async with get_async_session_maker()() as s:
            releases = (
                (
                    await s.execute(
                        select(G2PCatalogueRelease)
                        .where(G2PCatalogueRelease.status == VersionStatus.PUBLISHED)
                        .order_by(G2PCatalogueRelease.published_at.desc(), G2PCatalogueRelease.release_code)
                    )
                )
                .scalars()
                .all()
            )
            out = await self._release_view(s, list(releases), base)
        modified = max((r.published_at for r in releases if r.published_at), default=None)
        return out, modified

    async def get_release(self, code: str, base: str):
        async with get_async_session_maker()() as s:
            r = await s.get(G2PCatalogueRelease, code)
            if r is None or r.status != VersionStatus.PUBLISHED:
                raise PublicNotFound(f"release not found: {code}")
            out = await self._release_view(s, [r], base)
        if not out:
            raise PublicNotFound(f"release not found: {code}")
        return out[0], r.published_at

    # ------------------------------------------------------------------
    # DCAT catalogue
    # ------------------------------------------------------------------

    @staticmethod
    def _distribution(dist_id: str, title: str, url: str, fmt: str, licence) -> Dict[str, Any]:
        media, eu = FORMATS[fmt]
        return _compact(
            {
                "@id": dist_id,
                "@type": "dcat:Distribution",
                "dct:title": title,
                "dcat:downloadURL": {"@id": url},
                "dcat:accessURL": {"@id": url},
                "dcat:mediaType": {"@id": _IANA + media},
                "dct:format": {"@id": _EU_FILE_TYPE + eu},
                "dct:license": licence,
            }
        )

    async def catalog_jsonld(self, base: str):
        async with get_async_session_maker()() as s:
            lists = await self._public_lists(s)
            geo = None
            settings = await read_geo_settings(s)
            if settings.visibility == PUBLIC:
                versions = await self._geo_published(s)
                current = self._in_effect(versions)
                if current is not None:
                    levels = await self._geo_levels(s, current.version_no)
                    geo = (versions, current, levels)
        catalog_id = f"{base}/public/catalog"
        theme_id = f"{catalog_id}#themes"
        themes = sorted({normalise_domain(a.domain) for a, _, _ in lists if normalise_domain(a.domain)})
        datasets = []
        modified_all: List[datetime] = []
        for attr, versions, cur in lists:
            code = attr.attribute_code or attr.attribute_id
            ds = f"{base}/public/datasets/{quote(code, safe='')}"
            lic = _licence_ld(_licence(attr.licence_uri, attr.licence_label))
            domain = normalise_domain(attr.domain)
            q = f"?version={cur.version_no}"
            issued = min((v.published_at for v in versions if v.published_at), default=None)
            if cur.published_at:
                modified_all.append(cur.published_at)
            datasets.append(
                _compact(
                    {
                        "@id": ds,
                        "@type": "dcat:Dataset",
                        "dct:identifier": code,
                        "dct:title": _labels(cur.display or code, cur.display_i18n) or code,
                        "dct:description": attr.description,
                        "dct:publisher": (
                            {"@type": "foaf:Agent", "foaf:name": attr.owner_org} if attr.owner_org else None
                        ),
                        "dct:license": lic,
                        "dct:issued": _dt(issued),
                        "dct:modified": _dt(cur.published_at),
                        "dcat:theme": {"@id": f"{theme_id}-{quote(domain, safe='')}"} if domain else None,
                        "dcat:keyword": [domain] if domain else None,
                        "dcat:version": str(cur.version_no),
                        "owl:versionInfo": str(cur.version_no),
                        "dcat:landingPage": {"@id": ds},
                        "dcat:distribution": [
                            self._distribution(
                                f"{ds}#csv", f"{code} (CSV)", f"{ds}/download.csv{q}", "csv", lic
                            ),
                            self._distribution(
                                f"{ds}#json", f"{code} (JSON)", f"{ds}/download.json{q}", "json", lic
                            ),
                            self._distribution(
                                f"{ds}#skos", f"{code} (SKOS, JSON-LD)", f"{ds}/skos{q}", "skos", lic
                            ),
                        ],
                    }
                )
            )
        if geo:
            versions, cur, levels = geo
            gid = f"{base}/public/geography"
            lic = _licence_ld(_licence(settings.licence_uri, settings.licence_label))
            q = f"?version={cur.version_no}"
            dists = []
            for lv in levels:
                lurl = f"{gid}/levels/{quote(lv.level_mnemonic, safe='')}"
                dists.append(
                    self._distribution(
                        f"{gid}#{lv.level_mnemonic}-csv",
                        f"{lv.display or lv.level_mnemonic} units (CSV)",
                        f"{lurl}/units.csv{q}",
                        "csv",
                        lic,
                    )
                )
                if (cur.boundary_objects or {}).get(lv.level_mnemonic):
                    dists.append(
                        self._distribution(
                            f"{gid}#{lv.level_mnemonic}-geojson",
                            f"{lv.display or lv.level_mnemonic} boundaries (GeoJSON)",
                            f"{lurl}/boundaries.geojson{q}",
                            "geojson",
                            lic,
                        )
                    )
            if cur.published_at:
                modified_all.append(cur.published_at)
            datasets.append(
                _compact(
                    {
                        "@id": gid,
                        "@type": "dcat:Dataset",
                        "dct:identifier": "geography",
                        "dct:title": "Geography",
                        "dct:description": "Administrative hierarchy (levels and units) and boundaries.",
                        "dct:publisher": (
                            {"@type": "foaf:Agent", "foaf:name": cur.owner_org} if cur.owner_org else None
                        ),
                        "dct:license": lic,
                        "dct:issued": _dt(
                            min((v.published_at for v in versions if v.published_at), default=None)
                        ),
                        "dct:modified": _dt(cur.published_at),
                        "dcat:keyword": ["geography"],
                        "dcat:version": str(cur.version_no),
                        "owl:versionInfo": str(cur.version_no),
                        "dcat:landingPage": {"@id": gid},
                        "dcat:distribution": dists,
                    }
                )
            )
        publisher = (_config.public_catalogue_publisher or _config.catalogue_default_owner_org or "").strip()
        modified = max(modified_all, default=None)
        doc = {
            "@context": JSONLD_CONTEXT,
            **_compact(
                {
                    "@id": catalog_id,
                    "@type": "dcat:Catalog",
                    "dct:title": _config.public_catalogue_title,
                    "dct:description": _config.public_catalogue_description,
                    "dct:publisher": {"@type": "foaf:Agent", "foaf:name": publisher} if publisher else None,
                    "dct:modified": _dt(modified),
                    "foaf:homepage": {"@id": f"{base}/public/datasets"},
                    "dcat:themeTaxonomy": (
                        {
                            "@id": theme_id,
                            "@type": "skos:ConceptScheme",
                            "dct:title": "Themes",
                            "skos:hasTopConcept": [
                                {
                                    "@id": f"{theme_id}-{quote(t, safe='')}",
                                    "@type": "skos:Concept",
                                    "skos:prefLabel": t,
                                    "skos:inScheme": {"@id": theme_id},
                                }
                                for t in themes
                            ],
                        }
                        if themes
                        else None
                    ),
                }
            ),
            "dcat:dataset": datasets,
        }
        return doc, modified
