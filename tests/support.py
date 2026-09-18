import json
import subprocess
import sys
from pathlib import Path


def manage_hooks(action: str, harness: str, workspace: Path):
    return subprocess.run(
        [sys.executable, "-m", "i_insist", action, harness],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=10,
    )


def hook_path(workspace: Path, harness: str) -> Path:
    relative = ".codex/hooks.json" if harness == "codex" else ".claude/settings.json"
    return workspace.parent / relative


def rule(directory: Path, script: str, *, name: str = "guard", extra: str = "") -> Path:
    config = directory / ".i-insist"
    config.mkdir(exist_ok=True)
    checker = directory / f"{name}.py"
    checker.write_text(script)
    path = config / f"{name}.toml"
    path.write_text(
        f'[[rules]]\nid = "{name}"\nchecker = {json.dumps([sys.executable, "../" + checker.name])}\n{extra}'
    )
    return path


def invoke(repo: Path, payload: object, event: str = "pre-tool-use", *, harness: str = "codex"):
    return subprocess.run(
        [sys.executable, "-m", "i_insist", "hook", "--harness", harness, event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo,
        timeout=10,
    )


def tool(repo: Path, name: str = "Bash", **arguments: object) -> dict:
    if name == "Bash":
        arguments.setdefault("command", "true")
    return {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "cwd": str(repo),
        "tool_name": name,
        "tool_input": arguments,
    }


def denial(result) -> str:
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    return output["permissionDecisionReason"]


def allowed(result) -> None:
    assert result.returncode == 0, result.stderr
    assert not result.stdout.strip(), result.stdout
