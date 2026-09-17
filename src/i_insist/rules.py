"""Discover TOML rules and execute their provider-owned checkers."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from i_insist.events import Event, GuardError


@dataclass(frozen=True)
class Rule:
    id: str
    checker: tuple[str, ...]
    message: str
    directory: Path
    enabled: bool
    timeout: float


def config_files(event: Event) -> list[Path]:
    # NOTE: README documents additive ancestry, including explicit file targets.
    directories = [Path.home() / ".i-insist"]
    for location in (event.cwd, *(path.parent for path in event.paths)):
        directories.extend(parent / ".i-insist" for parent in reversed(location.parents))
        directories.append(location / ".i-insist")
    files: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        resolved = directory.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        # iterdir reports permission errors instead of silently omitting policy.
        try:
            children = list(resolved.iterdir())
        except FileNotFoundError:
            continue
        files.extend(sorted(path for path in children if path.suffix == ".toml" and path.is_file()))
    return files


def load_rules(path: Path) -> list[Rule]:
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
        if document.keys() - {"rules"}:
            raise ValueError("unknown top-level fields; expected [[rules]]")
        entries = document.get("rules", [])
        if not isinstance(entries, list):
            raise ValueError("rules must be an array of tables")
        result = []
        ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each rule must be a table")
            if entry.keys() - {"id", "checker", "message", "enabled", "timeout"}:
                raise ValueError("unknown rule fields")
            name, checker, message = (entry.get(key) for key in ("id", "checker", "message"))
            if not isinstance(name, str) or not name.strip() or name in ids:
                raise ValueError("each rule needs a nonempty id unique within its file")
            if not isinstance(message, str) or not message.strip():
                raise ValueError(f"{name}: message must be a nonempty string")
            if (
                not isinstance(checker, list)
                or not checker
                or any(not isinstance(arg, str) or "\0" in arg for arg in checker)
                or not checker[0]
            ):
                raise ValueError(
                    f"{name}: checker must be a nonempty argument list without NUL bytes"
                )
            enabled = entry.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError(f"{name}: enabled must be a boolean")
            timeout = entry.get("timeout", 10)
            if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
                raise ValueError(f"{name}: timeout must be a positive finite number")
            result.append(Rule(name, tuple(checker), message, path.parent, enabled, float(timeout)))
            ids.add(name)
        return result
    except (OSError, ValueError) as exc:
        raise GuardError(f"configuration {path}: {exc}") from exc


def run_checker(rule: Rule, event: Event) -> bool:
    try:
        payload = json.dumps(event.as_json(), allow_nan=False)
        with subprocess.Popen(
            rule.checker,
            cwd=rule.directory,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name == "posix",
        ) as process:
            try:
                stdout, stderr = process.communicate(
                    payload,
                    timeout=rule.timeout,
                )
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.communicate()
                raise GuardError(f"checker {rule.id}: timed out after {rule.timeout:g}s") from None
            if process.returncode:
                raise GuardError(
                    f"checker {rule.id}: exited {process.returncode}: {stderr.strip()[:1000]}"
                )
    except (OSError, UnicodeError, ValueError) as exc:
        raise GuardError(f"checker {rule.id}: {exc}") from exc
    try:
        result = json.loads(stdout)
    except ValueError:
        result = None
    if not isinstance(result, bool):
        raise GuardError(f"checker {rule.id}: checker must print a JSON boolean")
    return result


def check(event: Event) -> str | None:
    try:
        rules = [rule for path in config_files(event) for rule in load_rules(path)]
    except OSError as exc:
        raise GuardError(f"configuration discovery: {exc}") from exc
    for rule in rules:
        if rule.enabled and run_checker(rule, event):
            return rule.message
    return None
