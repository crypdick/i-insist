"""Installer locks stay outside configuration trees and serialize path aliases."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support import hook_path, manage_hooks


@pytest.mark.parametrize("location", ["runtime", "cache", "home"])
def test_installer_keeps_private_persistent_locks_outside_settings(workspace, monkeypatch, location):
    if location != "runtime":
        monkeypatch.delenv("XDG_RUNTIME_DIR")
    if location == "home":
        monkeypatch.delenv("XDG_CACHE_HOME")
    root = {
        "runtime": workspace.parent.parent / "runtime",
        "cache": workspace.parent.parent / "cache",
        "home": workspace.parent / ".cache",
    }[location]
    path = hook_path(workspace, "claude")
    path.parent.mkdir()
    path.write_text("{}")
    result = manage_hooks("install", "claude", workspace)
    assert result.returncode == 0, result.stderr
    assert sorted(path.parent.iterdir()) == [path]
    locks = list((root / "i-insist/locks").glob("*.lock"))
    assert len(locks) == 1
    lock = locks[0]
    assert lock.parent.stat().st_mode & 0o777 == 0o700
    assert lock.stat().st_mode & 0o777 == 0o600
    inode = lock.stat().st_ino
    assert manage_hooks("uninstall", "claude", workspace).returncode == 0
    assert lock.stat().st_ino == inode
    assert manage_hooks("install", "claude", workspace).returncode == 0
    assert lock.stat().st_ino == inode


def test_symlink_aliases_share_lock_but_unrelated_settings_do_not(workspace, monkeypatch):
    source = workspace / "tracked/settings.json"
    source.parent.mkdir()
    source.write_text("{}")
    alias = hook_path(workspace, "claude")
    alias.parent.mkdir()
    alias.symlink_to(source)
    assert manage_hooks("install", "claude", workspace).returncode == 0
    locks = Path(os.environ["XDG_RUNTIME_DIR"]) / "i-insist/locks"
    (lock,) = locks.glob("*.lock")
    assert sorted(source.parent.iterdir()) == [source]
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(source.parent))
    with lock.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        with subprocess.Popen(
            [sys.executable, "-m", "i_insist", "install", "claude"],
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as process:
            try:
                with pytest.raises(subprocess.TimeoutExpired):
                    process.wait(timeout=0.5)
                # A different resource remains usable while this lock is held.
                monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(workspace / "other"))
                result = manage_hooks("install", "claude", workspace)
                assert result.returncode == 0, result.stderr
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
                _, stderr = process.communicate(timeout=5)
            assert process.returncode == 0, stderr
    assert len(list(locks.glob("*.lock"))) == 2
    assert alias.is_symlink()


@pytest.mark.parametrize("unsafe", ["relative", "symlink", "public"])
def test_installer_rejects_unsafe_lock_directory(workspace, monkeypatch, unsafe):
    path = hook_path(workspace, "claude")
    path.parent.mkdir()
    path.write_text("{}")
    root = Path(os.environ["XDG_RUNTIME_DIR"])
    locks = root / "i-insist/locks"
    if unsafe == "relative":
        monkeypatch.setenv("XDG_RUNTIME_DIR", "relative-runtime")
    else:
        locks.parent.mkdir(parents=True)
        if unsafe == "symlink":
            locks.symlink_to(workspace, target_is_directory=True)
        else:
            locks.mkdir(mode=0o755)
    result = manage_hooks("install", "claude", workspace)
    assert result.returncode == 2
    assert "lock directory" in result.stderr
    assert path.read_text() == "{}"
