# Architecture

The `i_insist` package contains these modules:

- `events.py` defines neutral `Event` input and harness adapters.
- `rules.py` discovers TOML rules and executes checker processes.
- `approval.py` records and evaluates human override scope.
- `install.py` owns Codex and Claude Code hook registration.
- `protect_config.py` checks for changes to rule registrations.
- `cli.py` composes these parts.

Provider payload handling stays in adapters. Checkers receive only documented neutral
events. Approval remains human-owned, and configuration or checker failure blocks
execution.

The modules share event types from `events.py`, and `cli.py` connects their
behavior. Add package-boundary enforcement when a second owned package or stable
external Python API creates a boundary to check.
