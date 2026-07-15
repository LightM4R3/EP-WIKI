from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_PATH = PROJECT_ROOT / "data" / "canonical" / "operator" / "tangtang.json"
LOCALIZATION_DIR = PROJECT_ROOT / "data" / "localization" / "operator"
RAG_DIR = PROJECT_ROOT / "data" / "rag" / "operator"
LOCALES = ("ko-KR", "en-US", "ja-JP", "zh-TW")
STAT_CODES = ("strength", "agility", "intellect", "will", "baseAttack", "baseHp")


PHRASES = {
    "ko-KR": {
        "profile": "오퍼레이터 프로필",
        "name": "이름",
        "rarity": "희귀도",
        "class": "클래스",
        "element": "속성",
        "weapon": "무기 유형",
        "primary": "주요 능력치",
        "secondary": "보조 능력치",
        "progression": "레벨별 능력치와 재료",
        "materials": "재료",
        "none": "없음",
        "metrics": "수치 항목",
        "operator_talents": "오퍼레이터 재능",
        "infrastructure_talents": "인프라 재능",
        "conditions": "활성화 조건",
        "potentials": "잠재능력",
    },
    "en-US": {
        "profile": "Operator profile",
        "name": "Name",
        "rarity": "Rarity",
        "class": "Class",
        "element": "Element",
        "weapon": "Weapon type",
        "primary": "Main attribute",
        "secondary": "Secondary attribute",
        "progression": "Stats and materials by level",
        "materials": "Materials",
        "none": "None",
        "metrics": "Metrics",
        "operator_talents": "Operator talents",
        "infrastructure_talents": "Base skills",
        "conditions": "Unlock conditions",
        "potentials": "Potentials",
    },
    "ja-JP": {
        "profile": "オペレータープロフィール",
        "name": "名前",
        "rarity": "レアリティ",
        "class": "クラス",
        "element": "属性",
        "weapon": "武器種類",
        "primary": "メイン能力",
        "secondary": "サブ能力",
        "progression": "レベル別能力値と素材",
        "materials": "素材",
        "none": "なし",
        "metrics": "数値項目",
        "operator_talents": "素質",
        "infrastructure_talents": "配属スキル",
        "conditions": "開放条件",
        "potentials": "潜在能力",
    },
    "zh-TW": {
        "profile": "幹員資料",
        "name": "名稱",
        "rarity": "稀有度",
        "class": "職業",
        "element": "屬性",
        "weapon": "武器類型",
        "primary": "主能力",
        "secondary": "副能力",
        "progression": "各等級能力值與材料",
        "materials": "材料",
        "none": "無",
        "metrics": "數值項目",
        "operator_talents": "幹員天賦",
        "infrastructure_talents": "後勤技能",
        "conditions": "解鎖條件",
        "potentials": "潛能",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _material_text(
    costs: list[dict[str, int]],
    labels: dict[str, str],
    locale: str,
) -> str:
    if not costs:
        return PHRASES[locale]["none"]
    return ", ".join(
        f"{labels[str(cost['materialId'])]} ×{cost['quantity']}" for cost in costs
    )


def _missing_metric_label(code: str, locale: str, html_lang: str) -> str:
    if locale == "ko-KR":
        return f"{code} [{html_lang} DOM 누락; ko-KR fallback]"
    if locale == "en-US":
        return f"{code} [missing in {html_lang} DOM; ko-KR fallback]"
    if locale == "ja-JP":
        return f"{code} [{html_lang} DOM欠落・ko-KRフォールバック]"
    return f"{code} [{html_lang} DOM缺漏；回退ko-KR]"


def _fallback_value(raw_value: str, unit: str, locale: str) -> str:
    if unit != "seconds":
        return raw_value
    match = re.search(r"-?\d+(?:\.\d+)?", raw_value)
    if match is None:
        return raw_value
    suffix = "s" if locale == "en-US" else "초" if locale == "ko-KR" else "秒"
    return f"{match.group(0)}{suffix}"


def _metadata(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    canonical_pointer: str,
    localization_pointer: str,
    content_status: str,
) -> dict[str, Any]:
    taxonomy = localization["taxonomy"]
    attributes = localization["attributes"]
    return {
        "entityType": "operator",
        "entityId": canonical["entityId"],
        "sourceUrl": canonical["source"]["url"],
        "canonicalRef": f"data/canonical/operator/tangtang.json#{canonical_pointer}",
        "localizationRef": (
            f"data/localization/operator/tangtang.{localization['locale']}.json"
            f"#{localization_pointer}"
        ),
        "contentStatus": content_status,
        "rarity": canonical["identity"]["rarity"],
        "classId": taxonomy["classId"],
        "classCode": taxonomy["classCode"],
        "elementId": taxonomy["elementId"],
        "elementCode": taxonomy["elementCode"],
        "weaponTypeId": taxonomy["weaponTypeId"],
        "weaponTypeCode": taxonomy["weaponTypeCode"],
        "primaryAttributeId": attributes["primaryId"],
        "secondaryAttributeId": attributes["secondaryId"],
    }


def _profile_document(
    canonical: dict[str, Any], localization: dict[str, Any]
) -> dict[str, Any]:
    locale = localization["locale"]
    words = PHRASES[locale]
    identity = localization["identity"]
    taxonomy = localization["taxonomy"]
    labels = localization["attributes"]["labels"]
    lines = [
        words["profile"],
        f"{words['name']}: {identity['name']}",
        f"{words['rarity']}: {identity['rarity']}",
        f"{words['class']}: {taxonomy['classLabel']} "
        f"(id={taxonomy['classId']}, code={taxonomy['classCode']}, verified)",
        f"{words['element']}: {taxonomy['elementLabel']} "
        f"(id={taxonomy['elementId']}, code={taxonomy['elementCode']})",
        f"{words['weapon']}: {taxonomy['weaponTypeLabel']} "
        f"(id={taxonomy['weaponTypeId']}, code={taxonomy['weaponTypeCode']})",
        f"{words['primary']}: {labels['agility']} (attributeId=1)",
        f"{words['secondary']}: {labels['strength']} (attributeId=0)",
    ]
    suffix = locale.lower()
    return {
        "documentId": f"operator.tangtang.profile.{suffix}",
        "section": "profile",
        "content": "\n".join(lines),
        "metadata": _metadata(canonical, localization, "", "", "verified"),
    }


def _progression_document(
    canonical: dict[str, Any], localization: dict[str, Any]
) -> dict[str, Any]:
    locale = localization["locale"]
    words = PHRASES[locale]
    stat_labels = localization["attributes"]["labels"]
    material_labels = localization["materialLabels"]
    lines = [words["progression"]]
    for index, row in enumerate(canonical["progression"]):
        stats = " / ".join(
            f"{stat_labels[code]}={row['stats'][code]}" for code in STAT_CODES
        )
        costs = _material_text(row["materialCosts"], material_labels, locale)
        level_label = localization["progression"]["levelLabels"][index]
        lines.append(f"{level_label}: {stats}; {words['materials']}: {costs}")
    suffix = locale.lower()
    return {
        "documentId": f"operator.tangtang.progression.{suffix}",
        "section": "progression",
        "content": "\n".join(lines),
        "metadata": _metadata(
            canonical, localization, "/progression", "/progression", "verified"
        ),
    }


def _skill_status(localization: dict[str, Any], skill_index: int) -> str:
    prefix = f"/combatSkills/{skill_index}/"
    anomalies = [
        anomaly
        for anomaly in localization["sourceAnomalies"]
        if anomaly["path"].startswith(prefix)
    ]
    if any(anomaly["kind"] == "missing_in_locale_dom" for anomaly in anomalies):
        return "has_source_gaps"
    if anomalies:
        return "needs_review"
    return "verified"


def _skill_document(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    skill_index: int,
) -> dict[str, Any]:
    locale = localization["locale"]
    words = PHRASES[locale]
    saved_skill = canonical["combatSkills"][skill_index]
    local_skill = localization["combatSkills"][skill_index]
    html_lang = localization["source"]["htmlLang"]
    material_labels = localization["materialLabels"]
    local_metric_by_code = {metric["code"]: metric for metric in local_skill["metrics"]}
    metric_labels: dict[str, str] = {}
    for metric in saved_skill["metrics"]:
        localized_metric = local_metric_by_code[metric["code"]]
        metric_labels[metric["code"]] = (
            localized_metric["sourceLabel"]
            if localized_metric["sourceLabel"] is not None
            else _missing_metric_label(metric["code"], locale, html_lang)
        )

    lines = [f"{local_skill['sourceType']}: {local_skill['name']}"]
    lines.extend(local_skill["descriptionBlocks"])
    lines.append(
        f"{words['metrics']}: "
        + "; ".join(
            f"{metric_labels[metric['code']]} [{metric['code']}]"
            for metric in saved_skill["metrics"]
        )
    )
    for level_index, saved_level in enumerate(saved_skill["levels"]):
        local_level = local_skill["levels"][level_index]
        values = []
        for metric in saved_skill["metrics"]:
            code = metric["code"]
            value = local_level["values"].get(code)
            if value is None:
                value = _fallback_value(saved_level["values"][code], metric["unit"], locale)
            values.append(f"{metric_labels[code]}={value}")
        costs = _material_text(saved_level["materialCosts"], material_labels, locale)
        lines.append(
            f"{local_level['sourceLabel']}: {'; '.join(values)}; "
            f"{words['materials']}: {costs}"
        )

    status = _skill_status(localization, skill_index)
    metadata = _metadata(
        canonical,
        localization,
        f"/combatSkills/{skill_index}",
        f"/combatSkills/{skill_index}",
        status,
    )
    metadata["skillId"] = saved_skill["id"]
    metadata["skillTypeId"] = saved_skill["typeId"]
    suffix = locale.lower()
    return {
        "documentId": f"operator.tangtang.skill.{saved_skill['typeCode']}.{suffix}",
        "section": "combat_skill",
        "content": "\n".join(lines),
        "metadata": metadata,
    }


def _talent_document(
    canonical: dict[str, Any],
    localization: dict[str, Any],
    group: str,
) -> dict[str, Any]:
    locale = localization["locale"]
    words = PHRASES[locale]
    heading_key = "operator_talents" if group == "operator" else "infrastructure_talents"
    lines = [words[heading_key]]
    for local_talent, saved_talent in zip(
        localization["talents"][group], canonical["talents"][group], strict=True
    ):
        lines.append(f"{local_talent['sourceType']}: {local_talent['name']}")
        for local_stage, saved_stage in zip(
            local_talent["stages"], saved_talent["stages"], strict=True
        ):
            conditions = " / ".join(local_stage["activationConditions"])
            costs = _material_text(
                saved_stage["materialCosts"], localization["materialLabels"], locale
            )
            lines.append(
                f"{local_stage['sourceLabel']}: {local_stage['effect']}; "
                f"{words['conditions']}: {conditions}; {words['materials']}: {costs}"
            )
    section = "operator_talent" if group == "operator" else "infrastructure_talent"
    suffix = locale.lower()
    return {
        "documentId": f"operator.tangtang.talent.{group}.{suffix}",
        "section": section,
        "content": "\n".join(lines),
        "metadata": _metadata(
            canonical,
            localization,
            f"/talents/{group}",
            f"/talents/{group}",
            "verified",
        ),
    }


def _potential_document(
    canonical: dict[str, Any], localization: dict[str, Any]
) -> dict[str, Any]:
    locale = localization["locale"]
    lines = [PHRASES[locale]["potentials"]]
    for potential in localization["potentials"]:
        lines.append(
            f"{potential['sourceLabel']} — {potential['name']}: {potential['description']}"
        )
    suffix = locale.lower()
    return {
        "documentId": f"operator.tangtang.potential.{suffix}",
        "section": "potential",
        "content": "\n".join(lines),
        "metadata": _metadata(
            canonical, localization, "/potentials", "/potentials", "verified"
        ),
    }


def build_rag_documents(
    canonical: dict[str, Any], localization: dict[str, Any]
) -> dict[str, Any]:
    documents = [
        _profile_document(canonical, localization),
        _progression_document(canonical, localization),
    ]
    documents.extend(
        _skill_document(canonical, localization, index) for index in range(4)
    )
    documents.extend(
        (
            _talent_document(canonical, localization, "operator"),
            _talent_document(canonical, localization, "infrastructure"),
            _potential_document(canonical, localization),
        )
    )
    return {
        "schemaVersion": "1.0.0",
        "entityId": canonical["entityId"],
        "locale": localization["locale"],
        "documents": documents,
    }


def _target_path(locale: str) -> Path:
    return RAG_DIR / f"tangtang.{locale}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Tangtang locale RAG documents")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when committed RAG documents differ from generated output",
    )
    args = parser.parse_args()
    canonical = load_json(CANONICAL_PATH)
    failures: list[str] = []
    for locale in LOCALES:
        localization = load_json(LOCALIZATION_DIR / f"tangtang.{locale}.json")
        generated = build_rag_documents(canonical, localization)
        target = _target_path(locale)
        if args.check:
            if not target.exists() or load_json(target) != generated:
                failures.append(locale)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(generated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if failures:
        raise SystemExit(f"Outdated RAG documents: {', '.join(failures)}")


if __name__ == "__main__":
    main()
