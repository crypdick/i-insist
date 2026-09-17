# i-insist

Block agent tool calls using your own checks. Say **“I insist”** to override them.

Rules live in `~/.i-insist/*.toml` globally and `.i-insist/*.toml` within a
directory or repository. Each rule runs a program you own and displays your
message when that program returns `true`. Codex and Claude Code integrations use
public lifecycle hooks. Other harnesses can use the neutral JSON interface.

## Install

Requires Python 3.12 or newer. Hook installation supports Linux and macOS.

```sh
uv tool install 'git+https://github.com/crypdick/i-insist@main'
i-insist install codex
i-insist install claude
```

Run the install command only for the harnesses you use. It registers
`PreToolUse`, `UserPromptSubmit`, and `SessionStart` hooks in:

- Codex: `~/.codex/hooks.json`, or `$CODEX_HOME/hooks.json`.
- Claude Code: `~/.claude/settings.json`, or `$CLAUDE_CONFIG_DIR/settings.json`.

The installer preserves other settings and hooks, keeps existing file permissions
and symlinks, and can be run repeatedly without duplicate registrations. Writes
are atomic; concurrent i-insist installers coordinate through a lock file beside
the configuration. Start a new harness session after installation and review
Codex hooks through `/hooks` when required by your settings.

Update the shared runner through uv:

```sh
uv tool upgrade i-insist
```

Re-run `i-insist install <harness>` when an update changes hook registrations.
There is no separately installed native plugin or second copy of the runner.

For a checkout under development:

```sh
uv tool install --reinstall .
```

To remove the integration, unregister hooks before uninstalling the tool:

```sh
i-insist uninstall codex
i-insist uninstall claude
uv tool uninstall i-insist
```

Uninstall removes only i-insist's hook handlers. It leaves provider rules,
approval caches, and unrelated configuration intact.

No rules are installed automatically. Existing guards from other plugins remain
independent until their providers migrate them.

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
message = "These originals require your permission to edit."
# enabled = false
# timeout = 10
```

`enabled` defaults to `true`. A disabled rule's checker does not run.
`timeout` is the checker's time limit in seconds; it defaults to 10 and must be
positive. Each TOML can contain multiple `[[rules]]`. IDs must be unique within
their file. Invalid configuration blocks execution rather than silently omitting
a check, including invalid fields on disabled rules.

Checker locations are unrestricted. `.i-insist/scripts/` is an optional
convention, not a requirement. The checker is an argument list executed directly,
without a shell. Use `sh` explicitly if you want a shell script. The checker runs
from its TOML file's directory, so relative script paths resolve there. The
intercepted tool's working directory is passed in the event as `cwd`.

Discovery combines:

1. `~/.i-insist/*.toml`.
2. `.i-insist/*.toml` in ancestors of the tool's working directory, outermost first.
3. The same ancestry for explicit file targets, in target order. This protects
   direct edits made from outside the target directory.

Directories are resolved and deduplicated; each directory's TOML files run in
filename order, with rules in declaration order. Discovery does not recursively
scan `.i-insist/` subdirectories. Paths use their physical, symlink-resolved
locations. Global and local rules accumulate; a local disabled rule does not
disable a global rule with the same ID. The first matching rule supplies the
block message, unchanged.

Shell text is opaque to discovery: `cd`, `git -C`, shell write targets, and paths
inside custom tool arguments are not inferred. Put such policies at a scope the
invocation reaches, or resolve their targets in your provider's checker.

## Write a checker

Read one JSON object on stdin. Print exactly one JSON boolean on stdout and exit
with status 0: `true` blocks; `false` allows the next check. Write any debugging
output to stderr. Checker crashes, invalid output, missing executables, and
timeouts block with an error. On POSIX, timeout cleanup kills the checker process
group, including its children unless they detach into another session.

```python
import json
import sys
from pathlib import Path


def should_block(event: dict) -> bool:
    return any("_sources" in Path(path).parts for path in event["paths"])


print(json.dumps(should_block(json.load(sys.stdin))))
```

This example protects **direct file edits**. It does not parse shell writes.
A runnable copy is in [examples/project](examples/project).

Checker input:

```json
{
  "kind": "file_write",
  "command": null,
  "cwd": "/repo",
  "paths": ["/repo/_sources/original.txt"],
  "harness": "claude",
  "tool_name": "Write",
  "tool_input": {"file_path": "_sources/original.txt", "content": "replacement"}
}
```

| Field | Meaning |
| --- | --- |
| `kind` | `shell`, `file_write`, `file_edit`, or `other` |
| `command` | Shell text, or `null` for other tools |
| `cwd` | Absolute working directory of the intercepted operation |
| `paths` | Absolute explicit file targets; empty when targets are unknown |
| `harness` | Adapter identity, such as `codex` or `claude` |
| `tool_name` | Original tool name |
| `tool_input` | Original tool arguments, unchanged, including unknown fields |

Adapters recognize shell calls and common direct editing tools, including
`Write`, `Edit`, `MultiEdit`, `NotebookEdit`, and `apply_patch`. Patch targets
include additions, updates, deletions, and both sides of renames. Unknown tools
still reach every applicable checker as `other`; custom policies can inspect
their original names and arguments.

Providers own their TOML, checker programs, and dependencies. Installers should
update only their own files, preserve user changes such as `enabled = false`,
and remove their registrations on uninstall. Existing plugin-specific policy
configuration can stay where it is; the provider's checker reads it.

## Protecting configuration

`i-insist install` installs `~/.i-insist/i-insist.toml`. Its checker blocks
explicit file edits under `.i-insist` and common shell mutations that name those
directories. Human approval is required for changes, including disabling this
rule. The same rule ships in [examples/config-protection.toml](examples/config-protection.toml).
Existing configuration is preserved on repeated installation.

The shell check recognizes common file commands, redirections, in-place `sed`,
and interpreter commands naming `.i-insist`. Opaque scripts, dynamically
constructed paths, and commands that change directories internally can evade
it. This remains a cooperative guard, not a filesystem sandbox.

## Provider dependency setup

Providers can install a missing runner with `uv tool install` and then call
`i-insist ensure`. It registers all three hooks for Codex/Claude installations
found on `PATH` or through existing user configuration. Explicit disabled hooks
cause a nonzero exit. It checks user settings, Codex per-hook disable state, and
conservatively rejects disable flags in the current directory's ancestry.

Registration is not proof of live execution: Codex hook trust, managed policy,
command-line overrides, and a running session's snapshot remain harness-owned.
Restart and review `/hooks` after installation. `ensure` never creates trust
records or clears explicit disable settings. Providers must stop migration when
it fails and keep existing guards until setup succeeds.

## Human overrides

Rules may set `overridable = false` (default: `true`). These rules still run
after human approval, including shell environment overrides. `enabled = false`
still disables a rule. Invalid configuration still blocks approved calls.

Send `I insist` on its own line, optionally followed by `.` or `!`, for example:

```text
I insist.
Update both protected files.
```

Matching ignores case. Quoted lines, fenced code, and indented code examples do
not grant approval. A phrase embedded in another sentence does not match.

`UserPromptSubmit` records approval for the current response. Subsequent tool
calls in that response bypass these rules, including direct file edits and custom
tools. A new user message replaces the approval with that message's decision.
Starting or resuming a session clears approval; compaction preserves it. Codex
also requires the same `turn_id`, so approval does not transfer to another turn.
The agent remains responsible for respecting the scope you described.

For a single shell tool invocation, the agent may use this explicit prefix only
after human authorization:

```sh
HUMAN_PERMISSION_GRANTED=1 some-command
```

This skips checks for that shell **tool call**, including any chained commands in
it; it does not persist to later calls. Only a leading assignment is recognized.
Mentions in arguments or comments and inherited/exported environment variables
do not grant approval. Approval never overrides another plugin or the harness's
own permission policy.

The approval cache stores a boolean and optional turn ID, not your prompt text,
under `$XDG_CACHE_HOME/i-insist/approvals/` (default `~/.cache/i-insist/approvals/`).
Cache keys separate harnesses and sessions. Missing or corrupt records do not
grant approval. No approval IDs, synthetic tool calls, or transcript parsing are
used. See [the approval decision](docs/decisions/001-approval.md).

## Other harnesses

Send a normalized event to:

```sh
i-insist check < event.json
```

The result is `{"blocked": false, "message": null}` or
`{"blocked": true, "message": "your configured message"}`. Both normal decisions
exit 0; input/configuration/checker failures return `blocked: true` and exit 2.
The caller must honor both the decision and execution failures. This endpoint
recognizes the shell marker but does not read Codex/Claude approval state.

An adapter owns native tool normalization, message approval, and converting the
decision into its harness's blocking response. Checkers need no changes when
another harness provides the same neutral event.

Hook coverage depends on the harness. For example, Codex does not issue a fresh
`PreToolUse` for `write_stdin` or hosted web tools. If the harness never calls a
hook, this package cannot intercept that action. A missing CLI or a harness-level
hook timeout can also prevent the runner from issuing a denial. Keep providers
fast enough to fit the enclosing hook timeout (600 seconds in generated registrations).
This is a cooperative agent guard, not a sandbox: registered checkers themselves
execute code with your account's privileges.

Public hook references: [Codex](https://learn.chatgpt.com/docs/hooks) and
[Claude Code](https://code.claude.com/docs/en/hooks).

## Develop

Runtime type checks instrument package imports through Beartype. Development checks run through
prek and uv; install hooks once per checkout with `uv run prek install`.

Create an isolated checkout with one command:

```sh
new-feature <name> --no-agent && uv sync --locked --directory ".worktrees/<name>"
```

```sh
uv sync --locked
uv run prek run --all-files
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Tests exercise installed hook commands and actual checker subprocesses using
temporary homes, projects, and approval caches. They do not enable hooks in your
active harness.

## Publishing

`.github/workflows/publish.yml` runs tests, lint, formatting, and a package build
on pull requests. Each successful push to `main` publishes a release to PyPI
and creates a GitHub release with the wheel and source distribution attached.
Manual workflow dispatch retries a release without needing another commit.

The workflow preserves an unpublished version from `pyproject.toml`; otherwise,
it increments the latest stable PyPI patch version. Use `uv version --bump minor`
or `uv version --bump major` for an intentional version change. The release
commit updates `pyproject.toml` and `uv.lock` together. Superseded runs are
skipped, and retries reuse their release commit and already uploaded files.

Publishing uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
and the GitHub environment `pypi`, restricted to `main`. No PyPI API token is
stored in GitHub. To configure a first publication, add a pending publisher at
[PyPI account publishing](https://pypi.org/manage/account/publishing/) with:

- Project: `i-insist`
- GitHub owner: `crypdick`
- Repository: `i-insist`
- Workflow filename: `publish.yml`
- Environment: `pypi`

After the first release, install from PyPI with `uv tool install i-insist`.
