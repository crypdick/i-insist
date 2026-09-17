from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import hook_path, manage_hooks
from tests.test_cli import allowed, denial, invoke, rule, tool


@pytest.mark.parametrize("harness", ["codex", "claude"])
def test_install_preserves_other_hooks_and_is_idempotent(workspace: Path, harness: str):
    path = hook_path(workspace, harness)
    path.parent.mkdir()
    existing = {
        "description": "Keep me",
        "permissions": {"allow": ["Read"]},
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "other-hook"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "another-hook"}]}],
        },
    }
    path.write_text(json.dumps(existing))
    path.chmod(0o640)
    assert manage_hooks("install", harness, workspace).returncode == 0
    installed = path.read_bytes()
    data = json.loads(installed)
    assert data["description"] == "Keep me"
    assert data["permissions"] == existing["permissions"]
    assert data["hooks"]["Stop"] == existing["hooks"]["Stop"]
    assert data["hooks"]["PreToolUse"][0] == existing["hooks"]["PreToolUse"][0]
    assert path.stat().st_mode & 0o777 == 0o640
    assert manage_hooks("install", harness, workspace).returncode == 0
    assert path.read_bytes() == installed
    assert manage_hooks("uninstall", harness, workspace).returncode == 0
    assert json.loads(path.read_text()) == existing
    assert manage_hooks("uninstall", harness, workspace).returncode == 0
    assert json.loads(path.read_text()) == existing


def test_uninstall_removes_only_owned_handlers_in_mixed_group(workspace: Path):
    path = hook_path(workspace, "codex")
    path.parent.mkdir()
    other = {"type": "command", "command": "echo 'i-insist hook --harness codex pre-tool-use'"}
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "extra": "preserve",
                            "hooks": [
                                other,
                                {
                                    "type": "command",
                                    "command": "i-insist hook --harness codex pre-tool-use",
                                },
                            ],
                        }
                    ]
                }
            }
        )
    )
    assert manage_hooks("uninstall", "codex", workspace).returncode == 0
    assert json.loads(path.read_text()) == {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "extra": "preserve",
                    "hooks": [other],
                }
            ]
        }
    }


@pytest.mark.parametrize(
    "contents",
    [
        "invalid json!",
        "[]",
        '{"hooks": []}',
        '{"hooks": {"PreToolUse": {}}}',
        '{"hooks": {"PreToolUse": [{"hooks": {}}]}}',
    ],
)
def test_installer_rejects_malformed_settings_without_overwriting(workspace: Path, contents: str):
    path = hook_path(workspace, "claude")
    path.parent.mkdir()
    path.write_text(contents)
    for action in ("install", "uninstall"):
        result = manage_hooks(action, "claude", workspace)
        assert result.returncode == 2
        assert "configuration" in result.stderr
        assert path.read_text() == contents


def test_uninstall_missing_configuration_is_a_noop(workspace: Path):
    assert manage_hooks("uninstall", "codex", workspace).returncode == 0
    assert not hook_path(workspace, "codex").parent.exists()


def test_installer_preserves_settings_symlink(workspace: Path):
    path = hook_path(workspace, "claude")
    path.parent.mkdir()
    target = workspace / "settings.json"
    target.write_text('{"description": "linked"}')
    path.symlink_to(target)
    assert manage_hooks("install", "claude", workspace).returncode == 0
    assert path.is_symlink()
    assert "PreToolUse" in json.loads(target.read_text())["hooks"]
    assert manage_hooks("uninstall", "claude", workspace).returncode == 0
    assert path.is_symlink()
    assert json.loads(target.read_text()) == {"description": "linked"}


@pytest.mark.parametrize(
    "contents",
    ['{"description":"leave formatting alone"}', '{"hooks":{}}', '{"hooks":{"PreToolUse":[]}}'],
)
def test_uninstall_without_owned_hooks_does_not_rewrite_settings(workspace: Path, contents: str):
    path = hook_path(workspace, "codex")
    path.parent.mkdir()
    path.write_text(contents)
    assert manage_hooks("uninstall", "codex", workspace).returncode == 0
    assert path.read_text() == contents


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("Write", {"file_path": ".i-insist/policy.toml"}),
        (
            "apply_patch",
            {"patch": "*** Begin Patch\n*** Delete File: .i-insist/policy.toml\n*** End Patch"},
        ),
        ("Bash", {"command": "rm -rf .i-insist"}),
        ("Bash", {"command": 'printf "enabled = false" > ~/.i-insist/policy.toml'}),
    ],
)
def test_config_protection_requires_human_approval(workspace: Path, name, arguments):
    installed = subprocess.run(
        [sys.executable, "-m", "i_insist", "install", "codex"], capture_output=True, text=True
    )
    assert installed.returncode == 0, installed.stderr
    payload = tool(workspace, name, **arguments)
    assert "human approval" in denial(invoke(workspace, payload))
    allowed(invoke(workspace, {**payload, "prompt": "I insist"}, "user-prompt-submit"))
    allowed(invoke(workspace, payload))


@pytest.mark.parametrize("command", ["cat .i-insist/policy.toml", "rg enabled ~/.i-insist", "git status"])
def test_config_protection_allows_reads(workspace: Path, command: str):
    installed = subprocess.run(
        [sys.executable, "-m", "i_insist", "install", "codex"], capture_output=True, text=True
    )
    assert installed.returncode == 0, installed.stderr
    allowed(invoke(workspace, tool(workspace, command=command)))


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_install_refuses_explicitly_disabled_hooks(workspace: Path, harness: str):
    directory = Path.home() / (".codex" if harness == "codex" else ".claude")
    directory.mkdir()
    path = directory / ("config.toml" if harness == "codex" else "settings.json")
    original = "[features]\nhooks = false\n" if harness == "codex" else '{"disableAllHooks": true}'
    path.write_text(original)
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "install", harness], capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "disabled" in result.stderr
    assert path.read_text() == original


def test_ensure_refuses_disabled_individual_codex_hook(workspace: Path):
    assert manage_hooks("install", "codex", workspace).returncode == 0
    root = Path.home() / ".codex"
    (root / "config.toml").write_text(
        f'[hooks.state."{root}/hooks.json:pre_tool_use:0:0"]\nenabled = false\n'
    )
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "ensure"], cwd=workspace, capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "disabled" in result.stderr


@pytest.mark.parametrize("harness", ["codex", "claude"])
def test_ensure_refuses_disabled_project_hooks(workspace: Path, harness: str):
    assert manage_hooks("install", harness, workspace).returncode == 0
    directory = workspace / (".codex" if harness == "codex" else ".claude")
    directory.mkdir()
    path = directory / ("config.toml" if harness == "codex" else "settings.local.json")
    path.write_text("[features]\nhooks = false\n" if harness == "codex" else '{"disableAllHooks": true}')
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "ensure"], cwd=workspace, capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "disabled" in result.stderr


def test_config_protection_example_matches_installed_rule(workspace: Path):
    assert manage_hooks("install", "codex", workspace).returncode == 0
    expected = Path(__file__).resolve().parents[1] / "examples/config-protection.toml"
    assert (Path.home() / ".i-insist/i-insist.toml").read_text() == expected.read_text()


def test_neutral_check_keeps_non_overridable_rules(workspace: Path):
    rule(workspace, "print('true')", extra="overridable = false\n")
    event = {
        "kind": "shell",
        "command": "HUMAN_PERMISSION_GRANTED=1 true",
        "cwd": str(workspace),
        "paths": [],
        "harness": "custom",
        "tool_name": "exec",
        "tool_input": {},
    }
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "check"],
        input=json.dumps(event),
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"blocked": True, "message": "Blocked by guard"}
