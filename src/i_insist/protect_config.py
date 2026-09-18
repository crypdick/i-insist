"""Cooperative protection for the runner's own configuration directories."""

from __future__ import annotations

import ast
import re
import shlex
from pathlib import Path

from i_insist.events import Event  # noqa: TC001  # Beartype resolves annotation at runtime.

DENIAL_MESSAGE = (
    "Editing i-insist configuration requires human approval. Show the intended rule change "
    "and ask the human to say I insist. Do not modify rules to evade a block."
)

PYTHON = r"(?:\S*/)?python(?:3(?:\.\d+)?)?"


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


def should_block(event: Event) -> bool:
    if any(".i-insist" in path.parts for path in event.paths):
        return True
    if event.kind != "shell" or not event.command:
        return False
    # NOTE: Opaque programs can hide writes. This covers explicit paths and
    # common shell mutations; an OS sandbox is required for hostile agents.
    command = normalize_python_heredocs(event.command)
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return ".i-insist" in command
    for index in range(2, len(words)):
        if words[index - 1] == "-c" and re.fullmatch(PYTHON, words[index - 2]):
            words[index] = python_config_reference(words[index])
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
    redirects_to_config = any(
        ">" in word
        and index + 1 < len(words)
        and ".i-insist" in (event.cwd / Path(words[index + 1]).expanduser()).resolve().parts
        for index, word in enumerate(words)
    )
    return touches and (
        mutates
        or redirects_to_config
        or (any(Path(word).name == "sed" for word in words) and any(word.startswith("-i") for word in words))
    )
