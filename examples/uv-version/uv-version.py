"""Block hand-edited [project] versions in uv projects; `uv version` keeps uv.lock in sync.

A uv project is a pyproject.toml with uv.lock in its directory or an ancestor
(workspace root). Shell detection is a text heuristic: a command naming
pyproject.toml and "version" that also rewrites files in place. Cooperative
guard, not a sandbox: scripts and computed paths evade it.
"""

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

MESSAGE = (
    "Manual version edit in a uv project ({where}). Use `uv version --bump "
    "major|minor|patch|stable|alpha|beta|rc|post|dev` (or `uv version X.Y.Z`), "
    "which also updates uv.lock. To edit by hand, ask the human to say I insist."
)
VERSION_LINE = re.compile(r"(?m)^\s*version\s*=")
IN_PLACE = re.compile(
    r"\b(sed|perl)\b[^|;&]*\s-\w*i|\bawk\s+-i\s*inplace|\btee\b[^|;&]*pyproject\.toml"
    r"|>>?\s*\S*pyproject\.toml|write_text|\.write\(|open\([^)]*['\"][wa]"
)


def in_uv_project(directory: Path) -> bool:
    return any((parent / "uv.lock").is_file() for parent in (directory, *directory.parents))


def project_version(text: str) -> str | None:
    # NOTE: unparsable TOML counts as "no version" so an agent can still repair the file.
    try:
        version = tomllib.loads(text).get("project", {}).get("version")
    except tomllib.TOMLDecodeError:
        return None
    return version if isinstance(version, str) else None


def edited_text(current: str, tool_input: dict[str, Any]) -> str | None:
    """Rebuild the file after Claude Edit/MultiEdit, or None for other edit shapes."""
    edits = tool_input.get("edits") or ([tool_input] if "old_string" in tool_input else None)
    if edits is None:
        return None
    for item in edits:
        count = -1 if item.get("replace_all") else 1
        current = current.replace(item["old_string"], item["new_string"], count)
    return current


def changes_version(change: dict[str, str], tool_input: dict[str, Any]) -> bool:
    path = Path(change["path"])
    if path.name != "pyproject.toml" or change["operation"] == "delete" or not in_uv_project(path.parent):
        return False
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    new_text = change["content"] if change["operation"] == "write" else edited_text(current, tool_input)
    if new_text is None:
        # NOTE: patches only expose added lines; any added `version =` line counts,
        # including non-[project] tables. Reconstruct patched text if that misfires.
        return bool(VERSION_LINE.search(change["content"]))
    return project_version(new_text) != project_version(current)


def check(event: dict[str, Any]) -> str | None:
    if event["kind"] == "shell" and event.get("command"):
        command = event["command"]
        if (
            "pyproject.toml" in command
            and "version" in command
            and IN_PLACE.search(command)
            and in_uv_project(Path(event["cwd"]))
        ):
            return MESSAGE.format(where="shell rewrite of pyproject.toml")
        return None
    for change in event.get("changes", []):
        if changes_version(change, event.get("tool_input") or {}):
            return MESSAGE.format(where=change["path"])
    return None


if __name__ == "__main__":
    print(json.dumps(check(json.load(sys.stdin))))
