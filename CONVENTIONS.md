# Design conventions

## Keep harness policy in adapters

Normalize harness payloads into `i_insist.events.Event` at adapter boundaries.
Checkers consume that neutral event. Runner and rule discovery must not depend on
provider payload shapes or policy.

## Parse at boundaries

Parse external JSON and TOML once; reject malformed values before core behavior.
Use types that enforce meaningful domain constraints.

## Prefer composition

Prefer focused functions and values over inheritance. Add abstractions when
current behavior needs them, not for hypothetical implementations.

## Keep documentation aligned

Keep documented behavior aligned with code. For easily missed dependencies, link
the relevant document from the code definition.
