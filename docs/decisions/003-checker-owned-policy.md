# Checker-owned policy and generated registrations

Status: accepted for 0.4.0.

Installed rule TOML previously mixed provider definitions with human customizations.
Preserving edits left stale definitions in place. Replacing files erased user choices.

Providers own their entire registration files. Setup replaces only that provider's
file atomically. TOML contains `id`, `checker`, optional `timeout`, and optional
`overridable`. The schema excludes `message` and `enabled` and has no user override
layer. Human approval bypasses overridable checks for its documented scope.

A checker prints JSON `null` to allow or a nonempty denial string to block. It owns
the wording. Evaluation failures exit nonzero. The runner blocks and reports stderr,
including exception tracebacks. Providers must not turn evaluation errors into allows.

This is a breaking protocol change. Old registrations and boolean output fail closed.
Runner and provider releases need coordinated migration. The runner never rewrites
another provider's registrations or interprets its policy configuration.
