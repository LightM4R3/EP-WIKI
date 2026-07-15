from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from epwiki_crawler.config import PROJECT_ROOT
from epwiki_crawler.normalizer import (
    materialize_normalized_snapshot,
    normalize_entity,
)


SNAPSHOT_PATH = PROJECT_ROOT / "data" / "rag" / "published" / "latest.ko-KR.json"


class NormalizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        cls.artifacts = [
            normalize_entity(entity) for entity in cls.snapshot["entities"]
        ]

    def artifact(self, domain: str, game_entry_id: int) -> dict[str, object]:
        return next(
            artifact
            for artifact in self.artifacts
            if artifact["entityType"] == domain
            and artifact["identity"]["gameEntryId"] == game_entry_id
        )

    def test_every_entity_is_query_ready_and_has_a_group(self) -> None:
        self.assertEqual(320, len(self.artifacts))
        self.assertTrue(
            all(artifact["quality"]["queryReady"] for artifact in self.artifacts)
        )
        self.assertEqual(
            320,
            len(
                {
                    (
                        artifact["entityType"],
                        artifact["identity"]["gameEntryId"],
                    )
                    for artifact in self.artifacts
                }
            ),
        )
        self.assertTrue(
            all(artifact["group"]["code"] != "unknown" for artifact in self.artifacts)
        )

    def test_tangtang_operator_fields_are_structured(self) -> None:
        tangtang = self.artifact("operator", 25)
        self.assertEqual("cryo", tangtang["taxonomy"]["element"]["code"])
        self.assertEqual(
            "handcannon", tangtang["taxonomy"]["weaponType"]["code"]
        )
        self.assertEqual("agility", tangtang["attributes"]["primary"]["code"])
        self.assertEqual("strength", tangtang["attributes"]["secondary"]["code"])
        self.assertEqual(179, tangtang["progression"][-1]["stats"]["agility"])
        self.assertEqual(321, tangtang["progression"][-1]["stats"]["baseAttack"])

    def test_rebellion_weapon_fields_are_structured(self) -> None:
        rebellion = self.artifact("weapon", 732)
        self.assertEqual(
            "handcannon", rebellion["taxonomy"]["weaponType"]["code"]
        )
        self.assertEqual(
            [51, 148, 250, 352, 454, 505],
            [row["baseAttack"] for row in rebellion["progression"]],
        )
        self.assertEqual(
            ["민첩 증가 · 대", "공격력 증가 · 대", "방출 · 토벌의 원한"],
            [option["name"] for option in rebellion["options"]],
        )

    def test_verified_identity_and_weapon_type_overrides_are_applied(self) -> None:
        administrator = self.artifact("operator", 2)
        self.assertEqual("관리자", administrator["identity"]["name"])
        self.assertEqual(
            "administrator", administrator["identity"]["canonicalCode"]
        )
        self.assertEqual("관리자(남)", administrator["identity"]["sourceName"])
        self.assertFalse(
            any(
                artifact["entityType"] == "operator"
                and artifact["identity"]["gameEntryId"] == 3
                for artifact in self.artifacts
            )
        )

        rational_farewell = self.artifact("weapon", 89)
        self.assertEqual("이성적인 작별", rational_farewell["identity"]["name"])
        self.assertEqual(
            "handcannon", rational_farewell["taxonomy"]["weaponType"]["code"]
        )
        self.assertEqual("권총", rational_farewell["group"]["label"])
        self.assertIn("normalizationOverride", rational_farewell)

    def test_gear_fields_and_forging_are_structured(self) -> None:
        gear = self.artifact("gear", 1023)
        self.assertEqual(
            "echo_of_ancient_sword", gear["taxonomy"]["gearSet"]["code"]
        )
        self.assertEqual("gloves", gear["taxonomy"]["gearType"]["code"])
        self.assertEqual("yellow", gear["taxonomy"]["quality"]["code"])
        self.assertEqual(70, gear["level"])
        self.assertEqual(42, gear["defense"])
        self.assertEqual(["민첩", "힘", "오리지늄 아츠 강도"], [
            option["name"] for option in gear["options"]
        ])
        self.assertEqual(
            [65, 71, 78, 84],
            [value["value"] for value in gear["forging"]["options"][0]["values"]],
        )

    def test_gear_without_second_attribute_keeps_slots_one_and_three(self) -> None:
        candidates = [
            artifact
            for artifact in self.artifacts
            if artifact["entityType"] == "gear"
            and len(artifact["options"]) == 2
            and "attribute" in artifact["options"][0]
            and "attribute" not in artifact["options"][1]
        ]
        self.assertGreater(len(candidates), 0)
        self.assertTrue(
            all(
                [option["slot"] for option in artifact["options"]] == [1, 3]
                for artifact in candidates
            )
        )

    def test_materializer_writes_one_file_per_entity_and_query_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_path = root / "published" / "latest.ko-KR.json"
            snapshot_path.parent.mkdir(parents=True)
            snapshot_path.write_text(
                json.dumps(self.snapshot, ensure_ascii=False), encoding="utf-8"
            )
            result = materialize_normalized_snapshot(
                snapshot_path,
                normalized_root=root / "normalized",
                query_index_root=root / "published",
            )
            entity_files = [
                path
                for path in (root / "normalized" / "ko-KR").rglob("*.json")
            ]
            self.assertEqual(320, len(entity_files))
            self.assertEqual("query_ready", result["quality"]["verdict"])
            self.assertEqual(320, result["manifest"]["stats"]["entities"])
            self.assertEqual(1, result["manifest"]["stats"]["excludedEntities"])
            self.assertTrue((root / "published" / "query-index.ko-KR.json").exists())
            self.assertTrue(
                (root / "normalized" / "ko-KR" / "operator" / "냉기").is_dir()
            )
            self.assertTrue(
                (root / "normalized" / "ko-KR" / "weapon" / "권총").is_dir()
            )
            self.assertTrue(
                (root / "normalized" / "ko-KR" / "gear" / "고검의_잔향").is_dir()
            )


if __name__ == "__main__":
    unittest.main()
