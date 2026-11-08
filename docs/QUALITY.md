# Quality policy

The production package must pass strict mypy and configured Ruff checks, including
complexity limits, and contain no known dead code.

Preserve the established branch coverage floor in `pyproject.toml`. Improve
coverage with meaningful behavior tests, not assertions added for a score.

Test behavior through public CLI and subprocess boundaries, including timeouts and
parallel execution. Don't import private implementation details in tests.
