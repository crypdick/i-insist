"""Neutral file changes through public hook and checker commands."""

import json
import subprocess
import sys

import pytest

from tests.support import allowed, denial, invoke, rule, tool


@pytest.mark.parametrize(
    ("name", "arguments", "changes"),
    [
        ("Write", {"file_path": "a.md", "content": "body"}, [("a.md", "write", "body")]),
        ("Edit", {"file_path": "a.md", "new_string": "new"}, [("a.md", "edit", "new")]),
        (
            "MultiEdit",
            {"file_path": "a.md", "edits": [{"new_string": "one"}, {"new_string": "two"}]},
            [("a.md", "edit", "one\ntwo")],
        ),
        (
            "NotebookEdit",
            {"notebook_path": "a.ipynb", "new_source": "print(1)"},
            [("a.ipynb", "edit", "print(1)")],
        ),
        (
            "apply_patch",
            {
                "patch": (
                    "*** Begin Patch\n*** Update File: a.md\n*** Move to: b.md\n@@\n-old\n+new\n"
                    "*** Add File: c.md\n+created\n*** Delete File: d.md\n*** End Patch"
                )
            },
            [
                ("a.md", "delete", ""),
                ("b.md", "write", "new"),
                ("c.md", "write", "created"),
                ("d.md", "delete", ""),
            ],
        ),
    ],
)
def test_checker_receives_neutral_file_changes(workspace, name, arguments, changes):
    expected = [
        {"path": str(workspace / path), "operation": operation, "content": content}
        for path, operation, content in changes
    ]
    rule(
        workspace,
        f"import json, sys\nassert json.load(sys.stdin)['changes'] == {expected!r}\nprint('false')",
    )
    allowed(invoke(workspace, tool(workspace, name, **arguments)))


def test_custom_harness_changes_reach_checker_and_target_rules(workspace):
    target = workspace / "protected"
    target.mkdir()
    rule(
        target,
        "import json, sys\nprint(json.dumps(json.load(sys.stdin)['changes'][0]['content'] == 'blocked'))",
    )
    event = {
        "kind": "file_write",
        "cwd": str(workspace),
        "harness": "custom",
        "tool_name": "save",
        "changes": [{"path": "protected/note.md", "operation": "write", "content": "blocked"}],
    }
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "check"],
        input=json.dumps(event),
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"blocked": True, "message": "Blocked by guard"}


@pytest.mark.parametrize(
    "change",
    [
        None,
        {"path": "note.md", "operation": "bad", "content": ""},
        {"path": "note.md", "operation": "write", "content": 42},
        {"path": "", "operation": "write", "content": ""},
    ],
)
def test_neutral_check_rejects_invalid_changes(workspace, change):
    event = {
        "kind": "file_write",
        "cwd": str(workspace),
        "harness": "custom",
        "tool_name": "save",
        "changes": [change],
    }
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "check"],
        input=json.dumps(event),
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["blocked"] is True


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("Write", {"file_path": "a.md", "content": None}),
        ("MultiEdit", {"file_path": "a.md", "edits": [None]}),
        ("apply_patch", {"patch": "*** Begin Patch\n*** Move to: a.md\n*** End Patch"}),
    ],
)
def test_invalid_native_file_changes_fail_closed(workspace, name, arguments):
    assert "input" in denial(invoke(workspace, tool(workspace, name, **arguments)))
