from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from epwiki_crawler.config import PROJECT_ROOT
from epwiki_crawler.core.naming import safe_entity_file_stem, safe_path_segment
from epwiki_crawler.core.storage import write_json_atomic
from epwiki_crawler.normalizer import NORMALIZED_RAG_ROOT


RETRIEVAL_RAG_ROOT = PROJECT_ROOT / "data" / "rag" / "retrieval"
RETRIEVAL_DOCUMENT_SCHEMA = PROJECT_ROOT / "schemas" / "retrieval-document.schema.json"
RETRIEVAL_MANIFEST_SCHEMA = PROJECT_ROOT / "schemas" / "retrieval-manifest.schema.json"

LEVELS = (1, 20, 40, 60, 80, 90)
RANK_LABELS = (
    "RANK1",
    "RANK2",
    "RANK3",
    "RANK4",
    "RANK5",
    "RANK6",
    "RANK7",
    "RANK8",
    "RANK9",
    "마스터리I",
    "마스터리II",
    "마스터리III",
)
SKILL_TYPES = (
    (0, "normal_attack", "일반 공격"),
    (1, "battle_skill", "배틀 스킬"),
    (2, "combo_skill", "연계 스킬"),
    (3, "ultimate", "궁극기"),
)
ATTRIBUTE_FIELD_CODES = {
    "힘": "strength",
    "민첩": "agility",
    "지능": "intellect",
    "의지": "will",
    "기초 공격력": "baseAttack",
    "기초 생명력": "baseHp",
}
SCALAR = re.compile(r"^[+-]?\d[\d,]*(?:\.\d+)?(?:%|초)?$")
RANK = re.compile(r"^RANK\s*([1-9])$")
MASTERY = re.compile(r"^마스터리\s*([IVX]+)$")
POTENTIAL = re.compile(r"^잠재능력\s*0?([1-5])$")
STAGE_EFFECT = re.compile(r"^단계 효과\s*(\d+)$")
PIECE_EFFECT = re.compile(r"^(\d+)개 세트 효과:?$")
UI_RESIDUES = (
    "일괄 채우기",
    "entity:",
    "category:",
    "section:",
)


class RetrievalBuildError(RuntimeError):
    """Raised when semantic extraction or a strict retrieval gate fails."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RetrievalBuildError(f"JSON root must be an object: {path}")
    return value


def _project_ref(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n")
    return "\n".join(line.rstrip() for line in normalized.strip().splitlines())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(_normalized_text(value).encode("utf-8")).hexdigest()


def _payload_sha256(document: dict[str, Any]) -> str:
    payload = copy.deepcopy(document)
    payload.get("indexing", {}).pop("payloadSha256", None)
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _source_documents(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        document
        for document in artifact.get("documents", [])
        if document.get("metadata", {}).get("contentStatus") != "normalized"
    ]


def _document_lines(document: dict[str, Any]) -> list[str]:
    lines = [line.strip() for line in document["content"].splitlines() if line.strip()]
    while lines and any(
        lines[0].startswith(prefix)
        for prefix in ("entity:", "category:", "section:")
    ):
        lines.pop(0)
    return lines


def _section_groups(
    artifact: dict[str, Any], section: str
) -> list[tuple[list[str], list[str]]]:
    grouped: dict[tuple[int, int | None], list[dict[str, Any]]] = defaultdict(list)
    order: list[tuple[int, int | None]] = []
    for document in _source_documents(artifact):
        if document.get("section") != section:
            continue
        metadata = document.get("metadata", {})
        key = (metadata.get("chapterIndex", -1), metadata.get("widgetIndex"))
        if key not in grouped:
            order.append(key)
        grouped[key].append(document)
    result: list[tuple[list[str], list[str]]] = []
    for key in order:
        documents = sorted(
            grouped[key],
            key=lambda item: (
                item.get("metadata", {}).get("chunkIndex", 0),
                item["documentId"],
            ),
        )
        lines = [line for document in documents for line in _document_lines(document)]
        result.append((lines, [document["documentId"] for document in documents]))
    return result


def _single_section(
    artifact: dict[str, Any], section: str
) -> tuple[list[str], list[str]]:
    groups = _section_groups(artifact, section)
    if not groups:
        return [], []
    if len(groups) != 1:
        raise RetrievalBuildError(
            f"Expected one {section} source for {artifact['entityId']}, got {len(groups)}"
        )
    return groups[0]


def _join_text(segments: Iterable[str]) -> str:
    text = " ".join(segment.strip() for segment in segments if segment.strip())
    text = re.sub(r"\s+([,.:;!?%])", r"\1", text)
    text = re.sub(r"([\[(])\s+", r"\1", text)
    text = re.sub(r"\s+([\])])", r"\1", text)
    text = re.sub(
        r"\s+(을|를|이|가|은|는|의|에|에게|에서|으로|로|와|과|도|만|보다|까지|부터)"
        r"(?=\s|[,.:;!?]|$)",
        r"\1",
        text,
    )
    text = re.sub(r"\s+(합니다|됩니다)(?=[.!?]|$)", r"\1", text)
    text = re.sub(
        r"(?<!을)(?<!를)\s+(줍니다|받습니다)(?=[.!?]|$)",
        r"\1",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def _parse_scalar(raw: str) -> dict[str, Any]:
    if not SCALAR.fullmatch(raw):
        raise RetrievalBuildError(f"Not a scalar value: {raw!r}")
    unit = "flat"
    number = raw.replace(",", "")
    if number.endswith("%"):
        unit = "percent"
        number = number[:-1]
    elif number.endswith("초"):
        unit = "seconds"
        number = number[:-1]
    parsed = float(number)
    value: int | float = int(parsed) if parsed.is_integer() else parsed
    return {"value": value, "unit": unit, "display": raw}


def _parse_int(raw: str) -> int:
    value = raw.replace(",", "").strip()
    if not re.fullmatch(r"\d+", value):
        raise RetrievalBuildError(f"Expected integer, got {raw!r}")
    return int(value)


def _rank_label(raw: str) -> str | None:
    if match := RANK.fullmatch(raw):
        return f"RANK{match.group(1)}"
    if match := MASTERY.fullmatch(raw):
        return f"마스터리{match.group(1)}"
    return None


def _material_catalog() -> dict[str, dict[str, Any]]:
    payload = _read_json(PROJECT_ROOT / "data" / "catalog" / "materials.json")
    return {
        entry["labels"]["ko-KR"]: {
            "id": entry["id"],
            "code": entry["code"],
            "name": entry["labels"]["ko-KR"],
            "catalogStatus": "mapped",
        }
        for entry in payload["entries"]
        if entry.get("labels", {}).get("ko-KR")
    }


def _material(name: str, amount: int) -> dict[str, Any]:
    known = _material_catalog().get(name)
    if known:
        return {**known, "amount": amount}
    return {
        "id": None,
        "code": None,
        "name": name,
        "amount": amount,
        "catalogStatus": "unmapped",
    }


def _is_material_quadruple(lines: list[str], index: int) -> bool:
    if index + 3 >= len(lines) or lines[index + 2] != "*":
        return False
    try:
        return _parse_int(lines[index]) == _parse_int(lines[index + 3])
    except RetrievalBuildError:
        return False


def _parse_material_items(lines: list[str]) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    index = 0
    while _is_material_quadruple(lines, index):
        amount = _parse_int(lines[index])
        items.append(_material(lines[index + 1], amount))
        index += 4
    return items, index


def _parse_currency_groups(
    lines: list[str], *, expected_groups: int
) -> tuple[list[list[dict[str, Any]]], int]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    index = 0
    while index < len(lines) and len(groups) < expected_groups:
        if not _is_material_quadruple(lines, index):
            raise RetrievalBuildError(
                f"Broken material quadruple at {index}: {lines[index:index + 4]}"
            )
        amount = _parse_int(lines[index])
        item = _material(lines[index + 1], amount)
        current.append(item)
        index += 4
        if item["name"] == "탈로시안 화폐":
            groups.append(current)
            current = []
    if len(groups) != expected_groups or current:
        raise RetrievalBuildError(
            f"Expected {expected_groups} material rows, got {len(groups)}"
        )
    return groups, index


def _material_text(items: list[dict[str, Any]]) -> str:
    return ", ".join(f"{item['name']} {item['amount']}개" for item in items)


def _withheld(path: str, reason: str, status: str = "missing") -> dict[str, str]:
    return {"path": path, "reason": reason, "status": status}


def _authority(artifact: dict[str, Any]) -> tuple[str, str, str]:
    if artifact.get("normalizationOverride"):
        return "human_override", "verified", "high"
    if artifact.get("canonicalRef"):
        return "canonical", "verified", "high"
    return "normalized_extraction", "rule_validated", "medium"


def _make_document(
    artifact: dict[str, Any],
    *,
    slug: str,
    document_type: str,
    title: str,
    content: str,
    facts: dict[str, Any],
    evidence_ids: list[str],
    filters: dict[str, Any] | None = None,
    withheld_fields: list[dict[str, str]] | None = None,
    authority: tuple[str, str, str] | None = None,
) -> dict[str, Any]:
    locale = artifact["locale"]
    identity = artifact["identity"]
    entity_type = artifact["entityType"]
    game_entry_id = identity.get("gameEntryId")
    identity_token = str(game_entry_id) if game_entry_id is not None else identity["code"]
    document_id = (
        f"epwiki.{locale.lower()}.{entity_type}.{identity_token}.{slug}"
        .replace("_", "-")
        .lower()
    )
    normalized_content = _normalized_text(content)
    authority_value, status, confidence = authority or _authority(artifact)
    entity: dict[str, Any] = {
        "type": entity_type,
        "key": artifact["entityId"],
        "name": identity["name"],
        "aliases": identity.get("aliases", []),
    }
    if game_entry_id is not None:
        entity["gameEntryId"] = game_entry_id
    document: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "documentId": document_id,
        "semanticKey": f"{locale}|{entity_type}|{identity_token}|{slug}",
        "locale": locale,
        "documentType": document_type,
        "channel": "gameplay_facts",
        "entity": entity,
        "title": title,
        "content": normalized_content,
        "facts": facts,
        "filters": {
            "entityType": entity_type,
            "documentType": document_type,
            "groupAxis": artifact.get("group", {}).get("axis"),
            "groupCode": artifact.get("group", {}).get("code"),
            "groupLabel": artifact.get("group", {}).get("label"),
            **(filters or {}),
        },
        "provenance": {
            "normalizedRef": artifact.get("ragRef"),
            "sourceUrl": artifact.get("source", {}).get("url"),
            "sourceSha256": artifact.get("source", {}).get("contentSha256"),
            "authority": authority_value,
            "verificationStatus": status,
            "confidence": confidence,
            "evidenceDocumentIds": sorted(set(evidence_ids)),
        },
        "coverage": {"withheldFields": withheld_fields or []},
        "indexing": {
            "eligible": True,
            "vector": True,
            "keyword": True,
            "structured": True,
            "contentSha256": _sha256_text(normalized_content),
        },
    }
    document["indexing"]["payloadSha256"] = _payload_sha256(document)
    return document


def _operator_profile(artifact: dict[str, Any]) -> dict[str, Any]:
    identity = artifact["identity"]
    taxonomy = artifact["taxonomy"]
    attributes = artifact["attributes"]
    facts: dict[str, Any] = {
        "name": identity["name"],
        "element": taxonomy["element"],
        "weaponType": taxonomy["weaponType"],
        "primaryAttribute": attributes["primary"],
        "secondaryAttribute": attributes["secondary"],
        "attributeCatalogOrder": attributes["catalogOrder"],
    }
    sentences = [
        f"{identity['name']} 오퍼레이터의 기본 정보.",
        f"속성은 {taxonomy['element']['label']}, 무기 유형은 "
        f"{taxonomy['weaponType']['label']}이다.",
        f"주요 능력치는 {attributes['primary']['label']}, 보조 능력치는 "
        f"{attributes['secondary']['label']}이다.",
    ]
    withheld: list[dict[str, str]] = []
    if "rarity" in identity:
        facts["rarity"] = identity["rarity"]
        sentences.append(f"희귀도는 {identity['rarity']}성이다.")
    else:
        withheld.append(_withheld("facts.rarity", "원문에서 희귀도를 텍스트로 확정할 수 없음"))
    if taxonomy.get("class"):
        facts["class"] = taxonomy["class"]
        class_label = taxonomy["class"].get("label") or taxonomy["class"].get(
            "sourceLabel"
        )
        sentences.append(f"클래스는 {class_label}이다.")
    else:
        withheld.append(_withheld("facts.class", "클래스 이미지 매핑이 검증되지 않음"))
    if identity.get("portraitUrl"):
        facts["portraitUrl"] = identity["portraitUrl"]
    else:
        withheld.append(_withheld("facts.portraitUrl", "초상화 URL이 구조화되지 않음"))
    evidence = [
        document["documentId"]
        for document in _source_documents(artifact)
        if document.get("section") == "profile"
    ]
    return _make_document(
        artifact,
        slug="profile",
        document_type="operator_profile",
        title=f"{identity['name']} — 오퍼레이터 기본 정보",
        content=" ".join(sentences),
        facts=facts,
        evidence_ids=evidence,
        filters={
            "elementCode": taxonomy["element"]["code"],
            "weaponTypeCode": taxonomy["weaponType"]["code"],
            "primaryAttributeCode": attributes["primary"]["code"],
            "secondaryAttributeCode": attributes["secondary"]["code"],
        },
        withheld_fields=withheld,
    )


def _operator_level_materials(
    artifact: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    groups = _section_groups(artifact, "progression")
    source = next(
        ((lines, ids) for lines, ids in groups if lines and lines[0] == "업그레이드"),
        None,
    )
    if source is None:
        raise RetrievalBuildError(f"Missing operator upgrade table: {artifact['entityId']}")
    lines, evidence = source
    start = next(
        (
            index + 2
            for index in range(len(lines) - 1)
            if lines[index] == "재료 소모" and lines[index + 1] == "-"
        ),
        None,
    )
    if start is None:
        raise RetrievalBuildError(f"Missing level material anchor: {artifact['entityId']}")
    rows, _ = _parse_currency_groups(lines[start:], expected_groups=5)
    return [
        {"targetLevel": level, "items": items}
        for level, items in zip(LEVELS[1:], rows)
    ], evidence


def _ambiguous_operator_fields(artifact: dict[str, Any]) -> dict[str, str]:
    blocked: dict[str, str] = {}
    for conflict in artifact.get("progressionSourceConflicts", []):
        if "ambiguous" not in conflict.get("resolution", ""):
            continue
        code = ATTRIBUTE_FIELD_CODES.get(conflict["field"])
        if code:
            blocked[code] = conflict["field"]
    return blocked


def _operator_progression(artifact: dict[str, Any]) -> dict[str, Any]:
    identity = artifact["identity"]
    blocked = _ambiguous_operator_fields(artifact)
    rows: list[dict[str, Any]] = []
    content_lines = [f"{identity['name']} 오퍼레이터의 레벨별 기본 능력치."]
    for row in artifact["progression"]:
        stats = {
            code: value
            for code, value in row["stats"].items()
            if code not in blocked
        }
        rows.append({"level": row["level"], "stats": stats})
        labels = {
            "strength": "힘",
            "agility": "민첩",
            "intellect": "지능",
            "will": "의지",
            "baseAttack": "기초 공격력",
            "baseHp": "기초 생명력",
        }
        content_lines.append(
            f"LV.{row['level']}: "
            + ", ".join(f"{labels[code]} {value}" for code, value in stats.items())
        )
    materials, material_evidence = _operator_level_materials(artifact)
    content_lines.append(f"{identity['name']}의 레벨 돌파 재료.")
    for row in materials:
        content_lines.append(
            f"LV.{row['targetLevel']} 도달: {_material_text(row['items'])}."
        )
    withheld = [
        _withheld(
            f"facts.progression[].stats.{code}",
            f"{label} 값이 두 원문 표에서 충돌하고 자동 선택 근거가 부족함",
            "source_conflict",
        )
        for code, label in blocked.items()
    ]
    evidence = sorted(
        set(
            material_evidence
            + [
                conflict["evidenceDocumentId"]
                for conflict in artifact.get("progressionSourceConflicts", [])
            ]
        )
    )
    return _make_document(
        artifact,
        slug="progression",
        document_type="operator_progression",
        title=f"{identity['name']} — 레벨 능력치와 재료",
        content="\n".join(content_lines),
        facts={"levels": rows, "materialCosts": materials},
        evidence_ids=evidence or material_evidence,
        withheld_fields=withheld,
    )


def _parse_metrics(lines: list[str]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(lines):
        value_start = next(
            (
                index
                for index in range(cursor + 1, len(lines) - 11)
                if all(SCALAR.fullmatch(value) for value in lines[index : index + 12])
            ),
            None,
        )
        if value_start is None:
            raise RetrievalBuildError(f"Cannot locate 12 scalar metric values: {lines[cursor:]}")
        label = _join_text(lines[cursor:value_start])
        if not label:
            raise RetrievalBuildError("Empty skill metric label")
        values = [_parse_scalar(value) for value in lines[value_start : value_start + 12]]
        metrics.append(
            {
                "label": label,
                "values": [
                    {"rankIndex": index, "rankLabel": RANK_LABELS[index - 1], **value}
                    for index, value in enumerate(values, 1)
                ],
            }
        )
        cursor = value_start + 12
    return metrics


def _parse_operator_skills(artifact: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    lines, evidence = _single_section(artifact, "combat_skill")
    if not lines or lines[0] != "전투 스킬":
        raise RetrievalBuildError(f"Missing combat skill header: {artifact['entityId']}")
    skills: list[dict[str, Any]] = []
    cursor = 1
    for skill_index, (type_id, type_code, type_label) in enumerate(SKILL_TYPES, 1):
        try:
            type_position = lines.index(type_label, cursor)
        except ValueError as error:
            raise RetrievalBuildError(
                f"Missing {type_label} after material boundary: {artifact['entityId']}"
            ) from error
        if type_position == 0:
            raise RetrievalBuildError("Skill type has no title")
        name = lines[type_position - 1]
        rank_start = next(
            (
                index
                for index in range(type_position + 1, len(lines))
                if _rank_label(lines[index]) == "RANK1"
            ),
            None,
        )
        if rank_start is None:
            raise RetrievalBuildError(f"Missing RANK1 for {name}")
        headers = [_rank_label(value) for value in lines[rank_start : rank_start + 12]]
        if tuple(headers) != RANK_LABELS:
            raise RetrievalBuildError(f"Invalid rank headers for {name}: {headers}")
        material_start = next(
            (
                index
                for index in range(rank_start + 12, len(lines) - 1)
                if lines[index] == "재료 소모" and lines[index + 1] == "-"
            ),
            None,
        )
        if material_start is None:
            raise RetrievalBuildError(f"Missing material table for {name}")
        metrics = _parse_metrics(lines[rank_start + 12 : material_start])
        material_rows, consumed = _parse_currency_groups(
            lines[material_start + 2 :], expected_groups=11
        )
        costs = [{"rankIndex": 1, "rankLabel": RANK_LABELS[0], "items": []}]
        costs.extend(
            {
                "rankIndex": rank_index,
                "rankLabel": RANK_LABELS[rank_index - 1],
                "items": items,
            }
            for rank_index, items in enumerate(material_rows, 2)
        )
        skills.append(
            {
                "index": skill_index,
                "name": name,
                "type": {"id": type_id, "code": type_code, "label": type_label},
                "description": _join_text(lines[type_position + 1 : rank_start]),
                "rankLabels": list(RANK_LABELS),
                "metrics": metrics,
                "materialCosts": costs,
            }
        )
        cursor = material_start + 2 + consumed
    if cursor != len(lines):
        trailing = [value for value in lines[cursor:] if value]
        if trailing:
            raise RetrievalBuildError(
                f"Unexpected combat skill trailing data for {artifact['entityId']}: {trailing[:5]}"
            )
    return skills, evidence


def _operator_skill_documents(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    identity = artifact["identity"]
    skills, evidence = _parse_operator_skills(artifact)
    documents: list[dict[str, Any]] = []
    for skill in skills:
        lines = [
            f"{identity['name']} 오퍼레이터의 {skill['type']['label']} "
            f"‘{skill['name']}’. {skill['description']}"
        ]
        for metric in skill["metrics"]:
            lines.append(
                f"{metric['label']}: "
                + ", ".join(
                    f"{value['rankLabel']} {value['display']}"
                    for value in metric["values"]
                )
                + "."
            )
        lines.append(f"{identity['name']}의 ‘{skill['name']}’ 강화 재료.")
        for cost in skill["materialCosts"][1:]:
            lines.append(
                f"{cost['rankLabel']}: {_material_text(cost['items'])}."
            )
        documents.append(
            _make_document(
                artifact,
                slug=f"skill-{skill['index']}",
                document_type="operator_combat_skill",
                title=f"{identity['name']} — {skill['name']}",
                content="\n".join(lines),
                facts=skill,
                evidence_ids=evidence,
                filters={
                    "skillIndex": skill["index"],
                    "skillTypeCode": skill["type"]["code"],
                },
            )
        )
    return documents


def _parse_conditioned_block(lines: list[str]) -> dict[str, Any]:
    material_start = next(
        (index for index in range(len(lines)) if _is_material_quadruple(lines, index)),
        None,
    )
    prefix = lines if material_start is None else lines[:material_start]
    conditions = [
        value
        for value in prefix
        if ("도달" in value or "돌파" in value) and value != "-"
    ]
    effect_segments = [
        value
        for value in prefix
        if value not in conditions and value not in {"-", "활성화 후", "활성화 조건", "재료 소모"}
    ]
    materials: list[dict[str, Any]] = []
    if material_start is not None:
        materials, _ = _parse_material_items(lines[material_start:])
    return {
        "effect": _join_text(effect_segments),
        "conditions": conditions,
        "materials": materials,
    }


def _parse_effect_stages(lines: list[str]) -> list[dict[str, Any]]:
    markers = [
        (index, int(match.group(1)))
        for index, value in enumerate(lines)
        if (match := STAGE_EFFECT.fullmatch(value))
    ]
    stages: list[dict[str, Any]] = []
    for marker_index, (start, stage) in enumerate(markers):
        end = markers[marker_index + 1][0] if marker_index + 1 < len(markers) else len(lines)
        stages.append({"stage": stage, **_parse_conditioned_block(lines[start + 1 : end])})
    return stages


def _talent_content(
    operator_name: str, talent_name: str, talent_kind: str, stages: list[dict[str, Any]]
) -> str:
    lines = [f"{operator_name} 오퍼레이터의 {talent_kind} ‘{talent_name}’."]
    for stage in stages:
        effect = (stage["effect"] or "추가 효과 정보 없음").rstrip(".")
        sentence = f"단계 {stage['stage']}: {effect}."
        if stage["conditions"]:
            sentence += f" 활성화 조건: {', '.join(stage['conditions'])}."
        if stage["materials"]:
            sentence += f" 재료: {_material_text(stage['materials'])}."
        lines.append(sentence)
    return "\n".join(lines)


def _operator_talent_documents(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    identity = artifact["identity"]
    lines, evidence = _single_section(artifact, "operator_talent")
    if not lines or lines[0] != "재능 배열":
        raise RetrievalBuildError(f"Missing talent array: {artifact['entityId']}")
    documents: list[dict[str, Any]] = []

    try:
        trust_index = lines.index("신뢰도")
    except ValueError as error:
        raise RetrievalBuildError(f"Missing trust boundary: {artifact['entityId']}") from error
    attribute_name = lines[1]
    attribute_stages = _parse_effect_stages(lines[1:trust_index])
    if len(attribute_stages) != 4:
        raise RetrievalBuildError(
            f"Expected 4 attribute talent stages for {artifact['entityId']}"
        )
    documents.append(
        _make_document(
            artifact,
            slug="talent-attribute",
            document_type="operator_talent",
            title=f"{identity['name']} — {attribute_name}",
            content=_talent_content(
                identity["name"], attribute_name, "능력치 재능", attribute_stages
            ),
            facts={
                "kind": "attribute_talent",
                "name": attribute_name,
                "stages": attribute_stages,
            },
            evidence_ids=evidence,
            filters={"talentKind": "attribute_talent"},
        )
    )

    markers = [index for index, value in enumerate(lines) if value == "오퍼레이터 재능"]
    if len(markers) != 2:
        raise RetrievalBuildError(
            f"Expected 2 operator talents for {artifact['entityId']}, got {len(markers)}"
        )
    for talent_index, marker in enumerate(markers, 1):
        title_index = marker - 1
        end = markers[talent_index] - 1 if talent_index < len(markers) else len(lines)
        name = lines[title_index]
        stages = _parse_effect_stages(lines[marker + 1 : end])
        if not stages:
            raise RetrievalBuildError(f"No stages parsed for operator talent {name}")
        documents.append(
            _make_document(
                artifact,
                slug=f"talent-{talent_index}",
                document_type="operator_talent",
                title=f"{identity['name']} — {name}",
                content=_talent_content(
                    identity["name"], name, "오퍼레이터 재능", stages
                ),
                facts={
                    "kind": "combat_talent",
                    "index": talent_index,
                    "name": name,
                    "stages": stages,
                },
                evidence_ids=evidence,
                filters={"talentKind": "combat_talent", "talentIndex": talent_index},
            )
        )
    return documents


def _infra_variant_headers(lines: list[str]) -> list[dict[str, Any]]:
    headers: list[dict[str, Any]] = []
    occupied: set[int] = set()
    for index, value in enumerate(lines):
        separated = re.fullmatch(r"·\s*([αβγ])", value)
        if separated:
            if index == 0:
                raise RetrievalBuildError("Infrastructure separator has no name")
            base = lines[index - 1].removesuffix("·").strip()
            headers.append(
                {
                    "start": index - 1,
                    "end": index + 1,
                    "name": f"{base} · {separated.group(1)}",
                    "grade": separated.group(1),
                }
            )
            occupied.update({index - 1, index})
            continue
        match = re.fullmatch(r"(.+?)\s*·\s*([αβγ])", value)
        if match:
            headers.append(
                {
                    "start": index,
                    "end": index + 1,
                    "name": f"{match.group(1).strip()} · {match.group(2)}",
                    "grade": match.group(2),
                }
            )
            occupied.add(index)
            continue
        if value not in {"α", "β", "γ"}:
            continue
        if index == 0:
            raise RetrievalBuildError("Infrastructure grade has no name")
        start = index - 1
        base = lines[start]
        if base == "·":
            start -= 1
            if start < 0:
                raise RetrievalBuildError("Infrastructure separator has no name")
            base = lines[start]
        else:
            base = base.removesuffix("·").strip()
        if any(position in occupied for position in range(start, index + 1)):
            continue
        headers.append(
            {
                "start": start,
                "end": index + 1,
                "name": f"{base} · {value}",
                "grade": value,
            }
        )
        occupied.update(range(start, index + 1))
    return sorted(headers, key=lambda header: header["start"])


def _operator_infrastructure_documents(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    identity = artifact["identity"]
    lines, evidence = _single_section(artifact, "infrastructure_talent")
    if not lines:
        return []
    markers = [index for index, value in enumerate(lines) if value == "인프라 스킬"]
    if len(markers) != 2:
        raise RetrievalBuildError(
            f"Expected 2 infrastructure talents for {artifact['entityId']}, got {len(markers)}"
        )
    documents: list[dict[str, Any]] = []
    for group_index, marker in enumerate(markers, 1):
        end = markers[group_index] - 1 if group_index < len(markers) else len(lines)
        block = lines[marker + 1 : end]
        headers = _infra_variant_headers(block)
        if len(headers) != 2:
            raise RetrievalBuildError(
                f"Expected 2 infrastructure variants for {artifact['entityId']} group "
                f"{group_index}, got {len(headers)}"
            )
        variants: list[dict[str, Any]] = []
        for variant_index, header in enumerate(headers):
            variant_end = (
                headers[variant_index + 1]["start"]
                if variant_index + 1 < len(headers)
                else len(block)
            )
            parsed = _parse_conditioned_block(block[header["end"] : variant_end])
            variants.append(
                {
                    "grade": header["grade"],
                    "name": header["name"],
                    "description": parsed["effect"],
                    "conditions": parsed["conditions"],
                    "materials": parsed["materials"],
                }
            )
        name = variants[0]["name"].rsplit("·", 1)[0].strip()
        content_lines = [f"{identity['name']} 오퍼레이터의 인프라 재능 ‘{name}’."]
        for variant in variants:
            description = variant["description"].rstrip(".")
            sentence = f"{variant['name']}: {description}."
            if variant["conditions"]:
                sentence += f" 활성화 조건: {', '.join(variant['conditions'])}."
            if variant["materials"]:
                sentence += f" 재료: {_material_text(variant['materials'])}."
            content_lines.append(sentence)
        documents.append(
            _make_document(
                artifact,
                slug=f"infrastructure-{group_index}",
                document_type="operator_infrastructure_talent",
                title=f"{identity['name']} — 인프라 재능 {name}",
                content="\n".join(content_lines),
                facts={"index": group_index, "name": name, "variants": variants},
                evidence_ids=evidence,
                filters={"infrastructureTalentIndex": group_index},
            )
        )
    return documents


def _operator_potential_documents(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    identity = artifact["identity"]
    lines, evidence = _single_section(artifact, "potential")
    markers = [
        (index, int(match.group(1)))
        for index, value in enumerate(lines)
        if (match := POTENTIAL.fullmatch(value))
    ]
    if len(markers) != 5:
        raise RetrievalBuildError(
            f"Expected 5 potentials for {artifact['entityId']}, got {len(markers)}"
        )
    lore_boundary = next(
        (index for index, value in enumerate(lines) if value == "오퍼레이터 기념사진"),
        len(lines),
    )
    documents: list[dict[str, Any]] = []
    for marker_index, (start, stage) in enumerate(markers):
        title_index = start - 1
        end = (
            markers[marker_index + 1][0] - 1
            if marker_index + 1 < len(markers)
            else lore_boundary
        )
        name = lines[title_index]
        effect_segments = lines[start + 1 : end]
        unavailable = not effect_segments or all(value == "???" for value in effect_segments)
        effect = "" if unavailable else _join_text(effect_segments)
        status = "source_unavailable" if unavailable else "rule_validated"
        content = (
            f"{identity['name']} 오퍼레이터의 잠재능력 {stage} ‘{name}’은 현재 "
            "공개된 효과 정보가 없다."
            if unavailable
            else f"{identity['name']} 오퍼레이터의 잠재능력 {stage} ‘{name}’. {effect}"
        )
        withheld = (
            [_withheld("facts.effect", "원문이 비공개 상태임", "source_unavailable")]
            if unavailable
            else []
        )
        documents.append(
            _make_document(
                artifact,
                slug=f"potential-{stage}",
                document_type="operator_potential",
                title=f"{identity['name']} — 잠재능력 {stage} {name}",
                content=content,
                facts={"stage": stage, "name": name, "status": status, "effect": effect or None},
                evidence_ids=evidence,
                filters={"potentialStage": stage},
                withheld_fields=withheld,
            )
        )
    return documents


def _operator_promotion_document(artifact: dict[str, Any]) -> dict[str, Any]:
    identity = artifact["identity"]
    groups = _section_groups(artifact, "progression")
    source = next(
        ((lines, ids) for lines, ids in groups if lines and lines[0] == "정예화"),
        None,
    )
    if source is None:
        raise RetrievalBuildError(f"Missing elite promotion source: {artifact['entityId']}")
    lines, evidence = source
    romans = ("I", "II", "III", "IV")
    expected_caps = (40, 60, 80, 90)
    promotions: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for stage, (roman, expected_cap) in enumerate(zip(romans, expected_caps), 1):
        title = f"정예화 {roman}"
        start = next(
            (
                index
                for index in range(len(lines) - 1)
                if lines[index] == title
                and lines[index + 1].startswith("활성화 후, 오퍼레이터 레벨 최대치")
            ),
            None,
        )
        if start is None:
            raise RetrievalBuildError(f"Missing parsed promotion {title}: {artifact['entityId']}")
        boundary_label = f"장비 조합 {roman}" if stage <= 3 else None
        end = (
            lines.index(boundary_label, start + 1)
            if boundary_label and boundary_label in lines[start + 1 :]
            else len(lines)
        )
        effect = lines[start + 1]
        condition = lines[start + 2]
        materials, _ = _parse_material_items(lines[start + 3 : end])
        match = re.search(r"최대치\s*(\d+)레벨", effect)
        max_level = int(match.group(1)) if match else None
        status = "rule_validated"
        if max_level != expected_cap:
            status = "source_conflict"
            max_level = None
            blocked.append(
                _withheld(
                    f"facts.promotions[{stage - 1}].maxLevel",
                    f"정예화 {roman} 원문 최대 레벨이 진행 표의 LV.{expected_cap}과 충돌함",
                    "source_conflict",
                )
            )
        promotions.append(
            {
                "stage": stage,
                "label": title,
                "maxLevel": max_level,
                "condition": condition,
                "materials": materials,
                "status": status,
            }
        )

    equipment_unlocks: list[dict[str, Any]] = []
    for stage, roman in enumerate(romans[:3], 1):
        title = f"장비 조합 {roman}"
        start = next(
            (
                index
                for index in range(len(lines) - 1)
                if lines[index] == title and lines[index + 1].startswith("활성화 후,")
            ),
            None,
        )
        if start is None:
            raise RetrievalBuildError(f"Missing equipment unlock {title}")
        condition_index = next(
            index for index in range(start + 1, len(lines)) if "돌파" in lines[index]
        )
        effect = _join_text(lines[start + 1 : condition_index])
        next_promotion = f"정예화 {romans[stage]}"
        end = lines.index(next_promotion, condition_index + 1)
        materials, _ = _parse_material_items(lines[condition_index + 1 : end])
        equipment_unlocks.append(
            {
                "stage": stage,
                "label": title,
                "effect": effect,
                "condition": lines[condition_index],
                "materials": materials,
            }
        )
    content_lines = [f"{identity['name']} 오퍼레이터의 정예화와 장비 품질 해금."]
    for promotion in promotions:
        cap = (
            f"최대 레벨 {promotion['maxLevel']}"
            if promotion["maxLevel"] is not None
            else "최대 레벨은 원문 충돌로 검색 제외"
        )
        content_lines.append(
            f"{promotion['label']}: {cap}, 조건 {promotion['condition']}, "
            f"재료 {_material_text(promotion['materials'])}."
        )
    for unlock in equipment_unlocks:
        content_lines.append(
            f"{unlock['label']}: {unlock['effect']}, 조건 {unlock['condition']}, "
            f"재료 {_material_text(unlock['materials'])}."
        )
    return _make_document(
        artifact,
        slug="promotion",
        document_type="operator_promotion",
        title=f"{identity['name']} — 정예화와 장비 해금",
        content="\n".join(content_lines),
        facts={"promotions": promotions, "equipmentUnlocks": equipment_unlocks},
        evidence_ids=evidence,
        withheld_fields=blocked,
    )


def _operator_documents(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    documents = [_operator_profile(artifact), _operator_progression(artifact)]
    documents.append(_operator_promotion_document(artifact))
    documents.extend(_operator_skill_documents(artifact))
    documents.extend(_operator_talent_documents(artifact))
    documents.extend(_operator_infrastructure_documents(artifact))
    documents.extend(_operator_potential_documents(artifact))
    return documents


def _weapon_option_names(lines: list[str], rank_start: int) -> list[str]:
    try:
        start = lines.index("스킬 상세 및 기질") + 1
    except ValueError as error:
        raise RetrievalBuildError("Missing weapon option heading") from error
    names: list[str] = []
    for value in lines[start:rank_start]:
        if value.startswith("·") and names:
            names[-1] = f"{names[-1]} {value}"
        else:
            names.append(value)
    if len(names) not in {2, 3}:
        raise RetrievalBuildError(f"Expected 2 or 3 weapon options, got {names}")
    return names


def _parse_weapon_options(
    artifact: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    lines, evidence = _single_section(artifact, "weapon_option")
    rank_positions = [
        index for index, value in enumerate(lines) if RANK.fullmatch(value)
    ]
    if len(rank_positions) != 9:
        raise RetrievalBuildError(
            f"Expected 9 weapon ranks for {artifact['entityId']}, got {len(rank_positions)}"
        )
    names = _weapon_option_names(lines, rank_positions[0])
    options = [
        {"slot": slot, "name": name, "ranks": []}
        for slot, name in enumerate(names, 1)
    ]
    recommendation_boundary = next(
        (
            index
            for index, value in enumerate(lines)
            if value.startswith("추천 주입 기질")
        ),
        len(lines),
    )
    for rank_index, start in enumerate(rank_positions, 1):
        end = (
            rank_positions[rank_index]
            if rank_index < len(rank_positions)
            else recommendation_boundary
        )
        block = lines[start + 1 : end]
        cursor = 0
        for option in options[:-1]:
            if cursor + 1 >= len(block) or not SCALAR.fullmatch(block[cursor + 1]):
                raise RetrievalBuildError(
                    f"Broken weapon option scalar for {artifact['entityId']} rank {rank_index}"
                )
            option["ranks"].append(
                {
                    "rank": rank_index,
                    "rankLabel": f"RANK{rank_index}",
                    "metric": block[cursor],
                    **_parse_scalar(block[cursor + 1]),
                }
            )
            cursor += 2
        trait_text = _join_text(block[cursor:])
        if not trait_text:
            raise RetrievalBuildError(
                f"Missing weapon trait text for {artifact['entityId']} rank {rank_index}"
            )
        options[-1]["ranks"].append(
            {
                "rank": rank_index,
                "rankLabel": f"RANK{rank_index}",
                "effect": trait_text,
            }
        )
    if any(len(option["ranks"]) != 9 for option in options):
        raise RetrievalBuildError(f"Incomplete weapon option ranks: {artifact['entityId']}")
    return options, evidence


def _weapon_documents(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    identity = artifact["identity"]
    weapon_type = artifact["taxonomy"]["weaponType"]
    options, option_evidence = _parse_weapon_options(artifact)
    profile_evidence = [
        document["documentId"]
        for document in _source_documents(artifact)
        if document.get("section") == "profile"
    ]
    option_refs = [
        f"epwiki.{artifact['locale'].lower()}.weapon.{identity['gameEntryId']}.option-{option['slot']}"
        for option in options
    ]
    profile_facts: dict[str, Any] = {
        "name": identity["name"],
        "weaponType": weapon_type,
        "options": [
            {"slot": option["slot"], "name": option["name"], "documentRef": ref}
            for option, ref in zip(options, option_refs)
        ],
    }
    withheld: list[dict[str, str]] = []
    profile_sentences = [
        f"{identity['name']} 무기의 기본 정보.",
        f"무기 유형은 {weapon_type['label']}이다.",
        "옵션은 "
        + ", ".join(f"{option['slot']}번 {option['name']}" for option in options)
        + "이다.",
    ]
    if "rarity" in identity:
        profile_facts["rarity"] = identity["rarity"]
        profile_sentences.append(f"희귀도는 {identity['rarity']}성이다.")
    else:
        withheld.append(_withheld("facts.rarity", "원문 희귀도 이미지가 구조화되지 않음"))
    if identity.get("imageUrl"):
        profile_facts["imageUrl"] = identity["imageUrl"]
    else:
        withheld.append(_withheld("facts.imageUrl", "무기 이미지 URL이 구조화되지 않음"))
    documents = [
        _make_document(
            artifact,
            slug="profile",
            document_type="weapon_profile",
            title=f"{identity['name']} — 무기 기본 정보",
            content=" ".join(profile_sentences),
            facts=profile_facts,
            evidence_ids=profile_evidence,
            filters={"weaponTypeCode": weapon_type["code"]},
            withheld_fields=withheld,
        )
    ]

    progression_evidence = [
        document["documentId"]
        for document in _source_documents(artifact)
        if document.get("section") == "progression"
    ]
    progression_lines = [f"{identity['name']} 무기의 레벨별 기초 공격력."]
    progression_lines.extend(
        f"LV.{row['level']}: 기초 공격력 {row['baseAttack']}."
        for row in artifact["progression"]
    )
    documents.append(
        _make_document(
            artifact,
            slug="progression",
            document_type="weapon_progression",
            title=f"{identity['name']} — 기초 공격력",
            content="\n".join(progression_lines),
            facts={"levels": artifact["progression"]},
            evidence_ids=progression_evidence,
            withheld_fields=[
                _withheld(
                    "facts.materialCosts",
                    "돌파 재료 아이콘의 이름이 렌더링 텍스트에 없어 수량과 연결할 수 없음",
                )
            ],
        )
    )

    for option in options:
        content_lines = [
            f"{identity['name']} 무기의 {option['slot']}번 옵션 ‘{option['name']}’."
        ]
        for rank in option["ranks"]:
            if "effect" in rank:
                content_lines.append(f"{rank['rankLabel']}: {rank['effect']}")
            else:
                content_lines.append(
                    f"{rank['rankLabel']}: {rank['metric']} {rank['display']}."
                )
        documents.append(
            _make_document(
                artifact,
                slug=f"option-{option['slot']}",
                document_type="weapon_option",
                title=f"{identity['name']} — {option['slot']}번 옵션 {option['name']}",
                content="\n".join(content_lines),
                facts=option,
                evidence_ids=option_evidence,
                filters={"optionSlot": option["slot"]},
            )
        )

    potential_evidence = [
        document["documentId"]
        for document in _source_documents(artifact)
        if document.get("section") == "potential"
    ]
    trait = options[-1]
    potential_stages = [
        {
            "stage": stage,
            "baseRank": stage,
            "maxRank": stage + 3,
            "effectRef": f"{option_refs[-1]}#rank-{stage}",
        }
        for stage in range(1, 7)
    ]
    documents.append(
        _make_document(
            artifact,
            slug="potential",
            document_type="weapon_potential",
            title=f"{identity['name']} — 잠재능력",
            content=(
                f"{identity['name']} 무기의 잠재능력은 마지막 옵션 ‘{trait['name']}’의 "
                "기본/최대 RANK를 올린다. "
                + ", ".join(
                    f"잠재 {stage['stage']}는 RANK {stage['baseRank']}/{stage['maxRank']}"
                    for stage in potential_stages
                )
                + "."
            ),
            facts={"traitRef": option_refs[-1], "stages": potential_stages},
            evidence_ids=potential_evidence,
        )
    )
    return documents


def _gear_conflicted_slots(artifact: dict[str, Any]) -> set[int]:
    base = {option["slot"]: option for option in artifact["options"]}
    conflicted: set[int] = set()
    for forged in artifact.get("forging", {}).get("options", []):
        level_zero = next(
            (value for value in forged["values"] if value["forgeLevel"] == 0),
            None,
        )
        option = base.get(forged["slot"])
        if level_zero is None or option is None:
            continue
        if (
            level_zero["value"] != option["baseValue"]["value"]
            or level_zero["unit"] != option["baseValue"]["unit"]
        ):
            conflicted.add(forged["slot"])
    return conflicted


def _display_value(value: dict[str, Any]) -> str:
    suffix = "%" if value["unit"] == "percent" else ""
    return f"{value['value']}{suffix}"


def _gear_documents(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    identity = artifact["identity"]
    taxonomy = artifact["taxonomy"]
    set_entry = taxonomy["gearSet"]
    conflicted_slots = _gear_conflicted_slots(artifact)
    safe_options: list[dict[str, Any]] = []
    content_options: list[str] = []
    withheld: list[dict[str, str]] = []
    for option in artifact["options"]:
        value = copy.deepcopy(option)
        if option["slot"] in conflicted_slots:
            value.pop("baseValue", None)
            value["status"] = "source_conflict"
            content_options.append(
                f"{option['slot']}번 {option['name']}은 기본 표와 단조 표가 충돌해 수치 검색 제외"
            )
            withheld.append(
                _withheld(
                    f"facts.options[slot={option['slot']}].baseValue",
                    "장비 기본 옵션과 정밀 단조 +0 값이 충돌함",
                    "source_conflict",
                )
            )
        else:
            content_options.append(
                f"{option['slot']}번 {option['name']} {_display_value(option['baseValue'])}"
            )
        safe_options.append(value)
    set_effect_ref = (
        None
        if set_entry["code"] == "none"
        else (
            f"epwiki.{artifact['locale'].lower()}.gear-set.{set_entry['code']}.effect"
        ).replace("_", "-")
    )
    profile_facts = {
        "name": identity["name"],
        "gearType": taxonomy["gearType"],
        "quality": taxonomy["quality"],
        "gearSet": set_entry,
        "level": artifact["level"],
        "defense": artifact["defense"],
        "supportsForging": artifact["forging"]["supported"],
        "options": safe_options,
        "setEffectRef": set_effect_ref,
    }
    profile_evidence = [
        document["documentId"]
        for document in _source_documents(artifact)
        if document.get("section") == "profile"
    ]
    documents = [
        _make_document(
            artifact,
            slug="profile",
            document_type="gear_profile",
            title=f"{identity['name']} — 장비 기본 정보",
            content=(
                f"{identity['name']} 장비의 기본 정보. 유형은 {taxonomy['gearType']['label']}, "
                f"품질은 {taxonomy['quality']['label']}, 세트는 {set_entry['label']}이다. "
                f"LV.{artifact['level']}, 방어력 {artifact['defense']}. 옵션은 "
                + ", ".join(content_options)
                + ". "
                + (
                    "정밀 단조를 지원한다."
                    if artifact["forging"]["supported"]
                    else "정밀 단조 대상이 아니다."
                )
            ),
            facts=profile_facts,
            evidence_ids=profile_evidence,
            filters={
                "gearTypeCode": taxonomy["gearType"]["code"],
                "qualityCode": taxonomy["quality"]["code"],
                "gearSetCode": set_entry["code"],
            },
            withheld_fields=withheld,
        )
    ]
    if not artifact["forging"]["supported"]:
        return documents

    forging_options: list[dict[str, Any]] = []
    content_lines = [f"{identity['name']} 장비의 정밀 단조 +0부터 +3까지의 옵션 수치."]
    forging_withheld: list[dict[str, str]] = []
    for option in artifact["forging"]["options"]:
        if option["slot"] in conflicted_slots:
            forging_options.append(
                {"slot": option["slot"], "name": option["name"], "status": "source_conflict"}
            )
            content_lines.append(
                f"{option['slot']}번 {option['name']} 수치는 기본 표와 단조 표가 충돌해 검색 제외."
            )
            forging_withheld.append(
                _withheld(
                    f"facts.options[slot={option['slot']}].values",
                    "장비 기본 옵션과 정밀 단조 +0 값이 충돌함",
                    "source_conflict",
                )
            )
            continue
        forging_options.append(option)
        content_lines.append(
            f"{option['slot']}번 {option['name']}: "
            + ", ".join(
                f"+{value['forgeLevel']} {_display_value(value)}"
                for value in option["values"]
            )
            + "."
        )
    forging_evidence = [
        document["documentId"]
        for document in _source_documents(artifact)
        if document.get("section") == "gear_option"
    ]
    documents.append(
        _make_document(
            artifact,
            slug="forging",
            document_type="gear_forging",
            title=f"{identity['name']} — 정밀 단조",
            content="\n".join(content_lines),
            facts={"maxLevel": 3, "options": forging_options},
            evidence_ids=forging_evidence,
            filters={"supportsForging": True},
            withheld_fields=forging_withheld,
        )
    )
    return documents


def _clean_set_effect(artifact: dict[str, Any]) -> tuple[int, str, list[str]] | None:
    lines, evidence = _single_section(artifact, "gear_set_effect")
    marker = next(
        (
            (index, match)
            for index, value in enumerate(lines)
            if (match := PIECE_EFFECT.fullmatch(value))
        ),
        None,
    )
    if marker is None:
        if artifact["taxonomy"]["gearSet"]["code"] == "none":
            return None
        raise RetrievalBuildError(f"Missing set effect anchor: {artifact['entityId']}")
    index, match = marker
    effect = _join_text(lines[index + 1 :]).removeprefix(":").strip()
    if not effect:
        raise RetrievalBuildError(f"Empty set effect: {artifact['entityId']}")
    return int(match.group(1)), effect, evidence


def _set_effect_signature(effect: str) -> str:
    without_sentence_periods = re.sub(r"(?<!\d)\.|\.(?!\d)", "", effect)
    normalized_signs = re.sub(r"([+-])\s+(?=\d)", r"\1", without_sentence_periods)
    return re.sub(r"\s+", " ", normalized_signs).strip()


def _gear_set_documents(gear_artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in gear_artifacts:
        grouped[artifact["taxonomy"]["gearSet"]["code"]].append(artifact)
    documents: list[dict[str, Any]] = []
    for set_code, members in sorted(grouped.items()):
        if set_code == "none":
            continue
        signatures: Counter[tuple[int, str]] = Counter()
        display_candidates: Counter[str] = Counter()
        evidence: list[str] = []
        for member in members:
            parsed = _clean_set_effect(member)
            if parsed is None:
                continue
            required_pieces, effect, ids = parsed
            signatures[(required_pieces, _set_effect_signature(effect))] += 1
            display_candidates[effect] += 1
            evidence.extend(ids)
        if len(signatures) != 1:
            raise RetrievalBuildError(
                f"Conflicting set effects for {set_code}: {dict(signatures)}"
            )
        (required_pieces, _), count = signatures.most_common(1)[0]
        effect = display_candidates.most_common(1)[0][0]
        set_entry = members[0]["taxonomy"]["gearSet"]
        member_ids = sorted(member["identity"]["gameEntryId"] for member in members)
        combined_source_hash = hashlib.sha256(
            "".join(
                sorted(
                    member.get("source", {}).get("contentSha256") or ""
                    for member in members
                )
            ).encode("utf-8")
        ).hexdigest()
        set_artifact = {
            "entityType": "gear_set",
            "entityId": f"gear_set_{set_code}",
            "locale": members[0]["locale"],
            "identity": {"code": set_code, "name": set_entry["label"]},
            "source": {
                "url": members[0]["source"]["url"],
                "contentSha256": combined_source_hash,
            },
            "group": {"axis": "gearSet", **set_entry},
            "ragRef": None,
        }
        documents.append(
            _make_document(
                set_artifact,
                slug="effect",
                document_type="gear_set_effect",
                title=f"{set_entry['label']} — 장비 세트 효과",
                content=(
                    f"{set_entry['label']} 장비 세트의 {required_pieces}개 세트 효과. {effect}"
                ),
                facts={
                    "gearSet": set_entry,
                    "requiredPieces": required_pieces,
                    "effect": effect,
                    "memberGameEntryIds": member_ids,
                    "evidenceCopyCount": count,
                },
                evidence_ids=evidence,
                filters={"gearSetCode": set_code, "requiredPieces": required_pieces},
                authority=("cross_checked_extraction", "rule_validated", "high"),
            )
        )
    return documents


def _load_artifacts(
    locale: str, normalized_root: Path
) -> tuple[list[dict[str, Any]], Path, dict[str, Any]]:
    manifest_path = normalized_root / f"manifest.{locale}.json"
    if not manifest_path.exists():
        raise RetrievalBuildError(f"Normalized manifest does not exist: {manifest_path}")
    manifest = _read_json(manifest_path)
    artifacts: list[dict[str, Any]] = []
    for entity in manifest.get("entities", []):
        ref = entity.get("ragRef")
        if not ref:
            raise RetrievalBuildError(f"Normalized entity has no ragRef: {entity}")
        path = PROJECT_ROOT / ref
        if not path.exists():
            raise RetrievalBuildError(f"Normalized artifact does not exist: {path}")
        artifact = _read_json(path)
        if artifact.get("locale") != locale:
            raise RetrievalBuildError(f"Locale mismatch in {path}")
        artifacts.append(artifact)
    artifacts.sort(
        key=lambda artifact: (
            artifact["entityType"],
            artifact["identity"]["gameEntryId"],
        )
    )
    return artifacts, manifest_path, manifest


def _document_relative_path(document: dict[str, Any]) -> Path:
    entity_type = document["entity"]["type"].replace("_", "-")
    group_label = document.get("filters", {}).get("groupLabel") or "미확인"
    group = safe_path_segment(group_label, fallback="미확인")
    if document["entity"].get("gameEntryId") is not None:
        entity_folder = safe_entity_file_stem(
            document["entity"]["gameEntryId"], document["entity"]["name"]
        )
    else:
        entity_folder = safe_path_segment(document["entity"]["key"], fallback="gear-set")
    slug = document["semanticKey"].rsplit("|", 1)[-1]
    filename = safe_path_segment(slug, fallback="document") + ".json"
    return Path(entity_type) / group / entity_folder / filename


def _all_evidence_ids(artifacts: list[dict[str, Any]]) -> set[str]:
    return {
        document["documentId"]
        for artifact in artifacts
        for document in _source_documents(artifact)
    }


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _recursive_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _recursive_keys(child)}
    return set()


def _document_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith("Ref") and isinstance(child, str) and child.startswith("epwiki."):
                yield child
            yield from _document_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _document_refs(child)


def _semantic_errors(
    documents: list[dict[str, Any]], artifacts: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    by_type = Counter(document["documentType"] for document in documents)
    artifacts_by_type = Counter(artifact["entityType"] for artifact in artifacts)
    expected_fixed = {
        "operator_profile": artifacts_by_type["operator"],
        "operator_progression": artifacts_by_type["operator"],
        "operator_promotion": artifacts_by_type["operator"],
        "operator_combat_skill": artifacts_by_type["operator"] * 4,
        "operator_talent": artifacts_by_type["operator"] * 3,
        "operator_potential": artifacts_by_type["operator"] * 5,
        "weapon_profile": artifacts_by_type["weapon"],
        "weapon_progression": artifacts_by_type["weapon"],
        "weapon_potential": artifacts_by_type["weapon"],
        "gear_profile": artifacts_by_type["gear"],
    }
    for document_type, expected in expected_fixed.items():
        if by_type[document_type] != expected:
            errors.append(
                f"{document_type}: expected {expected}, got {by_type[document_type]}"
            )
    for document in documents:
        facts = document["facts"]
        kind = document["documentType"]
        if kind == "operator_progression":
            if [row["level"] for row in facts["levels"]] != list(LEVELS):
                errors.append(f"Invalid operator levels: {document['documentId']}")
            for withheld in document["coverage"]["withheldFields"]:
                match = re.search(r"stats\.([A-Za-z]+)$", withheld["path"])
                if match and any(match.group(1) in row["stats"] for row in facts["levels"]):
                    errors.append(f"Conflicted stat leaked: {document['documentId']}")
        elif kind == "operator_combat_skill":
            if facts["rankLabels"] != list(RANK_LABELS):
                errors.append(f"Invalid skill ranks: {document['documentId']}")
            if any(len(metric["values"]) != 12 for metric in facts["metrics"]):
                errors.append(f"Invalid skill metric width: {document['documentId']}")
            if len(facts["materialCosts"]) != 12:
                errors.append(f"Invalid skill material rows: {document['documentId']}")
        elif kind == "weapon_progression":
            if [row["level"] for row in facts["levels"]] != list(LEVELS):
                errors.append(f"Invalid weapon levels: {document['documentId']}")
        elif kind == "weapon_option":
            if [row["rank"] for row in facts["ranks"]] != list(range(1, 10)):
                errors.append(f"Invalid weapon option ranks: {document['documentId']}")
        elif kind == "weapon_potential":
            expected = [(stage, stage + 3) for stage in range(1, 7)]
            observed = [(row["baseRank"], row["maxRank"]) for row in facts["stages"]]
            if observed != expected:
                errors.append(f"Invalid weapon potential ranks: {document['documentId']}")
        elif kind == "gear_profile":
            slots = tuple(option["slot"] for option in facts["options"])
            if slots not in {(1, 2, 3), (1, 3), (1,)}:
                errors.append(f"Invalid gear slots {slots}: {document['documentId']}")
        elif kind == "gear_forging":
            for option in facts["options"]:
                if option.get("status") == "source_conflict":
                    if "values" in option:
                        errors.append(f"Conflicted forging values leaked: {document['documentId']}")
                    continue
                if [row["forgeLevel"] for row in option["values"]] != [0, 1, 2, 3]:
                    errors.append(f"Invalid forging levels: {document['documentId']}")
    return errors


def _quality_report(
    documents: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    schema: dict[str, Any],
) -> dict[str, Any]:
    validator = Draft202012Validator(schema)
    schema_errors: list[dict[str, str]] = []
    for document in documents:
        for error in validator.iter_errors(document):
            schema_errors.append(
                {"documentId": document.get("documentId", ""), "message": error.message}
            )
    ids = [document["documentId"] for document in documents]
    semantic_keys = [document["semanticKey"] for document in documents]
    content_hashes = [document["indexing"]["contentSha256"] for document in documents]
    evidence_ids = _all_evidence_ids(artifacts)
    missing_evidence = [
        {"documentId": document["documentId"], "evidenceId": evidence_id}
        for document in documents
        for evidence_id in document["provenance"]["evidenceDocumentIds"]
        if evidence_id not in evidence_ids
    ]
    document_id_set = set(ids)
    dangling_refs = [
        {"documentId": document["documentId"], "ref": ref}
        for document in documents
        for ref in _document_refs(document["facts"])
        if ref.split("#", 1)[0] not in document_id_set
    ]
    forbidden_fields = []
    for document in documents:
        keys = _recursive_keys(document)
        found = sorted(keys.intersection({"rawRef", "extractionMode", "contentStatus"}))
        if found:
            forbidden_fields.append({"documentId": document["documentId"], "fields": found})
    ui_residue = []
    context_errors = []
    for document in documents:
        content = document["content"]
        found = [token for token in UI_RESIDUES if token in content]
        if re.search(r"(?m)^\s*\*\s*$", content):
            found.append("standalone_asterisk")
        if re.search(r"(을|를)(줍니다|받습니다)|수있습니다", content):
            found.append("joined_particle_verb")
        if ".." in content:
            found.append("double_period")
        if found:
            ui_residue.append({"documentId": document["documentId"], "tokens": found})
        if document["entity"]["name"] not in content[:200]:
            context_errors.append(document["documentId"])
        if re.match(r"^[+*%\d]", content):
            context_errors.append(document["documentId"])
    semantic_errors = _semantic_errors(documents, artifacts)
    checks = {
        "schema": {"passed": not schema_errors, "errors": schema_errors},
        "uniqueDocumentIds": {
            "passed": len(ids) == len(set(ids)),
            "duplicates": sorted(key for key, count in Counter(ids).items() if count > 1),
        },
        "uniqueSemanticKeys": {
            "passed": len(semantic_keys) == len(set(semantic_keys)),
            "duplicates": sorted(
                key for key, count in Counter(semantic_keys).items() if count > 1
            ),
        },
        "uniqueContentHashes": {
            "passed": len(content_hashes) == len(set(content_hashes)),
            "duplicates": sorted(
                key for key, count in Counter(content_hashes).items() if count > 1
            ),
        },
        "evidenceCoverage": {"passed": not missing_evidence, "missing": missing_evidence},
        "documentReferences": {"passed": not dangling_refs, "dangling": dangling_refs},
        "forbiddenSourceFields": {
            "passed": not forbidden_fields,
            "documents": forbidden_fields,
        },
        "uiResidue": {"passed": not ui_residue, "documents": ui_residue},
        "contextAnchors": {"passed": not context_errors, "documents": context_errors},
        "semanticInvariants": {"passed": not semantic_errors, "errors": semantic_errors},
    }
    indexable = all(check["passed"] for check in checks.values())
    source_hash_algorithms = Counter(
        artifact.get("source", {}).get("contentHashAlgorithm") or "unknown"
        for artifact in artifacts
    )
    source_conflicts = sum(
        withheld["status"] == "source_conflict"
        for document in documents
        for withheld in document["coverage"]["withheldFields"]
    )
    source_absent = [
        {
            "entityType": artifact["entityType"],
            "gameEntryId": artifact["identity"]["gameEntryId"],
            "name": artifact["identity"]["name"],
            "field": "infrastructureTalents",
        }
        for artifact in artifacts
        if artifact["entityType"] == "operator"
        and not _section_groups(artifact, "infrastructure_talent")
    ]
    return {
        "schemaVersion": "1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "grain": "one JSON file per semantic retrieval document",
            "entities": len(artifacts),
            "documents": len(documents),
            "byEntityType": dict(sorted(Counter(a["entityType"] for a in artifacts).items())),
            "byDocumentType": dict(
                sorted(Counter(d["documentType"] for d in documents).items())
            ),
        },
        "checks": checks,
        "coverage": {
            "complete": False,
            "refreshStatus": (
                "verified"
                if source_hash_algorithms == {"rendered_chapters_v1": len(artifacts)}
                else "provisional_legacy_source_hashes"
            ),
            "sourceHashAlgorithms": dict(sorted(source_hash_algorithms.items())),
            "withheldSourceConflicts": source_conflicts,
            "sourceAbsent": source_absent,
            "unmappedMaterials": sorted(
                {
                    item["name"]
                    for document in documents
                    for item in _walk_materials(document["facts"])
                    if item.get("catalogStatus") == "unmapped"
                }
            ),
        },
        "verdict": "indexable" if indexable else "blocked",
    }


def _walk_materials(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if {"name", "amount", "catalogStatus"}.issubset(value):
            yield value
        for child in value.values():
            yield from _walk_materials(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_materials(child)


def _manifest(
    *,
    locale: str,
    documents: list[dict[str, Any]],
    records: list[dict[str, Any]],
    quality: dict[str, Any],
    normalized_manifest_path: Path,
    retrieval_root: Path,
    release_id: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0.0",
        "datasetId": "epwiki-retrieval",
        "releaseId": release_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "locale": locale,
        "intendedUse": "llm_retrieval",
        "source": {
            "normalizedManifestRef": _project_ref(normalized_manifest_path),
            "normalizedManifestSha256": _sha256_text(
                normalized_manifest_path.read_text(encoding="utf-8")
            ),
        },
        "ingestion": {
            "manifestIsSoleEntryPoint": True,
            "documentsRoot": _project_ref(retrieval_root / locale / release_id),
            "namespace": f"epwiki:{locale}:retrieval-v1",
            "mode": "synchronize",
            "deleteMissing": True,
            "forbiddenRoots": [
                "data/rag/normalized",
                "data/rag/published",
            ],
        },
        "quality": {
            "indexable": quality["verdict"] == "indexable",
            "coverageComplete": quality["coverage"]["complete"],
            "refreshStatus": quality["coverage"]["refreshStatus"],
            "qualityReportRef": _project_ref(
                retrieval_root / f"quality-report.{locale}.json"
            ),
        },
        "stats": {
            "documents": len(documents),
            "byDocumentType": quality["dataset"]["byDocumentType"],
        },
        "documents": sorted(records, key=lambda item: item["documentId"]),
    }


def _build_documents(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    gear_artifacts: list[dict[str, Any]] = []
    for artifact in artifacts:
        domain = artifact["entityType"]
        if domain == "operator":
            documents.extend(_operator_documents(artifact))
        elif domain == "weapon":
            documents.extend(_weapon_documents(artifact))
        elif domain == "gear":
            gear_artifacts.append(artifact)
            documents.extend(_gear_documents(artifact))
        else:
            raise RetrievalBuildError(f"Unsupported normalized domain: {domain}")
    documents.extend(_gear_set_documents(gear_artifacts))
    return documents


def _release_id(documents: list[dict[str, Any]]) -> str:
    release_source = "\n".join(
        f"{document['documentId']}:{document['indexing']['payloadSha256']}"
        for document in sorted(documents, key=lambda item: item["documentId"])
    )
    return hashlib.sha256(release_source.encode("utf-8")).hexdigest()


def _link_published_manifest(
    locale: str, manifest: dict[str, Any], quality: dict[str, Any]
) -> None:
    path = PROJECT_ROOT / "data" / "rag" / "published" / "manifest.json"
    if not path.exists():
        return
    payload = _read_json(path)
    changed = False
    for snapshot in payload.get("snapshots", []):
        if snapshot.get("locale") != locale:
            continue
        snapshot.update(
            {
                "retrievalManifestRef": _project_ref(
                    RETRIEVAL_RAG_ROOT / f"manifest.{locale}.json"
                ),
                "retrievalReleaseId": manifest["releaseId"],
                "retrievalDocuments": manifest["stats"]["documents"],
                "retrievalVerdict": quality["verdict"],
            }
        )
        changed = True
    if changed:
        payload["generatedAt"] = datetime.now(timezone.utc).isoformat()
        write_json_atomic(path, payload)


def build_retrieval_corpus(
    locale: str = "ko-KR",
    *,
    normalized_root: Path = NORMALIZED_RAG_ROOT,
    retrieval_root: Path = RETRIEVAL_RAG_ROOT,
    strict: bool = True,
) -> dict[str, Any]:
    """Build, strictly validate, and atomically promote the retrieval-only corpus."""

    artifacts, normalized_manifest_path, _ = _load_artifacts(locale, normalized_root)
    documents = _build_documents(artifacts)
    document_schema = _read_json(RETRIEVAL_DOCUMENT_SCHEMA)
    quality = _quality_report(documents, artifacts, document_schema)
    if strict and quality["verdict"] != "indexable":
        raise RetrievalBuildError(
            "Retrieval quality gates failed: "
            + "; ".join(
                name
                for name, check in quality["checks"].items()
                if not check["passed"]
            )
        )

    release_id = _release_id(documents)
    records: list[dict[str, Any]] = []
    relative_paths: dict[str, Path] = {}
    for document in documents:
        relative = _document_relative_path(document)
        if relative in relative_paths.values():
            raise RetrievalBuildError(f"Retrieval path collision: {relative}")
        relative_paths[document["documentId"]] = relative
        records.append(
            {
                "documentId": document["documentId"],
                "semanticKey": document["semanticKey"],
                "documentType": document["documentType"],
                "entity": document["entity"],
                "ref": _project_ref(retrieval_root / locale / release_id / relative),
                "contentSha256": document["indexing"]["contentSha256"],
                "payloadSha256": document["indexing"]["payloadSha256"],
            }
        )
    manifest = _manifest(
        locale=locale,
        documents=documents,
        records=records,
        quality=quality,
        normalized_manifest_path=normalized_manifest_path,
        retrieval_root=retrieval_root,
        release_id=release_id,
    )
    manifest_errors = list(
        Draft202012Validator(_read_json(RETRIEVAL_MANIFEST_SCHEMA)).iter_errors(manifest)
    )
    if manifest_errors:
        raise RetrievalBuildError(
            "Retrieval manifest schema failed: "
            + "; ".join(error.message for error in manifest_errors)
        )

    release_target = retrieval_root / locale / release_id
    retrieval_root.mkdir(parents=True, exist_ok=True)
    if release_target.exists():
        shutil.rmtree(release_target)
    try:
        document_index = {document["documentId"]: document for document in documents}
        for document_id, relative in relative_paths.items():
            write_json_atomic(release_target / relative, document_index[document_id])
        write_json_atomic(retrieval_root / f"manifest.{locale}.json", manifest)
        write_json_atomic(retrieval_root / f"quality-report.{locale}.json", quality)
    except Exception:
        if release_target.exists():
            shutil.rmtree(release_target)
        raise
    for sibling in (retrieval_root / locale).iterdir():
        if sibling.is_dir() and sibling.name != release_id:
            shutil.rmtree(sibling)
    if retrieval_root.resolve() == RETRIEVAL_RAG_ROOT.resolve():
        _link_published_manifest(locale, manifest, quality)

    return {
        "locale": locale,
        "manifest": manifest,
        "quality": quality,
        "manifestRef": _project_ref(retrieval_root / f"manifest.{locale}.json"),
        "qualityReportRef": _project_ref(
            retrieval_root / f"quality-report.{locale}.json"
        ),
    }


def _resolve_ref(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else PROJECT_ROOT / path


def validate_retrieval_corpus(
    locale: str = "ko-KR",
    *,
    retrieval_root: Path = RETRIEVAL_RAG_ROOT,
) -> dict[str, Any]:
    """Validate an already promoted corpus and its stable release hashes."""

    manifest_path = retrieval_root / f"manifest.{locale}.json"
    manifest = _read_json(manifest_path)
    manifest_errors = list(
        Draft202012Validator(_read_json(RETRIEVAL_MANIFEST_SCHEMA)).iter_errors(manifest)
    )
    document_validator = Draft202012Validator(_read_json(RETRIEVAL_DOCUMENT_SCHEMA))
    errors = [f"manifest: {error.message}" for error in manifest_errors]
    release_rows: list[str] = []
    seen_ids: set[str] = set()
    locale_root = (retrieval_root / locale).resolve()
    for record in manifest.get("documents", []):
        path = _resolve_ref(record["ref"]).resolve()
        try:
            path.relative_to(locale_root)
        except ValueError:
            errors.append(f"outside retrieval root: {path}")
            continue
        if not path.exists():
            errors.append(f"missing document: {path}")
            continue
        document = _read_json(path)
        for error in document_validator.iter_errors(document):
            errors.append(f"{record['documentId']}: {error.message}")
        if document["documentId"] != record["documentId"]:
            errors.append(f"document ID mismatch: {path}")
        if record["documentId"] in seen_ids:
            errors.append(f"duplicate manifest ID: {record['documentId']}")
        seen_ids.add(record["documentId"])
        if _sha256_text(document["content"]) != record["contentSha256"]:
            errors.append(f"content hash mismatch: {record['documentId']}")
        if _payload_sha256(document) != record["payloadSha256"]:
            errors.append(f"payload hash mismatch: {record['documentId']}")
        release_rows.append(f"{record['documentId']}:{record['payloadSha256']}")
    release_id = hashlib.sha256("\n".join(sorted(release_rows)).encode("utf-8")).hexdigest()
    if release_id != manifest.get("releaseId"):
        errors.append("releaseId mismatch")
    return {
        "schemaVersion": "1.0.0",
        "locale": locale,
        "manifestRef": _project_ref(manifest_path),
        "documents": len(release_rows),
        "releaseId": release_id,
        "errors": errors,
        "verdict": "indexable" if not errors else "blocked",
    }
