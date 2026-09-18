# Quality policy

The production package must meet these requirements:

- Pass strict mypy and the configured Ruff checks.
- Keep cyclomatic complexity at most 15, enforced by Ruff's `C901` rule.
- Contain no known dead code.
- Keep the branch coverage floor in `pyproject.toml` at least as high as the
  recorded baseline. Raise it toward 100% as you
  add meaningful cases. Don't add tautological tests to increase coverage.

Tests must exercise public command-line and subprocess boundaries, including
timeouts and parallel execution. Checks reject private implementation imports.

Update this file when package boundaries, coverage floor, or test execution policy
changes.
