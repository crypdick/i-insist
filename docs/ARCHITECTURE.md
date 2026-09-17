# Architecture

`i-insist` is one Python package with four responsibilities:

- `events.py` defines neutral `Event` input and harness adapters.
- `rules.py` discovers TOML rules and executes checker processes.
- `approval.py` records and evaluates human override scope.
- `install.py` owns Codex and Claude Code hook registration; `cli.py` composes these parts.

Provider payload handling stays in adapters. Checkers receive only documented neutral events.
Approval remains human-owned, and configuration or checker failure blocks execution.

No executable package-boundary policy exists yet: these modules form one cohesive package and
cross-import only through the composition root. Add boundary enforcement when a second owned
package or stable external Python API creates a meaningful boundary.
