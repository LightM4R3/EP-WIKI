from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from epwiki_crawler.config import CrawlerSettings, Locale, load_locale_specs


def create_chrome_driver(settings: CrawlerSettings, locale: Locale) -> webdriver.Chrome:
    """Create an isolated Chrome session for one locale.

    Site-specific locale switching and authentication will be added after the
    rendered SKPort page and network behavior have been inspected.
    """

    locale_spec = load_locale_specs()[locale]
    options = Options()
    options.add_argument(f"--lang={locale_spec.html_lang}")
    options.add_experimental_option(
        "prefs", {"intl.accept_languages": locale_spec.browser_language}
    )
    if settings.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1200")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(settings.page_load_timeout)
    return driver
