"""Cooperative protection for the runner's own configuration directories."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from i_insist.events import Event  # noqa: TC001  # Beartype resolves annotation at runtime.


def should_block(event: Event) -> bool:
    if any(".i-insist" in path.parts for path in event.paths):
        return True
    if event.kind != "shell" or not event.command:
        return False
    # NOTE: Opaque programs can hide writes. This covers explicit paths and
    # common shell mutations; an OS sandbox is required for hostile agents.
    command = event.command
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return ".i-insist" in command
    touches = ".i-insist" in event.cwd.parts or any(".i-insist" in word for word in words)
    if not touches:
        touches = any(
            ".i-insist" in (event.cwd / Path(word).expanduser()).resolve().parts
            for word in words
            if word and "\n" not in word
        )
    mutates = any(
        Path(word).name
        in {
            "rm",
            "mv",
            "cp",
            "install",
            "touch",
            "mkdir",
            "rmdir",
            "tee",
            "truncate",
            "chmod",
            "chown",
            "ln",
            "patch",
        }
        or Path(word).name in {"python", "python3", "perl", "ruby", "node"}
        or re.fullmatch(r"python3\.\d+", Path(word).name)
        for word in words
    )
    return touches and (
        mutates
        or any(">" in word for word in words)
        or (any(Path(word).name == "sed" for word in words) and any(word.startswith("-i") for word in words))
    )
