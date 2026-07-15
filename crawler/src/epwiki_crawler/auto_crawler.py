from __future__ import annotations

from selenium.webdriver.remote.webdriver import WebDriver

from epwiki_crawler.core.contracts import CrawlContext, CrawlTarget, RawRecord
from epwiki_crawler.core.detail_page import capture_detail_page


class AutoCrawler:
    """Probe one global gameEntryId and defer category selection to page content."""

    domain = "auto"

    def crawl_entry(
        self,
        driver: WebDriver,
        context: CrawlContext,
        target: CrawlTarget,
    ) -> RawRecord:
        if target.domain != self.domain:
            raise ValueError(f"AutoCrawler cannot crawl domain: {target.domain}")
        return capture_detail_page(driver, context, target)
