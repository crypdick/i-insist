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

Follow [CONVENTIONS.md](CONVENTIONS.md), [architecture map](docs/ARCHITECTURE.md), and
[quality policy](docs/QUALITY.md). Architecture policy is documented rather than enforced by a
separate boundary checker while `i_insist` remains one package.

For behavior changes and bug fixes, use red/green TDD: first confirm a focused behavior test fails
for the expected reason, make the smallest passing change, then refactor while it stays green.

Changes to configuration, approval scope, or the checker protocol need matching
behavior tests and README updates. Do not enable new guards in the development
session or migrate other plugins without including that work in the task scope.
