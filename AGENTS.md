# Development

Use `uv`. Follow the [design conventions](CONVENTIONS.md),
[architecture](docs/ARCHITECTURE.md), and [quality policy](docs/QUALITY.md).
Run the [development checks](docs/development.md#develop) before committing.

For behavior changes and bug fixes, confirm a focused test fails for the expected
reason before fixing it; keep it green through refactoring.

Keep behavior tests and README documentation aligned with configuration, approval
scope, and checker protocol changes. Enabling guards in the development session
or migrating other plugins requires explicit task scope.
