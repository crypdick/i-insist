"""Normalize public hook inputs without discarding native tool arguments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
type Kind = Literal["shell", "file_write", "file_edit", "other"]


class GuardError(Exception):
    """An invalid request, configuration, or checker execution."""


def object_input(value: Json) -> dict[str, Json]:
    if not isinstance(value, dict):
        raise GuardError("input must be a JSON object")
    return value


def text_field(value: Json, name: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise GuardError(f"input {name} must be a nonempty string without NUL bytes")
    return value


def absolute_path(value: str, cwd: Path) -> Path:
    return (cwd / Path(value).expanduser()).resolve()


@dataclass(frozen=True)
class Event:
    kind: Kind
    command: str | None
    cwd: Path
    paths: tuple[Path, ...]
    harness: str
    tool_name: str
    tool_input: Json

    def as_json(self) -> dict[str, Json]:
        return {
            "kind": self.kind,
            "command": self.command,
            "cwd": str(self.cwd),
            "paths": [str(path) for path in self.paths],
            "harness": self.harness,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
        }

    @classmethod
    def from_json(cls, value: Json) -> Event:
        data = object_input(value)
        kind = data.get("kind")
        if kind not in ("shell", "file_write", "file_edit", "other"):
            raise GuardError("input kind must be shell, file_write, file_edit, or other")
        cwd = absolute_path(text_field(data.get("cwd"), "cwd"), Path.cwd())
        paths = data.get("paths", [])
        if not isinstance(paths, list):
            raise GuardError("input paths must be an array")
        command = data.get("command")
        if kind == "shell":
            command = text_field(command, "command")
        elif command is not None:
            raise GuardError("input command must be null for non-shell tools")
        return cls(
            cast(Kind, kind),
            command,
            cwd,
            tuple(absolute_path(text_field(path, "path"), cwd) for path in paths),
            text_field(data.get("harness"), "harness"),
            text_field(data.get("tool_name"), "tool_name"),
            data.get("tool_input"),
        )


def normalize_hook(data: dict[str, Json], harness: str) -> Event:
    name = text_field(data.get("tool_name"), "tool_name")
    native = data.get("tool_input", {})
    arguments = native if isinstance(native, dict) else {}
    base = absolute_path(text_field(data.get("cwd", str(Path.cwd())), "cwd"), Path.cwd())
    cwd = base
    kind: Kind = "other"
    command = None
    paths: list[Path] = []
    if name in {"Bash", "exec_command", "shell_command", "terminal"}:
        kind = "shell"
        workdir = arguments.get("workdir")
        if workdir is None:
            workdir = arguments.get("cwd")
        if workdir is not None:
            cwd = absolute_path(text_field(workdir, "workdir"), base)
        command = text_field(arguments.get("command", arguments.get("cmd")), "command")
    elif name in {"Write", "write_file", "Edit", "MultiEdit", "NotebookEdit"}:
        kind = "file_write" if name in {"Write", "write_file"} else "file_edit"
        target = arguments.get("file_path", arguments.get("path", arguments.get("notebook_path")))
        paths.append(absolute_path(text_field(target, "file_path"), cwd))
    elif name == "apply_patch":
        kind = "file_edit"
        patch = (
            native if isinstance(native, str) else arguments.get("command", arguments.get("patch"))
        )
        patch = text_field(patch, "patch")
        for line in patch.splitlines():
            for prefix in (
                "*** Add File: ",
                "*** Update File: ",
                "*** Delete File: ",
                "*** Move to: ",
            ):
                if line.startswith(prefix):
                    target = text_field(line.removeprefix(prefix).strip(), "patch path")
                    paths.append(absolute_path(target, cwd))
        if not paths:
            raise GuardError("input patch contains no file targets")
    return Event(kind, command, cwd, tuple(dict.fromkeys(paths)), harness, name, native)
