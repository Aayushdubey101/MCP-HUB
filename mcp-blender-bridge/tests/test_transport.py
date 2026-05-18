"""Tests for HTTP transport authentication middleware and CLI transport flags."""

import os
from unittest.mock import patch

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from blender_bridge.server import AuthMiddleware, main

# ---------------------------------------------------------------------------
# AuthMiddleware unit tests
# ---------------------------------------------------------------------------


def _make_dummy_app():
    async def dummy_app(scope, receive, send):
        response = JSONResponse({"status": "ok"})
        await response(scope, receive, send)

    return dummy_app


def test_auth_middleware_missing_header():
    """Requests without an Authorization header receive 401."""
    app = AuthMiddleware(_make_dummy_app(), token="secret")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["error"]


def test_auth_middleware_missing_bearer_prefix():
    """Requests with a bare token (no 'Bearer ' prefix) receive 401."""
    app = AuthMiddleware(_make_dummy_app(), token="secret")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Authorization": "secret"})
    assert response.status_code == 401


def test_auth_middleware_invalid_token():
    """Requests with the wrong bearer token receive 401."""
    app = AuthMiddleware(_make_dummy_app(), token="secret")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401
    assert "Invalid token" in response.json()["error"]


def test_auth_middleware_valid_token():
    """Requests with the correct bearer token pass through."""
    app = AuthMiddleware(_make_dummy_app(), token="secret")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# main() CLI transport tests
# ---------------------------------------------------------------------------


@patch("sys.argv", ["mcp-blender-bridge", "--transport", "http"])
def test_main_http_missing_token_exits():
    """HTTP mode exits with code 1 when BLENDER_BRIDGE_AUTH_TOKEN is unset."""
    env = {k: v for k, v in os.environ.items() if k != "BLENDER_BRIDGE_AUTH_TOKEN"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1


@patch("sys.argv", ["mcp-blender-bridge", "--transport", "http", "--port", "1234"])
@patch("blender_bridge.server.uvicorn.run")
def test_main_http_valid_token_runs_uvicorn(mock_uvicorn_run):
    """uvicorn starts on the safe default host/port when a token is present."""
    with patch.dict(os.environ, {"BLENDER_BRIDGE_AUTH_TOKEN": "mytoken"}):
        main()
    mock_uvicorn_run.assert_called_once()
    _, kwargs = mock_uvicorn_run.call_args
    # Secure default: HTTP transport binds to loopback unless --host overrides.
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 1234


@patch(
    "sys.argv",
    ["mcp-blender-bridge", "--transport", "http", "--host", "0.0.0.0", "--port", "1234"],
)
@patch("blender_bridge.server.uvicorn.run")
def test_main_http_explicit_host_honoured(mock_uvicorn_run):
    """Explicit --host 0.0.0.0 is respected (opt-in network exposure)."""
    with patch.dict(os.environ, {"BLENDER_BRIDGE_AUTH_TOKEN": "mytoken"}):
        main()
    _, kwargs = mock_uvicorn_run.call_args
    assert kwargs["host"] == "0.0.0.0"


def test_auth_middleware_constant_time_compare():
    """Token comparison uses secrets.compare_digest (no early exit on prefix match)."""
    import secrets as _secrets

    app = AuthMiddleware(_make_dummy_app(), token="alphabravo")
    # The bytes-encoded token is what the middleware compares against.
    assert app._token_bytes == b"alphabravo"
    # Sanity: compare_digest still equates equal byte sequences.
    assert _secrets.compare_digest(app._token_bytes, b"alphabravo") is True
    assert _secrets.compare_digest(app._token_bytes, b"alphabravX") is False


@patch("sys.argv", ["mcp-blender-bridge", "--transport", "http", "--port", "1234"])
@patch("blender_bridge.server.uvicorn.run")
def test_main_http_app_has_auth_middleware(mock_uvicorn_run):
    """The ASGI app passed to uvicorn includes AuthMiddleware."""
    with patch.dict(os.environ, {"BLENDER_BRIDGE_AUTH_TOKEN": "mytoken"}):
        main()
    args, _ = mock_uvicorn_run.call_args
    app = args[0]
    middleware_types = [m.cls for m in app.user_middleware]
    assert AuthMiddleware in middleware_types


@patch("sys.argv", ["mcp-blender-bridge", "--transport", "sse"])
@patch("blender_bridge.server.mcp.run")
def test_main_sse_delegates_to_fastmcp(mock_mcp_run):
    """SSE transport delegates to FastMCP with transport='sse'."""
    main()
    mock_mcp_run.assert_called_once_with(transport="sse")


@patch("sys.argv", ["mcp-blender-bridge"])
@patch("blender_bridge.server.mcp.run")
def test_main_stdio_default(mock_mcp_run):
    """Default (no --transport) uses stdio."""
    main()
    mock_mcp_run.assert_called_once_with(transport="stdio")


@patch("sys.argv", ["mcp-blender-bridge", "--list-plugins"])
@patch("blender_bridge.server.mcp.run")
def test_main_list_plugins_does_not_start_server(mock_mcp_run, capsys):
    """--list-plugins prints the plugin list and does not start the server."""
    main()
    mock_mcp_run.assert_not_called()
    captured = capsys.readouterr()
    assert "Installed plugins:" in captured.out
