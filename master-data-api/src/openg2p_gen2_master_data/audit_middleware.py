"""
Audit middleware — emits one CloudEvent to OpenG2P Audit Manager per
audited API call.

Mirrors the pattern of `iam_core.user_auth.middleware.ResolvePermissionMiddleware`:

  * Registered AFTER ResolvePermissionMiddleware in main.py → becomes the OUTERMOST
    middleware. Request flow: AuditMiddleware → ResolvePermissionMiddleware → handler →
    response → ResolvePermissionMiddleware → AuditMiddleware. By the time we read
    request.state.auth and the response status, both are populated.

Audit policy (v2):

  Request kind                                              | Audited?
  --------------------------------------------------------- | --------
  Authenticated (request.state.auth set), any outcome       | YES
  Anonymous + outcome 2xx (legitimate public endpoint)      | NO
  Anonymous + outcome non-2xx, audit_anonymous_failures=true| YES (anon)
  Health probes / OpenAPI surfaces / OPTIONS preflight      | NO
  Service caller (request.state.audit_actor set), any outcome| YES

Server-to-server endpoints that authenticate without a JWT (e.g. the AWE
decision webhook, HMAC-signed) set `request.state.audit_actor` to a service
actor dict once the caller is verified, so their successful calls are
audited too.

For 403 (Forbidden) responses the JWT was definitely valid (ResolvePermissionMiddleware
validated it before raising the perms error), so we decode the bearer
token to recover the real actor — even though `request.state.auth` is
not set on that path. For 401 (Unauthorized) responses the JWT may be
invalid/missing/expired, so we record the call as anonymous (only the
client IP is trustworthy).

Emission is fire-and-forget via `asyncio.create_task` — never delays the
response. All errors are logged, never raised to the caller.

Disabled by default: set REGISTRY_STAFF_PORTAL_API_AUDIT_ENABLED=true
AND REGISTRY_STAFF_PORTAL_API_AUDIT_MANAGER_URL=<base-url> to turn on.
Set REGISTRY_STAFF_PORTAL_API_AUDIT_ANONYMOUS_FAILURES=false to skip
auditing of rejected anonymous calls.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from .config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


_SKIP_PATHS = frozenset(
    {
        "/ping",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/docs/oauth2-redirect",
    }
)


def _status_to_outcome(status_code: int) -> str:
    """Map HTTP status to CloudEvents outcome enum."""
    # 304 Not Modified: a conditional GET (e.g. the public catalogue's ETags) succeeded.
    if 200 <= status_code < 300 or status_code == 304:
        return "success"
    if status_code in (401, 403):
        return "denied"
    return "failure"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _decode_jwt_payload(token: str) -> dict | None:
    """Base64url-decode a JWT's payload segment WITHOUT verifying the signature.

    Safe to use only on tokens we know were validated by an upstream
    middleware (e.g. ResolvePermissionMiddleware confirms signature validity before
    raising 403). For untrusted tokens (401 path), do NOT trust the
    decoded claims — record the request as anonymous instead.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None


def _extract_bearer(request: Request) -> str | None:
    """Pull the bearer token from the Authorization header, or None."""
    auth = request.headers.get("authorization", "")
    parts = auth.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _client_ip(request: Request) -> str | None:
    """Real client IP — prefer the first hop in `X-Forwarded-For` so audits
    behind Istio / a load balancer record the actual user, not the proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else None


class AuditMiddleware(BaseHTTPMiddleware):
    """Emit one CloudEvent to Audit Manager per audited API call."""

    def __init__(
        self,
        app,
        *,
        audit_manager_url: str | None,
        enabled: bool = True,
        timeout_seconds: float = 2.0,
        source: str = "/openg2p/master-data-api",
        module: str = "master-data-api",
        type_prefix: str = "org.openg2p.master_data_api",
        client_id: str | None = None,
        state_key: str = "auth",
        audit_anonymous_failures: bool = True,
    ):
        super().__init__(app)
        self._type_prefix = type_prefix.rstrip(".")
        self._url = (audit_manager_url or "").rstrip("/")
        self._enabled = enabled and bool(self._url)
        self._timeout_seconds = timeout_seconds
        self._source = source
        self._module = module
        self._client_id = client_id
        self._state_key = state_key
        self._audit_anonymous_failures = audit_anonymous_failures
        self._client: httpx.AsyncClient | None = None
        # Strong references to in-flight emissions: the event loop keeps only
        # weak references to tasks, so an unreferenced task can be collected
        # before it runs.
        self._tasks: set[asyncio.Task] = set()

        if self._enabled:
            _logger.info(
                "AuditMiddleware enabled — emitting to %s " "(audit_anonymous_failures=%s)",
                self._url + "/v1/auditmanager/events",
                self._audit_anonymous_failures,
            )
        else:
            _logger.info(
                "AuditMiddleware disabled (enabled=%s, url=%r). No-op.",
                enabled,
                audit_manager_url,
            )

    def _get_client(self) -> httpx.AsyncClient:
        # Lazy-create on first emit so import time is unaffected.
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds),
            )
        return self._client

    def _match_route(self, request: Request) -> Any | None:
        """The route FastAPI matched for this request.

        Routing records it in the request scope while the request is handled
        (``scope["route"]``). Re-matching ``app.router.routes`` is only a
        fallback: since FastAPI wraps each included router (``_IncludedRouter``),
        the first full match there is the wrapper, which has no endpoint.
        """
        route = request.scope.get("route")
        if getattr(route, "endpoint", None) is not None:
            return route
        router = getattr(request.app, "router", None)
        for route in getattr(router, "routes", []):
            try:
                match, _ = route.matches(request.scope)
            except Exception:  # a route type that cannot match this scope
                continue
            if match == Match.FULL and getattr(route, "endpoint", None) is not None:
                return route
        return None

    # ---------- audit decision ----------

    async def dispatch(self, request: Request, call_next):
        # Always run the inner stack first — never delay the user's response.
        # If the inner stack raises (e.g. JWKS fetch fails, DB error,
        # unhandled exception in a handler), we still emit an audit event
        # marked as a 5xx failure before re-raising — this is exactly the
        # kind of incident operators want recorded.
        response = None
        raised: BaseException | None = None
        try:
            response = await call_next(request)
        except BaseException as exc:  # noqa: BLE001 — we re-raise below
            raised = exc

        # Skip-list checks apply to both success and failure paths.
        if self._enabled and request.method != "OPTIONS" and request.url.path not in _SKIP_PATHS:
            self._maybe_emit(request, response, raised)

        if raised is not None:
            raise raised
        return response

    def _maybe_emit(self, request: Request, response, raised) -> None:
        """Decide whether to emit, build the event, fire-and-forget."""
        principal = getattr(request.state, self._state_key, None)
        service_actor = getattr(request.state, "audit_actor", None)
        if not isinstance(service_actor, dict):
            service_actor = None

        # If the inner stack raised, treat this as outcome=failure / 500.
        # The actor may still be available (auth ran successfully and a
        # later layer crashed) or may be missing (auth itself crashed,
        # e.g. JWKS unreachable).
        if raised is not None:
            status_code = 500
            is_success = False
        else:
            status_code = response.status_code
            is_success = 200 <= status_code < 300 or status_code == 304

        # Audit decision
        if principal is not None or service_actor is not None:
            pass  # authenticated (user or verified service caller) — always audit
        elif (not is_success) and self._audit_anonymous_failures:
            pass  # rejected anonymous — audit per v2 policy
        else:
            return  # successful anonymous — skip

        try:
            route = self._match_route(request)
            actor = (
                self._build_actor(request, principal, response, status_code)
                if principal is not None or service_actor is None
                else {**service_actor, "ip": service_actor.get("ip") or _client_ip(request)}
            )
            event = self._build_event(request, response, status_code, actor, route, raised)
            task = asyncio.create_task(self._emit(event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except Exception:
            _logger.exception("AuditMiddleware: failed to build event; skipping")

    # ---------- actor construction ----------

    def _build_actor(self, request: Request, principal, response, status_code: int) -> dict:
        """Produce the `data.actor` payload from the best available identity source.

        Three paths, in order of preference:
          1. AuthPrincipal (request.state.auth set) — name, sub, roles.
             Try to enrich with `username` and `session_id` from JWT claims
             since AuthPrincipal doesn't carry them.
          2. 403 Forbidden + bearer token — JWT is known-valid (ResolvePermissionMiddleware
             verified it before raising), so decode is trustworthy.
          3. Anonymous fallback — actor.type=anonymous, only IP is recorded.

        `response` may be None if the inner stack raised an exception
        before producing a response — in that case status_code=500 is
        passed in and we fall through to either the principal path (if
        auth completed before the crash) or anonymous fallback.
        """
        ip = _client_ip(request)
        bearer = _extract_bearer(request)

        if principal is not None:
            roles: list[str] = []
            if self._client_id and principal.client_roles:
                roles = list(principal.client_roles.get(self._client_id, []))
            # Enrich from JWT claims (AuthPrincipal lacks preferred_username
            # and session_state).
            username = None
            session_id = None
            if bearer:
                claims = _decode_jwt_payload(bearer)
                if claims:
                    username = claims.get("preferred_username")
                    session_id = claims.get("session_state") or claims.get("sid")
            return {
                "type": "user",
                "id": principal.sub or "",
                "name": principal.name,
                "username": username,
                "roles": roles,
                "ip": ip,
                "session_id": session_id,
            }

        if status_code == 403 and bearer:
            # ResolvePermissionMiddleware confirmed signature validity before raising.
            # We can trust the decoded claims.
            claims = _decode_jwt_payload(bearer)
            if claims:
                roles = []
                if self._client_id:
                    roles = list(claims.get("resource_access", {}).get(self._client_id, {}).get("roles", []))
                return {
                    "type": "user",
                    "id": claims.get("sub") or "unknown",
                    "name": claims.get("name"),
                    "username": claims.get("preferred_username"),
                    "roles": roles,
                    "ip": ip,
                    "session_id": claims.get("session_state") or claims.get("sid"),
                }

        # Anonymous fallback — token absent, malformed, or unverified, or
        # the inner stack crashed before auth populated state.auth.
        return {
            "type": "anonymous",
            "id": "anonymous",
            "ip": ip,
        }

    # ---------- event construction ----------

    def _build_event(
        self,
        request: Request,
        response,
        status_code: int,
        actor: dict,
        route,
        raised: BaseException | None,
    ) -> dict:
        # Endpoint function name → CloudEvents `type` and `action` derivation.
        func_name = "unknown"
        if route is not None and getattr(route, "endpoint", None) is not None:
            func_name = route.endpoint.__name__

        # First word of the function name as the action verb (best effort).
        action = func_name.split("_", 1)[0] if "_" in func_name else func_name

        # Build context, plus a `reason` when the inner stack raised.
        context: dict = {
            "api": f"{request.method} {request.url.path}",
            "module": self._module,
            "http_status": status_code,
            "request_id": request.headers.get("x-request-id"),
        }
        data: dict = {
            "actor": actor,
            "action": action,
            "outcome": _status_to_outcome(status_code),
            "context": context,
        }
        if raised is not None:
            # Capture exception class + truncated message into reason so
            # ops can grep for "JWKS" / "Connection refused" / etc. without
            # leaking full stack traces into the audit store.
            data["reason"] = f"{type(raised).__name__}: {str(raised)[:200]}"

        return {
            "specversion": "1.0",
            "id": str(uuid4()),
            "source": self._source,
            "type": f"{self._type_prefix}.{func_name}",
            "time": _now_iso(),
            "datacontenttype": "application/json",
            "data": data,
        }

    # ---------- emission ----------

    async def _emit(self, event: dict) -> None:
        """POST a single CloudEvent. Errors logged, never raised."""
        try:
            client = self._get_client()
            url = f"{self._url}/v1/auditmanager/events"
            resp = await client.post(url, json=event)
            if resp.status_code != 202:
                _logger.warning(
                    "Audit Manager returned %s for event %s: %s",
                    resp.status_code,
                    event["id"],
                    resp.text[:200],
                )
        except httpx.HTTPError as exc:
            _logger.warning("Audit emission failed for event %s: %s", event["id"], exc)
        except Exception:
            _logger.exception(
                "Audit emission failed unexpectedly for event %s",
                event.get("id"),
            )
