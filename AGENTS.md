# Development

Keep provider policy out of the runner. Harness-specific payload handling belongs
in adapters. Checkers receive the documented neutral event.

Use `uv`. Before committing, run:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Follow [CONVENTIONS.md](CONVENTIONS.md), [architecture map](docs/ARCHITECTURE.md), and
[quality policy](docs/QUALITY.md). While `i_insist` remains one package, use these
documents to guide architecture reviews without a separate boundary checker.

For behavior changes and bug fixes, use red/green test-driven development: first confirm a focused behavior test fails
for the expected reason, make the smallest passing change, then refactor while it stays green.

Changes to configuration, approval scope, or the checker protocol need matching
behavior tests and README updates. Don't enable new guards in the development
session or migrate other plugins without including that work in the task scope.
