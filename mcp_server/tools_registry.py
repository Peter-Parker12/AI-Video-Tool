"""list_capabilities MCP tool — the static tool catalog, scrubbed of
server-local status.

This is a read-only, in-process call (registry.capability_catalog()), unlike
invoke_tool — it never touches provider keys or spends money.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from tools.tool_registry import registry


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_capabilities() -> dict[str, list[dict[str, Any]]]:
        """List every registered tool, grouped by capability (video_generation, tts, image_generation, ...).

        Each entry includes name, provider, input_schema,
        install_instructions, dependencies (which env vars it reads),
        agent_skills (Layer-3 vendor prompting guidance — read these before
        calling invoke_tool with a generation tool, per AGENT_GUIDE.md),
        best_for, not_good_for, and fallback_tools. The "status"
        (available/unavailable) field from the underlying registry is
        deliberately omitted here — it reflects THIS SERVER's own
        environment, not yours. You bring your own provider_keys to
        invoke_tool, so a tool this server reports as locally unavailable
        may work fine for you.
        """
        catalog = registry.capability_catalog()
        return {
            capability: [{k: v for k, v in entry.items() if k != "status"} for entry in entries]
            for capability, entries in catalog.items()
        }
