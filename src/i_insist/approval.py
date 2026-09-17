"""Human-message approval state and explicit shell-call overrides."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import tempfile
from pathlib import Path

from i_insist.events import Event, GuardError, Json, text_field


def prompt_approves(prompt: str) -> bool:
    # NOTE: README defines a standalone phrase, excluding fenced/quoted examples.
    fence: str | None = None
    for line in prompt.splitlines():
        stripped = line.strip()
        match = re.match(r"(`{3,}|~{3,})", stripped)
        if match:
            marker = match[0]
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if (
            fence is None
            and not line.startswith(("    ", "\t"))
            and re.fullmatch(
                r"i\s+insist[.!]?",
                stripped,
                flags=re.IGNORECASE,
            )
        ):
            return True
    return False


def shell_approved(event: Event) -> bool:
    if event.kind != "shell" or not event.command:
        return False
    # Inspect only leading literal assignments, never inherited process state.
    lexer = shlex.shlex(event.command, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""  # A comment must not become an override.
    try:
        for token in lexer:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
                return False
            if token == "HUMAN_PERMISSION_GRANTED=1":
                return True
    except ValueError:
        return False
    return False


class Approvals:
    def __init__(self, harness: str, session_id: str) -> None:
        root = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
        key = hashlib.sha256(f"{harness}\0{session_id}".encode()).hexdigest()
        self.path = root / "i-insist" / "approvals" / f"{key}.json"

    def record(self, approved: bool, turn_id: str | None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.path.parent,
                prefix=".approval-",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump({"approved": approved, "turn_id": turn_id}, stream)
            temporary.replace(self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def reset(self) -> None:
        self.path.unlink(missing_ok=True)

    def allows(self, turn_id: str | None) -> bool:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return False
        return isinstance(data, dict) and data.get("approved") is True and data.get("turn_id") == turn_id


def context(
    data: dict[str, Json], harness: str, *, required: bool = False
) -> tuple[Approvals | None, str | None]:
    session = data.get("session_id")
    turn = data.get("turn_id")
    if turn is not None:
        turn = text_field(turn, "turn_id")
    if session is None and not required:
        return None, turn
    if session is None:
        raise GuardError("input session_id is required for approval hooks")
    return Approvals(harness, text_field(session, "session_id")), turn
