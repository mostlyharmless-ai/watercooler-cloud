"""Integration tests for HTTP Facade authentication flow.

Tests the auth middleware and identity header extraction for the
Remote MCP HTTP facade.

NOTE: These tests require the HTTP facade dependencies.
Install with: pip install -e ".[http]"
"""

import os
import importlib.util
from pathlib import Path
import pytest

# Skip entire module if fastapi is not installed
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

# Mark all tests in this module as requiring HTTP dependencies
pytestmark = pytest.mark.http


def _import_http_facade():
    """Import http_facade module directly to avoid package __init__ chain."""
    path = Path("src/watercooler_mcp/http_facade.py").resolve()
    if not path.exists():
        pytest.skip("http_facade not implemented yet")
    spec = importlib.util.spec_from_file_location("watercooler_mcp_http_facade", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


@pytest.fixture
def auth_secret():
    """Set and return a test auth secret."""
    secret = "test-secret-12345"
    os.environ["INTERNAL_AUTH_SECRET"] = secret
    os.environ["ALLOW_DEV_MODE"] = "false"  # Force production mode
    yield secret
    # Cleanup
    os.environ.pop("INTERNAL_AUTH_SECRET", None)
    os.environ.pop("ALLOW_DEV_MODE", None)


@pytest.fixture
def client():
    """Create test client for HTTP facade."""
    http_facade = _import_http_facade()
    return TestClient(http_facade.app)


class TestAuthFlow:
    """Test authentication flow for HTTP facade endpoints."""

    def test_health_endpoint_no_auth_required(self, client):
        """Health endpoint should be accessible without authentication."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_missing_auth_header_rejected(self, client, auth_secret):
        """Requests without X-Internal-Auth header should be rejected."""
        response = client.post(
            "/mcp/watercooler_v1_health",
            headers={
                "X-User-Id": "gh:testuser",
                "X-Project-Id": "test-project"
            }
        )
        assert response.status_code == 403
        assert "Invalid internal authentication" in response.json()["detail"]

    def test_incorrect_auth_secret_rejected(self, client, auth_secret):
        """Requests with incorrect auth secret should be rejected."""
        response = client.post(
            "/mcp/watercooler_v1_health",
            headers={
                "X-Internal-Auth": "wrong-secret",
                "X-User-Id": "gh:testuser",
                "X-Project-Id": "test-project"
            }
        )
        assert response.status_code == 403
        assert "Invalid internal authentication" in response.json()["detail"]

    def test_correct_auth_secret_accepted(self, client, auth_secret):
        """Requests with correct auth secret should be accepted."""
        response = client.post(
            "/mcp/watercooler_v1_health",
            headers={
                "X-Internal-Auth": auth_secret,
                "X-User-Id": "gh:testuser",
                "X-Project-Id": "test-project"
            }
        )
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_missing_user_id_header(self, client, auth_secret):
        """Requests without X-User-Id should be rejected."""
        response = client.post(
            "/mcp/watercooler_v1_health",
            headers={
                "X-Internal-Auth": auth_secret,
                "X-Project-Id": "test-project"
            }
        )
        assert response.status_code == 400
        assert "Missing X-User-Id header" in response.json()["error"]

    def test_missing_project_id_header(self, client, auth_secret):
        """Requests without X-Project-Id should be rejected."""
        response = client.post(
            "/mcp/watercooler_v1_health",
            headers={
                "X-Internal-Auth": auth_secret,
                "X-User-Id": "gh:testuser"
            }
        )
        assert response.status_code == 400
        assert "Missing X-Project-Id header" in response.json()["error"]

    def test_identity_headers_extracted(self, client, auth_secret):
        """Identity headers should be properly extracted and returned."""
        response = client.post(
            "/mcp/watercooler_v1_health",
            headers={
                "X-Internal-Auth": auth_secret,
                "X-User-Id": "gh:octocat",
                "X-Agent-Name": "Claude",
                "X-Project-Id": "watercooler-collab"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "gh:octocat"
        assert data["agent"] == "Claude"
        assert data["project_id"] == "watercooler-collab"

    def test_agent_name_defaults_to_agent(self, client, auth_secret):
        """When X-Agent-Name is missing, should default to 'Agent'."""
        response = client.post(
            "/mcp/watercooler_v1_health",
            headers={
                "X-Internal-Auth": auth_secret,
                "X-User-Id": "gh:testuser",
                "X-Project-Id": "test-project"
            }
        )
        assert response.status_code == 200
        assert response.json()["agent"] == "Agent"

    def test_whoami_returns_identity(self, client, auth_secret):
        """whoami endpoint should return user identity."""
        response = client.post(
            "/mcp/watercooler_v1_whoami",
            headers={
                "X-Internal-Auth": auth_secret,
                "X-User-Id": "gh:octocat",
                "X-Agent-Name": "Codex",
                "X-Project-Id": "test-project"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "gh:octocat"
        assert data["agent"] == "Codex"
        assert data["project_id"] == "test-project"


class TestDevMode:
    """Test development mode behavior."""

    def test_dev_mode_skips_auth_check(self):
        """In dev mode, auth secret is not enforced."""
        # Set dev mode
        os.environ["ALLOW_DEV_MODE"] = "true"
        os.environ.pop("INTERNAL_AUTH_SECRET", None)

        try:
            http_facade = _import_http_facade()
            client = TestClient(http_facade.app)

            # Request without auth secret should work in dev mode
            response = client.post(
                "/mcp/watercooler_v1_health",
                headers={
                    "X-User-Id": "gh:testuser",
                    "X-Project-Id": "test-project"
                }
            )
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"
        finally:
            # Cleanup
            os.environ.pop("ALLOW_DEV_MODE", None)
