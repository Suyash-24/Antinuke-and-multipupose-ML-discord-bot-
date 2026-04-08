from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class Step:
    title: str
    commands: list[str]
    expected: list[str]


def with_prefix(prefix: str, command: str) -> str:
    return f"{prefix}{command}".strip()


def render_steps(steps: Iterable[Step]) -> str:
    lines: list[str] = []
    lines.append("Aegis Anti-Nuke Full Smoke Test Plan")
    lines.append("=")
    lines.append("")
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step.title}")
        lines.append("   Commands:")
        for cmd in step.commands:
            lines.append(f"   - {cmd}")
        lines.append("   Expected:")
        for expectation in step.expected:
            lines.append(f"   - {expectation}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_threshold_commands(prefix: str) -> list[str]:
    return [
        with_prefix(prefix, "antinuke threshold bot_add 1 60"),
        with_prefix(prefix, "antinuke threshold admin_permission_grant 1 60"),
        with_prefix(prefix, "antinuke threshold channel_create 5 10"),
        with_prefix(prefix, "antinuke threshold channel_delete 2 10"),
        with_prefix(prefix, "antinuke threshold channel_update 5 10"),
        with_prefix(prefix, "antinuke threshold role_create 5 10"),
        with_prefix(prefix, "antinuke threshold role_delete 2 10"),
        with_prefix(prefix, "antinuke threshold role_update 5 10"),
        with_prefix(prefix, "antinuke threshold webhook_create 2 10"),
        with_prefix(prefix, "antinuke threshold webhook_delete 2 10"),
        with_prefix(prefix, "antinuke threshold webhook_update 5 10"),
        with_prefix(prefix, "antinuke threshold guild_update 2 60"),
    ]


def build_protect_toggle_commands(prefix: str) -> list[str]:
    events = [
        "bot_add",
        "admin_permission_grant",
        "channel_create",
        "channel_delete",
        "channel_update",
        "role_create",
        "role_delete",
        "role_update",
        "webhook_create",
        "webhook_delete",
        "webhook_update",
        "guild_update",
    ]

    commands: list[str] = []
    for event_name in events:
        commands.append(with_prefix(prefix, f"antinuke protect {event_name} off"))
        commands.append(with_prefix(prefix, f"antinuke protect {event_name} on"))
    return commands


def build_plan(prefix: str) -> list[Step]:
    return [
        Step(
            title="Pre-flight baseline and health",
            commands=[
                with_prefix(prefix, "antinuke status"),
                with_prefix(prefix, "antinuke incidents 5"),
            ],
            expected=[
                "Status panel renders successfully.",
                "Health is Ready, or degraded reasons are clearly listed if permissions/hierarchy are missing.",
                "Incidents command responds without errors.",
            ],
        ),
        Step(
            title="Enable anti-nuke and set log destination",
            commands=[
                with_prefix(prefix, "antinuke enable"),
                with_prefix(prefix, "antinuke mode contain"),
                with_prefix(prefix, "antinuke log #antinuke-log"),
                with_prefix(prefix, "antinuke status"),
            ],
            expected=[
                "Anti-nuke is enabled.",
                "Mode shows contain.",
                "Anti-nuke log channel is set to #antinuke-log.",
            ],
        ),
        Step(
            title="Threshold commands full coverage",
            commands=build_threshold_commands(prefix) + [with_prefix(prefix, "antinuke status")],
            expected=[
                "Every threshold command succeeds.",
                "Status panel Thresholds section reflects all configured values.",
            ],
        ),
        Step(
            title="Protection toggle full coverage",
            commands=build_protect_toggle_commands(prefix) + [with_prefix(prefix, "antinuke status")],
            expected=[
                "Each protect off/on command succeeds for all event types.",
                "No invalid-event or validation errors are returned.",
            ],
        ),
        Step(
            title="Trust workflow (server owner only)",
            commands=[
                with_prefix(prefix, "antinuke trust"),
                with_prefix(prefix, "antinuke trust add @TrustedUser"),
                with_prefix(prefix, "antinuke trust add @TrustedRole"),
                with_prefix(prefix, "antinuke trust"),
                with_prefix(prefix, "antinuke trust remove @TrustedUser"),
                with_prefix(prefix, "antinuke trust remove @TrustedRole"),
                with_prefix(prefix, "antinuke trust"),
            ],
            expected=[
                "Trust add/remove works for both user and role targets.",
                "Trust list reflects each change.",
                "Non-owner callers are blocked from trust commands.",
            ],
        ),
        Step(
            title="Event trigger matrix (all anti-nuke event types)",
            commands=[
                "Manual action by NON-TRUSTED test actor: invite/add a bot account (bot_add).",
                "Manual action by NON-TRUSTED test actor: grant Administrator or dangerous perms via role/member update (admin_permission_grant).",
                "Manual action by NON-TRUSTED test actor: create, update, and delete a temporary text channel.",
                "Manual action by NON-TRUSTED test actor: create, update, and delete a temporary role.",
                "Manual action by NON-TRUSTED test actor: create, update, and delete a temporary webhook.",
                "Manual action by NON-TRUSTED test actor: change guild name or similar guild setting (guild_update).",
                with_prefix(prefix, "antinuke incidents 10"),
            ],
            expected=[
                "Incidents show entries for each triggered event family.",
                "Incident reason includes threshold/mixed-score trigger context.",
                "Anti-nuke logs contain actor, target, event, and response details.",
            ],
        ),
        Step(
            title="Mode behavior validation: alert, contain, ban",
            commands=[
                with_prefix(prefix, "antinuke mode alert"),
                "Trigger one destructive action as NON-TRUSTED actor.",
                with_prefix(prefix, "antinuke incidents 5"),
                with_prefix(prefix, "antinuke mode contain"),
                "Trigger one destructive action as NON-TRUSTED actor.",
                with_prefix(prefix, "antinuke incidents 5"),
                with_prefix(prefix, "antinuke mode ban"),
                "Trigger one destructive action as NON-TRUSTED actor on an account below bot hierarchy.",
                with_prefix(prefix, "antinuke incidents 5"),
                with_prefix(prefix, "antinuke mode contain"),
            ],
            expected=[
                "Alert mode records incidents without applying punishment.",
                "Contain mode strips dangerous roles or removes bot actors when possible.",
                "Ban mode attempts to ban untrusted actor (if hierarchy permits).",
            ],
        ),
        Step(
            title="Freeze handling and cleanup",
            commands=[
                with_prefix(prefix, "antinuke status"),
                with_prefix(prefix, "antinuke resetfreeze"),
                with_prefix(prefix, "antinuke status"),
                with_prefix(prefix, "antinuke disable"),
                with_prefix(prefix, "antinuke status"),
            ],
            expected=[
                "Active freeze is visible before reset when triggered.",
                "resetfreeze clears emergency freeze state.",
                "disable turns anti-nuke off cleanly.",
            ],
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate anti-nuke smoke test commands for Aegis.")
    parser.add_argument("--prefix", default="^", help="Command prefix to use in generated commands.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file path. If omitted, output is printed to stdout.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = build_plan(args.prefix)
    output = render_steps(plan)

    if args.output is None:
        print(output, end="")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Wrote anti-nuke smoke test plan to {args.output}")


if __name__ == "__main__":
    main()
