"""Configuration protection distinguishes Python source data from paths."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["heredoc", "inline"])
@pytest.mark.parametrize("trailing_write", [False, True])
@pytest.mark.parametrize(
    ("source", "blocked"),
    [
        (
            (
                "from pathlib import Path\n"
                "p = Path('tests/test_first_install.py')\n"
                "s = p.read_text().replace('return base / \".i-insist/policy.toml\"', 'replacement')\n"
                "p.write_text(s)\n"
            ),
            False,
        ),
        ("from pathlib import Path\nPath('.i-insist/policy.toml').write_text('x')", True),
        ("from pathlib import Path\np = Path.home() / '.i-insist' / 'policy.toml'\np.unlink()", True),
        ("from pathlib import Path\np = Path(f'{root}/.i-insist/policy.toml')\np.unlink()", True),
        ("invalid python .i-insist/policy.toml", True),
        ("exec(\"Path('.i-insist/policy.toml').unlink()\")", True),
        ("import os; os.system('rm -r .i-insist')", True),
    ],
)
def test_python_config_protection(
    workspace: Path, source: str, blocked: bool, mode: str, trailing_write: bool
):
    command = f"python - <<'PY'\n{source}\nPY\n" if mode == "heredoc" else f"python3 -c {shlex.quote(source)}"
    command += "\nrm -rf .i-insist" if trailing_write else "\nuv run pytest tests/test_first_install.py"
    payload = {
        "kind": "shell",
        "command": command,
        "cwd": str(workspace),
        "paths": [],
        "harness": "codex",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "protect-config"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    assert bool(json.loads(result.stdout)) is (blocked or trailing_write)
