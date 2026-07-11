"""MCP resources — the prose/creative content a connecting Claude session needs.

Stage director skills, meta skills, and pipeline manifests are written to be
read and interpreted by an LLM (see AGENT_GUIDE.md and skills/pipelines/*/
*-director.md) — there is no Python orchestration to call instead. These
resources serve that content as-is, straight from disk, so a remote Claude
session (with no local checkout of this repo) can read the exact same
guidance a local Claude Code session would.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lib.paths import REPO_ROOT
from lib.pipeline_loader import list_pipelines, load_pipeline_readonly

SKILLS_DIRS = {
    "skills": REPO_ROOT / "skills",
    "agent-skills": REPO_ROOT / ".agents" / "skills",
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _resolve_skill_path(path: str) -> Path:
    """Resolve a skill:// path against SKILLS_DIRS, rejecting traversal.

    `path` is expected as "<root>/<rest...>", e.g. "skills/pipelines/
    explainer/idea-director.md" or "agent-skills/ai-video-gen/SKILL.md".
    """
    parts = path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"invalid skill path: {path!r} (expected '<root>/<rest>')")
    root_key, rest = parts
    root = SKILLS_DIRS.get(root_key)
    if root is None:
        raise ValueError(f"unknown skill root {root_key!r}; expected one of {sorted(SKILLS_DIRS)}")

    resolved = (root / rest).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"path escapes skill root: {path!r}") from None
    if not resolved.is_file():
        raise FileNotFoundError(f"no such skill file: {path!r}")
    return resolved


def register_resources(mcp: FastMCP) -> None:
    @mcp.resource(
        "openmontage://guide",
        name="AGENT_GUIDE.md",
        description="The operating guide and agent contract for OpenMontage — read this first.",
        mime_type="text/markdown",
    )
    def guide() -> str:
        return _read_text(REPO_ROOT / "AGENT_GUIDE.md")

    @mcp.resource(
        "openmontage://project-context",
        name="PROJECT_CONTEXT.md",
        description="Architecture, key files, and conventions for OpenMontage.",
        mime_type="text/markdown",
    )
    def project_context() -> str:
        return _read_text(REPO_ROOT / "PROJECT_CONTEXT.md")

    @mcp.resource(
        "openmontage://pipelines",
        name="pipeline list",
        description="Names of all available pipeline manifests (pass one to openmontage://pipeline/{name}).",
        mime_type="application/json",
    )
    def pipelines() -> str:
        return json.dumps(sorted(list_pipelines()))

    @mcp.resource(
        "openmontage://pipeline/{name}",
        name="pipeline manifest",
        description="A validated pipeline_defs/<name>.yaml manifest: stages, skill paths, gates, tools_available.",
        mime_type="application/json",
    )
    def pipeline(name: str) -> str:
        if name not in list_pipelines():
            raise ValueError(f"unknown pipeline: {name!r}")
        return json.dumps(load_pipeline_readonly(name))

    @mcp.resource(
        "openmontage://skill/{path}",
        name="skill file",
        description=(
            "A director/meta skill or Layer-3 vendor skill, by path. "
            "path is '<root>/<rest>' where root is 'skills' (pipeline director + "
            "meta skills) or 'agent-skills' (vendor/provider knowledge, "
            "formerly .agents/skills/) — e.g. "
            "'skills/pipelines/explainer/idea-director.md' or "
            "'agent-skills/ai-video-gen/SKILL.md'."
        ),
        mime_type="text/markdown",
    )
    def skill(path: str) -> str:
        return _read_text(_resolve_skill_path(path))
