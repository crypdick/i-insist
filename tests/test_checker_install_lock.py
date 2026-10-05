"""Checker execution stays outside uv's in-place tool installation window."""

import fcntl
import json
import os
import subprocess
import sys
import time

import pytest

from tests.support import allowed, denial, invoke, tool


@pytest.fixture
def uv_checker(workspace, monkeypatch):
    tools = workspace / "tools"
    environment = tools / "provider"
    binary = environment / "bin"
    binary.mkdir(parents=True)
    (environment / "uv-receipt.toml").write_text("[tool]\n")
    lock = tools / ".lock"
    lock.touch()
    module = environment / "policy.py"
    module.write_text("result = 'null'\n")
    executable = binary / "provider-check"
    executable.write_text(
        f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(environment)!r})\n"
        "import policy\nprint(policy.result)\n"
    )
    executable.chmod(0o755)
    links = workspace / "bin"
    links.mkdir()
    (links / executable.name).symlink_to(executable)
    monkeypatch.setenv("PATH", str(links) + os.pathsep + os.environ["PATH"])
    config = workspace / ".i-insist"
    config.mkdir()
    registration = config / "provider.toml"
    registration.write_text('[[rules]]\nid = "provider"\nchecker = ["provider-check"]\n')
    return lock, executable, module, registration


@pytest.mark.parametrize("missing", ["module", "executable"])
@pytest.mark.parametrize("command", ["path", "absolute", "relative"])
def test_checker_waits_until_install_restores_files(workspace, uv_checker, missing, command):
    lock, executable, module, registration = uv_checker
    if command != "path":
        target = str(executable) if command == "absolute" else "../tools/provider/bin/provider-check"
        registration.write_text(f'[[rules]]\nid = "provider"\nchecker = {json.dumps([target])}\n')
    removed = module if missing == "module" else executable
    content = removed.read_bytes()
    mode = removed.stat().st_mode
    with lock.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        removed.unlink()
        with subprocess.Popen(
            [sys.executable, "-m", "i_insist", "hook", "--harness", "codex", "pre-tool-use"],
            cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as process:
            process.stdin.write(json.dumps(tool(workspace)))
            process.stdin.close()
            process.stdin = None
            try:
                with pytest.raises(subprocess.TimeoutExpired):
                    process.wait(timeout=0.3)
            finally:
                removed.write_bytes(content)
                removed.chmod(mode)
                fcntl.flock(stream, fcntl.LOCK_UN)
                stdout, stderr = process.communicate(timeout=5)
            allowed(subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr))


def test_install_waits_for_concurrent_checkers(workspace, uv_checker):
    lock, executable, _, _ = uv_checker
    release = workspace / "release"
    executable.write_text(
        f"#!{sys.executable}\nimport os, time\nfrom pathlib import Path\n"
        f"Path({str(workspace)!r}, str(os.getpid()) + '.started').touch()\n"
        f"while not Path({str(release)!r}).exists(): time.sleep(0.01)\nprint('null')\n"
    )
    processes = []
    try:
        for _ in range(2):
            process = subprocess.Popen(
                [sys.executable, "-m", "i_insist", "hook", "--harness", "codex", "pre-tool-use"],
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append(process)
            process.stdin.write(json.dumps(tool(workspace)))
            process.stdin.close()
            process.stdin = None
        deadline = time.monotonic() + 5
        while len(list(workspace.glob("*.started"))) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(list(workspace.glob("*.started"))) == 2
        with lock.open("rb") as stream, pytest.raises(BlockingIOError):
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        release.touch()
        for process in processes:
            stdout, stderr = process.communicate(timeout=5)
            allowed(subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr))


def test_install_lock_timeout_blocks_without_starting_checker(workspace, uv_checker):
    lock, executable, _, registration = uv_checker
    started = workspace / "started"
    executable.write_text(
        f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(started)!r}).touch()\nprint('null')\n"
    )
    registration.write_text('[[rules]]\nid = "provider"\nchecker = ["provider-check"]\ntimeout = 0.1\n')
    with lock.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        assert "timed out" in denial(invoke(workspace, tool(workspace)))
    assert not started.exists()


def test_missing_install_lock_fails_closed(workspace, uv_checker):
    lock, _, _, _ = uv_checker
    lock.unlink()
    assert "No such file or directory" in denial(invoke(workspace, tool(workspace)))


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        ("result = '\"Policy denial\"'\n", "Policy denial"),
        ("raise RuntimeError('broken policy')\n", "RuntimeError: broken policy"),
    ],
)
def test_uv_checker_denials_and_errors_are_preserved(workspace, uv_checker, policy, expected):
    lock, _, module, _ = uv_checker
    module.write_text(policy)
    message = denial(invoke(workspace, tool(workspace)))
    assert expected in message
    with lock.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
