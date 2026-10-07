"""Anonymous, read-only GET endpoints of the public catalogue: ``/public/...``.

Off unless ``public_catalogue_enabled`` (every route then answers 404), and even
then only datasets / geography an administrator marked ``public``, at their
PUBLISHED versions (see services/g2p_catalogue_public_service.py).

Authentication: none, deliberately. iam-core's middlewares act only on endpoints
marked with ``@require_permissions`` / ``@requires_auth`` — none of these is, and
nothing outside ``/public`` is left unmarked (tests/test_public_catalogue.py
checks every route). CSRF does not apply to GET. PublicCatalogueGuardMiddleware
(path prefix ``/public``) answers 404 while the catalogue is off and enforces a
per-client-IP in-process token bucket (429 with Retry-After). Responses carry an
ETag (304 on If-None-Match), Last-Modified (the version's publication time),
Cache-Control: public and ``Access-Control-Allow-Origin: *`` (no credentials),
so any website or open-data portal can read them.
"""

import hashlib
import inspect
import json
import logging
import threading
import time
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any, Dict, Optional

from fastapi import Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openg2p_fastapi_common.controller import BaseController

from ..config import Settings
from ..helpers.catalogue_integrations import BoundaryStore
from ..services.g2p_catalogue_public_service import (
    G2PCataloguePublicService,
    PublicBadRequest,
    PublicNotFound,
    PublicSelector,
)

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)

TAG = "/public — open catalogue (anonymous, read-only)"
MAX_PAGE_SIZE = 5000


class TokenBucketLimiter:
    """Per-key token bucket: ``rate`` tokens per minute, burst ``rate``. Per process."""

    MAX_KEYS = 10000

    def __init__(self) -> None:
        self._buckets: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def take(self, key: str, rate_per_minute: int) -> float:
        """0 when allowed, else seconds until a token is available."""
        if rate_per_minute <= 0:
            return 0.0
        now = time.monotonic()
        per_second = rate_per_minute / 60.0
        with self._lock:
            tokens, at = self._buckets.get(key, (float(rate_per_minute), now))
            tokens = min(float(rate_per_minute), tokens + (now - at) * per_second)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                allowed = 0.0
            else:
                self._buckets[key] = (tokens, now)
                allowed = (1.0 - tokens) / per_second
            if len(self._buckets) > self.MAX_KEYS:
                # Drop buckets that have refilled completely (idle clients).
                idle = 60.0
                for k in [k for k, (_, t) in self._buckets.items() if now - t > idle]:
                    del self._buckets[k]
        return allowed


LIMITER = TokenBucketLimiter()


def client_ip(request: Request) -> str:
    hops = max(0, int(_config.public_catalogue_trusted_proxy_hops or 0))
    xff = request.headers.get("x-forwarded-for")
    if hops and xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[max(0, len(parts) - hops)]
    return request.client.host if request.client else "unknown"


def base_url(request: Request) -> str:
    configured = (_config.public_base_url or "").strip().rstrip("/")
    if configured:
        return configured
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (
        (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc)
        .split(",")[0]
        .strip()
    )
    return f"{proto}://{host}"


def is_public_path(scope) -> bool:
    path = scope.get("path") or ""
    root = scope.get("root_path") or ""
    if root and path.startswith(root):
        path = path[len(root) :]
    return path == "/public" or path.startswith("/public/")


class PublicCatalogueGuardMiddleware:
    """Path-prefix guard for ``/public``: 404 for everything under it while the
    public catalogue is off (before routing, so a disabled catalogue reveals
    nothing, not even parameter validation), then the per-IP rate limit (429).
    Other paths pass through untouched. Answers directly (no exception), so a
    flood of public 404/429s does not fill the error log; the audit middleware
    outside still records them as anonymous failures."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and is_public_path(scope):
            if not _config.public_catalogue_enabled:
                await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
                return
            if scope.get("method") != "OPTIONS":
                wait = LIMITER.take(
                    client_ip(Request(scope)), int(_config.public_catalogue_rate_limit_per_minute or 0)
                )
                if wait:
                    await JSONResponse(
                        {"detail": "Too Many Requests"},
                        status_code=429,
                        headers={
                            "Retry-After": str(max(1, int(wait + 0.999))),
                            "Access-Control-Allow-Origin": "*",
                        },
                    )(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def _common_headers(last_modified: Optional[datetime]) -> Dict[str, str]:
    headers = {
        "Cache-Control": f"public, max-age={max(0, int(_config.public_catalogue_cache_seconds or 0))}",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "ETag, Last-Modified, Link, Content-Disposition",
        "X-Content-Type-Options": "nosniff",
    }
    if last_modified is not None:
        lm = last_modified if last_modified.tzinfo else last_modified.replace(tzinfo=timezone.utc)
        headers["Last-Modified"] = format_datetime(
            lm.astimezone(timezone.utc).replace(microsecond=0), usegmt=True
        )
    return headers


def _not_modified(request: Request, etag: str, last_modified: Optional[datetime]) -> bool:
    inm = request.headers.get("if-none-match")
    if inm is not None:
        tags = {t.strip() for t in inm.split(",")}
        return "*" in tags or etag in tags or etag.removeprefix("W/") in {t.removeprefix("W/") for t in tags}
    ims = request.headers.get("if-modified-since")
    if ims and last_modified is not None:
        try:
            since = parsedate_to_datetime(ims)
        except (TypeError, ValueError):
            return False
        lm = last_modified if last_modified.tzinfo else last_modified.replace(tzinfo=timezone.utc)
        return lm.replace(microsecond=0) <= since
    return False


def respond(
    request: Request,
    body: bytes,
    media_type: str,
    last_modified: Optional[datetime] = None,
    filename: Optional[str] = None,
    link: Optional[str] = None,
) -> Response:
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    headers = {**_common_headers(last_modified), "ETag": etag}
    if link:
        headers["Link"] = link
    if _not_modified(request, etag, last_modified):
        return Response(status_code=304, headers=headers)
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=body, media_type=media_type, headers=headers)


def as_json(
    request: Request, data: Any, last_modified=None, media_type="application/json", link=None
) -> Response:
    body = json.dumps(data, ensure_ascii=False, default=str).encode()
    return respond(request, body, media_type, last_modified, link=link)


class G2PPublicCatalogueController(BaseController):
    """Anonymous GET endpoints; see the module docstring."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.router.prefix = "/public"
        self.router.tags += [TAG]
        self.svc = G2PCataloguePublicService.get_component()
        self._register()

    def _get(self, path: str, endpoint, summary: str, description: str) -> None:
        async def wrapped(request: Request, **kwargs):
            try:
                return await endpoint(request, **kwargs)
            except PublicNotFound as exc:
                status, message = 404, exc.message
            except PublicBadRequest as exc:
                status, message = 400, exc.message
            return JSONResponse(
                {"detail": message}, status_code=status, headers={"Access-Control-Allow-Origin": "*"}
            )

        # Keep the endpoint's own signature (query/path parameters) for FastAPI.
        wrapped.__signature__ = inspect.signature(endpoint)
        wrapped.__name__ = "public_" + endpoint.__name__
        self.router.add_api_route(
            path,
            wrapped,
            methods=["GET"],
            tags=[TAG],
            summary=summary,
            description=description,
            include_in_schema=bool(_config.public_catalogue_enabled),
            response_class=Response,
        )

    def _register(self) -> None:  # noqa: C901 — one closure per route
        S = self.svc
        VERSION = Query(default=None, description='Published version number or "latest" (default).')
        AS_OF = Query(default=None, description="The published version in effect at this date-time.")

        def sel(version, as_of) -> PublicSelector:
            return PublicSelector.parse(version, as_of)

        def page_args(page: int, page_size: int):
            if page < 1 or page_size < 1 or page_size > MAX_PAGE_SIZE:
                raise PublicBadRequest(f"page >= 1 and 1 <= page_size <= {MAX_PAGE_SIZE}")

        async def catalog(request: Request):
            doc, modified = await S.catalog_jsonld(base_url(request))
            return as_json(request, doc, modified, media_type="application/ld+json")

        self._get(
            "/catalog",
            catalog,
            "DCAT catalogue (JSON-LD)",
            "dcat:Catalog of the public datasets (and the geography when public) as JSON-LD, DCAT-AP style: "
            "dct:title / description / publisher / license / issued / modified, dcat:theme, dcat:version "
            "(and owl:versionInfo), dcat:distribution per format with dcat:downloadURL and dcat:mediaType. "
            "Harvestable by CKAN / DCAT harvesters.",
        )

        async def datasets(request: Request):
            items, modified = await S.list_datasets(base_url(request))
            return as_json(request, {"datasets": items}, modified)

        self._get(
            "/datasets",
            datasets,
            "Public datasets",
            "Every public code list with a published version in effect: code, title, description, theme, "
            "publisher, licence, current version, effective date, issued / modified and links.",
        )

        async def dataset(request: Request, code: str):
            data, modified = await S.get_dataset(code, base_url(request))
            link = f'<{data["links"]["skos"]}>; rel="alternate"; type="application/ld+json"'
            return as_json(request, data, modified, link=link)

        self._get("/datasets/{code}", dataset, "One public dataset", "Metadata plus its published versions.")

        async def entries(
            request: Request,
            code: str,
            version: Optional[str] = VERSION,
            as_of: Optional[datetime] = AS_OF,
            parent_code: Optional[str] = Query(default=None, description='"" for the top level.'),
            include_retired: bool = False,
            page: int = 1,
            page_size: int = 1000,
        ):
            page_args(page, page_size)
            data, modified = await S.get_entries(
                code,
                sel(version, as_of),
                parent_code=parent_code,
                include_retired=include_retired,
                page=page,
                page_size=page_size,
            )
            return as_json(request, data, modified)

        self._get(
            "/datasets/{code}/entries",
            entries,
            "Entries of a public dataset",
            "Entries (code, label, labels per language, parent, attributes, roles, status) of the selected "
            "PUBLISHED version: `version` (number or latest) or `as_of`. Paged with `page` / `page_size`.",
        )

        async def entry(
            request: Request,
            code: str,
            entry_code: str,
            version: Optional[str] = VERSION,
            as_of: Optional[datetime] = AS_OF,
        ):
            data, modified = await S.get_entry(code, entry_code, sel(version, as_of))
            return as_json(request, data, modified)

        self._get(
            "/datasets/{code}/entries/{entry_code:path}",
            entry,
            "One entry of a public dataset",
            "Also the dereferenceable IRI of the entry's skos:Concept.",
        )

        async def download_csv(
            request: Request,
            code: str,
            version: Optional[str] = VERSION,
            as_of: Optional[datetime] = AS_OF,
            include_retired: bool = False,
        ):
            body, modified, name = await S.download_csv(code, sel(version, as_of), include_retired)
            return respond(request, body, "text/csv; charset=utf-8", modified, filename=name)

        self._get("/datasets/{code}/download.csv", download_csv, "Download a version as CSV", "")

        async def download_json(
            request: Request,
            code: str,
            version: Optional[str] = VERSION,
            as_of: Optional[datetime] = AS_OF,
            include_retired: bool = False,
        ):
            body, modified, name = await S.download_json(code, sel(version, as_of), include_retired)
            return respond(request, body, "application/json", modified, filename=name)

        self._get("/datasets/{code}/download.json", download_json, "Download a version as JSON", "")

        async def skos(
            request: Request,
            code: str,
            version: Optional[str] = VERSION,
            as_of: Optional[datetime] = AS_OF,
        ):
            doc, modified = await S.skos_jsonld(code, sel(version, as_of), base_url(request))
            return as_json(request, doc, modified, media_type="application/ld+json")

        self._get(
            "/datasets/{code}/skos",
            skos,
            "SKOS concept scheme (JSON-LD)",
            "skos:ConceptScheme of the selected published version with one skos:Concept per active entry: "
            "skos:notation (code), skos:prefLabel per language, skos:broader (parent), skos:inScheme.",
        )

        async def geography(
            request: Request, version: Optional[str] = VERSION, as_of: Optional[datetime] = AS_OF
        ):
            data, modified = await S.get_geography(sel(version, as_of), base_url(request))
            return as_json(request, data, modified)

        self._get(
            "/geography",
            geography,
            "Public geography",
            "404 unless the geography is public. Country, publisher, licence, version, levels (with unit "
            "counts and download links) and published versions.",
        )

        async def geo_levels(
            request: Request, version: Optional[str] = VERSION, as_of: Optional[datetime] = AS_OF
        ):
            data, modified = await S.get_geo_levels(sel(version, as_of), base_url(request))
            return as_json(request, data, modified)

        self._get("/geography/levels", geo_levels, "Geography levels", "")

        async def geo_units(
            request: Request,
            level: Optional[str] = Query(default=None, description="Level mnemonic or id."),
            parent: Optional[str] = Query(default=None, description='Parent unit id; "" for the root.'),
            version: Optional[str] = VERSION,
            as_of: Optional[datetime] = AS_OF,
            include_retired: bool = False,
            page: int = 1,
            page_size: int = 1000,
        ):
            page_args(page, page_size)
            data, modified = await S.get_geo_units(
                sel(version, as_of),
                level=level,
                parent=parent,
                include_retired=include_retired,
                page=page,
                page_size=page_size,
            )
            return as_json(request, data, modified)

        self._get("/geography/units", geo_units, "Geography units", "Filter by `level` and `parent`; paged.")

        async def units_csv(
            request: Request,
            level: str,
            version: Optional[str] = VERSION,
            as_of: Optional[datetime] = AS_OF,
            include_retired: bool = False,
        ):
            body, modified, name = await S.units_csv(sel(version, as_of), level, include_retired)
            return respond(request, body, "text/csv; charset=utf-8", modified, filename=name)

        self._get("/geography/levels/{level}/units.csv", units_csv, "Units of a level as CSV", "")

        async def boundaries(
            request: Request,
            level: str,
            version: Optional[str] = VERSION,
            as_of: Optional[datetime] = AS_OF,
        ):
            key, seed, v, name = await S.boundary_object(sel(version, as_of), level)
            store = BoundaryStore.get_component()
            if not store.enabled():
                raise PublicNotFound("boundaries are not available")
            # Published boundary objects are immutable (versioned keys): the key
            # and checksum identify the content.
            etag = 'W/"' + hashlib.sha256(seed.encode()).hexdigest()[:32] + '"'
            headers = {
                **_common_headers(v.published_at),
                "ETag": etag,
                "Content-Disposition": f'attachment; filename="{name}"',
            }
            if _not_modified(request, etag, v.published_at):
                return Response(status_code=304, headers=headers)
            try:
                chunks = await store.stream(key)
            except Exception as exc:  # noqa: BLE001 — missing object or store down
                _logger.warning("public boundary %s unavailable: %s", key, exc)
                raise PublicNotFound("boundary not available") from None
            return StreamingResponse(chunks, media_type="application/geo+json", headers=headers)

        self._get(
            "/geography/levels/{level}/boundaries.geojson",
            boundaries,
            "Boundaries of a level (GeoJSON)",
            "Streamed from the boundary object store (immutable per version).",
        )

        async def releases(request: Request):
            items, modified = await S.list_releases(base_url(request))
            return as_json(request, {"releases": items}, modified)

        self._get(
            "/releases",
            releases,
            "Published releases",
            "Published catalogue releases, each with only its public members (and the geography version when "
            "the geography is public); a release with nothing public is not listed.",
        )

        async def release(request: Request, code: str):
            data, modified = await S.get_release(code, base_url(request))
            return as_json(request, data, modified)

        self._get("/releases/{code}", release, "One published release", "Public members only.")
