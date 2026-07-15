from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from epwiki_crawler.publisher import publish_runs


def _quality(_run_dir: Path) -> dict[str, object]:
    return {
        "verdict": "raw_rendered_rag_only",
        "checks": {
            "structural": {"passed": True},
            "normalization": {
                "passed": False,
                "entityMetadataGaps": [
                    {"entityId": "weapon_1001", "missing": ["weaponTypeId"]}
                ],
                "detailMetadataGaps": [
                    {
                        "documentId": "auto.weapon_1001.profile.ko-kr",
                        "missing": ["optionId"],
                    }
                ],
            },
            "hashing": {"allUseStableRenderedHash": True},
        },
    }


class PublisherTests(unittest.TestCase):
    def test_publish_builds_an_inspectable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "output" / "test-run"
            rag_dir = run_dir / "rag" / "ko-KR" / "weapon"
            rag_dir.mkdir(parents=True)
            summary = {
                "runId": "test-run",
                "total": 1,
                "succeeded": 1,
                "skipped": 0,
                "failed": 0,
                "results": [
                    {
                        "status": "succeeded",
                        "domain": "weapon",
                        "gameEntryId": 1001,
                        "locale": "ko-KR",
                        "entityName": "적영",
                    }
                ],
            }
            rag = {
                "schemaVersion": "1.0.0",
                "entityId": "weapon_1001",
                "locale": "ko-KR",
                "documents": [
                    {
                        "documentId": "auto.weapon_1001.profile.ko-kr",
                        "section": "profile",
                        "content": "entity: 적영\ncategory: weapon",
                        "metadata": {
                            "entityType": "weapon",
                            "entityId": "weapon_1001",
                            "sourceUrl": "https://wiki.skport.com/example",
                            "rawRef": "output/test-run/raw/ko-KR/weapon/1001.json",
                            "contentStatus": "raw_rendered",
                            "subTypeId": 2,
                            "gameEntryId": 1001,
                            "contentHashAlgorithm": "rendered_chapters_v1",
                            "contentSha256": "a" * 64,
                        },
                    }
                ],
            }
            (run_dir / "summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            (rag_dir / "1001_적영.json").write_text(
                json.dumps(rag, ensure_ascii=False), encoding="utf-8"
            )

            manifest = publish_runs(
                [run_dir],
                publish_root=root / "published",
                locales=["ko-KR"],
                merge_existing=False,
                quality_validator=_quality,
            )

            snapshot = json.loads(
                (root / "published" / "latest.ko-KR.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("incomplete", snapshot["publicationStatus"])
            expected_source_url = (
                "https://wiki.skport.com/endfield/detail?mainTypeId=1"
                "&subTypeId=2&gameEntryId=1001&header=0"
            )
            self.assertEqual(
                expected_source_url,
                snapshot["entities"][0]["sourceUrl"],
            )
            self.assertEqual(
                expected_source_url,
                snapshot["entities"][0]["documents"][0]["metadata"]["sourceUrl"],
            )
            self.assertEqual((1, 2), (snapshot["stats"]["entities"], snapshot["stats"]["documents"]))
            self.assertEqual(1, snapshot["stats"]["sourceDocuments"])
            self.assertEqual("적영", snapshot["entities"][0]["name"])
            self.assertIn(
                "taxonomy.weaponType",
                snapshot["entities"][0]["normalization"]["missingEntityMetadata"],
            )
            self.assertEqual(0, snapshot["entities"][0]["normalization"]["detailDocumentsWithGaps"])
            self.assertEqual(1, manifest["snapshots"][0]["entities"])
            self.assertTrue((root / "published" / "query-index.ko-KR.json").exists())


if __name__ == "__main__":
    unittest.main()
