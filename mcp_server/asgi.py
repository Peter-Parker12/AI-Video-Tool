"""ASGI entrypoint for the OpenMontage remote MCP server.

Run with: uvicorn mcp_server.asgi:app --host 0.0.0.0 --port 2384

Deliberately a second, standalone process/port from the Backlot board
(backlot/server.py) rather than mounted into it: FastMCP's streamable-http
transport owns its session manager's lifespan at the ASGI root
(FastMCP.streamable_http_app() sets lifespan=lambda app: self.session_manager.run()),
and Starlette does not propagate lifespan into mounted sub-apps — mounting
would require converting the board's existing @app.on_event("startup")
watcher to lifespan= and hand-composing two lifespans for no functional
benefit. Both processes share the same projects/ volume, so anything
written here shows up live on the already-running board with zero extra
wiring (backlot/state.py is purely disk-based).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import Response

from lib.paths import REPO_ROOT
from mcp_server import oauth, resources, tools_invoke, tools_project, tools_registry

# Registered DCR clients + issued tokens survive container restarts via this
# file — without it, every redeploy forces everyone connected to remove and
# re-add their connector (see oauth.py's module docstring). Override with
# MCP_OAUTH_STATE_PATH if the deploy mounts state somewhere other than the
# repo root (e.g. a dedicated volume).
DEFAULT_OAUTH_STATE_PATH = REPO_ROOT / ".mcp_state" / "oauth_store.json"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(
            f"mcp_server: refusing to start — {name} is not set. "
            f"This server is unauthenticated without it; set it in .env and retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return value


def build_app():
    shared_password = _require_env("MCP_SHARED_TOKEN")
    static_client_id = _require_env("MCP_OAUTH_CLIENT_ID")
    static_client_secret = _require_env("MCP_OAUTH_CLIENT_SECRET")

    static_redirect_uris = [
        uri.strip()
        for uri in os.environ.get("MCP_OAUTH_STATIC_REDIRECT_URIS", "").split(",")
        if uri.strip()
    ]
    public_url = os.environ.get("MCP_PUBLIC_URL", "http://localhost:2384").rstrip("/")
    state_path_override = os.environ.get("MCP_OAUTH_STATE_PATH")
    state_path = Path(state_path_override) if state_path_override else DEFAULT_OAUTH_STATE_PATH

    provider = oauth.SharedPasswordOAuthProvider(
        shared_password=shared_password,
        static_client_id=static_client_id,
        static_client_secret=static_client_secret,
        static_redirect_uris=static_redirect_uris,
        state_path=state_path,
    )

    mcp = FastMCP(
        name="openmontage",
        instructions=(
            "OpenMontage video production toolkit. Start by reading the "
            "openmontage://guide resource (AGENT_GUIDE.md) — it defines Rule "
            "Zero (all production goes through a pipeline), the checkpoint/gate "
            "protocol, and the decision-communication contract you must follow "
            "before spending anyone's money via invoke_tool."
        ),
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=public_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )

    resources.register_resources(mcp)
    tools_project.register_tools(mcp)
    tools_registry.register_tools(mcp)
    tools_invoke.register_tools(mcp)

    @mcp.custom_route("/login", methods=["GET"])
    async def login_get_route(request: Request) -> Response:
        return await oauth.login_get(request, provider)

    @mcp.custom_route("/login", methods=["POST"])
    async def login_post_route(request: Request) -> Response:
        return await oauth.login_post(request, provider)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        from starlette.responses import JSONResponse

        return JSONResponse({"ok": True, "app": "openmontage-mcp"})

    return mcp.streamable_http_app()


app = build_app()
