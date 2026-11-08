"""Normalize public hook inputs without discarding native tool arguments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

type Json = bool | int | float | str | list[Json] | dict[str, Json] | None
type Kind = Literal["shell", "file_write", "file_edit", "other"]
type Phase = Literal["pre", "post"]


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
    path = requested_path(value, cwd)
    try:
        return path.resolve()
    except (OSError, RuntimeError) as exc:
        raise GuardError(f"cannot resolve path {str(path)!r}: {exc}") from exc


def requested_path(value: str, cwd: Path) -> Path:
    """Retain supplied path components, including symlinks and `..`."""
    try:
        return cwd / Path(value).expanduser()
    except RuntimeError as exc:
        raise GuardError(f"cannot expand path {value!r}: {exc}") from exc


@dataclass(frozen=True)
class FileChange:
    path: Path
    operation: Literal["write", "edit", "delete"]
    content: str

    def as_json(self) -> dict[str, Json]:
        return {"path": str(self.path), "operation": self.operation, "content": self.content}

    @classmethod
    def from_json(cls, value: Json, cwd: Path) -> FileChange:
        data = object_input(value)
        operation = data.get("operation")
        if operation not in ("write", "edit", "delete"):
            raise GuardError("input change operation must be write, edit, or delete")
        content = data.get("content")
        if not isinstance(content, str):
            raise GuardError("input change content must be text")
        return cls(
            absolute_path(text_field(data.get("path"), "change path"), cwd),
            cast('Literal["write", "edit", "delete"]', operation),
            content,
        )


@dataclass(frozen=True)
class Event:
    kind: Kind
    command: str | None
    cwd: Path
    paths: tuple[Path, ...]
    harness: str
    tool_name: str
    tool_input: Json
    changes: tuple[FileChange, ...] = ()
    tool_use_id: str | None = None
    requested_cwd: Path | None = None
    requested_paths: tuple[Path, ...] = ()

    def as_json(self) -> dict[str, Json]:
        return {
            "kind": self.kind,
            "command": self.command,
            "cwd": str(self.cwd),
            "paths": [str(path) for path in self.paths],
            "harness": self.harness,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "changes": [change.as_json() for change in self.changes],
            "tool_use_id": self.tool_use_id,
            "requested_cwd": str(self.requested_cwd or self.cwd),
            "requested_paths": [str(path) for path in self.requested_paths],
        }

    @classmethod
    def from_json(cls, value: Json) -> Event:
        data = object_input(value)
        kind = data.get("kind")
        if kind not in ("shell", "file_write", "file_edit", "other"):
            raise GuardError("input kind must be shell, file_write, file_edit, or other")
        cwd = absolute_path(text_field(data.get("cwd"), "cwd"), Path.cwd())
        supplied_cwd = requested_path(
            text_field(data.get("requested_cwd", data.get("cwd")), "requested_cwd"), Path.cwd()
        )
        paths = data.get("paths", [])
        if not isinstance(paths, list):
            raise GuardError("input paths must be an array")
        command = data.get("command")
        if kind == "shell":
            command = text_field(command, "command")
        elif command is not None:
            raise GuardError("input command must be null for non-shell tools")
        changes = data.get("changes", [])
        if not isinstance(changes, list):
            raise GuardError("input changes must be an array")
        parsed_changes = tuple(FileChange.from_json(change, cwd) for change in changes)
        tool_use_id = data.get("tool_use_id")
        targets = [absolute_path(text_field(path, "path"), cwd) for path in paths]
        targets.extend(change.path for change in parsed_changes)
        supplied_paths = data.get(
            "requested_paths", paths + [object_input(change).get("path") for change in changes]
        )
        if not isinstance(supplied_paths, list):
            raise GuardError("input requested_paths must be an array")
        return cls(
            cast("Kind", kind),
            command,
            cwd,
            tuple(dict.fromkeys(targets)),
            text_field(data.get("harness"), "harness"),
            text_field(data.get("tool_name"), "tool_name"),
            data.get("tool_input"),
            parsed_changes,
            None if tool_use_id is None else text_field(tool_use_id, "tool_use_id"),
            supplied_cwd,
            tuple(
                dict.fromkeys(
                    requested_path(text_field(path, "requested path"), supplied_cwd)
                    for path in supplied_paths
                )
            ),
        )


def patch_changes(patch: str, cwd: Path) -> tuple[FileChange, ...]:
    changes: list[FileChange] = []
    for line in patch.splitlines():
        if line.startswith(("*** Add File: ", "*** Update File: ", "*** Delete File: ")):
            action, target = line.split(": ", 1)
            operation = {
                "*** Add File": "write",
                "*** Update File": "edit",
                "*** Delete File": "delete",
            }[action]
            changes.append(
                FileChange(
                    requested_path(text_field(target, "patch path"), cwd),
                    cast('Literal["write", "edit", "delete"]', operation),
                    "",
                )
            )
        elif line.startswith("*** Move to: "):
            if not changes or changes[-1].operation != "edit":
                raise GuardError("input patch move needs an update target")
            source = changes[-1]
            changes[-1] = FileChange(source.path, "delete", "")
            destination = requested_path(text_field(line.removeprefix("*** Move to: "), "patch path"), cwd)
            changes.append(FileChange(destination, "write", source.content))
        elif line.startswith("+") and changes:
            change = changes[-1]
            changes[-1] = FileChange(change.path, change.operation, change.content + line[1:] + "\n")
    if not changes:
        raise GuardError("input patch contains no file targets")
    return tuple(FileChange(c.path, c.operation, c.content.removesuffix("\n")) for c in changes)


def file_content(arguments: dict[str, Json]) -> str:
    edits = arguments.get("edits")
    if edits is not None:
        if not isinstance(edits, list) or any(not isinstance(edit, dict) for edit in edits):
            raise GuardError("input edits must be an array of objects")
        return "\n".join(file_content(object_input(edit)) for edit in edits)
    content = arguments.get("content", arguments.get("new_string", arguments.get("new_source", "")))
    if not isinstance(content, str):
        raise GuardError("input file content must be text")
    return content


def normalize_hook(data: dict[str, Json], harness: str) -> Event:
    name = text_field(data.get("tool_name"), "tool_name")
    native = data.get("tool_input", {})
    arguments = native if isinstance(native, dict) else {}
    base = requested_path(text_field(data.get("cwd", str(Path.cwd())), "cwd"), Path.cwd())
    cwd = base
    kind: Kind = "other"
    command = None
    paths: list[Path] = []
    changes: tuple[FileChange, ...] = ()
    if name in {"Bash", "exec_command", "shell_command", "terminal"}:
        kind = "shell"
        workdir = arguments.get("workdir")
        if workdir is None:
            workdir = arguments.get("cwd")
        if workdir is not None:
            cwd = requested_path(text_field(workdir, "workdir"), base)
        command = text_field(arguments.get("command", arguments.get("cmd")), "command")
    elif name in {"Write", "write_file", "Edit", "MultiEdit", "NotebookEdit"}:
        kind = "file_write" if name in {"Write", "write_file"} else "file_edit"
        target = arguments.get("file_path", arguments.get("path", arguments.get("notebook_path")))
        paths.append(requested_path(text_field(target, "file_path"), cwd))
        changes = (
            FileChange(paths[0], "write" if kind == "file_write" else "edit", file_content(arguments)),
        )
    elif name == "apply_patch":
        kind = "file_edit"
        patch = native if isinstance(native, str) else arguments.get("command", arguments.get("patch"))
        patch = text_field(patch, "patch")
        changes = patch_changes(patch, cwd)
        paths = [change.path for change in changes]
    tool_use_id = data.get("tool_use_id")
    return Event(
        kind,
        command,
        absolute_path(str(cwd), Path.cwd()),
        tuple(dict.fromkeys(absolute_path(str(path), cwd) for path in paths)),
        harness,
        name,
        native,
        tuple(
            FileChange(absolute_path(str(change.path), cwd), change.operation, change.content)
            for change in changes
        ),
        tool_use_id if isinstance(tool_use_id, str) and tool_use_id else None,
        cwd,
        tuple(dict.fromkeys(paths)),
    )
