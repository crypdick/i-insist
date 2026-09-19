# Integration reference

For plugin authors, custom checker authors, and harness integrations. For installation
and everyday use, see the [README](../README.md).

## Hook registration

The installer registers `PreToolUse`, `UserPromptSubmit`, and `SessionStart` in:

- Codex: `~/.codex/hooks.json`, or `$CODEX_HOME/hooks.json`.
- Claude Code: `~/.claude/settings.json`, or `$CLAUDE_CONFIG_DIR/settings.json`.

It preserves other settings, hooks, file permissions, and symlinks. Repeated runs
don't create duplicate registrations. Writes are atomic, and concurrent installers
coordinate through a lock file beside the configuration.

## Add a rule

Track these files in a repository, or put equivalent TOML under `~/.i-insist/`:

```text
my-project/
├── .i-insist/
│   └── protected-folders.toml
└── tools/
    └── protect_folders.py
```

```toml
[[rules]]
id = "my-plugin/protected-folders"
checker = ["python3", "../tools/protect_folders.py"]
# timeout = 10
```

Providers generate and own their registrations. Setup replaces each provider's
registration from its template, so don't customize installed files. Put denial
messages in the checker.

`timeout` is the checker's time limit in seconds. It defaults to 10 and must be
positive. Each TOML file can contain multiple `[[rules]]`. IDs must be unique within
their file. Invalid configuration blocks execution rather than silently omitting
a check. The runner rejects the former `message` and `enabled` fields.

Store checkers anywhere. The optional `.i-insist/scripts/` directory is one
convention. The runner executes the `checker` argument list without a shell.
Use `sh` explicitly for a shell script. Relative script paths resolve from the
TOML file's directory. The event's `cwd` field contains the intercepted tool's
working directory.

Rule discovery checks these locations:

1. `~/.i-insist/*.toml`.
2. `.i-insist/*.toml` in ancestors of the tool's working directory, outermost first.
3. The same ancestry for explicit file targets, in target order. This protects
   direct edits made from outside the target directory.

Rule discovery resolves and deduplicates directories. Each directory's TOML files
run in filename order, with rules in declaration order. Discovery doesn't recursively
scan `.i-insist/` subdirectories. Paths use their physical, symlink-resolved
locations. Global and local rules accumulate. The first checker to return a denial supplies
the block message, unchanged.

Shell text is opaque to discovery: `cd`, `git -C`, shell write targets, and paths
inside custom tool arguments aren't inferred. Put such policies at a scope the
invocation reaches, or resolve their targets in your provider's checker.

## Write a checker

Read one JSON object on stdin. Print exactly one JSON value on stdout and exit
with status 0. Return `null` to allow the next check or a nonempty string to block.
The runner shows that string unchanged as the denial message. Any other JSON
value, an empty or whitespace-only string, or extra output is a protocol error.
Write debugging output to stderr.

Let policy evaluation errors fail the checker. Don't catch an error and return
`null`: that falsely reports permission to proceed. Checkers run as subprocesses.
The runner detects a nonzero exit and reports the exit status and complete stderr,
including any exception traceback. Missing executables, invalid output, and
timeouts also block with an error. On POSIX, timeout cleanup kills the checker process
group, including its children unless they detach into another session.

This checker blocks direct edits to files under `_sources`:

```python
import json
import sys
from pathlib import Path


def should_block(event: dict) -> bool:
    return any("_sources" in Path(path).parts for path in event["paths"])


message = "These originals require your permission to edit. Ask the human to say I insist."
print(json.dumps(message if should_block(json.load(sys.stdin)) else None))
```

The example doesn't parse shell writes. See the [runnable example](../examples/project).

The checker receives input in this format:

```json
{
  "kind": "file_write",
  "command": null,
  "cwd": "/repo",
  "paths": ["/repo/_sources/original.txt"],
  "harness": "claude",
  "tool_name": "Write",
  "tool_input": {"file_path": "_sources/original.txt", "content": "replacement"},
  "changes": [{"path": "/repo/_sources/original.txt", "operation": "write", "content": "replacement"}]
}
```

The fields have these meanings:

| Field | Meaning |
| --- | --- |
| `kind` | `shell`, `file_write`, `file_edit`, or `other` |
| `command` | Shell text, or `null` for other tools |
| `cwd` | Absolute working directory of the intercepted operation |
| `paths` | Absolute explicit file targets, or empty when targets are unknown |
| `harness` | Adapter identity, such as `codex` or `claude` |
| `tool_name` | Original tool name |
| `tool_input` | Original tool arguments, unchanged, including unknown fields |
| `changes` | File changes: absolute `path`, `operation` (`write`, `edit`, or `delete`), and text `content` |

Adapters recognize shell calls and common direct editing tools, including
`Write`, `Edit`, `MultiEdit`, `NotebookEdit`, and `apply_patch`. Patch targets
include additions, updates, deletions, and both sides of renames. Unknown tools
still reach every applicable checker as `other`. Custom policies can inspect
their original names and arguments.

Since version 0.3.0, checkers can use `changes` without parsing tool arguments. Writes contain
the supplied body, and edits contain replacement text. `MultiEdit` joins
replacement strings with newlines. Notebook edits contain the supplied cell
source. Patches contain added lines for each target. A rename produces a
source deletion and destination write. Deletions have empty content. Shell and
unknown tools have no inferred file changes.

`content` is the supplied text, not a reconstruction of the resulting file.
Checks that need existing content must read the file themselves. Patch fragments
might not contain complete frontmatter or other surrounding syntax.

Custom harnesses can pass `changes` to `i-insist check`. Their paths participate
in rule discovery even when omitted from `paths`. Existing callers can omit
`changes`, but checkers requiring file content might reject those events.

Provider installers must replace only their own registrations, write them
atomically, remove obsolete rules, and remove their registrations on uninstall.
Providers also maintain their checker programs, messages, and dependencies.
Checkers can read existing plugin-specific policy configuration.
Use [human approval](#human-overrides) to override rules that permit it.

## Upgrade from 0.3.x

Version 0.4.0 changes the checker protocol and registration schema. Upgrade each
provider to emit a denial string or `null`, then regenerate its registrations:
remove `message` and `enabled`, and move denial text into checker code. Old
registrations and boolean checkers fail closed. There is no compatibility fallback.
Providers must require i-insist 0.4.0 or later before replacing their registrations.

Coordinate runner and provider upgrades, then restart the harness. The runner
can't regenerate another provider's files: that provider's setup owns migration.
See [the ownership decision](decisions/003-checker-owned-policy.md).

## Protecting configuration

`i-insist install` installs `~/.i-insist/i-insist.toml`. Its checker blocks
explicit file edits under `.i-insist` and common shell mutations that name those
directories. Registration changes require human approval. The same rule ships in
[the configuration protection example](../examples/config-protection.toml).
Repeated installation regenerates this provider-owned registration.

The shell check recognizes common file commands, redirections, in-place `sed`,
and interpreter commands naming `.i-insist`. For simple shell lists and pipelines,
each command is checked separately, so a config read does not make an unrelated
test invocation require approval. Quoting, escaping, and redirection operators
are preserved. Directory changes, variable assignments, shell control flow,
nested substitutions, and unnormalized heredocs keep the conservative whole-call
check. Opaque scripts, dynamically
constructed paths, and commands that change directories internally can evade
it. This remains a cooperative guard, not a filesystem sandbox.

## Provider dependency setup

Providers can install a missing runner with `uv tool install` and then call
`i-insist ensure`. It registers all three hooks for Codex and Claude Code installations
found on `PATH` or through existing user configuration. Explicitly disabled hooks
cause a nonzero exit. It checks user settings, Codex per-hook disable state, and
conservatively rejects disable flags in the current directory's ancestry.

Registration alone doesn't confirm that hooks run. The harness controls hook
trust, managed policy, command-line overrides, and the running session's settings.
Restart and examine `/hooks` after installation. `ensure` never creates trust
records or clears explicit disable settings. Providers must stop migration when
it fails and keep existing guards until setup succeeds.

## Human overrides

Providers can set `overridable = false` to keep a rule running after human
approval, including shell environment overrides. The default is `true`.
The provider controls this setting. Invalid configuration still blocks approved calls.

Include `i insist` anywhere in your message, in any capitalization:

```text
ok i insist, update both protected files
```

Matching is a case-insensitive substring check, including quoted text and code blocks.

`UserPromptSubmit` records approval for the current response. Subsequent tool
calls in that response bypass overridable rules, including direct file edits and
custom tools. A new user message replaces the approval with that message's decision.
Starting or resuming a session clears approval. Compaction preserves it. Codex
also requires the same `turn_id`, so approval doesn't transfer to another turn.
The agent remains responsible for respecting the scope you described.

For a single shell tool invocation, the agent can use this explicit prefix only
after human authorization:

```sh
HUMAN_PERMISSION_GRANTED=1 some-command
```

This skips overridable checks for that shell tool call, including any chained
commands. The approval applies only to that call. The runner recognizes only a
leading assignment. Mentions in arguments or comments, inherited variables, and
exported variables don't grant approval. Approval never overrides another plugin
or the harness's own permission policy.

The approval cache stores a boolean and optional turn ID, not your prompt text,
under `$XDG_CACHE_HOME/i-insist/approvals/` (default `~/.cache/i-insist/approvals/`).
Cache keys separate harnesses and sessions. Missing or corrupt records don't
grant approval. The runner uses no approval IDs, synthetic tool calls, or
transcript parsing. See [the approval decision](decisions/001-approval.md).

## Other harnesses

Send a normalized event to:

```sh
i-insist check < event.json
```

The result is `{"blocked": false, "message": null}` or
`{"blocked": true, "message": "your configured message"}`. Both normal decisions
exit 0. Input, configuration, or checker failures return `blocked: true` and exit 2.
The caller must honor both the decision and execution failures. This endpoint
recognizes the shell marker but doesn't read Codex or Claude Code approval state.

An adapter normalizes harness tool calls, records message approval, and converts the
decision into its harness's blocking response. Checkers need no changes when
another harness provides the same neutral event.

Hook coverage depends on the harness. For example, Codex doesn't issue a fresh
`PreToolUse` for `write_stdin` or hosted web tools. If the harness never calls a
hook, this package can't intercept that action. A missing command-line tool or a
harness-level hook timeout can also prevent the runner from issuing a denial. Keep providers
fast enough to fit the enclosing hook timeout, 600 seconds in generated registrations.
This is a cooperative agent guard, not a sandbox: registered checkers themselves
run code with your account's privileges.

For hook details, see the [Codex reference](https://learn.chatgpt.com/docs/hooks)
and the [Claude Code reference](https://code.claude.com/docs/en/hooks).
