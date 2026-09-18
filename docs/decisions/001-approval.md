# Approval follows the human message

Status: initial implementation decision.

The user wants cooperative guards, trusts agents to follow instructions, and
rejected an `allow-once <blocked-call-id>` workflow as too complex. Direct editing
tools can't carry an inline shell environment assignment, and approval must
allow several operations during a response.

Use the public `UserPromptSubmit` hook to recognize `i insist` anywhere in the
human message, ignoring case, and record approval for that session.
`PreToolUse` checks that record. Codex also
matches its public turn ID. Reset on a new prompt, session startup, or session resume,
preserve through compaction, and retain the inline environment marker for shell
tool calls. This avoids reading unstable transcript formats or injecting tool
calls into a harness.

The trade-off is intentionally broad approval for the response. The agent, not
this package, interprets the human's requested scope. A shell marker likewise
represents the agent's claim of authorization. If independently verified,
operation-specific permission becomes a requirement, replace this mechanism with
a harness-supported approval flow. Don't present this boolean as operation-specific
permission.

Exact syntax and runtime behavior are canonical in the
[integration reference](../reference.md#human-overrides).

Provider migration preserves policies that explicitly forbid overrides. Such
rules set `overridable = false`. Approval skips only overridable rules.
