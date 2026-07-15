from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal, get_args
from urllib.parse import urlencode, urlsplit

Locale = Literal["ko-KR", "en-US", "ja-JP", "zh-TW"]
SUPPORTED_LOCALES: Final[tuple[Locale, ...]] = get_args(Locale)
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS_PATH: Final[Path] = PROJECT_ROOT / "config" / "targets.json"
LOCALES_PATH: Final[Path] = PROJECT_ROOT / "config" / "locales.json"
SKPORT_DETAIL_MAIN_TYPE_ID: Final[int] = 1
SKPORT_DOMAIN_SUB_TYPE_IDS: Final[dict[str, int]] = {
    "operator": 1,
    "weapon": 2,
    "gear": 4,
}
SKPORT_SUB_TYPE_DOMAINS: Final[dict[int, str]] = {
    sub_type_id: domain
    for domain, sub_type_id in SKPORT_DOMAIN_SUB_TYPE_IDS.items()
}


def domain_for_sub_type(sub_type_id: int) -> str:
    try:
        return SKPORT_SUB_TYPE_DOMAINS[sub_type_id]
    except KeyError as error:
        raise ValueError(f"Unsupported SKPort subTypeId: {sub_type_id}") from error


def build_detail_url_for_sub_type(
    base_url: str, sub_type_id: int, game_entry_id: int
) -> str:
    """Build a detail URL while validating its domain and sparse entry ID."""

    domain_for_sub_type(sub_type_id)
    if isinstance(game_entry_id, bool) or game_entry_id < 1:
        raise ValueError(f"gameEntryId must be a positive integer: {game_entry_id}")
    query = urlencode(
        {
            "mainTypeId": SKPORT_DETAIL_MAIN_TYPE_ID,
            "subTypeId": sub_type_id,
            "gameEntryId": game_entry_id,
            "header": 0,
        }
    )
    return f"{base_url.rstrip('/')}/endfield/detail?{query}"


def canonicalize_detail_url(
    source_url: str, sub_type_id: int, game_entry_id: int
) -> str:
    """Rebuild a detail URL after an auto probe discovers the real category."""

    parsed = urlsplit(source_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"SKPort source URL must be absolute: {source_url}")
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return build_detail_url_for_sub_type(base_url, sub_type_id, game_entry_id)


def build_detail_url(base_url: str, domain: str, game_entry_id: int) -> str:
    """Build one SKPort detail URL from its domain and sparse global entry ID."""

    try:
        sub_type_id = SKPORT_DOMAIN_SUB_TYPE_IDS[domain]
    except KeyError as error:
        raise ValueError(f"Unsupported SKPort detail domain: {domain}") from error
    return build_detail_url_for_sub_type(base_url, sub_type_id, game_entry_id)


def _read_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class LocaleSpec:
    id: Locale
    browser_language: str
    site_option_label: str
    html_lang: str


@lru_cache(maxsize=1)
def load_locale_specs() -> dict[Locale, LocaleSpec]:
    payload = json.loads(LOCALES_PATH.read_text(encoding="utf-8"))
    specs = {
        entry["id"]: LocaleSpec(
            id=entry["id"],
            browser_language=entry["browserLanguage"],
            site_option_label=entry["siteOptionLabel"],
            html_lang=entry["htmlLang"],
        )
        for entry in payload["locales"]
    }
    if tuple(specs) != SUPPORTED_LOCALES:
        raise ValueError("config/locales.json must preserve supported locale order")
    return specs


@dataclass(frozen=True, slots=True)
class CrawlerSettings:
    base_url: str
    output_dir: Path
    headless: bool
    page_load_timeout: int
    wait_timeout: int
    missing_entry_timeout: int = 3
    save_html: bool = False

    @classmethod
    def from_env(cls) -> "CrawlerSettings":
        return cls(
            base_url=os.getenv("EPWIKI_CRAWLER_BASE_URL", "https://wiki.skport.com").rstrip("/"),
            output_dir=Path(os.getenv("EPWIKI_CRAWLER_OUTPUT_DIR", "output")),
            headless=_read_bool(os.getenv("EPWIKI_CRAWLER_HEADLESS", "true")),
            page_load_timeout=int(os.getenv("EPWIKI_CRAWLER_PAGE_LOAD_TIMEOUT", "30")),
            wait_timeout=int(os.getenv("EPWIKI_CRAWLER_WAIT_TIMEOUT", "15")),
            missing_entry_timeout=int(
                os.getenv("EPWIKI_CRAWLER_MISSING_ENTRY_TIMEOUT", "3")
            ),
            save_html=_read_bool(os.getenv("EPWIKI_CRAWLER_SAVE_HTML", "false")),
        )
