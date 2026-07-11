"""invoke_tool MCP tool — runs one OpenMontage tool with caller-supplied
provider keys, isolated per call. See tool_runner.py for why isolation is a
subprocess and not in-process env-var monkeypatching.
"""

from __future__ import annotations

from typing import Any, Optional

import jsonschema
from mcp.server.fastmcp import FastMCP

from lib.paths import PROJECTS_DIR, safe_project_id
from mcp_server.tool_runner import run_tool_isolated
from tools.tool_registry import registry


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def invoke_tool(
        tool_name: str,
        inputs: dict[str, Any],
        provider_keys: dict[str, str],
        project_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run one OpenMontage tool (video/image/TTS/music generation, composition, ...) using YOUR OWN provider keys.

        tool_name must be one returned by list_capabilities(). provider_keys
        is env-var-name -> value for JUST this call (e.g. {"FAL_KEY": "..."})
        — check the tool's install_instructions/dependencies from
        list_capabilities() for the exact variable name it expects. Keys are
        used only inside an isolated subprocess for this single call; they
        are never stored, logged, or reused for anyone else's call.

        Pass project_id and include an output_path under
        projects/<project_id>/assets/... in inputs (per AGENT_GUIDE.md's
        workspace convention) so the Backlot board can attribute the write
        and show it live.

        Returns a ToolResult-shaped dict: success, data, artifacts (output
        file paths), error, cost_usd, duration_seconds, seed, model — even
        on a crash or timeout, so you always get one predictable shape.
        Before calling this for any paid tool, announce the provider/model
        and cost to the human and wait for approval, per AGENT_GUIDE.md's
        Decision Communication Contract (openmontage://guide).
        """
        registry.ensure_discovered()
        tool = registry.get(tool_name)
        if tool is None:
            raise ValueError(f"unknown tool: {tool_name!r}. Call list_capabilities() for valid names.")

        try:
            jsonschema.validate(instance=inputs, schema=tool.input_schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"inputs failed schema validation for {tool_name!r}: {exc.message}") from None

        if project_id is not None:
            pid = safe_project_id(project_id)
            inputs = dict(inputs)
            inputs.setdefault("project_dir", str(PROJECTS_DIR / pid))

        return run_tool_isolated(tool_name, inputs, provider_keys)
