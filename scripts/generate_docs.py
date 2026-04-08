from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
COMMANDS_DIR = DOCS_DIR / "commands"
SYSTEMS_DIR = DOCS_DIR / "systems"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aegis.command_catalog import (
    CATEGORIES,
    SYSTEM_GUIDES,
    category_slug,
    commands_for_category,
    iter_commands,
    validate_catalog,
)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def markdown_list(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items)


def build_command_page(entry) -> str:
    aliases = ", ".join(f"`{alias}`" for alias in entry.aliases) if entry.aliases else "None"
    slug_map = {candidate.name: candidate.slug for candidate in iter_commands()}
    related = (
        ", ".join(f"[`{name}`]({slug_map[name]}.md)" for name in entry.related if name in slug_map)
        if entry.related
        else "None"
    )
    examples = "\n".join(f"- `{example}`" for example in entry.examples) if entry.examples else "- None"
    notes = "\n".join(f"- {note}" for note in entry.notes) if entry.notes else "- None"
    syntax = "\n".join(f"- `{line}`" for line in entry.syntax)

    return f"""
# {entry.name}

> Generated from the shared Aegis command catalog.

## Summary

{entry.summary}

## Description

{entry.description}

## Syntax

{syntax}

## Access

{entry.access}

## Aliases

{aliases}

## Examples

{examples}

## Notes

{notes}

## Related

{related}
"""


def build_category_page(category) -> str:
    entries = commands_for_category(category.key)
    sections = []
    for entry in entries:
        sections.append(
            "\n".join(
                [
                    f"### [`{entry.name}`]({entry.slug}.md)",
                    "",
                    entry.summary,
                    "",
                    f"- **Syntax:** `{entry.syntax[0]}`",
                    f"- **Access:** {entry.access}",
                ]
            )
        )

    body = "\n\n".join(sections) if sections else "No commands documented yet."
    return f"""
# {category.title}

{category.summary}

## Commands

{body}
"""


def build_command_index() -> str:
    sections = []
    for category in CATEGORIES:
        entries = commands_for_category(category.key)
        lines = [f"- [{entry.name}]({entry.slug}.md): {entry.summary}" for entry in entries]
        sections.append(f"## [{category.title}]({category_slug(category.key)}.md)\n\n" + "\n".join(lines))

    return """
# Commands

Browse the full Aegis command reference by category or jump straight into a specific command.

""" + "\n\n".join(sections)


def build_system_index() -> str:
    lines = [
        f"- [{guide.title}]({guide.slug}.md): {guide.summary}"
        for guide in SYSTEM_GUIDES
    ]
    return """
# Systems

These guides explain how Aegis features work at a system level, not just command-by-command.

""" + "\n".join(lines)


def generate_docs() -> None:
    validate_catalog(include_runtime_check=True)

    write_text(COMMANDS_DIR / "index.md", build_command_index())
    for category in CATEGORIES:
        write_text(COMMANDS_DIR / f"{category_slug(category.key)}.md", build_category_page(category))
    for entry in iter_commands():
        write_text(COMMANDS_DIR / f"{entry.slug}.md", build_command_page(entry))

    write_text(SYSTEMS_DIR / "index.md", build_system_index())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MkDocs command pages from the Aegis catalog.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the catalog without writing any files.",
    )
    args = parser.parse_args()

    if args.check:
        validate_catalog(include_runtime_check=True)
        print("Aegis command catalog is valid.")
        return

    generate_docs()
    print("Aegis docs generated successfully.")


if __name__ == "__main__":
    main()
