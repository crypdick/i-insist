# Checker-owned policy and generated registrations

Status: accepted for 0.4.0.

Installed rule TOML previously mixed provider definitions with human customizations.
Preserving edits left stale definitions in place; replacing files erased user choices.

Providers now own their entire registration files. Setup replaces only that provider's
file atomically. TOML contains `id`, `checker`, optional `timeout`, and optional
`overridable`. The `message` and `enabled` fields are removed; there is no user override
layer. Human approval still bypasses overridable checks for its documented scope.

A checker prints JSON `null` to allow or a nonempty denial string to block. It owns
the wording. Evaluation failures exit nonzero; the runner blocks and reports stderr,
including exception tracebacks. Providers must not turn evaluation errors into allows.

This is a breaking protocol change. Old registrations and boolean output fail closed.
Runner and provider releases need coordinated migration; the runner never rewrites
another provider's registrations or interprets its policy configuration.
