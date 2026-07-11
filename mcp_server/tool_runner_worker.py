"""Subprocess entrypoint for isolated tool execution.

Invoked as ``python -m mcp_server.tool_runner_worker <request.json> <result.json>``
by ``mcp_server/tool_runner.py``. Runs entirely inside a subprocess whose
environment was built explicitly by the parent (allowlisted vars +
that request's own provider API keys, never the parent's full
``os.environ``) — see tool_runner.py's module docstring for why.

Writes its result to ``result.json`` rather than stdout: third-party SDKs
(openai, google-genai, ...) can print warnings to stdout, which would
corrupt a stdout-as-JSON-envelope parse.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import traceback


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: tool_runner_worker.py <request.json> <result.json>", file=sys.stderr)
        return 2

    request_path, result_path = sys.argv[1], sys.argv[2]
    with open(request_path, encoding="utf-8") as f:
        request = json.load(f)

    tool_name = request["tool_name"]
    inputs = request["inputs"]

    result_dict: dict
    try:
        from tools.tool_registry import registry

        registry.discover()
        tool = registry.get(tool_name)
        if tool is None:
            result_dict = {
                "success": False,
                "data": {},
                "artifacts": [],
                "error": f"Unknown tool: {tool_name!r}",
                "cost_usd": 0.0,
                "duration_seconds": 0.0,
                "seed": None,
                "model": None,
            }
        else:
            tool_result = tool.execute(inputs)
            result_dict = dataclasses.asdict(tool_result)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this is the failure boundary
        result_dict = {
            "success": False,
            "data": {},
            "artifacts": [],
            "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=8)}",
            "cost_usd": 0.0,
            "duration_seconds": 0.0,
            "seed": None,
            "model": None,
        }

    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_dict, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
