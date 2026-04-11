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
    lines.append("Aegis Anti-Nuke Canary Lifecycle Smoke Test")
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
            title="Pre-flight anti-nuke status",
            commands=[
                with_prefix(prefix, "antinuke status"),
                with_prefix(prefix, "antinuke canary status"),
            ],
            expected=[
                "Anti-nuke status panel is visible.",
                "Canary status panel renders and shows capability gaps clearly if permissions are missing.",
            ],
        ),
        Step(
            title="Enable and arm canary trap",
            commands=[
                with_prefix(prefix, "antinuke enable"),
                with_prefix(prefix, "antinuke canary enable"),
                with_prefix(prefix, "antinuke canary status"),
            ],
            expected=[
                "Enable command succeeds without permission or hierarchy errors.",
                "Canary status shows Enabled (armed).",
                "Role, channel, and webhook canary values are present.",
            ],
        ),
        Step(
            title="Rotate canary assets",
            commands=[
                "Record current canary role/channel/webhook identifiers from status output.",
                with_prefix(prefix, "antinuke canary rotate"),
                with_prefix(prefix, "antinuke canary status"),
            ],
            expected=[
                "Rotate command succeeds.",
                "Canary status remains Enabled (armed).",
                "At least one canary identifier changes after rotation.",
            ],
        ),
        Step(
            title="Disable and clean up canary trap",
            commands=[
                with_prefix(prefix, "antinuke canary disable"),
                with_prefix(prefix, "antinuke canary status"),
                with_prefix(prefix, "antinuke status"),
            ],
            expected=[
                "Canary status shows Disabled.",
                "Canary assets are missing/not armed after cleanup.",
                "Anti-nuke can remain enabled and operational after canary disable.",
            ],
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate anti-nuke canary lifecycle smoke test commands for Aegis."
    )
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
    print(f"Wrote canary smoke test plan to {args.output}")


if __name__ == "__main__":
    main()