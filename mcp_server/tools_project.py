"""Project lifecycle MCP tools — thin wrappers over lib/checkpoint.py and
lib/pipeline_loader.py. No orchestration logic lives here: the connecting
Claude session decides what goes in each stage's artifact by reading the
resources in resources.py; these tools just persist that decision the same
way a local Claude Code session would via direct filesystem writes.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from lib.checkpoint import (
    PROJECT_MARKER_FILENAME,
    CheckpointValidationError,
    get_completed_stages,
    get_latest_checkpoint,
    get_next_stage,
)
from lib.checkpoint import init_project as _init_project
from lib.checkpoint import write_checkpoint as _write_checkpoint
from lib.paths import PROJECTS_DIR, safe_project_id
from lib.pipeline_loader import list_pipelines as _list_pipelines


def _board_url(project_id: str) -> str:
    base = os.environ.get("BACKLOT_PUBLIC_URL", "").rstrip("/")
    if not base:
        return "(BACKLOT_PUBLIC_URL is not configured on this server — ask the operator)"
    return f"{base}/p/{project_id}"


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_pipelines() -> list[str]:
        """List available OpenMontage pipeline names (pipeline_defs/*.yaml).

        Read the openmontage://pipeline/{name} resource for a given pipeline's
        stage order, human-approval gates, and per-stage skill paths before
        starting a production.
        """
        return sorted(_list_pipelines())

    @mcp.tool()
    def init_project(project_id: str, title: str, pipeline_type: str) -> dict[str, Any]:
        """Create (or idempotently re-open) a project workspace.

        Call this once per production before writing any stage checkpoint.
        project_id becomes the directory name under projects/ — keep it
        kebab-case and stable for the life of the production.
        """
        pid = safe_project_id(project_id)
        if pipeline_type not in _list_pipelines():
            raise ValueError(f"unknown pipeline_type: {pipeline_type!r}. Call list_pipelines() for valid names.")
        _init_project(pid, title=title, pipeline_type=pipeline_type)
        return {"project_id": pid, "board_url": _board_url(pid)}

    @mcp.tool()
    def get_project_status(project_id: str) -> dict[str, Any]:
        """Report a project's pipeline type, completed stages, next stage, and latest checkpoint."""
        pid = safe_project_id(project_id)
        project_dir = PROJECTS_DIR / pid
        if not project_dir.is_dir():
            raise ValueError(f"unknown project {pid!r} — call init_project first")

        marker_path = project_dir / PROJECT_MARKER_FILENAME
        pipeline_type: Optional[str] = None
        if marker_path.is_file():
            with open(marker_path, encoding="utf-8") as f:
                pipeline_type = json.load(f).get("pipeline_type")

        return {
            "project_id": pid,
            "pipeline_type": pipeline_type,
            "completed_stages": get_completed_stages(PROJECTS_DIR, pid, pipeline_type),
            "next_stage": get_next_stage(PROJECTS_DIR, pid, pipeline_type),
            "latest_checkpoint": get_latest_checkpoint(PROJECTS_DIR, pid),
            "board_url": _board_url(pid),
        }

    @mcp.tool()
    def write_stage_checkpoint(
        project_id: str,
        stage: str,
        status: str,
        artifacts: dict[str, Any],
        human_approval_required: bool = False,
        human_approved: bool = False,
        review: Optional[dict[str, Any]] = None,
        cost_snapshot: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Write a stage checkpoint (status: "in_progress" | "completed" | "failed" | "awaiting_human").

        Gated stages (per the pipeline manifest's human_approval_default)
        CANNOT be written status="completed" without human_approved=True —
        the underlying write raises a GATE VIOLATION whose message spells
        out the exact correction needed: write status="awaiting_human",
        present the artifact and review to the human in THIS chat, get
        their explicit approval, then call this again with
        human_approved=True. Read that error message verbatim if it fires;
        don't paraphrase or route around it.
        """
        pid = safe_project_id(project_id)
        try:
            path = _write_checkpoint(
                PROJECTS_DIR,
                pid,
                stage,
                status,
                artifacts,
                human_approval_required=human_approval_required,
                human_approved=human_approved,
                review=review,
                cost_snapshot=cost_snapshot,
                error=error,
                metadata=metadata,
            )
        except CheckpointValidationError as exc:
            raise ValueError(str(exc)) from None
        return {"checkpoint_path": str(path), "board_url": _board_url(pid)}

    @mcp.tool()
    def get_board_url(project_id: str) -> str:
        """Return the public Backlot board URL for a project, for sharing with the human."""
        return _board_url(safe_project_id(project_id))
