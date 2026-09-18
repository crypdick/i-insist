"""Install and remove only i-insist's hooks in native harness configuration."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import tempfile
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import cast

from i_insist.events import GuardError, Json

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


def edit_hooks(document: dict[str, Json], harness: str, *, install: bool) -> bool:  # noqa: PLR0912
    if "hooks" not in document and not install:
        return False
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")  # noqa: TRY004
    changed = False
    for name, event in EVENTS.items():
        groups = hooks.get(name, [])
        if not isinstance(groups, list):
            raise ValueError(f"hooks.{name} must be an array")  # noqa: TRY004
        retained: list[dict[str, Json]] = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(  # noqa: TRY004
                    f"hooks.{name} entries must contain a hooks array"
                )
            group_hooks = cast("list[Json]", group["hooks"])
            handlers = [handler for handler in group_hooks if not owned(handler, harness, event)]
            if handlers == group["hooks"]:
                retained.append(group)
            elif handlers:
                retained.append({**group, "hooks": handlers})
        if install:
            entry: dict[str, Json] = {
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
            hooks[name] = cast("list[Json]", retained)
        else:
            hooks.pop(name, None)
    if not hooks and changed:
        document.pop("hooks", None)
    return changed


def configure(harness: str, *, install: bool) -> Path:
    if os.name != "posix":
        raise GuardError("hook installation currently supports Linux and macOS")
    import fcntl  # noqa: PLC0415 -- unavailable on unsupported platforms.

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
                raise ValueError("root must be an object")  # noqa: TRY004
            if install:
                check_enabled(document, harness, path)
                install_config_protection()
            if not edit_hooks(document, harness, install=install):
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


def install_config_protection() -> None:
    destination = Path.home() / ".i-insist" / "i-insist.toml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    # NOTE: README's Protecting configuration describes provider-owned replacement.
    source = files("i_insist").joinpath("config-protection.toml").read_text()
    destination = destination.resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(source)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def check_enabled(document: dict[str, Json], harness: str, path: Path) -> None:
    """Reject explicit disables; trust decisions remain owned by the harness."""
    check_project_settings(harness)
    if harness == "claude":
        if document.get("disableAllHooks") is True or document.get("allowManagedHooksOnly") is True:
            raise GuardError("Claude hooks are disabled or managed-only; review /hooks and settings")
        return
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    config_path = root / "config.toml"
    config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    features = config.get("features", {})
    if features.get("hooks", features.get("codex_hooks", True)) is False:
        raise GuardError("Codex hooks are disabled in config.toml; enable hooks before migration")
    hooks = config.get("hooks", {})
    if hooks.get("allow_managed_hooks_only") is True:
        raise GuardError("Codex unmanaged hooks are disabled")
    states = hooks.get("state", {})
    registered = document.get("hooks", {})
    if not isinstance(registered, dict):
        raise GuardError("hooks must be an object")
    for event, groups in registered.items():
        if event not in EVENTS or not isinstance(groups, list):
            continue
        snake = {
            "PreToolUse": "pre_tool_use",
            "SessionStart": "session_start",
            "UserPromptSubmit": "user_prompt_submit",
        }[event]
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            group_hooks = cast("list[Json]", group["hooks"])
            for handler_index, handler in enumerate(group_hooks):
                if not owned(handler, harness, EVENTS[event]):
                    continue
                keys = [
                    f"{source}:{snake}:{group_index}:{handler_index}"
                    for source in {path, root / "hooks.json"}
                ]
                if any(states.get(key, {}).get("enabled") is False for key in keys):
                    raise GuardError("An i-insist hook is disabled in Codex; enable it with /hooks")


def check_project_settings(harness: str) -> None:
    # NOTE: README describes this conservative check of current ancestry.
    for parent in (*Path.cwd().parents, Path.cwd()):
        names = (
            (".codex/config.toml",)
            if harness == "codex"
            else (".claude/settings.json", ".claude/settings.local.json")
        )
        for name in names:
            path = parent / name
            if not path.exists():
                continue
            data = tomllib.loads(path.read_text()) if harness == "codex" else json.loads(path.read_text())
            if not isinstance(data, dict):
                raise GuardError(f"configuration must be an object: {path}")
            features = data.get("features", {})
            disabled = (
                features.get("hooks", features.get("codex_hooks", True)) is False
                if harness == "codex"
                else data.get("disableAllHooks") is True or data.get("allowManagedHooksOnly") is True
            )
            if disabled:
                raise GuardError(f"Hooks are disabled by {path}; enable them before migration")


def ensure() -> list[Path]:
    harnesses = [
        harness
        for harness in ("codex", "claude")
        if shutil.which(harness) or configuration_path(harness).exists()
    ]
    return [configure(harness, install=True) for harness in harnesses]
