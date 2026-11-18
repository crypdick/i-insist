"""Only bounded literal shell writes participate in configuration protection."""

import json
import subprocess
import sys

import pytest

from tests.support import allowed, denial, invoke, manage_hooks, tool


@pytest.mark.parametrize(
    "command",
    [
        "uv tool install example; echo $(date); ls ~/.i-insist",
        "for path in ~/.i-insist/*; do printf '%s\\n' \"$path\"; done; touch /tmp/result",
        "python3 - <<'PY'\nprint('~/.i-insist/policy.toml')\nPY",
        "python3 -c \"print('\\\\x00', '~/.i-insist/policy.toml')\"",
    ],
)
def test_opaque_shell_does_not_require_config_approval(workspace, command):
    assert config_result(workspace, command) is None


@pytest.mark.parametrize(
    "command",
    [
        "cd ~/.i-insist; rm policy.toml",
        "python3 -c 'from pathlib import Path; Path(\".i-insist/policy.toml\").unlink()'",
        "bash <<'EOF'\nrm ~/.i-insist/policy.toml\nEOF",
        "python3 'unclosed ~/.i-insist/policy.toml",
    ],
)
def test_opaque_shell_writes_are_outside_builtin_protection(workspace, command):
    assert config_result(workspace, command) is None


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf ~/.i-insist",
        "/bin/rm -- ~/.i-insist/policy.toml",
        "touch '.i-insist/policy with spaces.toml'",
        "mkdir .i-insist",
        "rmdir .i-insist",
        "tee .i-insist/policy.toml",
        "cp /tmp/policy.toml .i-insist/policy.toml",
        "mv .i-insist/policy.toml /tmp/backup",
        "install /tmp/policy.toml .i-insist/policy.toml",
        "ln /tmp/policy.toml .i-insist/policy.toml",
        "printf ok > ~/.i-insist/policy.toml",
        "echo ok >> '.i-insist/policy with spaces.toml'",
    ],
)
def test_literal_shell_writes_require_approval(workspace, command):
    message = config_result(workspace, command)
    assert "human approval" in message
    assert "Matched" in message


@pytest.mark.parametrize(
    "command",
    [
        "cp ~/.i-insist/policy.toml /tmp/backup",
        "ln ~/.i-insist/policy.toml /tmp/backup",
        "touch -r ~/.i-insist/policy.toml /tmp/result",
        "echo '>' ~/.i-insist/policy.toml",
        "echo 'rm ~/.i-insist/policy.toml'",
        "rm '.i-insist'notes/policy.toml",
        "echo ok > '.i-insist'notes/policy.toml",
        "sudo rm ~/.i-insist/policy.toml",
        "rm ~/.i-insist/policy.toml; true",
        "rm ~/.i-insist/*.toml",
        'echo ok > "$HOME/.i-insist/policy.toml"',
        "touch .i-insist-notes/policy.toml",
    ],
)
def test_reads_and_unsupported_shell_are_not_denied(workspace, command):
    assert config_result(workspace, command) is None


@pytest.mark.parametrize("harness", ["codex", "claude"])
def test_installed_config_rule_distinguishes_literal_and_opaque_shell(workspace, harness):
    assert manage_hooks("install", harness, workspace).returncode == 0
    payload = tool(workspace, command="rm ~/.i-insist/policy.toml")
    assert "human approval" in denial(invoke(workspace, payload, harness=harness))
    allowed(invoke(workspace, tool(workspace, command="sudo rm ~/.i-insist/policy.toml"), harness=harness))


def config_result(workspace, command):
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "protect-config"],
        input=json.dumps(
            {
                "kind": "shell",
                "command": command,
                "cwd": str(workspace),
                "paths": [],
                "harness": "codex",
                "tool_name": "exec_command",
                "tool_input": {"cmd": command},
            }
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)
