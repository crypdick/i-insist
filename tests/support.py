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
