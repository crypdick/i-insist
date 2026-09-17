from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import allowed, denial, hook_path, invoke, manage_hooks, rule, tool


@pytest.mark.parametrize("harness", ["codex", "claude"])
def test_checker_blocks_with_exact_custom_message(workspace: Path, harness: str):
    rule(workspace, "print('true')")
    assert denial(invoke(workspace, tool(workspace, command="git status"), harness=harness)) == (
        "Blocked by guard"
    )


def test_no_rules_allows_arbitrary_tools(workspace: Path):
    allowed(invoke(workspace, tool(workspace, "mcp__calendar__create", title="Lunch")))


def test_false_and_disabled_checkers_allow(workspace: Path):
    rule(workspace, "print('false')", name="allow")
    rule(workspace, "raise RuntimeError('must not run')", extra="enabled = false\n")
    allowed(invoke(workspace, tool(workspace, command="git status")))


def test_global_ancestor_and_local_rules_accumulate_once(workspace: Path):
    calls = workspace / "calls"
    script = (
        f"from pathlib import Path\nwith Path({str(calls)!r}).open('a') as f: f.write('x')\nprint('false')"
    )
    rule(workspace.parent, script, name="global")
    rule(workspace, script, name="repo")
    nested = workspace / "src"
    nested.mkdir()
    rule(nested, "print('true')", name="nested")
    assert denial(invoke(workspace, tool(nested, command="pwd"))) == "Blocked by nested"
    assert calls.read_text() == "xx"


def test_configs_are_not_discovered_recursively(workspace: Path):
    scripts = workspace / ".i-insist" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "not-a-rule.toml").write_text("invalid TOML !!")
    allowed(invoke(workspace, tool(workspace, command="true")))


def test_checker_receives_operation_cwd_but_runs_beside_config(workspace: Path):
    rule(
        workspace,
        """import json, os, sys
event = json.load(sys.stdin)
assert os.path.basename(os.getcwd()) == '.i-insist'
assert event['kind'] == 'shell'
assert event['command'] == 'git status'
assert event['harness'] == 'codex'
assert event['tool_name'] == 'Bash'
assert event['tool_input']['command'] == 'git status'
assert event['cwd'].endswith('/repo/src')
print('true')
""",
    )
    nested = workspace / "src"
    nested.mkdir()
    assert denial(invoke(workspace, tool(workspace, command="git status", workdir=str(nested)))) == (
        "Blocked by guard"
    )


@pytest.mark.parametrize(
    ("name", "arguments", "kind", "filenames"),
    [
        ("Write", {"file_path": "notes.md", "content": "hello"}, "file_write", ["notes.md"]),
        ("Edit", {"file_path": "notes.md", "new_string": "hello"}, "file_edit", ["notes.md"]),
        ("NotebookEdit", {"notebook_path": "a.ipynb"}, "file_edit", ["a.ipynb"]),
        ("MultiEdit", {"file_path": "a.py", "edits": []}, "file_edit", ["a.py"]),
        (
            "apply_patch",
            {
                "command": (
                    "*** Begin Patch\n*** Update File: a.py\n*** Move to: b.py\n"
                    "*** Add File: c.py\n*** Delete File: d.py\n*** End Patch"
                )
            },
            "file_edit",
            ["a.py", "b.py", "c.py", "d.py"],
        ),
        ("mcp__custom__action", {"nested": {"foo": 42}}, "other", []),
    ],
)
def test_normalized_input_preserves_native_arguments(workspace, name, arguments, kind, filenames):
    expected_paths = [str(workspace / name) for name in filenames]
    rule(
        workspace,
        f"""import json, sys
event = json.load(sys.stdin)
assert event['kind'] == {kind!r}
assert event['paths'] == {expected_paths!r}
assert event['tool_input'] == {arguments!r}
print('true')
""",
    )
    assert denial(invoke(workspace, tool(workspace, name, **arguments))) == "Blocked by guard"


def test_target_directory_rules_apply_to_edits_from_outside(workspace: Path):
    protected = workspace / "protected"
    protected.mkdir()
    rule(protected, "print('true')")
    assert denial(invoke(workspace, tool(workspace, "Write", file_path="protected/a.txt"))) == (
        "Blocked by guard"
    )


@pytest.mark.parametrize("output", ["1", "null", "{}", "true\nfalse", "not json"])
def test_invalid_checker_results_block(workspace: Path, output: str):
    rule(workspace, f"print({output!r})")
    assert "checker must print a JSON boolean" in denial(invoke(workspace, tool(workspace)))


@pytest.mark.parametrize("script", ["raise RuntimeError('broken')", "import time; time.sleep(2)"])
def test_checker_crash_or_timeout_blocks(workspace: Path, script: str):
    rule(workspace, script, extra="timeout = 0.1\n")
    assert "checker" in denial(invoke(workspace, tool(workspace)))


@pytest.mark.parametrize("extra", ["enabled = 'false'", "timeout = -1", "unknown = true"])
def test_bad_rule_config_blocks(workspace: Path, extra: str):
    rule(workspace, "print('false')", extra=extra)
    assert "configuration" in denial(invoke(workspace, tool(workspace)))


def test_missing_checker_blocks(workspace: Path):
    config = rule(workspace, "print('false')")
    (workspace / "guard.py").unlink()
    assert "checker" in denial(invoke(workspace, tool(workspace)))
    config.write_text("not valid = TOML !")
    assert "configuration" in denial(invoke(workspace, tool(workspace)))


def test_prompt_approval_allows_multiple_edits_then_resets(workspace: Path):
    rule(workspace, "print('true')")
    payload = tool(workspace, "Write", file_path="a.txt")
    allowed(invoke(workspace, {**payload, "prompt": "I insist.\nEdit both files."}, "user-prompt-submit"))
    allowed(invoke(workspace, payload))
    allowed(invoke(workspace, {**payload, "tool_input": {"file_path": "b.txt"}}))
    allowed(invoke(workspace, {**payload, "prompt": "Now do something else."}, "user-prompt-submit"))
    assert denial(invoke(workspace, payload)) == "Blocked by guard"


@pytest.mark.parametrize("harness", ["codex", "claude"])
@pytest.mark.parametrize("approval", ["prompt", "shell"])
def test_non_overridable_rules_still_run(workspace: Path, harness: str, approval: str):
    rule(workspace, "raise RuntimeError('approved rule must not run')", name="a-ordinary")
    rule(workspace, "print('true')", name="protected", extra="overridable = false\n")
    payload = tool(workspace, command="HUMAN_PERMISSION_GRANTED=1 true" if approval == "shell" else "true")
    if approval == "prompt":
        allowed(invoke(workspace, {**payload, "prompt": "I insist"}, "user-prompt-submit", harness=harness))
    assert denial(invoke(workspace, payload, harness=harness)) == "Blocked by protected"


def test_disabled_non_overridable_rule_does_not_run(workspace: Path):
    rule(workspace, "raise RuntimeError('disabled')", extra="enabled = false\noverridable = false\n")
    allowed(invoke(workspace, tool(workspace)))


def test_overridable_requires_boolean(workspace: Path):
    rule(workspace, "print('false')", extra="overridable = 'false'\n")
    assert "overridable must be a boolean" in denial(invoke(workspace, tool(workspace)))


@pytest.mark.parametrize(
    "prompt",
    [
        "Explain 'I insist'",
        "Do not use I insist.",
        "```\nI insist\n```",
        "> I insist",
        "I insist on naming it well.",
    ],
)
def test_mentions_and_quoted_phrases_are_not_approval(workspace: Path, prompt: str):
    rule(workspace, "print('true')")
    payload = tool(workspace, "Write", file_path="a.txt")
    allowed(invoke(workspace, {**payload, "prompt": prompt}, "user-prompt-submit"))
    assert denial(invoke(workspace, payload)) == "Blocked by guard"


def test_approval_does_not_cross_sessions_turns_or_harnesses(workspace: Path):
    rule(workspace, "print('true')")
    payload = tool(workspace, "Write", file_path="a.txt")
    allowed(invoke(workspace, {**payload, "prompt": "i insist!"}, "user-prompt-submit"))
    for changed in ({"session_id": "other"}, {"turn_id": "turn-2"}):
        assert denial(invoke(workspace, {**payload, **changed})) == "Blocked by guard"
    assert denial(invoke(workspace, payload, harness="claude")) == "Blocked by guard"


def test_claude_approval_without_turn_id(workspace: Path):
    rule(workspace, "print('true')")
    payload = tool(workspace, "Write", file_path="a.txt")
    del payload["turn_id"]
    allowed(invoke(workspace, {**payload, "prompt": "I insist"}, "user-prompt-submit", harness="claude"))
    allowed(invoke(workspace, payload, harness="claude"))
    assert (
        invoke(workspace, {**payload, "source": "compact"}, "session-start", harness="claude").returncode == 0
    )
    allowed(invoke(workspace, payload, harness="claude"))
    assert (
        invoke(workspace, {**payload, "source": "resume"}, "session-start", harness="claude").returncode == 0
    )
    assert denial(invoke(workspace, payload, harness="claude")) == "Blocked by guard"


def test_inline_marker_only_applies_to_that_shell_invocation(workspace: Path, monkeypatch):
    rule(workspace, "print('true')")
    allowed(invoke(workspace, tool(workspace, command="HUMAN_PERMISSION_GRANTED=1 git status")))
    assert denial(invoke(workspace, tool(workspace, command="git status"))) == "Blocked by guard"
    for command in (
        "echo HUMAN_PERMISSION_GRANTED=1",
        "HUMAN_PERMISSION_GRANTED=0 git status",
        "# HUMAN_PERMISSION_GRANTED=1\ngit status",
    ):
        assert denial(invoke(workspace, tool(workspace, command=command))) == "Blocked by guard"
    monkeypatch.setenv("HUMAN_PERMISSION_GRANTED", "1")
    assert denial(invoke(workspace, tool(workspace, command="git status"))) == "Blocked by guard"


def test_malformed_hook_input_blocks(workspace: Path):
    for payload in ([], {"tool_name": 123}, {"tool_name": "Bash", "tool_input": {"command": 1}}):
        assert "input" in denial(invoke(workspace, payload))


def test_neutral_check_protocol(workspace: Path):
    rule(workspace, "print('true')")
    event = {
        "kind": "other",
        "command": None,
        "paths": [],
        "cwd": str(workspace),
        "harness": "custom",
        "tool_name": "send_email",
        "tool_input": {"to": "example"},
    }
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "check"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=workspace,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"blocked": True, "message": "Blocked by guard"}


def test_unknown_tool_arguments_are_not_interpreted_as_shell_metadata(workspace: Path):
    rule(workspace, "print('true')")
    payload = tool(workspace, "mcp__custom__action", cwd=42, workdir=["unrelated"])
    assert denial(invoke(workspace, payload)) == "Blocked by guard"


def test_null_shell_workdir_uses_hook_cwd(workspace: Path):
    rule(workspace, "print('true')")
    assert denial(invoke(workspace, tool(workspace, workdir=None))) == "Blocked by guard"


def test_session_start_supplies_override_instructions(workspace: Path):
    result = invoke(workspace, tool(workspace), "session-start")
    assert result.returncode == 0, result.stderr
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "I insist" in context
    assert "HUMAN_PERMISSION_GRANTED=1" in context
    assert "human" in context


@pytest.mark.parametrize("harness", ["codex", "claude"])
def test_installed_hooks_block_approve_and_reset(workspace: Path, harness: str):
    result = manage_hooks("install", harness, workspace)
    assert result.returncode == 0, result.stderr
    hooks = json.loads(hook_path(workspace, harness).read_text())["hooks"]
    rule(workspace, "print('true')")
    payload = tool(workspace, "Edit", file_path="note.md", new_string="replacement")
    if harness == "claude":
        del payload["turn_id"]

    def run(name: str, **fields):
        command = hooks[name][0]["hooks"][0]["command"]
        environment = {
            **os.environ,
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        }
        return subprocess.run(
            shlex.split(command),
            input=json.dumps({**payload, **fields}),
            capture_output=True,
            text=True,
            cwd=workspace,
            env=environment,
            timeout=10,
        )

    assert run("SessionStart", source="startup").returncode == 0
    assert denial(run("PreToolUse")) == "Blocked by guard"
    allowed(run("UserPromptSubmit", prompt="I insist"))
    allowed(run("PreToolUse"))
    allowed(run("PreToolUse"))
    allowed(run("UserPromptSubmit", prompt="Next task"))
    assert denial(run("PreToolUse")) == "Blocked by guard"


def test_example_provider_with_real_files(workspace: Path):
    import shutil

    example = Path(__file__).resolve().parents[1] / "examples/project"
    shutil.copytree(example, workspace, dirs_exist_ok=True)
    assert "originals require your permission" in denial(
        invoke(workspace, tool(workspace, "Write", file_path="_sources/original.txt"))
    )
    allowed(invoke(workspace, tool(workspace, "Write", file_path="notes.txt")))


def test_nonfinite_json_is_rejected_before_checker_starts(workspace: Path):
    marker = workspace / "started"
    rule(workspace, f"from pathlib import Path\nPath({str(marker)!r}).touch()\nprint('false')")
    result = invoke(workspace, tool(workspace, "mcp__custom__action", value=float("nan")))
    assert "input" in denial(result)
    assert not marker.exists()


def test_corrupt_approval_does_not_grant_permission(workspace: Path):
    rule(workspace, "print('true')")
    payload = tool(workspace, "Write", file_path="a.txt")
    allowed(invoke(workspace, {**payload, "prompt": "I insist"}, "user-prompt-submit"))
    cache = Path(os.environ["XDG_CACHE_HOME"]) / "i-insist/approvals"
    for path in cache.glob("*.json"):
        path.write_text("broken")
    assert denial(invoke(workspace, payload)) == "Blocked by guard"
