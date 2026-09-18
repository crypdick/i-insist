# Development and releases

For contributors and release maintainers. See the [architecture](ARCHITECTURE.md),
[quality policy](QUALITY.md), and [design conventions](../CONVENTIONS.md).

## Develop

Beartype instruments package imports with runtime type checks. Development checks
run through prek and uv. Install hooks once per checkout with
`uv run prek install`.

Create an isolated checkout. Replace `<name>` with your feature name:

```sh
new-feature <name> --no-agent && uv sync --locked --directory ".worktrees/<name>"
```

From the checkout, install dependencies and run the checks:

```sh
uv sync --locked
uv run prek run --all-files
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Tests exercise installed hook commands and actual checker subprocesses using
temporary homes, projects, and approval caches. They don't enable hooks in your
active harness.

To test the installed command from a development checkout:

```sh
uv tool install --reinstall .
```

## Publishing

`.github/workflows/publish.yml` runs tests, lint, formatting, and a package build
on pull requests. Each successful push to `main` publishes a release to PyPI
and creates a GitHub release with the wheel and source distribution attached.
Manual workflow dispatch retries a release without needing another commit.

The workflow preserves an unpublished version from `pyproject.toml`. Otherwise,
it increments the latest stable PyPI patch version. Use `uv version --bump minor`
or `uv version --bump major` for an intentional version change. The release
commit updates `pyproject.toml` and `uv.lock` together. The workflow skips
superseded runs. Retries reuse their release commit and already uploaded files.

Publishing uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
and the GitHub environment `pypi`, restricted to `main`. GitHub stores no PyPI
API token. To configure a first publication, add a pending publisher at
[PyPI account publishing](https://pypi.org/manage/account/publishing/) with:

- Project: `i-insist`
- GitHub owner: `crypdick`
- Repository: `i-insist`
- Workflow filename: `publish.yml`
- Environment: `pypi`

After the first release, install from PyPI with `uv tool install i-insist`.
