"""CLI and public Codex/Claude hook protocol adapters."""

from __future__ import annotations

import argparse
import json
import sys

from i_insist.approval import context, prompt_approves, shell_approved
from i_insist.events import Event, GuardError, Json, normalize_hook, object_input
from i_insist.rules import check


def reject_constant(value: str) -> None:
    raise GuardError(f"input contains non-JSON numeric constant {value}")


def deny(message: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": message,
                }
            }
        )
    )


def run_hook(data: dict[str, Json], harness: str, event_name: str) -> None:
    approvals, turn = context(data, harness, required=event_name != "pre-tool-use")
    if event_name == "user-prompt-submit":
        prompt = data.get("prompt")
        if not isinstance(prompt, str):
            raise GuardError("input prompt must be a string")
        assert approvals is not None
        approvals.record(prompt_approves(prompt), turn)
    elif event_name == "session-start":
        assert approvals is not None
        if data.get("source") != "compact":
            approvals.reset()
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": (
                            "i-insist checks tool calls using global and directory-local "
                            ".i-insist/*.toml rules. "
                            "When blocked, show the configured message and follow its guidance. "
                            "Only the human can authorize an override. "
                            "A standalone line 'I insist' in their latest message permits calls "
                            "for that response, except rules marked overridable = false. "
                            "For an explicitly authorized shell invocation, "
                            "you may prefix HUMAN_PERMISSION_GRANTED=1; never export it or "
                            "set it to authorize yourself. Do not rewrite rules to evade a block."
                        ),
                    }
                }
            )
        )
    else:
        event = normalize_hook(data, harness)
        approved = shell_approved(event) or bool(approvals and approvals.allows(turn))
        reason = check(event, approved=approved)
        if reason is not None:
            deny(reason)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run agent tool guards and human overrides.")
    commands = parser.add_subparsers(dest="command", required=True)
    hook = commands.add_parser("hook", help="Handle a public harness hook payload on stdin")
    hook.add_argument("--harness", choices=("codex", "claude"), required=True)
    hook.add_argument("event", choices=("pre-tool-use", "user-prompt-submit", "session-start"))
    commands.add_parser("protect-config", help="Check edits to i-insist configuration")
    commands.add_parser("ensure", help="Install and verify hooks for available harnesses")
    commands.add_parser("check", help="Check a normalized event from any harness on stdin")
    for action in ("install", "uninstall"):
        registration = commands.add_parser(
            action, help=f"{action.title()} user-level harness hooks"
        )
        registration.add_argument("harness", choices=("codex", "claude"))
    args = parser.parse_args()
    try:
        if args.command in {"install", "uninstall"}:
            from i_insist.install import configure

            path = configure(args.harness, install=args.command == "install")
            print(f"{args.command.title()}ed {args.harness} hooks: {path}")
            if args.command == "install":
                print("Restart the harness and review hook trust with /hooks.")
            return 0
        if args.command == "ensure":
            from i_insist.install import ensure

            for path in ensure():
                print(f"Registered and checked hooks: {path}")
            print("Restart the harness and review hook trust with /hooks.")
            return 0
        data = object_input(json.load(sys.stdin, parse_constant=reject_constant))
        if args.command == "protect-config":
            from i_insist.protect_config import should_block

            print(json.dumps(should_block(Event.from_json(data))))
        elif args.command == "hook":
            run_hook(data, args.harness, args.event)
        else:
            event = Event.from_json(data)
            reason = check(event, approved=shell_approved(event))
            print(json.dumps({"blocked": reason is not None, "message": reason}))
        return 0
    except (GuardError, OSError, ValueError) as exc:
        message = f"i-insist: {exc}"
        if args.command == "hook" and args.event == "pre-tool-use":
            deny(message)
            return 0
        if args.command == "check":
            print(json.dumps({"blocked": True, "message": message}))
        else:
            print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
