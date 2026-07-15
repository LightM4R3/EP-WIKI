from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from epwiki_crawler.operator.rag_builder import build_rag_documents


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ("ko-KR", "en-US", "ja-JP", "zh-TW")


def load_json(relative_path: str) -> dict[str, Any]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class TangtangDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.operator = load_json("data/canonical/operator/tangtang.json")
        cls.localizations = {
            locale: load_json(f"data/localization/operator/tangtang.{locale}.json")
            for locale in LOCALES
        }
        cls.rags = {
            locale: load_json(f"data/rag/operator/tangtang.{locale}.json")
            for locale in LOCALES
        }
        cls.rag = cls.rags["ko-KR"]
        cls.catalogs = {
            name: load_json(f"data/catalog/{name}.json")
            for name in (
                "attributes",
                "classes",
                "elements",
                "weapon-types",
                "skill-types",
                "materials",
            )
        }

    def test_json_schemas_accept_tangtang_artifacts(self) -> None:
        cases = [("operator-canonical.schema.json", self.operator)]
        cases.extend(
            ("operator-localization.schema.json", localization)
            for localization in self.localizations.values()
        )
        cases.extend(
            ("rag-document.schema.json", rag) for rag in self.rags.values()
        )
        for schema_name, instance in cases:
            schema = load_json(f"schemas/{schema_name}")
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
            self.assertEqual([], [error.message for error in errors])

    def test_catalog_ids_and_codes_are_unique(self) -> None:
        for catalog in self.catalogs.values():
            ids = [entry["id"] for entry in catalog["entries"]]
            codes = [entry["code"] for entry in catalog["entries"]]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(len(codes), len(set(codes)))

    def test_taxonomy_and_attribute_refs_resolve(self) -> None:
        refs = (
            ("class", "classes"),
            ("element", "elements"),
            ("weaponType", "weapon-types"),
        )
        for field, catalog_name in refs:
            reference = self.operator["taxonomy"][field]
            matches = [
                entry
                for entry in self.catalogs[catalog_name]["entries"]
                if entry["id"] == reference["id"] and entry["code"] == reference["code"]
            ]
            self.assertEqual(1, len(matches))

        self.assertEqual([0, 1, 2, 3], self.operator["attributes"]["catalogOrder"])
        self.assertEqual(1, self.operator["attributes"]["primaryId"])
        self.assertEqual(0, self.operator["attributes"]["secondaryId"])
        attribute_by_id = {
            entry["id"]: entry["code"] for entry in self.catalogs["attributes"]["entries"]
        }
        self.assertEqual("agility", attribute_by_id[self.operator["attributes"]["primaryId"]])
        self.assertEqual("strength", attribute_by_id[self.operator["attributes"]["secondaryId"]])

    def test_progression_skill_levels_and_material_refs_are_complete(self) -> None:
        material_ids = {entry["id"] for entry in self.catalogs["materials"]["entries"]}
        costs: list[dict[str, int]] = []

        self.assertEqual([1, 20, 40, 60, 80, 90], [row["level"] for row in self.operator["progression"]])
        for row in self.operator["progression"]:
            costs.extend(row["materialCosts"])

        self.assertEqual(4, len(self.operator["combatSkills"]))
        for expected_type_id, skill in enumerate(self.operator["combatSkills"]):
            self.assertEqual(expected_type_id, skill["typeId"])
            self.assertEqual(list(range(1, 13)), [level["level"] for level in skill["levels"]])
            self.assertEqual(["rank"] * 9 + ["mastery"] * 3, [level["phase"] for level in skill["levels"]])
            metric_codes = {metric["code"] for metric in skill["metrics"]}
            for level in skill["levels"]:
                self.assertEqual(metric_codes, set(level["values"]))
                costs.extend(level["materialCosts"])

        for group in self.operator["talents"].values():
            for talent in group:
                for stage in talent["stages"]:
                    costs.extend(stage["materialCosts"])

        self.assertTrue(costs)
        self.assertTrue(all(cost["materialId"] in material_ids for cost in costs))

    def test_talents_potentials_and_rag_chunks_are_partitioned(self) -> None:
        self.assertEqual(3, len(self.operator["talents"]["operator"]))
        self.assertEqual(2, len(self.operator["talents"]["infrastructure"]))
        self.assertTrue(
            all(
                talent["category"] != "infrastructure_skill"
                for talent in self.operator["talents"]["operator"]
            )
        )
        self.assertTrue(
            all(
                talent["category"] == "infrastructure_skill"
                for talent in self.operator["talents"]["infrastructure"]
            )
        )
        self.assertEqual([1, 2, 3, 4, 5], [row["level"] for row in self.operator["potentials"]])

        document_ids = [document["documentId"] for document in self.rag["documents"]]
        self.assertEqual(len(document_ids), len(set(document_ids)))
        self.assertEqual(4, sum(document["section"] == "combat_skill" for document in self.rag["documents"]))
        profile = next(document for document in self.rag["documents"] if document["section"] == "profile")
        self.assertEqual(1, profile["metadata"]["primaryAttributeId"])
        self.assertEqual(0, profile["metadata"]["secondaryAttributeId"])
        self.assertEqual("verified", profile["metadata"]["contentStatus"])

    def test_all_locale_overlays_keep_ids_and_source_text_separate(self) -> None:
        expected_names = {
            "ko-KR": "탕탕",
            "en-US": "Tangtang",
            "ja-JP": "タンタン",
            "zh-TW": "湯湯",
        }
        canonical_metric_codes = [
            [metric["code"] for metric in skill["metrics"]]
            for skill in self.operator["combatSkills"]
        ]
        for locale, localization in self.localizations.items():
            self.assertEqual(expected_names[locale], localization["identity"]["name"])
            self.assertEqual("verified", localization["taxonomy"]["classMappingStatus"])
            self.assertEqual(15, len(localization["materialLabels"]))
            self.assertEqual(4, len(localization["combatSkills"]))
            for index, skill in enumerate(localization["combatSkills"]):
                self.assertEqual(
                    canonical_metric_codes[index],
                    [metric["code"] for metric in skill["metrics"]],
                )
                self.assertEqual(list(range(1, 13)), [level["level"] for level in skill["levels"]])

    def test_locale_source_gaps_are_explicit_and_use_ko_fallback(self) -> None:
        expected_missing = {
            "ko-KR": set(),
            "en-US": {
                ("tangtang.combo_skill", "ultimate_energy_gain"),
                ("tangtang.ultimate", "cooldown"),
            },
            "ja-JP": {
                ("tangtang.battle_skill", "skill_gauge_cost"),
                ("tangtang.ultimate", "cooldown"),
            },
            "zh-TW": {("tangtang.combo_skill", "ultimate_energy_gain")},
        }
        for locale, localization in self.localizations.items():
            missing = {
                (skill["id"], metric["code"])
                for skill in localization["combatSkills"]
                for metric in skill["metrics"]
                if metric["sourceStatus"] == "missing_in_locale_dom"
            }
            self.assertEqual(expected_missing[locale], missing)
            for skill in localization["combatSkills"]:
                for metric in skill["metrics"]:
                    if metric["sourceStatus"] == "missing_in_locale_dom":
                        self.assertEqual("ko-KR", metric["fallbackLocale"])

    def test_present_locale_values_match_canonical_numbers(self) -> None:
        def normalized(value: str) -> str:
            return re.sub(r"[^0-9.%+\-]", "", value)

        for localization in self.localizations.values():
            for skill_index, local_skill in enumerate(localization["combatSkills"]):
                canonical_skill = self.operator["combatSkills"][skill_index]
                present_codes = {
                    metric["code"]
                    for metric in local_skill["metrics"]
                    if metric["sourceStatus"] == "present"
                }
                for level_index, local_level in enumerate(local_skill["levels"]):
                    canonical_values = canonical_skill["levels"][level_index]["values"]
                    self.assertEqual(present_codes, set(local_level["values"]))
                    for code in present_codes:
                        self.assertEqual(
                            normalized(canonical_values[code]),
                            normalized(local_level["values"][code]),
                        )

    def test_rag_artifacts_match_the_reproducible_builder(self) -> None:
        for locale in LOCALES:
            self.assertEqual(
                build_rag_documents(self.operator, self.localizations[locale]),
                self.rags[locale],
            )
            self.assertEqual(9, len(self.rags[locale]["documents"]))
            self.assertEqual(
                4,
                sum(
                    document["section"] == "combat_skill"
                    for document in self.rags[locale]["documents"]
                ),
            )


if __name__ == "__main__":
    unittest.main()
