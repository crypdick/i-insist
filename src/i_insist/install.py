"""Install and remove only i-insist's hooks in native harness configuration."""

from __future__ import annotations

import json
import os
import shlex
import stat
import tempfile
from pathlib import Path

from i_insist.events import GuardError

EVENTS = {
    "PreToolUse": "pre-tool-use",
    "UserPromptSubmit": "user-prompt-submit",
    "SessionStart": "session-start",
}


def configuration_path(harness: str) -> Path:
    if harness == "codex":
        root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        return (root / "hooks.json").expanduser().resolve()
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    return (root / "settings.json").expanduser().resolve()


def owned(handler: object, harness: str, event: str) -> bool:
    if not isinstance(handler, dict) or handler.get("type") != "command":
        return False
    command = handler.get("command")
    if not isinstance(command, str):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    return (
        bool(words)
        and Path(words[0]).name == "i-insist"
        and words[1:]
        == [
            "hook",
            "--harness",
            harness,
            event,
        ]
    )


def edit_hooks(document: dict, harness: str, install: bool) -> bool:
    if "hooks" not in document and not install:
        return False
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    changed = False
    for name, event in EVENTS.items():
        groups = hooks.get(name, [])
        if not isinstance(groups, list):
            raise ValueError(f"hooks.{name} must be an array")
        retained = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"hooks.{name} entries must contain a hooks array")
            handlers = [handler for handler in group["hooks"] if not owned(handler, harness, event)]
            if handlers == group["hooks"]:
                retained.append(group)
            elif handlers:
                retained.append({**group, "hooks": handlers})
        if install:
            entry = {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"i-insist hook --harness {harness} {event}",
                        "timeout": 600 if name == "PreToolUse" else 10,
                    }
                ]
            }
            if name == "PreToolUse":
                entry["matcher"] = ".*"
            retained.append(entry)
        if retained == groups:
            continue
        changed = True
        if retained:
            hooks[name] = retained
        else:
            hooks.pop(name, None)
    if not hooks and changed:
        document.pop("hooks", None)
    return changed


def configure(harness: str, *, install: bool) -> Path:
    if os.name != "posix":
        raise GuardError("hook installation currently supports Linux and macOS")
    import fcntl

    path = configuration_path(harness)
    if not install and not path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.i-insist.lock")
    with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            original = path.read_text() if path.exists() else None
            document = json.loads(original) if original is not None else {}
            if not isinstance(document, dict):
                raise ValueError("root must be an object")
            if not edit_hooks(document, harness, install):
                return path
            updated = json.dumps(document, indent=2) + "\n"
            if updated == original:
                return path
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    dir=path.parent,
                    prefix=f".{path.name}.",
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    os.fchmod(stream.fileno(), mode)
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Detect external edits made while this installer held its own lock.
                current = path.read_text() if path.exists() else None
                if current != original:
                    raise ValueError("file changed during installation; retry")
                temporary.replace(path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            raise GuardError(f"configuration {path}: {exc}") from exc
    return path
