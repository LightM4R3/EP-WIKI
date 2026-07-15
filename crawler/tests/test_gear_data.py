from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from epwiki_crawler.config import build_detail_url
from epwiki_crawler.gear.rag_builder import (
    build_gear_rag_documents,
    build_set_rag_documents,
    validate_gear_option_rules,
)
from epwiki_crawler.gear.selectors import (
    BASIC_INFO_CHAPTER_INDEX,
    FORGING_CHAPTER_INDEX,
    HEADINGS,
    SET_EFFECT_CHAPTER_INDEX,
)


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict[str, Any]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class GearDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entity_id = "echo_of_ancient_sword_metal_gloves_i"
        cls.set_entity_id = "echo_of_ancient_sword"
        cls.gear = load_json(f"data/canonical/gear/{cls.entity_id}.json")
        cls.localization = load_json(
            f"data/localization/gear/{cls.entity_id}.ko-KR.json"
        )
        cls.gear_set = load_json(
            f"data/canonical/gear-set/{cls.set_entity_id}.json"
        )
        cls.set_localization = load_json(
            f"data/localization/gear-set/{cls.set_entity_id}.ko-KR.json"
        )
        cls.gear_rag = load_json(
            f"data/rag/gear/{cls.entity_id}.ko-KR.json"
        )
        cls.set_rag = load_json(
            f"data/rag/gear-set/{cls.set_entity_id}.ko-KR.json"
        )
        cls.gear_types = load_json("data/catalog/gear-types.json")
        cls.gear_qualities = load_json("data/catalog/gear-qualities.json")
        cls.gear_sets = load_json("data/catalog/gear-sets.json")
        cls.gear_options = load_json("data/catalog/gear-options.json")
        cls.slot_rules = load_json("data/catalog/gear-option-slot-rules.json")
        cls.materials = load_json("data/catalog/materials.json")

    def test_schemas_accept_gear_and_set_artifacts(self) -> None:
        cases = (
            ("gear-canonical.schema.json", self.gear),
            ("gear-localization.schema.json", self.localization),
            ("gear-set-canonical.schema.json", self.gear_set),
            ("gear-set-localization.schema.json", self.set_localization),
            ("rag-document.schema.json", self.gear_rag),
            ("rag-document.schema.json", self.set_rag),
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

    def test_route_and_rendered_chapter_map(self) -> None:
        self.assertEqual(
            (
                "https://wiki.skport.com/endfield/detail?mainTypeId=1&subTypeId=4"
                "&gameEntryId=1023&header=0"
            ),
            build_detail_url("https://wiki.skport.com", "gear", 1023),
        )
        self.assertEqual((1, 2, 3), (
            BASIC_INFO_CHAPTER_INDEX,
            FORGING_CHAPTER_INDEX,
            SET_EFFECT_CHAPTER_INDEX,
        ))
        self.assertEqual(
            {"basic_info": "장비 정보", "forging": "정밀 단조", "set_effect": "세트 효과"},
            HEADINGS,
        )

    def test_identity_taxonomy_level_and_defense(self) -> None:
        source = self.gear["source"]
        self.assertEqual((1, 4, 1023), (
            source["mainTypeId"], source["subTypeId"], source["gameEntryId"]
        ))
        self.assertEqual(
            "고검의 잔향 금속 장갑 · I", self.localization["identity"]["name"]
        )
        self.assertEqual(70, self.gear["level"])
        self.assertEqual(42, self.gear["baseStats"]["defense"])

        catalogs = {
            "gearType": self.gear_types,
            "quality": self.gear_qualities,
            "set": self.gear_sets,
        }
        for field, catalog in catalogs.items():
            reference = self.gear["taxonomy"][field]
            self.assertTrue(any(
                entry["id"] == reference["id"]
                and entry["code"] == reference["code"]
                for entry in catalog["entries"]
            ))

    def test_crafting_materials_use_catalog_ids(self) -> None:
        costs = self.gear["identity"]["acquisition"]["craftingCosts"]
        self.assertEqual(
            [(21, 25000), (22, 50)],
            [(cost["materialId"], cost["quantity"]) for cost in costs],
        )
        material_ids = {entry["id"] for entry in self.materials["entries"]}
        self.assertTrue({cost["materialId"] for cost in costs} <= material_ids)
        self.assertTrue(
            {cost["materialId"] for cost in costs}
            <= {int(key) for key in self.localization["materialLabels"]}
        )

    def test_forging_is_an_independent_yellow_quality_axis(self) -> None:
        forging = self.gear["forging"]
        eligibility = forging["eligibility"]
        self.assertTrue(forging["supported"])
        self.assertEqual("yellow_quality_only", eligibility["ruleCode"])
        self.assertEqual("user_confirmed", eligibility["verificationStatus"])
        self.assertEqual(
            self.gear["taxonomy"]["quality"]["id"], eligibility["qualityId"]
        )
        self.assertEqual(
            [0, 1, 2, 3], [stage["forgeLevel"] for stage in forging["stages"]]
        )
        self.assertEqual(
            [0, 6, 12, 20],
            [stage["cumulativeStageRequirement"] for stage in forging["stages"]],
        )
        quality = next(
            entry
            for entry in self.gear_qualities["entries"]
            if entry["id"] == eligibility["qualityId"]
        )
        self.assertEqual(
            {
                "supported": True,
                "minLevel": 0,
                "maxLevel": 3,
                "eligibilityStatus": "user_confirmed",
            },
            quality["forging"],
        )

    def test_option_values_and_catalog_refs(self) -> None:
        expected = {
            "agility_flat": [65, 71, 78, 84],
            "strength_flat": [43, 47, 51, 55],
            "originium_arts_intensity_flat": [34, 37, 41, 44],
        }
        catalog_by_id = {
            entry["id"]: entry for entry in self.gear_options["entries"]
        }
        for option in self.gear["options"]:
            catalog = catalog_by_id[option["optionId"]]
            self.assertEqual(catalog["code"], option["optionCode"])
            self.assertEqual([0, 1, 2, 3], [
                level["forgeLevel"] for level in option["levels"]
            ])
            self.assertEqual(
                expected[option["optionCode"]],
                [
                    level["values"][option["optionCode"]]
                    for level in option["levels"]
                ],
            )
            self.assertEqual(
                {metric["code"] for metric in catalog["metrics"]},
                set(option["levels"][0]["values"]),
            )
        self.assertNotIn("level", self.gear["options"][0]["levels"][0])
        self.assertNotEqual(self.gear["level"], len(self.gear["options"][0]["levels"]))

    def test_primary_and_optional_secondary_slots_are_core_attributes(self) -> None:
        rules_by_slot = {
            rule["slot"]: rule for rule in self.slot_rules["slots"]
        }
        self.assertEqual("required", rules_by_slot[1]["presence"])
        self.assertEqual("optional", rules_by_slot[2]["presence"])
        self.assertEqual("required", rules_by_slot[3]["presence"])
        self.assertEqual([0, 1, 2, 3], rules_by_slot[1]["allowedAttributeIds"])
        self.assertEqual([0, 1, 2, 3], rules_by_slot[2]["allowedAttributeIds"])

        validate_gear_option_rules(self.gear, self.gear_options)
        catalog_by_id = {
            entry["id"]: entry for entry in self.gear_options["entries"]
        }
        for option in self.gear["options"]:
            if option["slot"] in {1, 2}:
                catalog = catalog_by_id[option["optionId"]]
                self.assertEqual("attribute", catalog["categoryCode"])
                self.assertIn(catalog["parameters"]["attributeId"], {0, 1, 2, 3})

    def test_missing_second_option_keeps_slots_one_and_three(self) -> None:
        two_option_gear = deepcopy(self.gear)
        two_option_gear["options"] = [
            option for option in two_option_gear["options"] if option["slot"] != 2
        ]
        two_option_localization = deepcopy(self.localization)
        two_option_localization["options"] = [
            option
            for option in two_option_localization["options"]
            if option["slot"] != 2
        ]

        cases = (
            ("gear-canonical.schema.json", two_option_gear),
            ("gear-localization.schema.json", two_option_localization),
        )
        for schema_name, instance in cases:
            validator = Draft202012Validator(load_json(f"schemas/{schema_name}"))
            self.assertEqual([], list(validator.iter_errors(instance)))

        rag = build_gear_rag_documents(
            two_option_gear, two_option_localization, self.gear_options
        )
        option_documents = [
            document for document in rag["documents"]
            if document["section"] == "gear_option"
        ]
        self.assertEqual(
            {1, 3},
            {document["metadata"]["optionSlot"] for document in option_documents},
        )
        self.assertEqual(
            "distribution_check",
            self.slot_rules["missingSlot2Pattern"]["validationMode"],
        )

    def test_non_attribute_in_first_or_second_slot_is_rejected(self) -> None:
        invalid = deepcopy(self.gear)
        invalid["options"][0] = deepcopy(invalid["options"][2])
        invalid["options"][0]["slot"] = 1
        with self.assertRaisesRegex(ValueError, "must be strength, agility"):
            validate_gear_option_rules(invalid, self.gear_options)

    def test_set_is_separate_and_semantically_structured(self) -> None:
        set_reference = self.gear["taxonomy"]["set"]
        self.assertEqual(self.gear_set["identity"]["setId"], set_reference["id"])
        self.assertEqual(
            self.gear_set["identity"]["setCode"], set_reference["code"]
        )
        catalog_entry = next(
            entry
            for entry in self.gear_sets["entries"]
            if entry["id"] == set_reference["id"]
        )
        self.assertEqual(self.set_entity_id, catalog_entry["canonicalEntityId"])

        effect = self.gear_set["effects"][0]
        conditional = effect["conditionalEffect"]
        self.assertEqual(3, effect["requiredPieces"])
        self.assertEqual(8.0, effect["baseModifiers"]["attack_percent"])
        self.assertEqual(6.0, conditional["valuePerConsumedStack"])
        self.assertEqual(20, conditional["durationSeconds"])
        self.assertEqual(1.5, conditional["amplificationMultiplier"])
        self.assertEqual("non_stacking", conditional["stackingRule"])
        self.assertEqual(
            {"heavy_strike", "armor_break"}, set(conditional["triggerDamageCodes"])
        )
        self.assertEqual(3, len(conditional["amplificationConditionCodes"]))

    def test_rag_is_reproducible_and_partitioned(self) -> None:
        self.assertEqual(
            build_gear_rag_documents(
                self.gear, self.localization, self.gear_options
            ),
            self.gear_rag,
        )
        self.assertEqual(
            build_set_rag_documents(self.gear_set, self.set_localization),
            self.set_rag,
        )
        self.assertEqual(4, len(self.gear_rag["documents"]))
        option_documents = [
            document
            for document in self.gear_rag["documents"]
            if document["section"] == "gear_option"
        ]
        self.assertEqual(3, len(option_documents))
        self.assertTrue(all(
            document["metadata"]["forgeLevelCount"] == 4
            for document in option_documents
        ))
        self.assertEqual(1, len(self.set_rag["documents"]))
        self.assertEqual(
            "gear_set_effect", self.set_rag["documents"][0]["section"]
        )


if __name__ == "__main__":
    unittest.main()
