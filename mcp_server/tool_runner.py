"""Parent-side launcher for isolated tool execution (see tool_runner_worker.py).

Every ``invoke_tool`` MCP call runs the target BaseTool in a fresh subprocess
with an explicit, minimal environment: an allowlist of harmless vars the
interpreter/process needs (PATH, HOME, ...) plus that specific request's
caller-supplied provider API keys layered on top — never the parent
process's full ``os.environ``.

This exists because at least one tool (tools/video/sora_video.py) constructs
its SDK client with no explicit api_key=, so it reads OPENAI_API_KEY from
process-global os.environ at call time. Under concurrent multi-user
requests, monkeypatching env vars in-process has a real race: one request's
key could leak into another's concurrent call. Isolating every call in its
own process closes this for every tool, including that one, with zero
changes to any tool file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from lib.paths import REPO_ROOT

SCRATCH_DIR = REPO_ROOT / ".mcp_scratch"

# Vars the interpreter/subprocess machinery itself needs. Nothing
# credential-bearing lives here by construction — provider_keys are layered
# in per-call by the caller, separately.
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "PYTHONUNBUFFERED")

DEFAULT_TIMEOUT_SECONDS = 900


def _failure_result(error: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": {},
        "artifacts": [],
        "error": error,
        "cost_usd": 0.0,
        "duration_seconds": 0.0,
        "seed": None,
        "model": None,
    }


def run_tool_isolated(
    tool_name: str,
    inputs: dict[str, Any],
    provider_keys: dict[str, str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run `tool_name.execute(inputs)` in an isolated subprocess.

    Returns a ToolResult-shaped dict (success/data/artifacts/error/cost_usd/
    duration_seconds/seed/model) in every case, including crash and timeout,
    so callers always get one predictable shape to parse.
    """
    env: dict[str, str] = {}
    for var in _ENV_ALLOWLIST:
        value = os.environ.get(var)
        if value is not None:
            env[var] = value
    projects_dir_override = os.environ.get("OPENMONTAGE_PROJECTS_DIR")
    if projects_dir_override:
        env["OPENMONTAGE_PROJECTS_DIR"] = projects_dir_override
    env["OPENMONTAGE_SKIP_DOTENV"] = "1"
    # Caller-supplied provider keys go last so they always win.
    env.update(provider_keys)

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    call_id = uuid.uuid4().hex
    request_path = SCRATCH_DIR / f"{call_id}.request.json"
    result_path = SCRATCH_DIR / f"{call_id}.result.json"

    try:
        request_path.write_text(
            json.dumps({"tool_name": tool_name, "inputs": inputs}), encoding="utf-8"
        )

        started = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "mcp_server.tool_runner_worker", str(request_path), str(result_path)],
                env=env,
                cwd=str(REPO_ROOT),
                timeout=timeout,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - started
            result = _failure_result(f"Tool {tool_name!r} timed out after {elapsed:.0f}s")
            result["duration_seconds"] = elapsed
            return result

        if result_path.exists():
            try:
                return json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return _failure_result(f"Tool {tool_name!r} produced an unreadable result: {exc}")

        # Worker exited without writing a result: crash, OOM, or bad argv.
        stderr_tail = (proc.stderr or "")[-2000:]
        return _failure_result(
            f"Tool {tool_name!r} subprocess exited {proc.returncode} without writing a "
            f"result file. stderr tail:\n{stderr_tail}"
        )
    finally:
        for path in (request_path, result_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
