from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from epwiki_crawler.cli import main
from epwiki_crawler.config import CrawlerSettings, DEFAULT_TARGETS_PATH
from epwiki_crawler.core.contracts import CrawlContext, CrawlTarget, RawRecord
from epwiki_crawler.core.detail_page import EntryNotFoundError
from epwiki_crawler.core.naming import safe_entity_file_stem
from epwiki_crawler.core.rag_pipeline import (
    CategoryMismatchError,
    SourceDataUnavailableError,
    build_auto_rag,
    classify_record,
)
from epwiki_crawler.core.runner import run_crawl
from epwiki_crawler.core.targets import (
    auto_range_targets,
    build_jobs,
    direct_targets,
    load_manifest_targets,
    range_targets,
)


class FakeDriver:
    def __init__(self) -> None:
        self.quit_called = False

    def quit(self) -> None:
        self.quit_called = True


class FakeCrawler:
    def __init__(self, domain: str) -> None:
        self.domain = domain

    def crawl_entry(
        self,
        driver: FakeDriver,
        context: CrawlContext,
        target: CrawlTarget,
    ) -> RawRecord:
        if target.game_entry_id == 26:
            raise EntryNotFoundError("missing test entry")
        if target.game_entry_id == 27:
            raise RuntimeError("missing test entry")
        return RawRecord(
            entity_id=f"{target.domain}_{target.game_entry_id}",
            locale=context.locale,
            source_url=target.source_url,
            payload={
                "domain": target.domain,
                "subTypeId": target.sub_type_id,
                "gameEntryId": target.game_entry_id,
                "observedAt": "2026-07-14T00:00:00+00:00",
                "contentSha256": "a" * 64,
                "chapters": [
                    {
                        "index": 0,
                        "textSegments": ["Test Operator", "Profile"],
                        "widgets": [{}],
                    },
                    {
                        "index": 1,
                        "textSegments": ["Operator Information"],
                        "widgets": [{}],
                    },
                    {
                        "index": 2,
                        "textSegments": ["Upgrade", "LV.1"],
                        "widgets": [{}],
                    },
                    {
                        "index": 3,
                        "textSegments": ["Ability Matrix"],
                        "widgets": [
                            {"textSegments": ["Combat Skill"]},
                            {
                                "textSegments": [
                                    "Operator Talent",
                                    "인프라 스킬",
                                    "Base Skill",
                                ]
                            },
                            {"textSegments": ["Promotion"]},
                        ],
                    },
                    {
                        "index": 4,
                        "textSegments": ["Potential"],
                        "widgets": [{}],
                    },
                ],
            },
        )


class CrawlPipelineTests(unittest.TestCase):
    @staticmethod
    def _section_record(
        domain: str, sub_type_id: int, chapter_count: int
    ) -> RawRecord:
        info_labels = {
            "operator": "Operator Information",
            "weapon": "Weapon Information",
            "gear": "Gear Information",
        }
        return RawRecord(
            entity_id=f"{domain}_100",
            locale="ko-KR",
            source_url="https://wiki.skport.com/example",
            payload={
                "domain": domain,
                "subTypeId": sub_type_id,
                "gameEntryId": 100,
                "observedAt": "2026-07-14T00:00:00+00:00",
                "contentSha256": "b" * 64,
                "chapters": [
                    {
                        "index": index,
                        "textSegments": [
                            info_labels[domain] if index == 1 else f"chapter {index}"
                        ],
                        "widgets": [],
                    }
                    for index in range(chapter_count)
                ],
            },
        )

    def test_manifest_maps_sub_types_to_domains_and_urls(self) -> None:
        targets = load_manifest_targets(
            DEFAULT_TARGETS_PATH, "https://wiki.skport.com"
        )
        self.assertEqual(
            [
                ("operator", 1, 25),
                ("weapon", 2, 732),
                ("gear", 4, 1023),
            ],
            [
                (target.domain, target.sub_type_id, target.game_entry_id)
                for target in targets
            ],
        )
        self.assertTrue(all("mainTypeId=1" in target.source_url for target in targets))

    def test_direct_ids_only_need_one_domain_and_entry_values(self) -> None:
        targets = direct_targets(
            "https://wiki.skport.com", "weapon", [732, 733, 732]
        )
        self.assertEqual([732, 733], [target.game_entry_id for target in targets])
        self.assertTrue(all(target.sub_type_id == 2 for target in targets))

    def test_range_targets_are_inclusive_and_derive_the_domain(self) -> None:
        targets = range_targets("https://wiki.skport.com", 4, 1021, 1023)
        self.assertEqual([1021, 1022, 1023], [
            target.game_entry_id for target in targets
        ])
        self.assertTrue(all(target.domain == "gear" for target in targets))
        self.assertTrue(all(target.sub_type_id == 4 for target in targets))

    def test_auto_range_probes_each_global_id_only_once(self) -> None:
        targets = auto_range_targets("https://wiki.skport.com", 24, 26)
        self.assertEqual([24, 25, 26], [target.game_entry_id for target in targets])
        self.assertTrue(all(target.domain == "auto" for target in targets))
        self.assertTrue(all(target.sub_type_id == 1 for target in targets))

    def test_auto_record_is_reclassified_from_rendered_content(self) -> None:
        record = self._section_record("weapon", 2, 5)
        record.payload["domain"] = "auto"
        record.payload["subTypeId"] = 1
        classified = classify_record(record, "auto")
        self.assertEqual("weapon", classified.payload["domain"])
        self.assertEqual(2, classified.payload["subTypeId"])
        self.assertEqual(1, classified.payload["requestedSubTypeId"])
        self.assertEqual("weapon_100", classified.entity_id)
        self.assertEqual(
            "https://wiki.skport.com/endfield/detail?mainTypeId=1&subTypeId=2&gameEntryId=100&header=0",
            classified.source_url,
        )

    def test_entity_file_stem_keeps_id_and_readable_localized_name(self) -> None:
        self.assertEqual(
            "25_탕탕_대당가",
            safe_entity_file_stem(25, " 탕탕 / 대당가:*? "),
        )

    def test_duplicate_manifest_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "1.0.0",
                        "targets": [
                            {"subTypeId": 1, "gameEntryIds": [25, 25]}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Duplicate target"):
                load_manifest_targets(path, "https://wiki.skport.com")

    def test_cli_plan_supports_direct_sparse_ids(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "plan",
                    "--domain",
                    "weapon",
                    "--locale",
                    "ko-KR",
                    "--entry-id",
                    "732",
                    "--entry-id",
                    "900",
                ]
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual([732, 900], [job["gameEntryId"] for job in payload["jobs"]])
        self.assertTrue(all(job["subTypeId"] == 2 for job in payload["jobs"]))

    def test_cli_plan_supports_an_inclusive_sub_type_range(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "plan",
                    "--sub-type-id",
                    "1",
                    "--start",
                    "24",
                    "--end",
                    "25",
                    "--locale",
                    "ko-KR",
                ]
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual([24, 25], [job["gameEntryId"] for job in payload["jobs"]])
        self.assertTrue(all(job["domain"] == "operator" for job in payload["jobs"]))

    def test_cli_plan_auto_classifies_a_range_without_sub_type(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "plan",
                    "--start",
                    "24",
                    "--end",
                    "26",
                    "--locale",
                    "ko-KR",
                ]
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual([24, 25, 26], [job["gameEntryId"] for job in payload["jobs"]])
        self.assertTrue(all(job["domain"] == "auto" for job in payload["jobs"]))
        self.assertTrue(all(job["subTypeId"] == "auto" for job in payload["jobs"]))
        self.assertTrue(all(job["probeSubTypeId"] == 1 for job in payload["jobs"]))

    def test_weapon_and_gear_use_category_specific_rag_sections(self) -> None:
        weapon = build_auto_rag(
            self._section_record("weapon", 2, 5), "raw/weapon/100.json"
        )
        gear = build_auto_rag(
            self._section_record("gear", 4, 4), "raw/gear/100.json"
        )
        gear_without_forging = build_auto_rag(
            self._section_record("gear", 4, 3), "raw/gear/101.json"
        )
        self.assertEqual(
            ["profile", "profile", "progression", "weapon_option", "potential"],
            [document["section"] for document in weapon["documents"]],
        )
        self.assertEqual(
            ["profile", "profile", "gear_option", "gear_set_effect"],
            [document["section"] for document in gear["documents"]],
        )
        self.assertEqual(
            ["profile", "profile", "gear_set_effect"],
            [document["section"] for document in gear_without_forging["documents"]],
        )

    def test_unreleased_operator_without_game_data_is_not_indexed(self) -> None:
        with self.assertRaisesRegex(
            SourceDataUnavailableError, "In-game data is not published"
        ):
            build_auto_rag(
                self._section_record("operator", 1, 2),
                "raw/operator/1040.json",
            )

    def test_page_from_another_global_category_is_skipped_before_storage(self) -> None:
        wrong_category = self._section_record("operator", 1, 5)
        wrong_category.payload["chapters"][1]["textSegments"] = [
            "Weapon Information"
        ]
        with self.assertRaisesRegex(CategoryMismatchError, "belongs to weapon"):
            build_auto_rag(wrong_category, "raw/operator/100.json")

    def test_runner_builds_rag_skips_missing_ids_and_continues_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = CrawlerSettings(
                base_url="https://wiki.skport.com",
                output_dir=Path(directory),
                headless=True,
                page_load_timeout=30,
                wait_timeout=15,
            )
            targets = direct_targets(
                settings.base_url, "operator", [25, 26, 27]
            )
            jobs = build_jobs(targets, ["ko-KR"])
            driver = FakeDriver()
            summary = run_crawl(
                jobs,
                settings,
                run_id="test-run",
                driver_factory=lambda _settings, _locale: driver,
                crawler_factory=FakeCrawler,
            )

            self.assertEqual((3, 1, 1, 1), (
                summary["total"],
                summary["succeeded"],
                summary["skipped"],
                summary["failed"],
            ))
            self.assertTrue(driver.quit_called)
            raw_root = (
                Path(directory) / "test-run" / "raw" / "ko-KR" / "operator"
            )
            rag_root = (
                Path(directory) / "test-run" / "rag" / "ko-KR" / "operator"
            )
            error_root = (
                Path(directory) / "test-run" / "errors" / "ko-KR" / "operator"
            )
            self.assertTrue((raw_root / "25_Test_Operator.json").exists())
            self.assertTrue((rag_root / "25_Test_Operator.json").exists())
            self.assertFalse((error_root / "26.json").exists())
            self.assertTrue((error_root / "27.json").exists())
            self.assertTrue((Path(directory) / "test-run" / "summary.json").exists())
            progress = json.loads(
                (Path(directory) / "test-run" / "progress.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("completed", progress["status"])
            self.assertEqual((3, 0), (progress["processed"], progress["remaining"]))

            rag = json.loads(
                (rag_root / "25_Test_Operator.json").read_text(encoding="utf-8")
            )
            schema = json.loads(
                (Path(__file__).resolve().parents[1] / "schemas" / "rag-document.schema.json")
                .read_text(encoding="utf-8")
            )
            errors = list(
                Draft202012Validator(
                    schema, format_checker=FormatChecker()
                ).iter_errors(rag)
            )
            self.assertEqual([], [error.message for error in errors])
            self.assertEqual(
                {
                    "profile",
                    "progression",
                    "combat_skill",
                    "operator_talent",
                    "infrastructure_talent",
                    "potential",
                },
                {document["section"] for document in rag["documents"]},
            )


if __name__ == "__main__":
    unittest.main()
