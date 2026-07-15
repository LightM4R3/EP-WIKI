from __future__ import annotations

import unittest

from epwiki_crawler.core.detail_page import stable_rendered_content_sha256


def _chapters(chapter_id: str, text: str) -> list[dict[str, object]]:
    return [
        {
            "index": 0,
            "sourceChapterId": chapter_id,
            "title": "정보",
            "textSegments": [text],
            "text": text,
            "widgets": [
                {
                    "index": 0,
                    "title": "위젯",
                    "textSegments": ["수치", "10"],
                    "text": "수치\n10",
                }
            ],
        }
    ]


class StableContentHashTests(unittest.TestCase):
    def test_random_source_chapter_id_does_not_change_hash(self) -> None:
        self.assertEqual(
            stable_rendered_content_sha256(_chapters("random-a", "동일한 내용")),
            stable_rendered_content_sha256(_chapters("random-b", "동일한 내용")),
        )

    def test_rendered_text_change_changes_hash(self) -> None:
        self.assertNotEqual(
            stable_rendered_content_sha256(_chapters("same", "이전 내용")),
            stable_rendered_content_sha256(_chapters("same", "변경 내용")),
        )


if __name__ == "__main__":
    unittest.main()
