"""Outbound integrations of the catalogue: Audit Manager, WebSub, AWE, boundary store.

Each one is optional and off when its URL is empty. Audit and WebSub never fail
a request: the local change log (written in the request's transaction) is the
system of record and the outbox — services/catalogue_outbox.py delivers its
rows through the helpers below and retries what did not get through.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from openg2p_fastapi_common.service import BaseService

from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)

# Keep references to background tasks so they are not garbage-collected mid-flight.
_background: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()
        return
    _background.add(task)
    task.add_done_callback(_background.discard)


def spawn_background(coro) -> None:
    """Run ``coro`` fire-and-forget (kept referenced until done)."""
    _spawn(coro)


async def drain_background_tasks(timeout: float = 5.0) -> None:
    """Wait for pending fire-and-forget calls (used by tests and on shutdown)."""
    if _background:
        await asyncio.wait(list(_background), timeout=timeout)


def _delivered(status_code: int) -> bool:
    """True when the receiver has the event or will never take it.

    2xx: delivered. 4xx other than 408/429: the receiver rejects this event for
    good, so retrying would only block the outbox behind it (it is logged).
    Anything else (5xx, 408, 429, network errors) is retried later.
    """
    if 200 <= status_code < 300:
        return True
    return 400 <= status_code < 500 and status_code not in (408, 429)


_SYSTEM_ACTORS = {"system", "migration"}


# ---------------------------------------------------------------------------
# Audit Manager
# ---------------------------------------------------------------------------


class CatalogueAuditHelper(BaseService):
    """Sends catalogue lifecycle events to the Audit Manager as CloudEvents 1.0.

    POST {audit_manager_url}/v1/auditmanager/events. Off when the URL is empty.
    The CloudEvent ``id`` is derived from the change-log event id, so a retried
    delivery carries the same id and the receiver can de-duplicate.
    """

    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    @staticmethod
    def enabled() -> bool:
        return bool((_config.audit_manager_url or "").strip())

    @staticmethod
    def build_event(change: Dict[str, Any]) -> Dict[str, Any]:
        subject_type = change.get("subject_type") or "catalogue"
        subject_id = change.get("subject_id")
        version_no = change.get("version_no")
        resource: Dict[str, Any] = {"type": f"master_data.{subject_type}", "id": subject_id}
        if version_no is not None:
            resource["version_no"] = version_no
        actor = change.get("actor") or "system"
        actor_name = change.get("actor_name")
        # A user acting through the API always has a display name; the database
        # (migration, effective dates) and the country-pack loader do not.
        is_user = bool(actor_name) and actor not in _SYSTEM_ACTORS
        at = change.get("at")
        if isinstance(at, datetime):
            at = (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).isoformat()
        event_id = change.get("event_id")
        return {
            "specversion": "1.0",
            "id": (
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"{_config.audit_source}#{event_id}"))
                if event_id is not None
                else str(uuid.uuid4())
            ),
            "source": _config.audit_source,
            "type": f"org.openg2p.master_data.{change['event_type']}",
            "subject": f"{subject_type}/{subject_id}" + (f"/v{version_no}" if version_no is not None else ""),
            "time": at or datetime.now(timezone.utc).isoformat(),
            "datacontenttype": "application/json",
            "data": {
                "actor": {
                    "type": "user" if is_user else "system",
                    "id": actor,
                    **({"name": actor_name} if is_user else {}),
                },
                "action": change["event_type"],
                "outcome": "success",
                "resource": resource,
                "context": {
                    "module": "master-data-catalogue",
                    "change_log_event_id": event_id,
                },
                "details": change.get("details") or {},
            },
        }

    async def send(self, client: httpx.AsyncClient, change: Dict[str, Any]) -> bool:
        """Deliver one change-log event; True when it need not be retried."""
        url = (_config.audit_manager_url or "").strip().rstrip("/")
        if not url:
            return True
        event = self.build_event(change)
        try:
            resp = await client.post(
                f"{url}/v1/auditmanager/events", json=event, timeout=_config.audit_timeout_seconds
            )
        except httpx.HTTPError as exc:
            _logger.warning("Audit emission failed for %s: %s (will retry)", event["type"], exc)
            return False
        if resp.status_code not in (200, 201, 202):
            _logger.warning(
                "Audit Manager returned %s for %s: %s", resp.status_code, event["type"], resp.text[:200]
            )
        return _delivered(resp.status_code)


# ---------------------------------------------------------------------------
# WebSub
# ---------------------------------------------------------------------------


class CatalogueWebSubHelper(BaseService):
    """Publishes version notifications to a WebSub hub.

    Topics: ``<prefix>.list.published``, ``<prefix>.geo.published``,
    ``<prefix>.release.published`` (a version / release was published) and
    ``<prefix>.list.effective``, ``<prefix>.geo.effective`` (a future-effective
    version became the one in effect). A topic is registered on first use. Same
    form-encoded hub protocol as the registry platform's WebsubHelper.
    """

    def __init__(self, name: str = "") -> None:
        super().__init__(name)
        self._registered: set[str] = set()

    @staticmethod
    def enabled() -> bool:
        return bool((_config.websub_hub_url or "").strip())

    @staticmethod
    def topic_for(subject_type: str, kind: str = "published") -> str:
        return f"{_config.websub_topic_prefix}.{subject_type}.{kind}"

    async def send(self, client: httpx.AsyncClient, topic: str, payload: Dict[str, Any]) -> bool:
        """Publish one notification; True when it need not be retried."""
        hub = (_config.websub_hub_url or "").strip().rstrip("/")
        if not hub:
            return True
        url = hub if hub.endswith("/hub") or hub.endswith("/hub/") else f"{hub}/hub/"
        try:
            if topic not in self._registered:
                resp = await client.post(url, data={"hub.mode": "register", "hub.topic": topic})
                if resp.is_success:
                    self._registered.add(topic)
                else:
                    _logger.warning("WebSub register %s returned %s", topic, resp.status_code)
            resp = await client.post(
                url,
                data={
                    "hub.mode": "publish",
                    "hub.topic": topic,
                    "hub.content": json.dumps(payload, default=str),
                },
            )
        except httpx.HTTPError as exc:
            _logger.warning("WebSub publish %s failed: %s (will retry)", topic, exc)
            return False
        if not resp.is_success:
            _logger.warning("WebSub publish %s returned %s: %s", topic, resp.status_code, resp.text[:200])
        return _delivered(resp.status_code)


# ---------------------------------------------------------------------------
# AWE
# ---------------------------------------------------------------------------


class AweClientError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(f"[{error_code}] {message} (HTTP {status_code})")


class AweWebhookSignatureError(Exception):
    pass


def normalize_awe_base_url(url: str) -> str:
    """Host root only — ``/v1/awe/...`` is appended by the client."""
    normalized = (url or "").strip().rstrip("/")
    if normalized.endswith("/v1/awe"):
        normalized = normalized[: -len("/v1/awe")]
    return normalized.rstrip("/")


def awe_enabled() -> bool:
    return approval_mode() == "awe"


def approval_mode() -> str:
    """Effective approval mode. ``awe`` without a base URL falls back to ``permission``."""
    mode = (_config.catalogue_approval_mode or "permission").strip().lower()
    if mode == "awe" and not normalize_awe_base_url(_config.awe_base_url):
        _logger.warning("catalogue_approval_mode=awe but awe_base_url is empty; using permission mode")
        return "permission"
    return "awe" if mode == "awe" else "permission"


def verify_awe_webhook_signature(
    *,
    secret: str,
    body: bytes,
    signature_header: Optional[str],
    timestamp_header: Optional[str],
    tolerance_seconds: int = 300,
) -> None:
    """``X-Approval-Signature = sha256=HMAC_SHA256(secret, "<ts>." + body)`` (AWE's scheme)."""
    if not secret:
        raise AweWebhookSignatureError("AWE webhook HMAC secret is not configured")
    if not signature_header or not signature_header.startswith("sha256="):
        raise AweWebhookSignatureError("Missing or invalid X-Approval-Signature header")
    if not timestamp_header:
        raise AweWebhookSignatureError("Missing X-Approval-Timestamp header")
    try:
        timestamp = int(timestamp_header)
    except ValueError as exc:
        raise AweWebhookSignatureError("Invalid X-Approval-Timestamp header") from exc
    if abs(int(time.time()) - timestamp) > tolerance_seconds:
        raise AweWebhookSignatureError("Webhook timestamp outside allowed skew window")
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header.removeprefix("sha256=")):
        raise AweWebhookSignatureError("Webhook signature mismatch")


def sign_awe_webhook(secret: str, timestamp: int, body: bytes) -> str:
    """The counterpart of the check above (AWE signs this way; used by tests)."""
    return "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


class CatalogueAweHelper(BaseService):
    """Minimal async AWE client: create and cancel approval requests.

    Mirrors registry-platform's ``AweHelper``: the caller's bearer token is
    forwarded, the request carries a callback URL and the id of the HMAC secret
    AWE signs deliveries with, and an Idempotency-Key per draft.
    """

    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    def _client(self, token: str, extra: Optional[Dict[str, str]] = None) -> httpx.AsyncClient:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return httpx.AsyncClient(
            base_url=normalize_awe_base_url(_config.awe_base_url),
            headers=headers,
            timeout=_config.awe_http_timeout_seconds,
        )

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            body = response.json()
            code = body.get("errorCode", "AWE-UNKNOWN")
            message = body.get("message") or body.get("detail") or response.text
        except Exception:
            code, message = "AWE-UNKNOWN", response.text
        raise AweClientError(response.status_code, code, str(message))

    async def create_request(
        self,
        token: str,
        *,
        policy_key: str,
        artifact_type: str,
        artifact_id: str,
        context: Optional[Dict[str, Any]] = None,
        requester: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "policy_key": policy_key,
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "context": context or {},
        }
        if _config.awe_callback_url:
            payload["callback_url"] = _config.awe_callback_url
        if _config.awe_callback_secret_id:
            payload["callback_secret_id"] = _config.awe_callback_secret_id
        if requester:
            payload["requester"] = requester
        extra = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        async with self._client(token, extra) as client:
            response = await client.post("/v1/awe/requests", json=payload)
        self._raise_for_error(response)
        return response.json()

    async def cancel_request(self, token: str, request_id: str, reason: Optional[str] = None) -> None:
        async with self._client(token) as client:
            response = await client.post(f"/v1/awe/requests/{request_id}/cancel", json={"reason": reason})
        self._raise_for_error(response)


# ---------------------------------------------------------------------------
# Boundary object store (S3 / MinIO)
# ---------------------------------------------------------------------------


def boundary_object_key(country: str, version_no: int, level: str) -> str:
    """Immutable, versioned key: ``geo/<country>/v<version>/<level>.geojson``."""
    return f"geo/{country}/v{version_no}/{level}.geojson"


class BoundaryStore(BaseService):
    """S3/MinIO access for boundary GeoJSON. All calls run in a thread (boto3 is sync)."""

    def __init__(self, name: str = "") -> None:
        super().__init__(name)
        self._s3 = None

    @staticmethod
    def enabled() -> bool:
        return bool((_config.boundary_s3_endpoint or "").strip())

    def _client(self):
        if self._s3 is None:
            import boto3  # optional dependency, imported only when configured

            self._s3 = boto3.client(
                "s3",
                endpoint_url=_config.boundary_s3_endpoint,
                aws_access_key_id=_config.boundary_s3_access_key or None,
                aws_secret_access_key=_config.boundary_s3_secret_key or None,
                region_name=_config.boundary_s3_region,
            )
        return self._s3

    def public_url(self, key: Optional[str]) -> Optional[str]:
        if not key:
            return None
        base = (_config.boundary_public_base_url or "").strip().rstrip("/")
        return f"{base}/{_config.boundary_s3_bucket}/{key}" if base else None

    async def presigned_url(self, key: str) -> Optional[str]:
        if not self.enabled() or not key:
            return None

        def _sign():
            return self._client().generate_presigned_url(
                "get_object",
                Params={"Bucket": _config.boundary_s3_bucket, "Key": key},
                ExpiresIn=_config.boundary_presign_seconds,
            )

        try:
            return await asyncio.to_thread(_sign)
        except Exception as exc:
            _logger.warning("Could not presign %s: %s", key, exc)
            return None

    async def put(self, key: str, body: bytes, content_type: str = "application/geo+json") -> None:
        def _put():
            s3 = self._client()
            try:
                s3.head_bucket(Bucket=_config.boundary_s3_bucket)
            except Exception:
                s3.create_bucket(Bucket=_config.boundary_s3_bucket)
            s3.put_object(Bucket=_config.boundary_s3_bucket, Key=key, Body=body, ContentType=content_type)

        await asyncio.to_thread(_put)

    async def get(self, key: str) -> bytes:
        def _get():
            obj = self._client().get_object(Bucket=_config.boundary_s3_bucket, Key=key)
            return obj["Body"].read()

        return await asyncio.to_thread(_get)
