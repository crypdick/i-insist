# Design conventions

## Keep harness policy in adapters

Normalize harness payloads into `i_insist.events.Event` at adapter boundaries. Checkers consume
that neutral event; runner and rule discovery must not depend on provider payload shapes.

## Parse, don't validate

Parse external JSON and TOML once into constrained values or frozen dataclasses. Validation must
reject malformed values before core behavior sees them. `NewType` adds static separation but does
not validate data, so use it only when confusing two primitive domain values would be a real bug.

## Prefer composition

Combine focused functions and values when behavior varies. Use inheritance only for genuine is-a
relationships or framework contracts; do not add one-implementation interfaces or factories.

## Couple duplicated documentation

When prose repeats a code-owned value whose drift would mislead users, add a `NOTE:` at its code
definition naming the document that must change with it.
