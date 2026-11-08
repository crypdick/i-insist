"""Installer validation must precede writes and preserve indexed hook state."""

import json
from pathlib import Path

import pytest

from tests.support import hook_path, manage_hooks


def codex_layout(workspace, groups, state_index):
    path = hook_path(workspace, "codex")
    path.parent.mkdir()
    original = json.dumps({"hooks": {"PreToolUse": groups}})
    path.write_text(original)
    settings = path.with_name("config.toml")
    settings.write_text(f'[hooks.state."{path}:pre_tool_use:{state_index}"]\nenabled = false\n')
    return path, original, settings.read_text()


def handler(command):
    return {"type": "command", "command": command}


OWNED = handler("i-insist hook --harness codex pre-tool-use")
OTHER = handler("other-hook")


@pytest.mark.parametrize("action", ["install", "uninstall"])
@pytest.mark.parametrize(
    ("groups", "state_index"),
    [
        ([{"hooks": [OWNED]}, {"hooks": [OTHER]}], "1:0"),
        ([{"hooks": [OWNED, OTHER]}], "0:1"),
        ([{"hooks": [OWNED]}, {"hooks": [OWNED]}, {"hooks": [OTHER]}], "2:0"),
    ],
)
def test_codex_refuses_transferring_indexed_state(workspace, action, groups, state_index):
    path, original, settings = codex_layout(workspace, groups, state_index)
    result = manage_hooks(action, "codex", workspace)
    assert result.returncode == 2, result.stderr
    assert "indexed hook state" in result.stderr or "disabled in Codex" in result.stderr
    assert path.read_text() == original
    assert path.with_name("config.toml").read_text() == settings


def test_codex_can_remove_disabled_owned_hook_without_reassigning_state(workspace):
    path, _, settings = codex_layout(workspace, [{"hooks": [OWNED]}], "0:0")
    result = manage_hooks("uninstall", "codex", workspace)
    assert result.returncode == 0, result.stderr
    assert json.loads(path.read_text()) == {}
    assert path.with_name("config.toml").read_text() == settings


def test_codex_preserves_unrelated_indexed_state_when_layout_does_not_shift(workspace):
    path, _, settings = codex_layout(workspace, [{"hooks": [OTHER]}, {"hooks": [OWNED]}], "0:0")
    for action in ("install", "uninstall"):
        result = manage_hooks(action, "codex", workspace)
        assert result.returncode == 0, result.stderr
        assert json.loads(path.read_text())["hooks"]["PreToolUse"][0] == {"hooks": [OTHER]}
        assert path.with_name("config.toml").read_text() == settings


@pytest.mark.parametrize(
    "contents",
    [
        "features = []\n",
        "hooks = []\n",
        "[hooks]\nstate = []\n",
        '[hooks.state]\n"unused" = []\n',
    ],
)
@pytest.mark.parametrize("scope", ["user", "project"])
def test_codex_invalid_nested_settings_fail_cleanly(workspace, contents, scope):
    directory = (Path.home() if scope == "user" else workspace) / ".codex"
    directory.mkdir()
    settings = directory / "config.toml"
    settings.write_text(contents)
    result = manage_hooks("install", "codex", workspace)
    assert result.returncode == 2, result.stderr
    assert "must be an object" in result.stderr
    assert "Traceback" not in result.stderr
    assert settings.read_text() == contents
    assert not (Path.home() / ".i-insist/i-insist.toml").exists()


def test_codex_project_managed_only_blocks_install(workspace):
    directory = workspace / ".codex"
    directory.mkdir()
    (directory / "config.toml").write_text("[hooks]\nallow_managed_hooks_only = true\n")
    result = manage_hooks("install", "codex", workspace)
    assert result.returncode == 2, result.stderr
    assert "disabled" in result.stderr
    assert not (Path.home() / ".i-insist/i-insist.toml").exists()


@pytest.mark.parametrize("relative", [".codex/hooks.json", ".codex/config.toml", ".i-insist/i-insist.toml"])
def test_installer_symlink_loops_fail_cleanly(workspace, relative):
    path = Path.home() / relative
    path.parent.mkdir()
    path.symlink_to(path.name)
    result = manage_hooks("install", "codex", workspace)
    assert result.returncode == 2, result.stderr
    assert "Traceback" not in result.stderr
    assert path.is_symlink()


@pytest.mark.parametrize("harness", ["codex", "claude"])
@pytest.mark.parametrize("existing", [False, True])
def test_malformed_hook_groups_leave_all_registrations_unchanged(workspace, harness, existing):
    path = hook_path(workspace, harness)
    path.parent.mkdir()
    original = '{"hooks":{"SessionStart":[{"hooks":{}}]}}'
    path.write_text(original)
    protection = Path.home() / ".i-insist/i-insist.toml"
    if existing:
        protection.parent.mkdir()
        protection.write_text("# preserve existing provider registration\n")
    result = manage_hooks("install", harness, workspace)
    assert result.returncode == 2, result.stderr
    assert path.read_text() == original
    if existing:
        assert protection.read_text() == "# preserve existing provider registration\n"
    else:
        assert not protection.exists()
