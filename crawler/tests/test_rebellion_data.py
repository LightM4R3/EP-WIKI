from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from epwiki_crawler.config import build_detail_url
from epwiki_crawler.weapon.rag_builder import build_rag_documents


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict[str, Any]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class RebellionDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.weapon = load_json("data/canonical/weapon/rebellion.json")
        cls.localization = load_json(
            "data/localization/weapon/rebellion.ko-KR.json"
        )
        cls.rag = load_json("data/rag/weapon/rebellion.ko-KR.json")
        cls.materials = load_json("data/catalog/materials.json")
        cls.weapon_types = load_json("data/catalog/weapon-types.json")
        cls.option_categories = load_json(
            "data/catalog/weapon-option-categories.json"
        )
        cls.option_catalog = load_json("data/catalog/weapon-options.json")

    def test_schemas_accept_weapon_artifacts(self) -> None:
        cases = (
            ("weapon-canonical.schema.json", self.weapon),
            ("weapon-localization.schema.json", self.localization),
            ("rag-document.schema.json", self.rag),
        )
        for schema_name, instance in cases:
            schema = load_json(f"schemas/{schema_name}")
            validator = Draft202012Validator(
                schema, format_checker=FormatChecker()
            )
            errors = sorted(
                validator.iter_errors(instance), key=lambda error: list(error.path)
            )
            self.assertEqual([], [error.message for error in errors])

    def test_detail_url_uses_sub_type_for_domain_routing(self) -> None:
        base_url = "https://wiki.skport.com"
        self.assertIn(
            "mainTypeId=1&subTypeId=1&gameEntryId=22",
            build_detail_url(base_url, "operator", 22),
        )
        self.assertEqual(
            (
                "https://wiki.skport.com/endfield/detail?mainTypeId=1&subTypeId=2"
                "&gameEntryId=732&header=0"
            ),
            build_detail_url(base_url, "weapon", 732),
        )
        self.assertIn(
            "mainTypeId=1&subTypeId=4",
            build_detail_url(base_url, "gear", 1),
        )

    def test_weapon_identity_and_type_are_verified(self) -> None:
        source = self.weapon["source"]
        self.assertEqual((1, 2, 732), (
            source["mainTypeId"], source["subTypeId"], source["gameEntryId"]
        ))
        self.assertEqual("반항", self.localization["identity"]["name"])
        self.assertEqual(6, self.weapon["identity"]["rarity"])
        weapon_type = self.weapon["taxonomy"]["weaponType"]
        catalog_match = [
            entry
            for entry in self.weapon_types["entries"]
            if entry["id"] == weapon_type["id"]
            and entry["code"] == weapon_type["code"]
        ]
        self.assertEqual(1, len(catalog_match))
        self.assertEqual("handcannon", weapon_type["code"])

    def test_base_attack_progression_and_material_refs(self) -> None:
        self.assertEqual(
            [1, 20, 40, 60, 80, 90],
            [row["level"] for row in self.weapon["progression"]],
        )
        self.assertEqual(
            [51, 148, 250, 352, 454, 505],
            [row["baseAttack"] for row in self.weapon["progression"]],
        )
        material_ids = {entry["id"] for entry in self.materials["entries"]}
        used_ids = {
            cost["materialId"]
            for row in self.weapon["progression"]
            for cost in row["materialCosts"]
        }
        self.assertTrue(used_ids <= material_ids)
        self.assertTrue(used_ids <= {int(key) for key in self.localization["materialLabels"]})

    def test_options_are_global_catalog_refs_with_independent_ranks(self) -> None:
        catalog_by_id = {
            entry["id"]: entry for entry in self.option_catalog["entries"]
        }
        category_by_id = {
            entry["id"]: entry for entry in self.option_categories["entries"]
        }
        self.assertEqual([1, 2, 3], [option["slot"] for option in self.weapon["options"]])
        self.assertEqual(
            [
                "agility_increase_large",
                "attack_increase_large",
                "release_conquest_grudge",
            ],
            [option["optionCode"] for option in self.weapon["options"]],
        )
        for option in self.weapon["options"]:
            catalog = catalog_by_id[option["optionId"]]
            category = category_by_id[option["categoryId"]]
            self.assertEqual(catalog["code"], option["optionCode"])
            self.assertEqual(category["code"], option["categoryCode"])
            self.assertEqual(list(range(1, 10)), [row["level"] for row in option["levels"]])
            metric_codes = {metric["code"] for metric in catalog["metrics"]}
            for row in option["levels"]:
                self.assertEqual(metric_codes, set(row["values"]))

        self.assertNotIn("optionLevel", self.weapon["progression"][0])
        self.assertNotEqual(
            len(self.weapon["progression"]), len(self.weapon["options"][0]["levels"])
        )

    def test_rank_values_match_rendered_source(self) -> None:
        agility, attack, release = self.weapon["options"]
        self.assertEqual(
            [20, 36, 52, 68, 84, 100, 116, 132, 156],
            [row["values"]["agility_flat"] for row in agility["levels"]],
        )
        self.assertEqual(
            [5.0, 9.0, 13.0, 17.0, 21.0, 25.0, 29.0, 33.0, 39.0],
            [row["values"]["attack_percent"] for row in attack["levels"]],
        )
        self.assertEqual(
            [16.0, 19.2, 22.4, 25.6, 28.8, 32.0, 35.2, 38.4, 44.8],
            [row["values"]["cryo_damage_percent"] for row in release["levels"]],
        )
        self.assertEqual(
            [20.0, 24.0, 28.0, 32.0, 36.0, 40.0, 44.0, 48.0, 56.0],
            [
                row["values"]["cryo_damage_on_chill_percent"]
                for row in release["levels"]
            ],
        )
        self.assertEqual(
            [6.0, 7.2, 8.4, 9.6, 10.8, 12.0, 13.2, 14.4, 16.8],
            [
                row["values"]["arts_damage_taken_on_susceptibility_percent"]
                for row in release["levels"]
            ],
        )
        self.assertEqual(
            [20, 20],
            [rule["durationSeconds"] for rule in release["effectRules"] if "durationSeconds" in rule],
        )
        self.assertEqual("independent_non_stacking", release["stackingRule"])

    def test_localization_templates_only_reference_known_metrics(self) -> None:
        catalog_by_id = {
            entry["id"]: entry for entry in self.option_catalog["entries"]
        }
        for option in self.localization["options"]:
            metric_codes = {
                metric["code"] for metric in catalog_by_id[option["optionId"]]["metrics"]
            }
            template_codes = set(re.findall(r"\{([a-z0-9_]+)\}", option["descriptionTemplate"]))
            self.assertEqual(metric_codes, set(option["metricLabels"]))
            self.assertEqual(metric_codes, template_codes)

    def test_rag_is_reproducible_and_partitioned_by_option(self) -> None:
        self.assertEqual(
            build_rag_documents(self.weapon, self.localization, self.option_catalog),
            self.rag,
        )
        self.assertEqual(5, len(self.rag["documents"]))
        option_documents = [
            document
            for document in self.rag["documents"]
            if document["section"] == "weapon_option"
        ]
        self.assertEqual(3, len(option_documents))
        self.assertEqual(
            {0, 1, 2},
            {document["metadata"]["optionId"] for document in option_documents},
        )
        self.assertTrue(
            all(document["metadata"]["optionLevelCount"] == 9 for document in option_documents)
        )


if __name__ == "__main__":
    unittest.main()
