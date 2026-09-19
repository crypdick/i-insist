# i-insist

Block agent tool calls with checks from your plugins or your own scripts.
Works with Codex and Claude Code. When a check blocks an action, the agent sees
the reason and stops. Say `I insist` when you want to override it.

## Install

Requires [uv](https://docs.astral.sh/uv/), Python 3.12 or newer, and Linux or macOS.

```sh
uv tool install 'git+https://github.com/crypdick/i-insist@main'
i-insist install codex
i-insist install claude
```

Install only the integrations you use. Restart the agent and check hook trust
with `/hooks`.

## Rules

Plugins supply their own checks. Rules live in `~/.i-insist/*.toml` for global
use or `.i-insist/*.toml` within a project. Global and applicable local rules
run together.

Installation includes a rule requiring human approval to change `.i-insist`
files. Other checks come from your plugins or scripts.

To write your own, start with the [runnable example](examples/project) and
[rule and checker reference](docs/reference.md#add-a-rule).
Plugin installers replace their generated registrations, so don't edit those
files to customize a plugin.

## Human overrides

Include `I insist` anywhere in your message, in any capitalization:

```text
I insist, update both protected files.
```

Approval lasts for the current response and resets with your next message or
when you start or resume a session. Quoted text and code blocks count too.

Rules marked `overridable = false` still run. Invalid configuration still blocks
approved calls. Approval doesn't override other plugins or the agent's own
permissions.

These are cooperative guards, not a sandbox. They depend on the agent calling
hooks, and checkers run with your account's privileges.

Configuration protection recognizes literal paths in Python `-c` commands and
standalone quoted Python heredocs. Embedded replacement source text mentioning
`.i-insist` is not itself a configuration path. Literal configuration paths
(including f-string fragments) still require approval. Malformed Python,
recognized dynamic execution calls, and other shell forms retain conservative
checks. This is not arbitrary Python data-flow analysis or a shell sandbox.

Separate shell commands are checked independently: listing `.i-insist` followed
by an unrelated test or file operation does not require approval. Quoted and
escaped separators stay within their command, as do redirection operators.
Directory changes, variable assignments, shell control flow, substitutions,
and other heredocs retain the conservative whole-call check.

## Update or uninstall

Update the runner, then repeat the install command for each integration you use
if the update changes hook registrations:

```sh
uv tool upgrade i-insist
```

To uninstall, remove each integration you installed before removing the runner:

```sh
i-insist uninstall codex
i-insist uninstall claude
uv tool uninstall i-insist
```

Uninstall leaves provider rules and approval caches in place.

## Reference

- [Integration reference](docs/reference.md): checker protocol, rule discovery, approval details, and upgrades from 0.3.x
- [Development and releases](docs/development.md): contributing, checks, and publishing
