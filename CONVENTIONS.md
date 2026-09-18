# Design conventions

## Keep harness policy in adapters

Normalize harness payloads into `i_insist.events.Event` at adapter boundaries.
Checkers consume that neutral event. Runner and rule discovery must not depend on
provider payload shapes.

## Parse, don't validate

Parse external JSON and TOML once into constrained values or frozen dataclasses.
Reject malformed values before they reach core behavior. `NewType` adds static
separation but doesn't validate data. Use it only when confusing two primitive
domain values can cause a bug.

## Prefer composition

Combine focused functions and values when behavior varies. Use inheritance only for
genuine is-a relationships or framework contracts. Don't add interfaces or
factories with only one implementation.

## Couple duplicated documentation

When prose repeats a code-owned value whose drift can mislead users, add a `NOTE:`
at its code definition naming the document that must change with it.
