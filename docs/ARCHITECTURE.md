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

The modules share event types from `events.py`; `cli.py` connects their behavior.
Events retain requested lexical paths alongside physical paths. Discovery uses
physical paths; configuration protection also uses lexical names and discovery's
resolved configuration identities, so symlinks don't discard protected identity.
While this remains one package, review these boundaries without a separate
boundary checker.
