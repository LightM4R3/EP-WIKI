from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_PATH = PROJECT_ROOT / "data" / "canonical" / "weapon" / "rebellion.json"
LOCALIZATION_PATH = (
    PROJECT_ROOT / "data" / "localization" / "weapon" / "rebellion.ko-KR.json"
)
OPTION_CATALOG_PATH = PROJECT_ROOT / "data" / "catalog" / "weapon-options.json"
RAG_PATH = PROJECT_ROOT / "data" / "rag" / "weapon" / "rebellion.ko-KR.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _material_text(costs: list[dict[str, int]], labels: dict[str, str]) -> str:
    if not costs:
        return "없음"
    return ", ".join(
        f"{labels[str(cost['materialId'])]} ×{cost['quantity']}" for cost in costs
    )


def _format_value(value: int | float, unit: str) -> str:
    if unit == "percent":
        return f"+{float(value):.1f}%"
    if isinstance(value, float) and not value.is_integer():
        return f"+{value}"
    return f"+{int(value)}"


def _render_template(
    template: str,
    values: dict[str, int | float],
    units: dict[str, str],
) -> str:
    return re.sub(
        r"\{([a-z0-9_]+)\}",
        lambda match: _format_value(values[match.group(1)], units[match.group(1)]),
        template,
    )


def _metadata(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    canonical_pointer: str,
    localization_pointer: str,
) -> dict[str, Any]:
    taxonomy = localization["taxonomy"]
    return {
        "entityType": "weapon",
        "entityId": canonical["entityId"],
        "sourceUrl": canonical["source"]["url"],
        "canonicalRef": (
            f"data/canonical/weapon/{canonical['entityId']}.json#{canonical_pointer}"
        ),
        "localizationRef": (
            f"data/localization/weapon/{canonical['entityId']}.{localization['locale']}.json"
            f"#{localization_pointer}"
        ),
        "contentStatus": canonical["source"]["contentStatus"],
        "rarity": canonical["identity"]["rarity"],
        "weaponTypeId": taxonomy["weaponTypeId"],
        "weaponTypeCode": taxonomy["weaponTypeCode"],
    }


def _profile_document(
    canonical: dict[str, Any], localization: dict[str, Any]
) -> dict[str, Any]:
    identity = localization["identity"]
    taxonomy = localization["taxonomy"]
    lines = [
        "무기 프로필",
        f"이름: {identity['name']}",
        f"희귀도: {identity['rarity']}성",
        (
            f"무기 유형: {taxonomy['weaponTypeLabel']} "
            f"(id={taxonomy['weaponTypeId']}, code={taxonomy['weaponTypeCode']})"
        ),
        f"획득 방식: {identity['acquisitionLabel']}",
    ]
    lines.extend(identity["introductionBlocks"])
    return {
        "documentId": f"weapon.{canonical['entityId']}.profile.ko-kr",
        "section": "profile",
        "content": "\n".join(lines),
        "metadata": _metadata(canonical, localization, "", ""),
    }


def _progression_document(
    canonical: dict[str, Any], localization: dict[str, Any]
) -> dict[str, Any]:
    lines = ["무기 레벨별 기초 공격력과 돌파 재료"]
    for index, row in enumerate(canonical["progression"]):
        label = localization["progression"]["levelLabels"][index]
        costs = _material_text(row["materialCosts"], localization["materialLabels"])
        lines.append(f"{label}: 기초 공격력={row['baseAttack']}; 재료: {costs}")
    return {
        "documentId": f"weapon.{canonical['entityId']}.progression.ko-kr",
        "section": "progression",
        "content": "\n".join(lines),
        "metadata": _metadata(canonical, localization, "/progression", "/progression"),
    }


def _option_document(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    option_catalog: dict[str, Any],
    option_index: int,
) -> dict[str, Any]:
    saved_option = canonical["options"][option_index]
    local_option = localization["options"][option_index]
    catalog_option = next(
        entry
        for entry in option_catalog["entries"]
        if entry["id"] == saved_option["optionId"]
    )
    units = {metric["code"]: metric["unit"] for metric in catalog_option["metrics"]}
    metric_labels = local_option["metricLabels"]
    lines = [
        f"무기 옵션 슬롯 {saved_option['slot']}: {local_option['name']}",
        (
            f"분류: {local_option['categoryLabel']} "
            f"(categoryId={saved_option['categoryId']}, "
            f"categoryCode={saved_option['categoryCode']})"
        ),
        (
            f"옵션 ID: {saved_option['optionId']}; "
            f"옵션 코드: {saved_option['optionCode']}; "
            f"재사용 범위: {catalog_option['scope']}"
        ),
    ]
    for level in saved_option["levels"]:
        metrics = "; ".join(
            f"{metric_labels[code]}={_format_value(value, units[code])}"
            for code, value in level["values"].items()
        )
        description = _render_template(
            local_option["descriptionTemplate"], level["values"], units
        )
        lines.append(f"{level['sourceLabel']}: {metrics}; 효과: {description}")

    metadata = _metadata(
        canonical,
        localization,
        f"/options/{option_index}",
        f"/options/{option_index}",
    )
    metadata.update(
        {
            "optionId": saved_option["optionId"],
            "optionCode": saved_option["optionCode"],
            "optionCategoryId": saved_option["categoryId"],
            "optionCategoryCode": saved_option["categoryCode"],
            "optionSlot": saved_option["slot"],
            "optionLevelCount": len(saved_option["levels"]),
        }
    )
    return {
        "documentId": (
            f"weapon.{canonical['entityId']}.option.{saved_option['optionCode']}.ko-kr"
        ),
        "section": "weapon_option",
        "content": "\n".join(lines),
        "metadata": metadata,
    }


def build_rag_documents(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    option_catalog: dict[str, Any],
) -> dict[str, Any]:
    documents = [
        _profile_document(canonical, localization),
        _progression_document(canonical, localization),
    ]
    documents.extend(
        _option_document(canonical, localization, option_catalog, index)
        for index in range(len(canonical["options"]))
    )
    return {
        "schemaVersion": "1.0.0",
        "entityId": canonical["entityId"],
        "locale": localization["locale"],
        "documents": documents,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Rebellion weapon RAG documents")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed RAG document differs from generated output",
    )
    args = parser.parse_args()
    generated = build_rag_documents(
        load_json(CANONICAL_PATH),
        load_json(LOCALIZATION_PATH),
        load_json(OPTION_CATALOG_PATH),
    )
    if args.check:
        if not RAG_PATH.exists() or load_json(RAG_PATH) != generated:
            raise SystemExit("Outdated RAG document: rebellion.ko-KR")
        return
    RAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAG_PATH.write_text(
        json.dumps(generated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
