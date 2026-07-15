"""Stable SKPort weapon selectors discovered from the rendered detail page.

Hashed CSS class names are deliberately excluded. Chapter IDs except
``entryInfo`` are generated values, so the crawler anchors on the stable root,
chapter indexes, and visible section headings.
"""

DETAIL_ROOT = "#ENTRY_DETAIL_VIEW_ID"
ENTRY_INFO_CHAPTER = '[data-chapter-index="0"]'
BASIC_INFO_CHAPTER = '[data-chapter-index="1"]'
UPGRADE_CHAPTER = '[data-chapter-index="2"]'
SKILL_TRAIT_CHAPTER = '[data-chapter-index="3"]'
POTENTIAL_CHAPTER = '[data-chapter-index="4"]'

SECTION_HEADINGS = {
    "entry": "소개",
    "basic": "무기 정보",
    "upgrade": "업그레이드",
    "traits": "스킬 상세 및 기질",
    "potential": "잠재능력",
}
