"""Unit tests for ACL enforcement and project isolation.

Tests the per-user/per-project directory isolation logic in the HTTP facade.

NOTE: These tests require the HTTP facade dependencies.
Install with: pip install -e ".[http]"
"""

import os
import importlib.util
import tempfile
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
def temp_base_root():
    """Create temporary base root for threads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["BASE_THREADS_ROOT"] = tmpdir
        yield Path(tmpdir)
        os.environ.pop("BASE_THREADS_ROOT", None)


class TestProjectIsolation:
    """Test project-level isolation for threads directories."""

    def test_derive_threads_dir_creates_path(self, temp_base_root):
        """derive_threads_dir should create user/project directory path."""
        http_facade = _import_http_facade()

        user_id = "gh:alice"
        project_id = "project-a"

        threads_dir = http_facade.derive_threads_dir(user_id, project_id)

        assert threads_dir.exists()
        assert threads_dir.is_dir()
        assert str(threads_dir) == str(temp_base_root / user_id / project_id)

    def test_different_users_isolated(self, temp_base_root):
        """Different users should get isolated directories."""
        http_facade = _import_http_facade()
        derive_threads_dir = http_facade.derive_threads_dir

        alice_dir = derive_threads_dir("gh:alice", "project-shared")
        bob_dir = derive_threads_dir("gh:bob", "project-shared")

        assert alice_dir != bob_dir
        assert alice_dir.parent != bob_dir.parent
        assert alice_dir.exists() and bob_dir.exists()

    def test_different_projects_isolated(self, temp_base_root):
        """Same user with different projects should get isolated directories."""
        http_facade = _import_http_facade()
        derive_threads_dir = http_facade.derive_threads_dir

        project_a_dir = derive_threads_dir("gh:alice", "project-a")
        project_b_dir = derive_threads_dir("gh:alice", "project-b")

        assert project_a_dir != project_b_dir
        assert project_a_dir.parent == project_b_dir.parent  # Same user parent
        assert project_a_dir.exists() and project_b_dir.exists()

    def test_same_user_same_project_same_dir(self, temp_base_root):
        """Same user/project should consistently return same directory."""
        http_facade = _import_http_facade()
        derive_threads_dir = http_facade.derive_threads_dir

        dir1 = derive_threads_dir("gh:alice", "project-a")
        dir2 = derive_threads_dir("gh:alice", "project-a")

        assert dir1 == dir2

    def test_directory_structure(self, temp_base_root):
        """Verify correct directory hierarchy is created."""
        http_facade = _import_http_facade()
        derive_threads_dir = http_facade.derive_threads_dir

        user_id = "gh:octocat"
        project_id = "watercooler-collab"

        threads_dir = derive_threads_dir(user_id, project_id)

        # Check full path structure
        expected = temp_base_root / "gh:octocat" / "watercooler-collab"
        assert threads_dir == expected

        # Verify all parts exist
        assert (temp_base_root / "gh:octocat").exists()
        assert (temp_base_root / "gh:octocat" / "watercooler-collab").exists()

    def test_idempotent_directory_creation(self, temp_base_root):
        """Multiple calls should safely handle existing directories."""
        http_facade = _import_http_facade()
        derive_threads_dir = http_facade.derive_threads_dir

        # Create directory first time
        dir1 = derive_threads_dir("gh:alice", "project-a")

        # Create a file in the directory
        test_file = dir1 / "test.md"
        test_file.write_text("test content")

        # Call again - should not fail
        dir2 = derive_threads_dir("gh:alice", "project-a")

        # File should still exist
        assert test_file.exists()
        assert test_file.read_text() == "test content"
        assert dir1 == dir2


class TestInternalAuthVerification:
    """Test internal authentication verification logic."""

    def test_verify_with_correct_secret(self):
        """verify_internal_auth should accept correct secret."""
        http_facade = _import_http_facade()
        verify_internal_auth = http_facade.verify_internal_auth

        secret = "test-secret-xyz"
        os.environ["INTERNAL_AUTH_SECRET"] = secret

        try:
            # Should not raise exception
            verify_internal_auth(secret)
        finally:
            os.environ.pop("INTERNAL_AUTH_SECRET", None)

    def test_verify_with_incorrect_secret_raises(self):
        """verify_internal_auth should reject incorrect secret."""
        http_facade = _import_http_facade()
        verify_internal_auth = http_facade.verify_internal_auth
        from fastapi import HTTPException

        os.environ["INTERNAL_AUTH_SECRET"] = "correct-secret"

        try:
            with pytest.raises(HTTPException) as exc_info:
                verify_internal_auth("wrong-secret")

            assert exc_info.value.status_code == 403
            assert "Invalid internal authentication" in str(exc_info.value.detail)
        finally:
            os.environ.pop("INTERNAL_AUTH_SECRET", None)

    def test_verify_with_no_secret_configured_allows_all(self):
        """verify_internal_auth should skip check when no secret configured (dev mode)."""
        http_facade = _import_http_facade()
        verify_internal_auth = http_facade.verify_internal_auth

        # Ensure no secret is set
        os.environ.pop("INTERNAL_AUTH_SECRET", None)

        # Should not raise exception even with None
        verify_internal_auth(None)
        verify_internal_auth("any-value")

    def test_verify_with_empty_secret_allows_all(self):
        """verify_internal_auth should skip check when secret is empty string."""
        http_facade = _import_http_facade()
        verify_internal_auth = http_facade.verify_internal_auth

        os.environ["INTERNAL_AUTH_SECRET"] = ""

        try:
            # Should not raise exception
            verify_internal_auth(None)
            verify_internal_auth("any-value")
        finally:
            os.environ.pop("INTERNAL_AUTH_SECRET", None)


class TestACLEndToEnd:
    """End-to-end ACL tests with full request flow."""

    def test_project_isolation_in_health_endpoint(self):
        """Health endpoint should reflect correct project isolation."""
        import tempfile
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["BASE_THREADS_ROOT"] = tmpdir
            os.environ["ALLOW_DEV_MODE"] = "true"  # Skip auth for this test

            try:
                http_facade = _import_http_facade()
                client = TestClient(http_facade.app)

                # User Alice accessing project-a
                response = client.post(
                    "/mcp/watercooler_v1_health",
                    headers={
                        "X-User-Id": "gh:alice",
                        "X-Project-Id": "project-a"
                    }
                )

                assert response.status_code == 200
                alice_threads_dir = response.json()["threads_dir"]
                assert "gh:alice" in alice_threads_dir
                assert "project-a" in alice_threads_dir

                # User Bob accessing project-b
                response = client.post(
                    "/mcp/watercooler_v1_health",
                    headers={
                        "X-User-Id": "gh:bob",
                        "X-Project-Id": "project-b"
                    }
                )

                assert response.status_code == 200
                bob_threads_dir = response.json()["threads_dir"]
                assert "gh:bob" in bob_threads_dir
                assert "project-b" in bob_threads_dir

                # Verify directories are different
                assert alice_threads_dir != bob_threads_dir

            finally:
                os.environ.pop("BASE_THREADS_ROOT", None)
                os.environ.pop("ALLOW_DEV_MODE", None)

    def test_user_cannot_access_other_users_threads(self):
        """Verify that changing user_id changes threads directory."""
        import tempfile
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["BASE_THREADS_ROOT"] = tmpdir
            os.environ["ALLOW_DEV_MODE"] = "true"

            try:
                http_facade = _import_http_facade()
                client = TestClient(http_facade.app)

                # User alice creates threads in project-x
                response1 = client.post(
                    "/mcp/watercooler_v1_health",
                    headers={
                        "X-User-Id": "gh:alice",
                        "X-Project-Id": "project-x"
                    }
                )
                alice_dir = response1.json()["threads_dir"]

                # User bob accesses same project
                response2 = client.post(
                    "/mcp/watercooler_v1_health",
                    headers={
                        "X-User-Id": "gh:bob",
                        "X-Project-Id": "project-x"
                    }
                )
                bob_dir = response2.json()["threads_dir"]

                # They should get different directories despite same project
                assert alice_dir != bob_dir
                assert Path(alice_dir).exists()
                assert Path(bob_dir).exists()

            finally:
                os.environ.pop("BASE_THREADS_ROOT", None)
                os.environ.pop("ALLOW_DEV_MODE", None)
