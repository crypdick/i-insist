# Development

Keep provider policy out of the runner. Harness-specific payload handling belongs
in adapters; checkers receive the documented neutral event.

Use `uv`. Before committing, run:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Changes to configuration, approval scope, or the checker protocol need matching
behavior tests and README updates. Do not enable new guards in the development
session or migrate other plugins without including that work in the task scope.
