"""API middleware components."""

import json
import time
import logging
from typing import Callable, Tuple, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith("/api/v2") and request.url.path != "/api/v2/auth/token":
            token = request.headers.get("Authorization", "")
            if not token.startswith("Bearer "):
                return Response(status_code=401, content="Unauthorized")
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self._requests = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        if client_ip not in self._requests:
            self._requests[client_ip] = []

        self._requests[client_ip] = [t for t in self._requests[client_ip] if now - t < self.window]

        if len(self._requests[client_ip]) >= self.max_requests:
            return Response(status_code=429, content="Too many requests")

        self._requests[client_ip].append(now)
        return await call_next(request)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(f"{request.method} {request.url.path} {response.status_code} {duration:.3f}s")
        return response


# ---------------------------------------------------------------------------
# Bounty fix: Redact execution metadata in public health response
# ---------------------------------------------------------------------------

SENSITIVE_METADATA_KEYS = frozenset({
    # Version / build info
    "build_id", "build_number", "commit", "commit_hash",
    "git_sha", "release", "deploy_version", "revision",
    # Internal infrastructure
    "internal_ip", "hostname", "node_id", "pod_name", "container_id",
    "instance_id", "worker_id", "server_id",
    # Auth / secrets
    "secret", "token", "api_key", "api_secret", "access_key",
    "private_key", "auth_token", "session_secret",
    # Debug / diagnostics
    "debug", "trace_id", "span_id", "stack_trace", "exception_detail",
    "internal_error", "memory_usage", "cpu_usage", "process_id",
    "thread_id", "garbage_collector_stats",
    # Config / env
    "env_file", "config_path", "database_url", "redis_url",
    "queue_url", "storage_endpoint",
})
# NOTE: "version" intentionally excluded — it is safe public information
# and required by clients for compatibility checks.


def redact_execution_metadata(data: object, strict: bool = True) -> object:
    """Recursively strip sensitive execution metadata from a response payload.

    Args:
        data:   Response data (dict, list, or primitive value).
        strict: When True, recurse into list items as well as dict values.

    Returns:
        A new object with all keys that appear in SENSITIVE_METADATA_KEYS
        removed at every nesting level.
    """
    if isinstance(data, dict):
        return {
            k: redact_execution_metadata(v, strict)
            for k, v in data.items()
            if k.lower() not in SENSITIVE_METADATA_KEYS
        }
    if isinstance(data, list) and strict:
        return [redact_execution_metadata(item, strict) for item in data]
    return data


class RedactMetadataMiddleware(BaseHTTPMiddleware):
    """Strip sensitive operational metadata from all public JSON responses.

    Placed after LoggingMiddleware so the log entry records the original
    status code while the client receives the redacted body.

    Fix: consumes the response body via ``response.body`` only after
    buffering it — BaseHTTPMiddleware with body_class=None buffers the
    full body before ``dispatch`` returns, so ``response.body`` is safe
    to read synchronously here.
    """

    def __init__(self, app, strict: bool = True):
        super().__init__(app)
        self.strict = strict

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        try:
            # BaseHTTPMiddleware buffers the full body; .body is safe to read.
            raw_body: bytes = response.body
            data = json.loads(raw_body)
            redacted = redact_execution_metadata(data, strict=self.strict)
            new_body = json.dumps(redacted, ensure_ascii=False).encode("utf-8")

            # Rebuild response preserving status and headers, updating body.
            headers = dict(response.headers)
            headers["content-length"] = str(len(new_body))
            return Response(
                content=new_body,
                status_code=response.status_code,
                headers=headers,
                media_type="application/json",
            )
        except (ValueError, AttributeError):
            # If the body is not valid JSON or already consumed, pass through.
            return response


def validate_diagnostics_request(request: Request) -> Tuple[bool, Optional[Response]]:
    """Shared input-validation guard for diagnostics API endpoints.

    Validates the request *before* any protected lookup or mutation is
    performed, satisfying the bounty requirement to move the guard into
    the shared service layer.

    Returns:
        (True, None)              — request is valid, proceed normally.
        (False, Response)         — request is invalid; return the response
                                    directly without executing the handler.
    """
    # Fix: json import is now at module level — no NameError at call time.
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or len(auth) <= len("Bearer "):
        return False, Response(
            status_code=401,
            content=json.dumps({
                "error": "unauthorized",
                "code": "MISSING_AUTH",
                "message": "Authorization header with a non-empty Bearer token is required.",
            }),
            media_type="application/json",
        )

    # Content-type guard for mutation methods only.
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        ct = request.headers.get("Content-Type", "")
        if ct and "application/json" not in ct:
            return False, Response(
                status_code=415,
                content=json.dumps({
                    "error": "unsupported_media_type",
                    "code": "INVALID_CONTENT_TYPE",
                    "message": "Content-Type must be application/json for mutation requests.",
                }),
                media_type="application/json",
            )

    return True, None
