# Quality policy

Production package requirements: strict mypy, curated Ruff checks, complexity at most 15,
no known dead code, and branch coverage that cannot fall below the recorded baseline.
Tests must exercise public command-line interface (CLI) and subprocess boundaries.
Checks reject private implementation imports.

Current quality grades:

- Type safety: A. The production package passes strict mypy.
- Complexity: A. Ruff enforces the `C901` limit.
- Test health: A. The subprocess behavior suite tests timeouts and parallel
  execution.
- Coverage: `pyproject.toml` enforces the measured percentage. Raise it toward 100
  as you add meaningful cases. Do not add tautological tests solely to increase
  the percentage.

Update this file when package boundaries, coverage floor, or test execution policy
changes.
