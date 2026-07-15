from __future__ import annotations

import re
import unicodedata


INVALID_WINDOWS_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
REPEATED_SEPARATORS = re.compile(r"[\s_]+")


def safe_path_segment(value: str, *, fallback: str = "unnamed") -> str:
    """Keep a localized taxonomy label readable and safe as one path segment."""

    normalized = unicodedata.normalize("NFKC", value)
    normalized = INVALID_WINDOWS_FILENAME.sub("_", normalized)
    normalized = REPEATED_SEPARATORS.sub("_", normalized).strip(" ._")
    if not normalized:
        normalized = fallback
    return normalized[:80].rstrip(" ._") or fallback


def safe_entity_file_stem(game_entry_id: int, entity_name: str) -> str:
    """Keep the localized entity name readable while producing a safe file stem."""

    normalized = safe_path_segment(entity_name)
    return f"{game_entry_id}_{normalized}"
