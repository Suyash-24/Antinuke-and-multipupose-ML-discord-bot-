from __future__ import annotations

from difflib import get_close_matches

from discord.ext import commands

from aegis.bot import AegisBot
from aegis.command_catalog import (
    CATEGORIES,
    category_docs_url,
    commands_for_category,
    docs_url,
    get_category,
    get_command,
    iter_commands,
)
from aegis.ui import build_panel


class HelpCog(commands.Cog):
    def __init__(self, bot: AegisBot) -> None:
        self.bot = bot

    def _resolve_command(self, query: str):
        entry = get_command(query)
        if entry is not None:
            return entry

        normalized = query.strip().lower()
        tail_matches = []
        for candidate in iter_commands():
            if candidate.name.split()[-1].lower() == normalized:
                tail_matches.append(candidate)
                continue
            if any(alias.split()[-1].lower() == normalized for alias in candidate.aliases):
                tail_matches.append(candidate)

        if len(tail_matches) == 1:
            return tail_matches[0]
        return None

    def _suggestions(self, query: str) -> str:
        terms = [entry.name for entry in iter_commands()]
        terms.extend(category.title.lower() for category in CATEGORIES)
        terms.extend(category.key for category in CATEGORIES)
        matches = get_close_matches(query.lower(), terms, n=5, cutoff=0.45)
        return ", ".join(f"`{match}`" for match in matches) if matches else "No close matches found."

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context[AegisBot], *, topic: str | None = None) -> None:
        docs_home = self.bot.config.docs_base_url

        if topic is None:
            fields = []
            for category in CATEGORIES:
                entries = commands_for_category(category.key)
                preview = ", ".join(f"`{entry.name}`" for entry in entries[:4])
                if len(entries) > 4:
                    preview = f"{preview}, ..."
                fields.append(
                    (
                        f"{category.title} ({len(entries)})",
                        f"{category.summary}\n{preview}",
                    )
                )

            actions = []
            if docs_home:
                fields.insert(0, ("Docs", docs_home))
                actions.append(("Open Docs", docs_home))

            await ctx.send(
                view=build_panel(
                    "Aegis Help",
                    "Browse command categories or run `^help <category>` / `^help <command>` for details.",
                    tone="info",
                    fields=fields,
                    actions=actions,
                )
            )
            return

        category = get_category(topic)
        if category is not None:
            entries = commands_for_category(category.key)
            fields = [
                (
                    entry.name,
                    f"{entry.summary}\n**Syntax** {entry.syntax[0]}\n**Access** {entry.access}",
                )
                for entry in entries
            ]

            actions = []
            if docs_home:
                actions.append(("Docs Home", docs_home))

            category_url = category_docs_url(docs_home, category.key)
            if category_url:
                actions.append(("Category Docs", category_url))

            await ctx.send(
                view=build_panel(
                    f"{category.title} Commands",
                    category.summary,
                    tone="info",
                    fields=fields,
                    actions=actions,
                )
            )
            return

        entry = self._resolve_command(topic)
        if entry is not None:
            fields = [
                ("Syntax", "\n".join(f"`{line}`" for line in entry.syntax)),
                ("Access", entry.access),
            ]
            if entry.aliases:
                fields.append(("Aliases", ", ".join(f"`{alias}`" for alias in entry.aliases)))
            if entry.examples:
                fields.append(("Examples", "\n".join(f"`{example}`" for example in entry.examples)))
            if entry.notes:
                fields.append(("Notes", "\n".join(entry.notes)))
            if entry.related:
                fields.append(("Related", ", ".join(f"`{name}`" for name in entry.related)))

            actions = []
            if docs_home:
                actions.append(("Docs Home", docs_home))

            command_url = docs_url(docs_home, entry)
            if command_url:
                actions.append(("Command Docs", command_url))

            await ctx.send(
                view=build_panel(
                    entry.name,
                    entry.description,
                    tone="success",
                    fields=fields,
                    actions=actions,
                )
            )
            return

        await ctx.send(
            view=build_panel(
                "Help Topic Not Found",
                "Aegis could not find that category or command.",
                tone="warning",
                fields=[
                    ("Topic", f"`{topic}`"),
                    ("Suggestions", self._suggestions(topic)),
                ],
                actions=[("Open Docs", docs_home)] if docs_home else (),
            )
        )


async def setup(bot: AegisBot) -> None:
    await bot.add_cog(HelpCog(bot))
