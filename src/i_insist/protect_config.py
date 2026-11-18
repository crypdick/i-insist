"""Protect structured paths and bounded literal shell writes."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Sequence  # noqa: TC003  # Beartype resolves annotation at runtime.
from pathlib import Path

from i_insist.events import Event  # noqa: TC001  # Beartype resolves annotation at runtime.
from i_insist.rules import config_directories, config_files

DENIAL_MESSAGE = (
    "Editing i-insist configuration requires human approval. Show the intended rule change "
    "and ask the human to say I insist. Do not modify rules to evade a block."
)

# Deliberately unsupported, even inside quotes. No whole-command fallback.
# Supported commands and limits are documented in docs/reference.md.
OPAQUE_SYNTAX = frozenset("\n\r\x00;$`\\&|<(){}*?[]#")
MUTATORS = frozenset({"rm", "rmdir", "mkdir", "touch", "tee", "mv", "cp", "install", "ln"})
RM_OPTIONS = frozenset({"-r", "-R", "-f", "-rf", "-fr", "-Rf", "-fR", "--recursive", "--force"})
WORD = r"""(?:'[^']*'|"[^"]*"|[^\s'"<>]+)"""
SIMPLE_COMMAND = re.compile(rf"\s*(?P<command>{WORD}(?:\s+{WORD})*)(?:\s*>>?\s*(?P<target>{WORD}))?\s*")


def block_reason(event: Event) -> str | None:
    """Check explicit targets without interpreting opaque shell programs."""
    # Keep both identities: a symlink must not discard the protected lexical name
    # or the physical identity of an applicable configuration directory or file.
    protected = (*config_directories(event), *(path.resolve() for path in config_files(event)))
    for path in (*event.paths, *event.requested_paths):
        if is_config_path(path, protected):
            return f"path {str(path)!r}"
    if event.kind == "shell" and event.command:
        for target in literal_write_targets(event.command):
            path = (event.requested_cwd or event.cwd) / os.path.expanduser(target)  # noqa: PTH111 - Unknown users stay literal.
            if is_config_path(path, protected) or is_config_path(path.resolve(), protected):
                return f"shell write target {target!r}"
    return None


def is_config_path(path: Path, protected: Sequence[Path]) -> bool:
    return ".i-insist" in path.parts or any(path.is_relative_to(root) for root in protected)


def literal_write_targets(command: str) -> list[str]:
    """Recognize one simple command; unsupported syntax contributes no targets."""
    if any(char in OPAQUE_SYNTAX for char in command):
        return []
    # Require whole literal words and at most one trailing redirection. The grammar
    # excludes quote concatenation and preserves `echo '>' path` as plain arguments.
    match = SIMPLE_COMMAND.fullmatch(command)
    if match is None:
        return []
    words = shlex.split(match["command"])
    targets = shlex.split(match["target"]) if match["target"] is not None else []
    if Path(words[0]).name not in MUTATORS:
        return targets
    name = Path(words[0]).name
    arguments = []
    options = True
    for word in words[1:]:
        if options and word == "--":
            options = False
        elif options and word.startswith("-"):
            if name != "rm" or word not in RM_OPTIONS:
                return targets
        else:
            arguments.append(word)
    if name in {"cp", "install", "ln"}:
        return targets + arguments[-1:] if len(arguments) >= 2 else targets
    return targets + arguments
