"""Selectors for rendered SKPort gear detail pages.

Chapter ids after ``entryInfo`` are generated strings, so extraction must use
the chapter order and visible headings instead of persisting those ids.
"""

CHAPTERS = "[data-chapter-index][data-chapter-id]"

# Stable first chapter plus rendered chapter order observed on gear entry 1023.
ENTRY_INFO = '[data-chapter-index="0"][data-chapter-id="entryInfo"]'
BASIC_INFO_CHAPTER_INDEX = 1
FORGING_CHAPTER_INDEX = 2
SET_EFFECT_CHAPTER_INDEX = 3

BASIC_INFO_CHAPTER = '[data-chapter-index="1"]'
FORGING_CHAPTER = '[data-chapter-index="2"]'
SET_EFFECT_CHAPTER = '[data-chapter-index="3"]'

HEADINGS = {
    "basic_info": "장비 정보",
    "forging": "정밀 단조",
    "set_effect": "세트 효과",
}
