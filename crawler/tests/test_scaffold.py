from __future__ import annotations

import unittest

from epwiki_crawler.config import CrawlerSettings, SUPPORTED_LOCALES
from epwiki_crawler.registry import DOMAIN_NAMES, create_crawler


class ScaffoldTests(unittest.TestCase):
    def test_supported_locales_are_stable(self) -> None:
        self.assertEqual(SUPPORTED_LOCALES, ("ko-KR", "en-US", "ja-JP", "zh-TW"))

    def test_each_domain_is_registered(self) -> None:
        self.assertEqual(DOMAIN_NAMES, ("operator", "weapon", "gear"))
        self.assertEqual(
            tuple(create_crawler(domain).domain for domain in DOMAIN_NAMES),
            DOMAIN_NAMES,
        )
        self.assertTrue(all(
            callable(create_crawler(domain).crawl_entry) for domain in DOMAIN_NAMES
        ))

    def test_default_settings_do_not_target_frontend_data(self) -> None:
        settings = CrawlerSettings.from_env()
        self.assertEqual(settings.output_dir.as_posix(), "output")


if __name__ == "__main__":
    unittest.main()
