from __future__ import annotations

import unittest
from collections import Counter

from epwiki_crawler.normalizer import NORMALIZED_RAG_ROOT
from epwiki_crawler.retrieval import (
    RETRIEVAL_DOCUMENT_SCHEMA,
    RANK_LABELS,
    _build_documents,
    _load_artifacts,
    _quality_report,
    _read_json,
)


class RetrievalCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts, _, _ = _load_artifacts("ko-KR", NORMALIZED_RAG_ROOT)
        cls.documents = _build_documents(cls.artifacts)
        cls.index = {document["documentId"]: document for document in cls.documents}

    def test_full_corpus_has_expected_semantic_grain(self) -> None:
        counts = Counter(document["documentType"] for document in self.documents)
        self.assertEqual(1272, len(self.documents))
        self.assertEqual(112, counts["operator_combat_skill"])
        self.assertEqual(84, counts["operator_talent"])
        self.assertEqual(54, counts["operator_infrastructure_talent"])
        self.assertEqual(140, counts["operator_potential"])
        self.assertEqual(211, counts["weapon_option"])
        self.assertEqual(129, counts["gear_forging"])
        self.assertEqual(22, counts["gear_set_effect"])

    def test_strict_quality_gates_are_indexable(self) -> None:
        quality = _quality_report(
            self.documents,
            self.artifacts,
            _read_json(RETRIEVAL_DOCUMENT_SCHEMA),
        )
        self.assertEqual("indexable", quality["verdict"])
        self.assertTrue(all(check["passed"] for check in quality["checks"].values()))
        self.assertEqual(0, len(quality["checks"]["uniqueContentHashes"]["duplicates"]))
        self.assertEqual(0, len(quality["checks"]["uiResidue"]["documents"]))

    def test_tangtang_profile_and_skills_match_verified_values(self) -> None:
        profile = self.index["epwiki.ko-kr.operator.25.profile"]
        self.assertEqual("cryo", profile["facts"]["element"]["code"])
        self.assertEqual("handcannon", profile["facts"]["weaponType"]["code"])
        self.assertEqual("agility", profile["facts"]["primaryAttribute"]["code"])
        self.assertEqual("strength", profile["facts"]["secondaryAttribute"]["code"])
        self.assertEqual(6, profile["facts"]["rarity"])
        self.assertEqual("caster", profile["facts"]["class"]["code"])

        expected_metric_counts = [7, 9, 5, 8]
        for index, metric_count in enumerate(expected_metric_counts, 1):
            skill = self.index[f"epwiki.ko-kr.operator.25.skill-{index}"]["facts"]
            self.assertEqual(list(RANK_LABELS), skill["rankLabels"])
            self.assertEqual(metric_count, len(skill["metrics"]))
            self.assertEqual(12, len(skill["materialCosts"]))

        battle = self.index["epwiki.ko-kr.operator.25.skill-2"]["facts"]
        shooting = next(metric for metric in battle["metrics"] if metric["label"] == "사격 피해 배율")
        self.assertEqual((80, 180), (shooting["values"][0]["value"], shooting["values"][-1]["value"]))

    def test_rebellion_weapon_options_are_ranked_without_recommendation_noise(self) -> None:
        first = self.index["epwiki.ko-kr.weapon.732.option-1"]["facts"]
        second = self.index["epwiki.ko-kr.weapon.732.option-2"]["facts"]
        trait = self.index["epwiki.ko-kr.weapon.732.option-3"]
        self.assertEqual([20, 36, 52, 68, 84, 100, 116, 132, 156], [row["value"] for row in first["ranks"]])
        self.assertEqual([5, 9, 13, 17, 21, 25, 29, 33, 39], [row["value"] for row in second["ranks"]])
        self.assertEqual(9, len(trait["facts"]["ranks"]))
        self.assertNotIn("추천 주입 기질", trait["content"])

    def test_gear_and_set_effect_are_deduplicated(self) -> None:
        profile = self.index["epwiki.ko-kr.gear.1023.profile"]["facts"]
        forging = self.index["epwiki.ko-kr.gear.1023.forging"]["facts"]
        set_effect = self.index[
            "epwiki.ko-kr.gear-set.echo-of-ancient-sword.effect"
        ]
        self.assertEqual((70, 42), (profile["level"], profile["defense"]))
        self.assertEqual([1, 2, 3], [option["slot"] for option in profile["options"]])
        self.assertEqual([0, 1, 2, 3], [row["forgeLevel"] for row in forging["options"][0]["values"]])
        self.assertEqual(3, set_effect["facts"]["requiredPieces"])
        self.assertEqual(6, len(set_effect["facts"]["memberGameEntryIds"]))

    def test_source_conflicts_do_not_leak_as_answerable_values(self) -> None:
        gear_profile = self.index["epwiki.ko-kr.gear.328.profile"]
        conflicted_option = next(
            option
            for option in gear_profile["facts"]["options"]
            if option.get("status") == "source_conflict"
        )
        self.assertEqual(2, conflicted_option["slot"])
        self.assertNotIn("baseValue", conflicted_option)

        for entry_id, field in ((12, "intellect"), (17, "intellect"), (23, "agility")):
            progression = self.index[f"epwiki.ko-kr.operator.{entry_id}.progression"]
            self.assertTrue(all(field not in row["stats"] for row in progression["facts"]["levels"]))

        promotion = self.index["epwiki.ko-kr.operator.24.promotion"]
        stage_four = promotion["facts"]["promotions"][3]
        self.assertEqual("source_conflict", stage_four["status"])
        self.assertIsNone(stage_four["maxLevel"])

    def test_document_payloads_are_deterministic(self) -> None:
        rebuilt = _build_documents(self.artifacts)
        observed = {
            document["documentId"]: document["indexing"]["payloadSha256"]
            for document in rebuilt
        }
        expected = {
            document["documentId"]: document["indexing"]["payloadSha256"]
            for document in self.documents
        }
        self.assertEqual(expected, observed)


if __name__ == "__main__":
    unittest.main()
