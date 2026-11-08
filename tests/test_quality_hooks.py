"""Remaining custom quality gates exercise their documented syntax boundaries."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("source", "blocked"),
    [
        ("from i_insist.events import _hidden as public\n", True),
        ("from i_insist.events import (\n    _hidden,\n    Event,\n)\n", True),
        ("from i_insist.events import Event\n", False),
        ("from i_insist import __version__\n", False),
        ("from other_package import _hidden\n", False),
        ("from i_insist.events import _hidden  # allow: private-test-imports\n", False),
        ('marker = "# allow: private-test-imports"\nfrom i_insist.events import _hidden\n', True),
    ],
)
def test_private_import_gate(workspace, source, blocked):
    result = run_hook(workspace, "check_private_test_imports.py", source, "--package", "i_insist")
    assert result.returncode == int(blocked), result.stderr
    assert ("test_sample.py:" in result.stdout) is blocked


@pytest.mark.parametrize(
    ("handler", "blocked"),
    [
        ("except:\n    pass", True),
        ("except (ValueError, Exception):\n    pass", True),
        ("except builtins.BaseException:\n    pass", True),
        ("except Exception:\n    raise", False),
        ("except Exception:\n    logger.exception('failed')", False),
        ("except ValueError:\n    pass", False),
        ("except Exception:  # allow: exception-handling\n    pass", False),
    ],
)
def test_exception_handling_gate(workspace, handler, blocked):
    result = run_hook(workspace, "check_exception_handling.py", f"try:\n    work()\n{handler}\n")
    assert result.returncode == int(blocked), result.stderr
    assert ("test_sample.py:" in result.stdout) is blocked


def run_hook(workspace, script, source, *arguments):
    target = workspace / "test_sample.py"
    target.write_text(source)
    path = Path(__file__).resolve().parents[1] / "scripts/prek_hooks" / script
    return subprocess.run(
        [sys.executable, str(path), *arguments, str(target)],
        capture_output=True,
        text=True,
        timeout=5,
    )
