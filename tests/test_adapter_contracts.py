"""Supported tool shapes and conditional post-check execution through CLI."""

import pytest

from tests.support import allowed, feedback, invoke, rule, tool


@pytest.mark.parametrize(
    ("harness", "name", "arguments", "kind", "command", "relative_cwd", "paths"),
    [
        ("claude", "Bash", {"command": "pwd"}, "shell", "pwd", "", []),
        (
            "codex",
            "exec_command",
            {"cmd": "pwd", "workdir": "first", "cwd": "ignored"},
            "shell",
            "pwd",
            "first",
            [],
        ),
        ("codex", "shell_command", {"command": "pwd", "cwd": "second"}, "shell", "pwd", "second", []),
        ("codex", "terminal", {"cmd": "pwd"}, "shell", "pwd", "", []),
        ("codex", "write_file", {"path": "a.txt", "content": "body"}, "file_write", None, "", ["a.txt"]),
        (
            "codex",
            "apply_patch",
            "*** Begin Patch\n*** Update File: a.txt\n*** Move to: b.txt\n@@\n-before\n+after\n*** End Patch",
            "file_edit",
            None,
            "",
            ["a.txt", "b.txt"],
        ),
    ],
)
def test_native_adapter_contracts(workspace, harness, name, arguments, kind, command, relative_cwd, paths):
    expected = {
        "kind": kind,
        "command": command,
        "cwd": str(workspace / relative_cwd),
        "paths": [str(workspace / path) for path in paths],
        "harness": harness,
        "tool_name": name,
        "tool_input": arguments,
        "tool_use_id": "call-1",
    }
    rule(
        workspace,
        f"import json, sys\nevent = json.load(sys.stdin)\n"
        f"assert {{key: event[key] for key in {list(expected)!r}}} == {expected!r}\nprint('null')",
    )
    payload = {**tool(workspace, name), "tool_input": arguments, "tool_use_id": "call-1"}
    allowed(invoke(workspace, payload, harness=harness))


@pytest.mark.parametrize("failure", ["denial", "error"])
def test_post_pairing_is_conditional_on_earlier_providers(workspace, failure):
    snapshot = workspace / "snapshot"
    rule(workspace, "from pathlib import Path\nPath('../snapshot').touch()\nprint('null')", name="b-pre")
    rule(
        workspace,
        "print('\"Earlier provider flagged call\"')"
        if failure == "denial"
        else "raise RuntimeError('broken')",
        name="a-post",
        extra='phase = "post"\n',
    )
    rule(
        workspace,
        "from pathlib import Path\nPath('../snapshot').unlink()\nprint('null')",
        name="b-post",
        extra='phase = "post"\n',
    )
    payload = {**tool(workspace), "tool_use_id": "call-1"}
    allowed(invoke(workspace, payload))
    assert snapshot.exists()
    message = feedback(invoke(workspace, payload, "post-tool-use"))
    assert ("Earlier provider flagged call" if failure == "denial" else "broken") in message
    assert snapshot.exists()
