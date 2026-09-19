"""Exercise shell command boundaries through the public config checker."""

import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize("separator", ["\n", "; ", " && ", " || ", " | ", " & "])
@pytest.mark.parametrize("write", [False, True])
def test_config_shell_command_boundaries(workspace, separator, write):
    command = separator.join(
        [
            "ls -l ~/.i-insist/sensitive-orgs.*",
            "git status --short",
            "python3 /tmp/test_guard.py",
            "touch ~/.i-insist/policy.toml" if write else "touch /tmp/test-result",
        ]
    )
    assert config_denied(workspace, command) is write


@pytest.mark.parametrize(
    ("command", "blocked"),
    [
        ("python3 /tmp/test_guard.py\nls -l ~/.i-insist", False),
        ("ls ~/.i-insist\npython3 - <<'PY'\nprint('ok')\nPY\n", False),
        ("ls ~/.i-insist; python3 -c 'print(\"a;b\")'", False),
        ("ls ~/.i-insist # python3 is next\npython3 /tmp/test_guard.py", False),
        ("ls ~/.i-insist\n# unmatched quote ' in comment\npython3 /tmp/test_guard.py", False),
        ("ls ~/.i-insist; printf ok > /tmp/result", False),
        ("ls ~/.i-insist; sed -i s/a/b/ /tmp/result", False),
        ("ls ~/.i-insist; rm /tmp/result", False),
        ("printf ok > ~/.i-insist/policy.toml; python3 /tmp/test_guard.py", True),
        ("printf ok >& ~/.i-insist/policy.toml", True),
        ("printf ok >| ~/.i-insist/policy.toml", True),
        ("printf ok &> ~/.i-insist/policy.toml", True),
        ("printf ok &>> ~/.i-insist/policy.toml", True),
        ("ls ~/.i-insist 2>&1; python3 /tmp/test_guard.py", False),
        ("ls /tmp; sed -i s/a/b/ ~/.i-insist/policy.toml", True),
        ("ls /tmp; rm ~/.i-insist/policy.toml", True),
        ("ls /tmp; python3 -c 'from pathlib import Path; Path(\".i-insist/policy.toml\").unlink()'", True),
        ("python3 -c 'print(\";\")' ~/.i-insist/policy.toml", True),
        ("python3 -c \"print(';')\" ~/.i-insist/policy.toml", True),
        ("python3 /tmp/runner.py \\\n ~/.i-insist/policy.toml", True),
        ("python3 /tmp/runner.py foo\\;bar ~/.i-insist/policy.toml", True),
        ("python3 $(printf 'script.py;') ~/.i-insist/policy.toml", True),
        ("python3 `printf 'script.py;'` ~/.i-insist/policy.toml", True),
        ("cat <<EOF\nhello\nEOF\nrm ~/.i-insist/policy.toml", True),
        ("python3 'unclosed ~/.i-insist/policy.toml", True),
        ("cd ~/.i-insist; rm policy.toml", True),
        ("pushd ~/.i-insist; rm policy.toml", True),
        ('target=~/.i-insist/policy.toml; rm "$target"', True),
        ('for target in ~/.i-insist/*; do rm "$target"; done', True),
        ('remove() { rm "$1"; }; remove ~/.i-insist/policy.toml', True),
        ("(cd ~/.i-insist; rm policy.toml)", True),
    ],
)
def test_config_shell_quoting_and_writes(workspace, command, blocked):
    assert config_denied(workspace, command) is blocked


def config_denied(workspace, command):
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
    return bool(json.loads(result.stdout))
