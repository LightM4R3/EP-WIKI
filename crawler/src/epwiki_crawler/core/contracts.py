from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from selenium.webdriver.remote.webdriver import WebDriver

from epwiki_crawler.config import Locale


@dataclass(frozen=True, slots=True)
class CrawlContext:
    locale: Locale
    run_id: str
    output_dir: Path
    wait_timeout: int
    missing_entry_timeout: int
    save_html: bool


@dataclass(frozen=True, slots=True)
class CrawlTarget:
    domain: str
    sub_type_id: int
    game_entry_id: int
    source_url: str


@dataclass(frozen=True, slots=True)
class CrawlJob:
    target: CrawlTarget
    locale: Locale


@dataclass(frozen=True, slots=True)
class RawRecord:
    entity_id: str
    locale: Locale
    source_url: str
    payload: dict[str, Any]


class DomainCrawler(Protocol):
    domain: str

    def crawl_entry(
        self,
        driver: WebDriver,
        context: CrawlContext,
        target: CrawlTarget,
    ) -> RawRecord: ...
