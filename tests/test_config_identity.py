"""Configuration protection retains identity across symlink normalization."""

import json
import subprocess
import sys

import pytest

from tests.support import allowed, denial, invoke, manage_hooks, tool


@pytest.mark.parametrize("location", ["global", "local", "file"])
@pytest.mark.parametrize("target_form", ["named", "physical"])
def test_registered_config_symlink_targets_require_approval(workspace, location, target_form):
    installed = manage_hooks("install", "codex", workspace)
    assert installed.returncode == 0, installed.stderr
    directory = workspace.parent / ".i-insist"
    if location == "file":
        physical = workspace / "policy.toml"
        physical.write_text("# provider registration\n")
        named = directory / "provider.toml"
        named.symlink_to(physical)
    else:
        store = workspace / "policy-store"
        if location == "global":
            directory.rename(store)
        else:
            directory = workspace / ".i-insist"
            store.mkdir()
        directory.symlink_to(store, target_is_directory=True)
        named = directory / "provider.toml"
        physical = store / "provider.toml"
        physical.write_text("# provider registration\n")
    target = named if target_form == "named" else physical
    payload = tool(workspace, "Write", file_path=str(target), content="")
    assert "human approval" in denial(invoke(workspace, payload))
    allowed(invoke(workspace, {**payload, "prompt": "I insist"}, "user-prompt-submit"))
    allowed(invoke(workspace, payload))


@pytest.mark.parametrize("name", ["Write", "apply_patch"])
def test_lexical_config_target_outside_discovery_ancestry_still_protected(workspace, name):
    assert manage_hooks("install", "codex", workspace).returncode == 0
    project = workspace / "project"
    project.mkdir()
    store = workspace / "store"
    store.mkdir()
    (project / ".i-insist").symlink_to(store, target_is_directory=True)
    target = project / ".i-insist/provider.toml"
    arguments = (
        {"file_path": str(target), "content": ""}
        if name == "Write"
        else {"patch": f"*** Begin Patch\n*** Add File: {target}\n+body\n*** End Patch"}
    )
    assert "human approval" in denial(invoke(workspace, tool(workspace, name, **arguments)))


@pytest.mark.parametrize("operation", ["redirect", "mutator", "cwd", "python"])
def test_shell_protects_physical_config_identity(workspace, operation):
    assert manage_hooks("install", "codex", workspace).returncode == 0
    named = workspace.parent / ".i-insist"
    store = workspace / "store"
    named.rename(store)
    named.symlink_to(store, target_is_directory=True)
    command = {
        "redirect": f"printf ok > {store}/provider.toml",
        "mutator": f"rm {store}/provider.toml",
        "cwd": "rm provider.toml",
        "python": f"python3 -c 'from pathlib import Path; Path(\"{store}/provider.toml\").unlink()'",
    }[operation]
    payload = tool(workspace, command=command)
    if operation == "cwd":
        payload["tool_input"]["workdir"] = str(named)
    assert "human approval" in denial(invoke(workspace, payload))
    allowed(invoke(workspace, tool(workspace, command=f"cat {store}/provider.toml")))


def test_normalized_config_event_retains_requested_target(workspace):
    assert manage_hooks("install", "codex", workspace).returncode == 0
    project = workspace / "project"
    project.mkdir()
    store = workspace / "store"
    store.mkdir()
    (project / ".i-insist").symlink_to(store, target_is_directory=True)
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "check"],
        input=json.dumps(
            {
                "kind": "file_write",
                "cwd": str(workspace),
                "paths": [str(store / "provider.toml")],
                "requested_paths": [str(project / ".i-insist/provider.toml")],
                "harness": "custom",
                "tool_name": "save",
            }
        ),
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["blocked"] is True


def test_shell_cd_retains_lexical_config_identity_outside_discovery(workspace):
    assert manage_hooks("install", "codex", workspace).returncode == 0
    project = workspace / "project"
    project.mkdir()
    store = workspace / "store"
    store.mkdir()
    (project / ".i-insist").symlink_to(store, target_is_directory=True)
    payload = tool(workspace, command="cd project/.i-insist; rm provider.toml")
    assert "human approval" in denial(invoke(workspace, payload))
