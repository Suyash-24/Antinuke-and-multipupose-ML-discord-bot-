from __future__ import annotations

from typing import Literal, Sequence

import discord

PanelTone = Literal["info", "success", "warning", "danger", "neutral"]

_PALETTE: dict[PanelTone, discord.Colour] = {
    "info": discord.Colour.from_str("#4F8CFF"),
    "success": discord.Colour.from_str("#1DB885"),
    "warning": discord.Colour.from_str("#E8A224"),
    "danger": discord.Colour.from_str("#E14D5A"),
    "neutral": discord.Colour.from_str("#7A8194"),
}


def build_panel(
    title: str,
    description: str | None = None,
    *,
    tone: PanelTone = "info",
    fields: Sequence[tuple[str, str]] = (),
    actions: Sequence[tuple[str, str]] = (),
    footer: str | None = None,
    thumbnail_url: str | None = None,
    accented: bool = True,
) -> discord.ui.LayoutView:
    items: list[discord.ui.Item] = []

    header = f"## {title}"
    if description:
        cleaned_description = description.strip()
        if cleaned_description.lower().startswith("aegis "):
            cleaned_description = cleaned_description[6:].lstrip()
            if cleaned_description:
                cleaned_description = cleaned_description[0].upper() + cleaned_description[1:]
        header = f"{header}\n{cleaned_description}"
    if thumbnail_url:
        items.append(
            discord.ui.Section(
                header,
                accessory=discord.ui.Thumbnail(thumbnail_url),
            )
        )
    else:
        items.append(discord.ui.TextDisplay(header))

    if fields:
        items.append(
            discord.ui.Separator(
                visible=True,
                spacing=discord.SeparatorSpacing.small,
            )
        )
        for name, value in fields:
            items.append(discord.ui.TextDisplay(f"**{name}**\n{value or 'Not set'}"))

    if actions:
        buttons = [
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label=label,
                url=url,
            )
            for label, url in actions[:5]
            if url
        ]
        if buttons:
            items.append(
                discord.ui.Separator(
                    visible=True,
                    spacing=discord.SeparatorSpacing.small,
                )
            )
            items.append(discord.ui.ActionRow(*buttons))

    if footer:
        items.append(
            discord.ui.Separator(
                visible=False,
                spacing=discord.SeparatorSpacing.small,
            )
        )
        items.append(discord.ui.TextDisplay(footer))

    container_kwargs: dict[str, discord.Colour] = {}
    if accented:
        container_kwargs["accent_color"] = _PALETTE[tone]

    container = discord.ui.Container(*items, **container_kwargs)
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view

