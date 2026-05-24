"""
Tests for: Redact execution metadata in public health response — diagnostics API.

Covers authorized, unauthorized, and malformed requests as required by the
bounty acceptance criteria.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app


@pytest.fixture
def client():
    """Fresh app instance per test module — no shared state."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


AUTH_HEADER = {"Authorization": "Bearer test-token-12345"}


# ---------------------------------------------------------------------------
# GET /health — public liveness endpoint (no auth required)
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """GET /health must be reachable without authentication."""

    def test_health_no_auth_returns_200(self, client):
        """/health is public — missing Authorization must not return 401."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_with_auth_returns_200(self, client):
        """Authenticated requests also succeed."""
        resp = client.get("/health", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_response_contains_version(self, client):
        """'version' is safe public information and must be present."""
        # Fix: 'version' was incorrectly in SENSITIVE_METADATA_KEYS in the
        # original submission. It has been removed from the redaction set.
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "version" in resp.json()

    def test_health_does_not_expose_sensitive_keys(self, client):
        """Sensitive operational fields must not appear in /health response."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        sensitive = {
            "build_id", "commit", "commit_hash", "git_sha",
            "hostname", "internal_ip", "pod_name", "container_id",
            "secret", "token", "api_key", "api_secret",
            "database_url", "redis_url",
        }
        leaked = sensitive & data.keys()
        assert not leaked, f"Sensitive keys leaked in /health response: {leaked}"


# ---------------------------------------------------------------------------
# GET /api/v2/diagnostics/health — internal endpoint, auth required
# ---------------------------------------------------------------------------

class TestDiagnosticsHealthEndpoint:
    """Diagnostics endpoint enforces auth via shared guard — returns
    deterministic 4xx without performing any lookup when invalid."""

    def test_diagnostics_authorized_returns_200(self, client):
        """Valid Bearer token → 200 with operational status."""
        resp = client.get("/api/v2/diagnostics/health", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["status"] == "operational"

    def test_diagnostics_no_auth_returns_401(self, client):
        """Missing Authorization header → 401 before any lookup.

        Note: /api/v2/* routes are intercepted first by AuthMiddleware, which
        returns a plain-text 401. The route handler (and its JSON guard) is
        never reached. Both layers enforce the auth requirement.
        """
        resp = client.get("/api/v2/diagnostics/health")
        assert resp.status_code == 401

    def test_diagnostics_malformed_auth_returns_401(self, client):
        """Non-Bearer scheme → 401. AuthMiddleware intercepts before handler."""
        resp = client.get(
            "/api/v2/diagnostics/health",
            headers={"Authorization": "Token xyz"},
        )
        assert resp.status_code == 401

    def test_diagnostics_bearer_only_prefix_returns_401(self, client):
        """'Bearer ' with no token value → 401 (empty token is invalid)."""
        resp = client.get(
            "/api/v2/diagnostics/health",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401

    def test_diagnostics_does_not_expose_sensitive_keys(self, client):
        """Diagnostics response must not expose infrastructure metadata."""
        resp = client.get("/api/v2/diagnostics/health", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        sensitive = {
            "hostname", "internal_ip", "build_id", "commit",
            "python_version", "platform", "process_id",
        }
        leaked = sensitive & data.keys()
        assert not leaked, f"Sensitive keys leaked in diagnostics response: {leaked}"

    def test_diagnostics_post_returns_405(self, client):
        """POST to a GET-only endpoint → 405 Method Not Allowed."""
        resp = client.post(
            "/api/v2/diagnostics/health",
            headers=AUTH_HEADER,
            json={},
        )
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Unit tests — redact_execution_metadata()
# ---------------------------------------------------------------------------

class TestRedactExecutionMetadata:

    def test_removes_sensitive_keys_from_flat_dict(self):
        from src.api.middleware import redact_execution_metadata
        data = {
            "status": "ok",
            "build_id": "abc123",
            "commit": "deadbeef",
            "message": "hello",
        }
        result = redact_execution_metadata(data)
        assert result["status"] == "ok"
        assert result["message"] == "hello"
        assert "build_id" not in result
        assert "commit" not in result

    def test_removes_sensitive_keys_from_nested_dict(self):
        from src.api.middleware import redact_execution_metadata
        data = {
            "data": {
                "build_id": "1.0",
                "items": [{"id": 1, "secret": "s3cr3t"}],
            },
            "metadata": {"token": "abc", "name": "test"},
        }
        result = redact_execution_metadata(data)
        assert "build_id" not in result["data"]
        assert "secret" not in result["data"]["items"][0]
        assert result["data"]["items"][0]["id"] == 1
        assert "token" not in result["metadata"]
        assert result["metadata"]["name"] == "test"

    def test_preserves_version_key(self):
        """'version' must not be redacted — it is safe public information."""
        from src.api.middleware import redact_execution_metadata
        data = {"version": "2.4.1", "status": "ok"}
        result = redact_execution_metadata(data)
        assert result["version"] == "2.4.1"

    def test_passes_through_primitive_values(self):
        from src.api.middleware import redact_execution_metadata
        assert redact_execution_metadata("hello") == "hello"
        assert redact_execution_metadata(42) == 42
        assert redact_execution_metadata(None) is None

    def test_handles_empty_dict(self):
        from src.api.middleware import redact_execution_metadata
        assert redact_execution_metadata({}) == {}

    def test_handles_empty_list(self):
        from src.api.middleware import redact_execution_metadata
        assert redact_execution_metadata([]) == []


# ---------------------------------------------------------------------------
# Unit tests — validate_diagnostics_request()
# ---------------------------------------------------------------------------

class TestValidateDiagnosticsRequest:

    def _make_request(self, method: str = "GET", headers: list = None):
        from starlette.requests import Request
        encoded = [(k.lower().encode(), v.encode()) for k, v in (headers or [])]
        scope = {"type": "http", "method": method, "headers": encoded}
        return Request(scope)

    def test_valid_bearer_token_passes(self):
        from src.api.middleware import validate_diagnostics_request
        req = self._make_request(headers=[("authorization", "Bearer valid-token")])
        valid, err = validate_diagnostics_request(req)
        assert valid is True
        assert err is None

    def test_missing_auth_header_returns_401(self):
        from src.api.middleware import validate_diagnostics_request
        req = self._make_request()
        valid, err = validate_diagnostics_request(req)
        assert valid is False
        assert err.status_code == 401

    def test_non_bearer_scheme_returns_401(self):
        from src.api.middleware import validate_diagnostics_request
        req = self._make_request(headers=[("authorization", "Basic dGVzdDp0ZXN0")])
        valid, err = validate_diagnostics_request(req)
        assert valid is False
        assert err.status_code == 401

    def test_bearer_with_empty_token_returns_401(self):
        """'Bearer ' with no token value is treated as missing auth."""
        from src.api.middleware import validate_diagnostics_request
        req = self._make_request(headers=[("authorization", "Bearer ")])
        valid, err = validate_diagnostics_request(req)
        assert valid is False
        assert err.status_code == 401

    def test_post_with_wrong_content_type_returns_415(self):
        from src.api.middleware import validate_diagnostics_request
        req = self._make_request(
            method="POST",
            headers=[
                ("authorization", "Bearer token"),
                ("content-type", "text/plain"),
            ],
        )
        valid, err = validate_diagnostics_request(req)
        assert valid is False
        assert err.status_code == 415

    def test_post_with_json_content_type_passes(self):
        from src.api.middleware import validate_diagnostics_request
        req = self._make_request(
            method="POST",
            headers=[
                ("authorization", "Bearer token"),
                ("content-type", "application/json"),
            ],
        )
        valid, err = validate_diagnostics_request(req)
        assert valid is True
        assert err is None

    def test_get_ignores_content_type_check(self):
        """Content-Type guard only applies to mutation methods."""
        from src.api.middleware import validate_diagnostics_request
        req = self._make_request(
            method="GET",
            headers=[
                ("authorization", "Bearer token"),
                ("content-type", "text/plain"),
            ],
        )
        valid, err = validate_diagnostics_request(req)
        assert valid is True
