from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GEAR_ENTITY_ID = "echo_of_ancient_sword_metal_gloves_i"
SET_ENTITY_ID = "echo_of_ancient_sword"

GEAR_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "canonical" / "gear" / f"{GEAR_ENTITY_ID}.json"
)
GEAR_LOCALIZATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "localization"
    / "gear"
    / f"{GEAR_ENTITY_ID}.ko-KR.json"
)
SET_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "canonical" / "gear-set" / f"{SET_ENTITY_ID}.json"
)
SET_LOCALIZATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "localization"
    / "gear-set"
    / f"{SET_ENTITY_ID}.ko-KR.json"
)
OPTION_CATALOG_PATH = PROJECT_ROOT / "data" / "catalog" / "gear-options.json"
GEAR_RAG_PATH = (
    PROJECT_ROOT / "data" / "rag" / "gear" / f"{GEAR_ENTITY_ID}.ko-KR.json"
)
SET_RAG_PATH = (
    PROJECT_ROOT / "data" / "rag" / "gear-set" / f"{SET_ENTITY_ID}.ko-KR.json"
)
CORE_ATTRIBUTE_IDS = frozenset({0, 1, 2, 3})


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_value(value: int | float, unit: str) -> str:
    if unit == "percent":
        return f"+{float(value):g}%"
    return f"+{value:g}"


def _material_text(costs: list[dict[str, int]], labels: dict[str, str]) -> str:
    return ", ".join(
        f"{labels[str(cost['materialId'])]} ×{cost['quantity']}" for cost in costs
    )


def validate_gear_option_rules(
    canonical: dict[str, Any], option_catalog: dict[str, Any]
) -> None:
    """Validate the stable slot rules before producing searchable documents."""
    options = canonical["options"]
    slots = {option["slot"] for option in options}
    if slots not in ({1, 3}, {1, 2, 3}):
        raise ValueError("Gear options must use slots {1, 3} or {1, 2, 3}")

    catalog_by_id = {entry["id"]: entry for entry in option_catalog["entries"]}
    for option in options:
        catalog_option = catalog_by_id.get(option["optionId"])
        if catalog_option is None or catalog_option["code"] != option["optionCode"]:
            raise ValueError(f"Unknown gear option catalog reference: {option}")
        if option["slot"] not in {1, 2}:
            continue
        attribute_id = catalog_option["parameters"].get("attributeId")
        if (
            catalog_option["categoryCode"] != "attribute"
            or attribute_id not in CORE_ATTRIBUTE_IDS
        ):
            raise ValueError(
                f"Gear option slot {option['slot']} must be strength, agility, "
                "intellect, or will"
            )


def _gear_metadata(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    canonical_pointer: str,
    localization_pointer: str,
) -> dict[str, Any]:
    taxonomy = localization["taxonomy"]
    return {
        "entityType": "gear",
        "entityId": canonical["entityId"],
        "sourceUrl": canonical["source"]["url"],
        "canonicalRef": (
            f"data/canonical/gear/{canonical['entityId']}.json#{canonical_pointer}"
        ),
        "localizationRef": (
            f"data/localization/gear/{canonical['entityId']}.{localization['locale']}.json"
            f"#{localization_pointer}"
        ),
        "contentStatus": canonical["source"]["contentStatus"],
        "gearTypeId": taxonomy["gearTypeId"],
        "gearTypeCode": taxonomy["gearTypeCode"],
        "qualityId": taxonomy["qualityId"],
        "qualityCode": taxonomy["qualityCode"],
        "gearSetId": taxonomy["setId"],
        "gearSetCode": taxonomy["setCode"],
        "gearLevel": canonical["level"],
        "forgingSupported": canonical["forging"]["supported"],
    }


def _gear_profile_document(
    canonical: dict[str, Any], localization: dict[str, Any]
) -> dict[str, Any]:
    identity = localization["identity"]
    taxonomy = localization["taxonomy"]
    costs = _material_text(
        canonical["identity"]["acquisition"]["craftingCosts"],
        localization["materialLabels"],
    )
    stage_requirements = ", ".join(
        f"+{stage['forgeLevel']}={stage['cumulativeStageRequirement']}"
        for stage in canonical["forging"]["stages"]
    )
    lines = [
        "장비 프로필",
        f"이름: {identity['name']}",
        (
            f"장비 유형: {taxonomy['gearTypeLabel']} "
            f"(id={taxonomy['gearTypeId']}, code={taxonomy['gearTypeCode']})"
        ),
        (
            f"품질: {taxonomy['qualityLabel']} "
            f"(id={taxonomy['qualityId']}, code={taxonomy['qualityCode']})"
        ),
        (
            f"세트: {taxonomy['setLabel']} "
            f"(id={taxonomy['setId']}, code={taxonomy['setCode']})"
        ),
        f"LV: {canonical['level']}",
        f"{localization['statLabels']['defense']}: +{canonical['baseStats']['defense']}",
        f"획득 방법: {', '.join(identity['acquisitionLabels'])}",
        f"제작 재료: {costs}",
        (
            "정밀 단조: 지원함; 적용 규칙=노란색 품질 전용"
            f"; 적합 제제={localization['forging']['suitableAgentLabel']}"
        ),
        f"단조 단계별 누적 요구량: {stage_requirements}",
    ]
    lines.extend(identity["introductionBlocks"])
    return {
        "documentId": f"gear.{canonical['entityId']}.profile.ko-kr",
        "section": "profile",
        "content": "\n".join(lines),
        "metadata": _gear_metadata(canonical, localization, "", ""),
    }


def _gear_option_document(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    option_catalog: dict[str, Any],
    option_index: int,
) -> dict[str, Any]:
    saved_option = canonical["options"][option_index]
    local_option_index, local_option = next(
        (index, option)
        for index, option in enumerate(localization["options"])
        if option["slot"] == saved_option["slot"]
        and option["optionId"] == saved_option["optionId"]
    )
    catalog_option = next(
        entry
        for entry in option_catalog["entries"]
        if entry["id"] == saved_option["optionId"]
    )
    units = {metric["code"]: metric["unit"] for metric in catalog_option["metrics"]}
    metric_labels = local_option["metricLabels"]
    lines = [
        f"장비 옵션 슬롯 {saved_option['slot']}: {local_option['name']}",
        f"옵션 ID: {saved_option['optionId']}; 옵션 코드: {saved_option['optionCode']}",
        "이 수치는 장비 LV와 무관하며 정밀 단조 +0~+3 단계에 따라 변합니다.",
    ]
    for level in saved_option["levels"]:
        metrics = "; ".join(
            f"{metric_labels[code]}={_format_value(value, units[code])}"
            for code, value in level["values"].items()
        )
        lines.append(f"단조 +{level['forgeLevel']} ({level['sourceLabel']}): {metrics}")

    metadata = _gear_metadata(
        canonical,
        localization,
        f"/options/{option_index}",
        f"/options/{local_option_index}",
    )
    metadata.update(
        {
            "optionId": saved_option["optionId"],
            "optionCode": saved_option["optionCode"],
            "optionSlot": saved_option["slot"],
            "forgeLevelCount": len(saved_option["levels"]),
        }
    )
    return {
        "documentId": (
            f"gear.{canonical['entityId']}.option.{saved_option['optionCode']}.ko-kr"
        ),
        "section": "gear_option",
        "content": "\n".join(lines),
        "metadata": metadata,
    }


def build_gear_rag_documents(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    option_catalog: dict[str, Any],
) -> dict[str, Any]:
    validate_gear_option_rules(canonical, option_catalog)
    documents = [_gear_profile_document(canonical, localization)]
    documents.extend(
        _gear_option_document(canonical, localization, option_catalog, index)
        for index in range(len(canonical["options"]))
    )
    return {
        "schemaVersion": "1.0.0",
        "entityId": canonical["entityId"],
        "locale": localization["locale"],
        "documents": documents,
    }


def _set_effect_document(
    canonical: dict[str, Any], localization: dict[str, Any], effect_index: int
) -> dict[str, Any]:
    effect = canonical["effects"][effect_index]
    local_effect = localization["effects"][effect_index]
    conditional = effect["conditionalEffect"]
    set_id = canonical["identity"]["setId"]
    set_code = canonical["identity"]["setCode"]
    lines = [
        f"장비 세트: {localization['identity']['name']} (id={set_id}, code={set_code})",
        f"필요 장비 수: {effect['requiredPieces']}개",
        f"원문 효과: {local_effect['description']}",
        (
            "구조화 수치: 공격력 +"
            f"{effect['baseModifiers']['attack_percent']:g}%; "
            f"소모 스택당 물리 피해 +{conditional['valuePerConsumedStack']:g}%; "
            f"지속 {conditional['durationSeconds']:g}초; 조건 충족 시 "
            f"{conditional['amplificationMultiplier']:g}배; 중첩 불가"
        ),
    ]
    return {
        "documentId": f"gear-set.{effect['id']}.ko-kr",
        "section": "gear_set_effect",
        "content": "\n".join(lines),
        "metadata": {
            "entityType": "gear_set",
            "entityId": canonical["entityId"],
            "sourceUrl": canonical["source"]["url"],
            "canonicalRef": (
                f"data/canonical/gear-set/{canonical['entityId']}.json#/effects/{effect_index}"
            ),
            "localizationRef": (
                f"data/localization/gear-set/{canonical['entityId']}.{localization['locale']}.json"
                f"#/effects/{effect_index}"
            ),
            "contentStatus": canonical["source"]["contentStatus"],
            "gearSetId": set_id,
            "gearSetCode": set_code,
            "requiredPieces": effect["requiredPieces"],
            "effectId": effect["id"],
        },
    }


def build_set_rag_documents(
    canonical: dict[str, Any], localization: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0.0",
        "entityId": canonical["entityId"],
        "locale": localization["locale"],
        "documents": [
            _set_effect_document(canonical, localization, index)
            for index in range(len(canonical["effects"]))
        ],
    }


def _write_or_check(path: Path, generated: dict[str, Any], check: bool) -> None:
    if check:
        if not path.exists() or load_json(path) != generated:
            raise SystemExit(f"Outdated RAG document: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(generated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build gear and gear-set RAG documents")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when committed RAG documents differ from generated output",
    )
    args = parser.parse_args()

    gear_rag = build_gear_rag_documents(
        load_json(GEAR_CANONICAL_PATH),
        load_json(GEAR_LOCALIZATION_PATH),
        load_json(OPTION_CATALOG_PATH),
    )
    set_rag = build_set_rag_documents(
        load_json(SET_CANONICAL_PATH), load_json(SET_LOCALIZATION_PATH)
    )
    _write_or_check(GEAR_RAG_PATH, gear_rag, args.check)
    _write_or_check(SET_RAG_PATH, set_rag, args.check)


if __name__ == "__main__":
    main()
