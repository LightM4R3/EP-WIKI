from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from epwiki_crawler.config import SKPORT_DETAIL_MAIN_TYPE_ID, load_locale_specs
from epwiki_crawler.core.contracts import CrawlContext, CrawlTarget, RawRecord


CHAPTER_SELECTOR = "[data-chapter-index][data-chapter-id]"
ENTRY_INFO_SELECTOR = '[data-chapter-index="0"][data-chapter-id="entryInfo"]'
WIDGET_SELECTOR = '[class*="EndfieldChapterGroup__WidgetWrapper"]'
CONTENT_HASH_ALGORITHM = "rendered_chapters_v1"


class EntryNotFoundError(RuntimeError):
    """Raised when a sparse gameEntryId has no detail content for the subType."""


def _document_languages(driver: WebDriver) -> tuple[str, str]:
    html = driver.find_element(By.TAG_NAME, "html")
    return html.get_attribute("lang") or "", html.get_attribute("xml:lang") or ""


def _matches_locale(driver: WebDriver, expected_html_lang: str) -> bool:
    html_lang, xml_lang = _document_languages(driver)
    return html_lang == expected_html_lang and xml_lang == expected_html_lang


def _visible_option(driver: WebDriver, label: str) -> WebElement | bool:
    candidates = driver.find_elements(
        By.XPATH, f"//*[normalize-space(text())={_xpath_literal(label)}]"
    )
    return next((element for element in candidates if element.is_displayed()), False)


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"


def ensure_site_locale(
    driver: WebDriver, context: CrawlContext, wait: WebDriverWait
) -> None:
    spec = load_locale_specs()[context.locale]
    if _matches_locale(driver, spec.html_lang):
        return

    language_menu = wait.until(EC.element_to_be_clickable((By.ID, "lang")))
    driver.execute_script("arguments[0].click()", language_menu)
    option = wait.until(lambda current: _visible_option(current, spec.site_option_label))
    driver.execute_script("arguments[0].click()", option)
    wait.until(lambda current: _matches_locale(current, spec.html_lang))


def _text_segments(driver: WebDriver, element: WebElement) -> list[str]:
    return driver.execute_script(
        """
        const walker = document.createTreeWalker(
          arguments[0], NodeFilter.SHOW_TEXT
        );
        const segments = [];
        let node;
        while ((node = walker.nextNode())) {
          const value = node.nodeValue.replace(/\\s+/g, ' ').trim();
          if (value) segments.push(value);
        }
        return segments;
        """,
        element,
    )


def _widget_payload(
    driver: WebDriver, element: WebElement, index: int, save_html: bool
) -> dict[str, Any]:
    segments = _text_segments(driver, element)
    titles = element.find_elements(By.CSS_SELECTOR, "header .title")
    payload: dict[str, Any] = {
        "index": index,
        "title": (titles[0].get_attribute("textContent") or "").strip()
        if titles
        else "",
        "textSegments": segments,
        "text": "\n".join(segments),
    }
    if save_html:
        payload["renderedHtml"] = element.get_attribute("outerHTML")
    return payload


def _chapter_payload(
    driver: WebDriver, element: WebElement, save_html: bool
) -> dict[str, Any]:
    segments = _text_segments(driver, element)
    titles = element.find_elements(By.CSS_SELECTOR, "header .title")
    widgets = [
        _widget_payload(driver, widget, index, save_html)
        for index, widget in enumerate(
            element.find_elements(By.CSS_SELECTOR, WIDGET_SELECTOR)
        )
    ]
    payload: dict[str, Any] = {
        "index": int(element.get_attribute("data-chapter-index")),
        "sourceChapterId": element.get_attribute("data-chapter-id"),
        "title": (titles[0].get_attribute("textContent") or "").strip()
        if titles
        else "",
        "textSegments": segments,
        "text": "\n".join(segments),
        "widgets": widgets,
    }
    if save_html:
        payload["renderedHtml"] = element.get_attribute("outerHTML")
    return payload


def stable_rendered_content_sha256(chapters: list[dict[str, Any]]) -> str:
    """Hash stable rendered text while excluding SKPort's random chapter IDs."""

    normalized = [
        {
            "index": chapter["index"],
            "title": chapter["title"],
            "textSegments": chapter["textSegments"],
            "widgets": [
                {
                    "index": widget["index"],
                    "title": widget["title"],
                    "textSegments": widget["textSegments"],
                }
                for widget in chapter["widgets"]
            ],
        }
        for chapter in chapters
    ]
    serialized = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def capture_detail_page(
    driver: WebDriver, context: CrawlContext, target: CrawlTarget
) -> RawRecord:
    """Navigate to one sparse entry ID and preserve its rendered source."""

    driver.get(target.source_url)
    wait = WebDriverWait(driver, context.wait_timeout)
    wait.until(
        lambda current: current.execute_script("return document.readyState")
        == "complete"
    )
    try:
        WebDriverWait(driver, context.missing_entry_timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ENTRY_INFO_SELECTOR))
        )
    except TimeoutException as error:
        raise EntryNotFoundError(
            f"No {target.domain} entry for gameEntryId={target.game_entry_id}"
        ) from error
    ensure_site_locale(driver, context, wait)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ENTRY_INFO_SELECTOR)))
    chapter_elements = wait.until(
        lambda current: current.find_elements(By.CSS_SELECTOR, CHAPTER_SELECTOR)
        or False
    )

    page_source = driver.page_source
    html_lang, xml_lang = _document_languages(driver)
    chapters = sorted(
        (
            _chapter_payload(driver, element, context.save_html)
            for element in chapter_elements
        ),
        key=lambda chapter: chapter["index"],
    )
    observed_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "provider": "wiki.skport.com",
        "domain": target.domain,
        "mainTypeId": SKPORT_DETAIL_MAIN_TYPE_ID,
        "subTypeId": target.sub_type_id,
        "gameEntryId": target.game_entry_id,
        "requestedLocale": context.locale,
        "htmlLang": html_lang,
        "xmlLang": xml_lang,
        "localeVerified": _matches_locale(
            driver, load_locale_specs()[context.locale].html_lang
        ),
        "observedAt": observed_at,
        "resolvedUrl": driver.current_url,
        "pageTitle": driver.title,
        "contentHashAlgorithm": CONTENT_HASH_ALGORITHM,
        "contentSha256": stable_rendered_content_sha256(chapters),
        "chapters": chapters,
    }
    if context.save_html:
        payload["pageSource"] = page_source
    return RawRecord(
        entity_id=f"{target.domain}_{target.game_entry_id}",
        locale=context.locale,
        source_url=target.source_url,
        payload=payload,
    )
