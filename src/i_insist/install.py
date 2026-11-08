"""Install and remove only i-insist's hooks in native harness configuration."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import stat
import tempfile
import tomllib
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
from typing import cast

from i_insist.events import GuardError, Json, absolute_path

EVENTS = {
    "PreToolUse": "pre-tool-use",
    "PostToolUse": "post-tool-use",
    "UserPromptSubmit": "user-prompt-submit",
    "SessionStart": "session-start",
}
# Claude reports failed tool calls, including nonzero shell exits, only through this event.
CLAUDE_EVENTS = {**EVENTS, "PostToolUseFailure": "post-tool-use-failure"}
TOOL_HOOKS = {"PreToolUse", "PostToolUse", "PostToolUseFailure"}


def configuration_path(harness: str) -> Path:
    if harness == "codex":
        root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        return absolute_path(str(root / "hooks.json"), Path.cwd())
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    return absolute_path(str(root / "settings.json"), Path.cwd())


def _configuration_lock_path(path: Path) -> Path:
    # NOTE: docs/reference.md, Hook registration documents location and path identity.
    root = Path(
        os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    ).expanduser()
    if not root.is_absolute():
        raise GuardError(f"lock directory must be absolute: {root}")
    directory = root / "i-insist" / "locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise GuardError(f"lock directory must be an owned, private directory (0700): {directory}")
    key = hashlib.sha256(os.fsencode(path)).hexdigest()
    return directory / f"{key}.lock"


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
    for name, event in (CLAUDE_EVENTS if harness == "claude" else EVENTS).items():
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
                        "timeout": 600 if name in TOOL_HOOKS else 10,
                    }
                ]
            }
            if name in TOOL_HOOKS:
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
    lock_path = _configuration_lock_path(path)
    with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            original = path.read_text() if path.exists() else None
            document = json.loads(original) if original is not None else {}
            if not isinstance(document, dict):
                raise ValueError("root must be an object")  # noqa: TRY004
            prospective = deepcopy(document)
            changed = edit_hooks(prospective, harness, install=install)
            for settings_path, settings in settings_documents(harness, path, document):
                states = check_settings(settings, harness, settings_path, install=install)
                if harness == "codex":
                    check_indexed_state(document, prospective, path, states, install=install)
            if install:
                install_config_protection()
            if not changed:
                return path
            updated = json.dumps(prospective, indent=2) + "\n"
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
    # NOTE: docs/reference.md's Protecting configuration describes provider-owned replacement.
    source = files("i_insist").joinpath("config-protection.toml").read_text()
    destination = absolute_path(str(destination), Path.cwd())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(source)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def mapping_field(document: dict[str, Json], name: str) -> dict[str, Json]:
    value = document.get(name, {})
    if not isinstance(value, dict):
        raise GuardError(f"{name} must be an object")
    return value


def settings_documents(
    harness: str, configuration: Path, document: dict[str, Json]
) -> list[tuple[Path, dict[str, Json]]]:
    # NOTE: docs/reference.md describes this conservative check of current ancestry.
    paths = [configuration]
    if harness == "codex":
        root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
        paths = [root / "config.toml"]
    for parent in (*Path.cwd().parents, Path.cwd()):
        names = (
            (".codex/config.toml",)
            if harness == "codex"
            else (".claude/settings.json", ".claude/settings.local.json")
        )
        paths.extend(parent / name for name in names)
    result = []
    for path in dict.fromkeys(absolute_path(str(path), Path.cwd()) for path in paths):
        if path == configuration:
            data = document
        elif path.exists():
            data = tomllib.loads(path.read_text()) if harness == "codex" else json.loads(path.read_text())
        else:
            continue
        if not isinstance(data, dict):
            raise GuardError(f"configuration must be an object: {path}")
        result.append((path, data))
    return result


def check_settings(document: dict[str, Json], harness: str, path: Path, *, install: bool) -> dict[str, Json]:
    if harness == "claude":
        disabled = document.get("disableAllHooks") is True or document.get("allowManagedHooksOnly") is True
        states: dict[str, Json] = {}
    else:
        features = mapping_field(document, "features")
        hooks = mapping_field(document, "hooks")
        states = mapping_field(hooks, "state")
        for key in states:
            mapping_field(states, key)
        disabled = (
            features.get("hooks", features.get("codex_hooks", True)) is False
            or hooks.get("allow_managed_hooks_only") is True
        )
    if install and disabled:
        raise GuardError(f"Hooks are disabled by {path}; enable them before migration")
    return states


def indexed_handlers(document: dict[str, Json]) -> dict[tuple[str, int, int], tuple[Json, Json]]:
    result = {}
    for event, groups in mapping_field(document, "hooks").items():
        if event not in EVENTS:
            continue
        for group_index, group in enumerate(cast("list[dict[str, Json]]", groups)):
            for handler_index, handler in enumerate(cast("list[Json]", group["hooks"])):
                result[event, group_index, handler_index] = (group.get("matcher"), handler)
    return result


def check_indexed_state(
    original: dict[str, Json],
    prospective: dict[str, Json],
    path: Path,
    states: dict[str, Json],
    *,
    install: bool,
) -> None:
    before, after = indexed_handlers(original), indexed_handlers(prospective)
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    for coordinate in before.keys() | after.keys():
        event, group, handler = coordinate
        snake = EVENTS[event].replace("-", "_")
        entries = [
            mapping_field(states, f"{source}:{snake}:{group}:{handler}")
            for source in {path, root / "hooks.json"}
            if f"{source}:{snake}:{group}:{handler}" in states
        ]
        if not entries:
            continue
        old, new = before.get(coordinate), after.get(coordinate)
        if (
            install
            and any(entry.get("enabled") is False for entry in entries)
            and any(value and owned(value[1], "codex", EVENTS[event]) for value in (old, new))
        ):
            raise GuardError("An i-insist hook is disabled in Codex; enable it with /hooks")
        if old != new and not (new is None and old and owned(old[1], "codex", EVENTS[event])):
            raise GuardError("Changing indexed hook state requires manual review with /hooks")


def ensure() -> list[Path]:
    harnesses = [
        harness
        for harness in ("codex", "claude")
        if shutil.which(harness) or configuration_path(harness).exists()
    ]
    return [configure(harness, install=True) for harness in harnesses]
