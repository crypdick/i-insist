import os
import subprocess
import urllib.error
from pathlib import Path

import pytest

from scripts.prepare_release import published_versions, release_state, release_version


@pytest.mark.parametrize(
    ("current", "published", "expected"),
    [
        ("0.2.0", [], "0.2.0"),
        ("0.2.0", ["0.2.0"], "0.2.1"),
        ("0.3.0", ["0.2.9", "0.4.0rc1"], "0.3.0"),
        ("0.2.0", ["0.2.9"], "0.2.10"),
    ],
)
def test_choose_unpublished_release(current, published, expected):
    assert release_version(current, published) == expected


def test_only_missing_project_counts_as_first_publication(monkeypatch):
    def unavailable(*args, **_kwargs):
        raise urllib.error.HTTPError("https://pypi.org", status, "registry error", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    status = 404
    assert published_versions("i-insist") == []
    status = 503
    with pytest.raises(urllib.error.HTTPError):
        published_versions("i-insist")


def test_retry_reuses_release_and_overtaken_runs_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)

    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(tmp_path), *args],
            text=True,
        ).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Release test")
    git("config", "user.email", "test@example.com")
    git("commit", "--allow-empty", "-m", "source")
    source = git("rev-parse", "HEAD")
    assert release_state(tmp_path, source) == "new"
    git("commit", "--allow-empty", "-m", "Release 0.2.0", "-m", f"Source-Commit: {source}")
    assert release_state(tmp_path, source) == "retry"
    git("commit", "--allow-empty", "-m", "later change")
    assert release_state(tmp_path, source) == "stale"
