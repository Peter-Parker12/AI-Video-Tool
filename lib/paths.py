"""Canonical repository paths — single source of truth.

The projects root is the most load-bearing path in the system: checkpoints
are written under it, tool events are attributed against it, and the Backlot
board watches it. Define it once.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Overridable for staging/screenshots/tests. Everything — checkpoint writes,
# event attribution, the Backlot board — follows the same root.
PROJECTS_DIR = Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or (REPO_ROOT / "projects"))

# Piper voice models (.onnx + .onnx.json pairs). The installed `piper-tts`
# CLI has no auto-download flag (its --help exposes --data-dir, not the
# --download-dir the tool's own install_instructions used to claim) -- it
# only resolves a bare model name against files already present in this
# directory. tools/audio/piper_tts.py passes --data-dir explicitly so
# resolution doesn't depend on whatever the caller's cwd happens to be.
PIPER_VOICES_DIR = Path(os.environ.get("PIPER_VOICES_DIR") or (REPO_ROOT / ".piper-voices"))


def safe_project_id(project_id: str) -> str:
    """Reject a project_id that could escape PROJECTS_DIR via path traversal.

    Shared by backlot/server.py's read endpoints and the MCP server's
    write-capable tools — a single guard so the two can't drift apart.
    """
    if not project_id or any(c in project_id for c in "/\\:") or project_id in (".", ".."):
        raise ValueError(f"invalid project id: {project_id!r}")
    return project_id
