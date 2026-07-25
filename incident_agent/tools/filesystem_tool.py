"""Filesystem Tool -- read-only access scoped to a dedicated sandbox directory.

Never resolves against the repository root or any caller-supplied
absolute path: every request is joined under `_SANDBOX_ROOT` and the
resolved, real path is checked to still be contained within it before
any I/O happens. This is the standard defense against path traversal
(`../../etc/passwd`-style) and symlink escapes -- without it, a tool
whose `path` argument is ultimately LLM-controlled would be a arbitrary
file-read primitive over the whole host filesystem.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from incident_agent.config.settings import PROJECT_ROOT
from incident_agent.tools.base import run_structured

_SANDBOX_ROOT = (PROJECT_ROOT / "data" / "filesystem_sandbox").resolve()
_MAX_READ_BYTES = 50_000


class PathTraversalError(ValueError):
    """Raised when a requested path would escape the sandbox root."""


def _resolve_safe_path(relative_path: str) -> Path:
    _SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    candidate = (_SANDBOX_ROOT / relative_path).resolve()
    if not candidate.is_relative_to(_SANDBOX_ROOT):
        raise PathTraversalError(f"'{relative_path}' resolves outside the permitted sandbox directory.")
    return candidate


def _read_file(relative_path: str) -> dict:
    path = _resolve_safe_path(relative_path)
    if not path.is_file():
        raise FileNotFoundError(f"'{relative_path}' is not a file in the sandbox directory.")
    raw = path.read_bytes()
    truncated = len(raw) > _MAX_READ_BYTES
    content = raw[:_MAX_READ_BYTES].decode("utf-8", errors="replace")
    return {"path": relative_path, "size_bytes": len(raw), "truncated": truncated, "content": content}


def _list_directory(relative_path: str) -> dict:
    path = _resolve_safe_path(relative_path)
    if not path.is_dir():
        raise NotADirectoryError(f"'{relative_path}' is not a directory in the sandbox directory.")
    entries = [
        {"name": child.name, "type": "directory" if child.is_dir() else "file", "size_bytes": child.stat().st_size}
        for child in sorted(path.iterdir())
    ]
    return {"path": relative_path, "entries": entries}


@tool
def filesystem_read_file(path: str) -> str:
    """Read a text file from the investigation sandbox directory (relative
    path, e.g. 'deployment_notes.txt'). Reads outside this directory are
    rejected. Large files are truncated to 50KB."""
    return run_structured("filesystem_read_file", lambda: _read_file(path))


@tool
def filesystem_list_directory(path: str = ".") -> str:
    """List files and subdirectories under a path within the investigation
    sandbox directory."""
    return run_structured("filesystem_list_directory", lambda: _list_directory(path))
