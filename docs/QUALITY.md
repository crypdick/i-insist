# Quality policy

Production package target: strict mypy, curated Ruff checks, complexity at most 15, no known dead
code, and branch coverage that cannot fall below recorded baseline. Tests must exercise public CLI
and subprocess seams; private implementation imports are rejected.

Current domain grades after strictification:

- Type safety: A — production package passes strict mypy.
- Complexity: A — Ruff `C901` limit enforced.
- Test health: A — subprocess behavior suite has timeout and parallel execution.
- Coverage: measured percentage enforced in `pyproject.toml`; raise toward 100 as meaningful cases
  are added. Do not add tautological tests solely to increase percentage.

Review this file when package boundaries, coverage floor, or test execution policy changes.
