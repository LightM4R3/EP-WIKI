from __future__ import annotations

from typing import Final

from epwiki_crawler.auto_crawler import AutoCrawler
from epwiki_crawler.config import SKPORT_DOMAIN_SUB_TYPE_IDS
from epwiki_crawler.core.contracts import DomainCrawler
from epwiki_crawler.gear import GearCrawler
from epwiki_crawler.operator import OperatorCrawler
from epwiki_crawler.weapon import WeaponCrawler

DOMAIN_NAMES: Final[tuple[str, ...]] = tuple(SKPORT_DOMAIN_SUB_TYPE_IDS)


def create_crawler(domain: str) -> DomainCrawler:
    crawlers: dict[
        str, type[AutoCrawler | OperatorCrawler | WeaponCrawler | GearCrawler]
    ] = {
        "auto": AutoCrawler,
        "operator": OperatorCrawler,
        "weapon": WeaponCrawler,
        "gear": GearCrawler,
    }
    try:
        crawler_type = crawlers[domain]
    except KeyError as error:
        raise ValueError(f"Unsupported crawler domain: {domain}") from error
    return crawler_type()
