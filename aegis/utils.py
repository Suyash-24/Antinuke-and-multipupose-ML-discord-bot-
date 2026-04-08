from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Iterable, TypeVar

import discord

T = TypeVar("T")

_WHITESPACE_RE = re.compile(r"\s+")


def utcnow() -> datetime:
    return datetime.now(UTC)


def humanize_duration(value: timedelta | int | None) -> str:
    if value is None:
        return "Permanent"

    seconds = int(value.total_seconds()) if isinstance(value, timedelta) else int(value)
    if seconds <= 0:
        return "0s"

    parts: list[str] = []
    for suffix, chunk in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        amount, seconds = divmod(seconds, chunk)
        if amount:
            parts.append(f"{amount}{suffix}")
    return " ".join(parts)


def format_timestamp(dt: datetime, style: str = "F") -> str:
    return discord.utils.format_dt(dt, style=style)


def truncate(text: str, limit: int = 700) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def normalize_message_content(content: str) -> str:
    return _WHITESPACE_RE.sub(" ", content.strip().lower())


def format_identity(entity: object | None) -> str:
    if entity is None:
        return "System"

    entity_id = getattr(entity, "id", None)
    display_name = getattr(entity, "display_name", None) or getattr(entity, "name", None)
    if entity_id is None:
        return str(entity)
    if display_name:
        return f"{display_name} (`{entity_id}`)"
    return f"`{entity_id}`"


def parse_ratio(argument: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", argument)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def unique_by_id(items: Iterable[T]) -> list[T]:
    seen: set[int] = set()
    unique: list[T] = []
    for item in items:
        item_id = getattr(item, "id", None)
        if item_id is None or item_id in seen:
            continue
        seen.add(item_id)
        unique.append(item)
    return unique

