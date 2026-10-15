"""Cooperative protection for the runner's own configuration directories."""

from __future__ import annotations

import ast
import os
import re
import shlex
from collections.abc import Sequence  # noqa: TC003  # Beartype resolves annotation at runtime.
from pathlib import Path

from i_insist.events import Event  # noqa: TC001  # Beartype resolves annotation at runtime.

DENIAL_MESSAGE = (
    "Editing i-insist configuration requires human approval. Show the intended rule change "
    "and ask the human to say I insist. Do not modify rules to evade a block."
)

PYTHON = r"(?:\S*/)?python(?:3(?:\.\d+)?)?"
OPAQUE_WORD = re.compile(r"[\s'\"`$*?\[\](){}\\]")
MUTATORS = frozenset(
    {
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
)
INTERPRETERS = frozenset({"python", "python3", "perl", "ruby", "node"})


def python_config_reference(source: str) -> str:
    """Inspect literal paths without treating replacement source text as paths."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    # Keep the conservative check when strings can become executable code.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if name in {
                "exec",
                "eval",
                "compile",
                "system",
                "popen",
                "Popen",
                "run",
                "call",
                "check_call",
                "check_output",
            }:
                return source
    # NOTE: README.md documents this cooperative, literal-path check. Arbitrary
    # Python data flow and opaque programs still require an OS sandbox.
    return (
        ".i-insist"
        if any(
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and ".i-insist" in Path(node.value).parts
            for node in ast.walk(tree)
        )
        else ""
    )


def normalize_python_heredocs(command: str) -> str:
    """Quote recognized literal Python heredocs before shell tokenization."""
    return re.sub(
        rf"(?m)^(?P<python>{PYTHON})[ \t]+(?:-[ \t]+)?"
        r"<<[ \t]*(?P<quote>['\"])(?P<delimiter>\w+)(?P=quote)[ \t]*\n"
        r"(?P<source>[\s\S]*?)\n(?P=delimiter)(?=\n|$)",
        lambda match: f"{match['python']} -c {shlex.quote(match['source'])}",
        command,
    )


def block_reason(event: Event) -> str | None:
    """Name what matched, so a false positive can be rephrased instead of abandoned."""
    for path in event.paths:
        if ".i-insist" in path.parts:
            return f"path {str(path)!r}"
    if event.kind != "shell" or not event.command:
        return None
    # Every directory a literal `cd` may have reached stays suspect for later commands.
    cwds = [event.cwd]
    for part in shell_commands(normalize_python_heredocs(event.command)):
        target = cd_target(part, cwds[-1])
        if target is not None:
            cwds.append(target)
        if reason := shell_command_blocks(part, cwds):
            return reason
    return None


def cd_target(command: str, cwd: Path) -> Path | None:
    """Resolve a literal `cd`; computed targets keep the conservative word checks."""
    try:
        words = shlex.split(command, comments=True)
    except ValueError:
        return None
    if not words or words[0] != "cd" or "-" in words:
        return None
    args = [word for word in words[1:] if not word.startswith("-")]
    target = args[0] if args else "~"
    if len(args) > 1 or "$" in target:
        return None
    return (cwd / os.path.expanduser(target)).resolve()  # noqa: PTH111 - Unknown users stay literal.


def shell_commands(command: str) -> list[str]:
    """Separate simple commands without splitting quoted or escaped separators."""
    # Shared shell state, nested execution, and heredocs retain the whole-call check.
    if any(marker in command for marker in ("$(", "`", "<<", "<(", ">(")):
        return [command]
    try:
        words = shlex.split(command, comments=True)
    except ValueError:
        return [command]
    if any(
        word in {"pushd", "popd", "for", "while", "until", "if", "case", "eval", "source", "."}
        or re.match(r"[a-zA-Z_][a-zA-Z_0-9]*=", word)
        for word in words
    ):
        return [command]
    parts = []
    start = 0
    tokens = (
        r"""'[^']*'|"(?:\\[\s\S]|[^"\\])*"|\\[\s\S]|\#[^\n]*"""
        r"|(?P<group>[(){}])|(?P<boundary>[;\n]+|(?<![<>])[&|](?![<>]))"
    )
    for match in re.finditer(tokens, command):
        if match.lastgroup == "group":
            return [command]
        if match.lastgroup == "boundary":
            parts.append(command[start : match.start()])
            start = match.end()
    parts.append(command[start:])
    return parts


def names_config(word: str) -> bool:
    """Match `.i-insist` as a path component; free text and globs may hide a path."""
    if ".i-insist" not in word:
        return False
    return OPAQUE_WORD.search(word) is not None or ".i-insist" in Path(word).parts


def resolves_to_config(word: str, cwds: Sequence[Path]) -> bool:
    return (
        bool(word)
        and "\n" not in word
        and any(
            ".i-insist" in (cwd / os.path.expanduser(word)).resolve().parts  # noqa: PTH111 - Unknown users stay literal.
            for cwd in cwds
        )
    )


def shell_command_blocks(command: str, cwds: Sequence[Path]) -> str | None:
    """Return why one simple command edits protected configuration, if it does."""
    # NOTE: Opaque programs can hide writes. This covers explicit paths and
    # common shell mutations; an OS sandbox is required for hostile agents.
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return "unparseable command mentioning '.i-insist'" if ".i-insist" in command else None
    for index in range(2, len(words)):
        if words[index - 1] == "-c" and re.fullmatch(PYTHON, words[index - 2]):
            words[index] = python_config_reference(words[index])
    touched = (
        next((f"working directory {str(cwd)!r}" for cwd in cwds if ".i-insist" in cwd.parts), None)
        or next((repr(word) for word in words if names_config(word)), None)
        or next((repr(word) for word in words if resolves_to_config(word, cwds)), None)
    )
    if touched is None:
        return None
    mutator = next(
        (
            word
            for word in words
            if Path(word).name in MUTATORS | INTERPRETERS or re.fullmatch(r"python3\.\d+", Path(word).name)
        ),
        None,
    )
    if mutator is not None:
        return f"{touched} with command {mutator!r}"
    redirect = next(
        (
            words[index + 1]
            for index, word in enumerate(words)
            if ">" in word and index + 1 < len(words) and resolves_to_config(words[index + 1], cwds)
        ),
        None,
    )
    if redirect is not None:
        return f"redirect to {redirect!r}"
    if any(Path(word).name == "sed" for word in words) and any(word.startswith("-i") for word in words):
        return f"{touched} with 'sed -i'"
    return None
