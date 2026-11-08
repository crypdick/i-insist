"""Approval identity and bounded failures through public subprocess commands."""

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress

import pytest

from tests.support import allowed, denial, invoke, rule, tool


@pytest.mark.parametrize("name", ["Write", "apply_patch"])
def test_checker_retains_requested_paths_and_cwd(workspace, name):
    physical = workspace / "physical"
    physical.mkdir()
    alias = workspace / "alias"
    alias.symlink_to(physical, target_is_directory=True)
    rule(
        workspace,
        "import json, sys\n"
        "event = json.load(sys.stdin)\n"
        f"assert event['cwd'] == {str(physical)!r}\n"
        f"assert event['requested_cwd'] == {str(alias)!r}\n"
        f"assert event['paths'] == {[str(physical / 'note.txt')]!r}\n"
        f"assert event['requested_paths'] == {[str(alias / 'note.txt')]!r}\n"
        "print('null')\n",
    )
    arguments = (
        {"file_path": "note.txt"}
        if name == "Write"
        else {"patch": "*** Begin Patch\n*** Add File: note.txt\n+hello\n*** End Patch"}
    )
    allowed(invoke(workspace, tool(alias, name, **arguments)))


def test_normalized_event_preserves_requested_identity(workspace):
    event = {
        "kind": "file_write",
        "cwd": str(workspace),
        "paths": [str(workspace / "physical")],
        "requested_cwd": str(workspace / "alias"),
        "requested_paths": [str(workspace / "alias" / "target")],
        "harness": "custom",
        "tool_name": "save",
    }
    rule(
        workspace,
        "import json, sys\n"
        "event = json.load(sys.stdin)\n"
        f"assert event['requested_cwd'] == {event['requested_cwd']!r}\n"
        f"assert event['requested_paths'] == {event['requested_paths']!r}\n"
        "print('null')\n",
    )
    result = subprocess.run(
        [sys.executable, "-m", "i_insist", "check"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=workspace,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["blocked"] is False


@pytest.mark.parametrize("missing", ["prompt", "tool", "both"])
def test_codex_cached_approval_requires_turn_identity(workspace, missing):
    rule(workspace, 'import json; print(json.dumps("Needs approval"))')
    prompt = {**tool(workspace), "prompt": "I insist"}
    payload = tool(workspace)
    if missing in {"prompt", "both"}:
        prompt.pop("turn_id")
    if missing in {"tool", "both"}:
        payload.pop("turn_id")
    allowed(invoke(workspace, prompt, "user-prompt-submit"))
    assert denial(invoke(workspace, payload)) == "Needs approval"


def test_missing_codex_prompt_turn_revokes_prior_approval(workspace):
    rule(workspace, 'import json; print(json.dumps("Needs approval"))')
    payload = tool(workspace)
    allowed(invoke(workspace, {**payload, "prompt": "I insist"}, "user-prompt-submit"))
    prompt = {**payload, "prompt": "I insist"}
    prompt.pop("turn_id")
    allowed(invoke(workspace, prompt, "user-prompt-submit"))
    assert denial(invoke(workspace, payload)) == "Needs approval"


@pytest.mark.parametrize("endpoint", ["hook", "check"])
def test_symlink_loop_returns_structured_denial(workspace, endpoint):
    target = workspace / "loop"
    target.symlink_to(target.name)
    if endpoint == "hook":
        result = invoke(workspace, tool(workspace, "Write", file_path=str(target)))
        message = denial(result)
    else:
        result = subprocess.run(
            [sys.executable, "-m", "i_insist", "check"],
            input=json.dumps(
                {
                    "kind": "file_write",
                    "cwd": str(workspace),
                    "paths": [str(target)],
                    "harness": "custom",
                    "tool_name": "save",
                }
            ),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 2, result.stderr
        output = json.loads(result.stdout)
        assert output["blocked"] is True
        message = output["message"]
    assert "path" in message.lower()
    assert str(target) in message


def test_unknown_home_expansion_returns_structured_denial(workspace):
    target = "~i_insist_missing_user_7906e2c8cf/file.txt"
    result = invoke(workspace, tool(workspace, "Write", file_path=target))
    assert "home directory" in denial(result)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group cleanup")
@pytest.mark.parametrize("detached", [False, True])
def test_timeout_does_not_wait_for_descendant_pipes(workspace, detached):
    pid_file = workspace / "child.pid"
    survived = workspace / "child-survived"
    child = (
        "import os, time; from pathlib import Path; "
        f"Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        f"time.sleep({4 if detached else 1}); Path({str(survived)!r}).touch()"
    )
    rule(
        workspace,
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}], start_new_session={detached!r})\n"
        "time.sleep(30)\n",
        extra="timeout = 0.5\n",
    )
    started = time.monotonic()
    try:
        result = invoke(workspace, tool(workspace))
        elapsed = time.monotonic() - started
        assert "timed out" in denial(result)
        assert elapsed < 2.5, f"timeout cleanup took {elapsed:.2f}s"
        assert pid_file.exists(), "checker child did not start"
        if not detached:
            time.sleep(1.1)
            assert not survived.exists(), "checker child survived timeout cleanup"
    finally:
        if pid_file.exists():
            with suppress(ProcessLookupError):
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
