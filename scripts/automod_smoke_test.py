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
    lines.append("Aegis AutoMod Smoke Test Plan")
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


def build_plan(prefix: str) -> list[Step]:
    return [
        Step(
            title="Log and baseline setup",
            commands=[
                with_prefix(prefix, "modlog #mod-log"),
                with_prefix(prefix, "messagelog #message-log"),
                with_prefix(prefix, "serverlog #server-log"),
                with_prefix(prefix, "automod show"),
            ],
            expected=[
                "All log channels are acknowledged by the bot.",
                "AutoMod overview panel is visible with current values.",
            ],
        ),
        Step(
            title="Punishment ladder precondition",
            commands=[
                with_prefix(prefix, "punishment 2 warn"),
                with_prefix(prefix, "punishment 4 mute 10m"),
                with_prefix(prefix, "punishment 6 kick"),
                with_prefix(prefix, "punishment 8 softban"),
                with_prefix(prefix, "punishment 10 ban 1h"),
            ],
            expected=[
                "Punishment table shows all configured thresholds.",
                "No AutoMod command rejects with missing punishments.",
            ],
        ),
        Step(
            title="Enable Vortex-style AutoMod controls",
            commands=[
                with_prefix(prefix, "automod antiinvite 2"),
                with_prefix(prefix, "automod antireferral 2"),
                with_prefix(prefix, "automod anticopypasta 2"),
                with_prefix(prefix, "automod antieveryone 1"),
                with_prefix(prefix, "automod maxmentions 4"),
                with_prefix(prefix, "automod maxrolementions 2"),
                with_prefix(prefix, "automod maxlines 6"),
                with_prefix(prefix, "automod antiduplicate 4 2 1"),
                with_prefix(prefix, "automod resolvelinks on"),
                with_prefix(prefix, "automod autodehoist !"),
                with_prefix(prefix, "automod antiraid on"),
                with_prefix(prefix, "automod show"),
            ],
            expected=[
                "Snapshot shows anti-copypasta, resolve-links, and dehoist settings enabled.",
                "Duplicate filter shows strike threshold 4 and delete threshold 2.",
            ],
        ),
        Step(
            title="Invite whitelist and custom filters",
            commands=[
                with_prefix(prefix, "automod whitelist add 123456789012345678"),
                with_prefix(prefix, "automod whitelist show"),
                with_prefix(prefix, "automod filter add badads 3 \"earn money fast\" *nitro* `free\\s+gift`"),
                with_prefix(prefix, "automod filter list"),
            ],
            expected=[
                "Whitelist includes the configured guild ID.",
                "Filter list includes badads with 3 strikes and all patterns.",
            ],
        ),
        Step(
            title="Functional trigger checks (use a non-exempt test member)",
            commands=[
                "Send an external Discord invite in chat.",
                "Send a referral short-link in chat (for example bit.ly link).",
                "Send @everyone or @here from a member without mention-everyone permission.",
                "Send a message that mentions 5+ users.",
                "Send a message that mentions 3+ roles.",
                "Send a message with more than 6 lines.",
                "Send the same normalized message at least 4 times quickly.",
                "Send a known copypasta sample (for example Navy Seal opener).",
                "Send text matching the custom filter (for example earn money fast).",
                "Send a redirect link that eventually resolves to an invite or referral URL.",
                with_prefix(prefix, "check @test-user"),
            ],
            expected=[
                "Messages are deleted where applicable and strikes are added.",
                "Mod logs show combined AutoMod reasons when multiple rules hit one message.",
                "Check command confirms strike growth for the test member.",
            ],
        ),
        Step(
            title="Raid mode and dehoist checks",
            commands=[
                "Trigger rapid joins in a test guild to cross the anti-raid threshold.",
                "Confirm raid mode auto-enables and blocks new joins.",
                "Wait beyond quiet window and verify raid mode auto-disables on next join.",
                "Change a test member nickname to a hoisted prefix (for example !!!Name).",
            ],
            expected=[
                "Server logs include raid mode enable and disable transitions.",
                "Blocked join events are logged while raid mode is active.",
                "Hoisted nickname is adjusted by auto-dehoist.",
            ],
        ),
        Step(
            title="Cleanup",
            commands=[
                with_prefix(prefix, "automod whitelist remove 123456789012345678"),
                with_prefix(prefix, "automod filter remove badads"),
                with_prefix(prefix, "automod autodehoist off"),
                with_prefix(prefix, "automod resolvelinks off"),
                with_prefix(prefix, "automod antiraid off"),
                with_prefix(prefix, "automod show"),
            ],
            expected=[
                "Temporary test filter and whitelist entries are removed.",
                "Overview reflects cleanup settings.",
            ],
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AutoMod smoke test commands for Aegis.")
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
    print(f"Wrote smoke test plan to {args.output}")


if __name__ == "__main__":
    main()
