# Approval follows the human message

Status: initial implementation decision.

The user wants cooperative guards, trusts agents to follow instructions, and
rejected an `allow-once <blocked-call-id>` workflow as too complex. Direct editing
tools cannot carry an inline shell environment assignment, and approval should
allow several operations during a response.

Use the public `UserPromptSubmit` hook to recognize a standalone “I insist” line
and record a session-scoped approval. `PreToolUse` checks that record; Codex also
matches its public turn ID. Reset on a new prompt or session startup/resume,
preserve through compaction, and retain the inline environment marker for shell
tool calls. This avoids reading unstable transcript formats or injecting tool
calls into a harness.

The trade-off is intentionally broad approval for the response. The agent, not
this package, interprets the human's requested scope. A shell marker likewise
represents the agent's claim of authorization. If independently verified,
operation-specific permission becomes a requirement, replace this mechanism with
a harness-supported approval flow; do not disguise this boolean as such a flow.

Exact syntax and runtime behavior are canonical in [README](../../README.md#human-overrides).

Provider migration preserves policies that explicitly forbid overrides. Such
rules set `overridable = false`; approval skips only overridable rules.
