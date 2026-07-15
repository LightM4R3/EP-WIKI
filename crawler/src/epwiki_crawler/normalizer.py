from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from epwiki_crawler.config import PROJECT_ROOT
from epwiki_crawler.core.naming import safe_entity_file_stem, safe_path_segment
from epwiki_crawler.core.storage import write_json_atomic


NORMALIZED_RAG_ROOT = PROJECT_ROOT / "data" / "rag" / "normalized"
PUBLISHED_RAG_ROOT = PROJECT_ROOT / "data" / "rag" / "published"
LEVELS = (1, 20, 40, 60, 80, 90)
ATTRIBUTE_LABELS = ("힘", "민첩", "지능", "의지")
ATTRIBUTE_CODES = {
    "힘": (0, "strength"),
    "민첩": (1, "agility"),
    "지능": (2, "intellect"),
    "의지": (3, "will"),
}
GEAR_TYPE_CODES = {
    "글러브": (0, "gloves"),
    "방어구": (1, "armor"),
    "부품": (2, "component"),
}
GEAR_QUALITY_CODES = {
    "노란색 품질": (0, "yellow"),
    "보라색 품질": (1, "purple"),
    "파란색 품질": (2, "blue"),
    "초록색 품질": (3, "green"),
    "회색 품질": (4, "gray"),
}
RANK_LABEL = re.compile(r"^RANK\s*(\d+)$")
MASTERY_LABEL = re.compile(r"^마스터리\s*([IVX]+)$")
NUMBER_LABEL = re.compile(r"^([+-]?\d+(?:\.\d+)?)(%)?$")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _project_ref(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _source_documents(entity: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(document)
        for document in entity["documents"]
        if document.get("metadata", {}).get("normalizationMethod")
        != "rendered_label_v1"
    ]


@lru_cache(maxsize=1)
def _entity_overrides() -> dict[tuple[str, int], dict[str, Any]]:
    payload = _read_json(PROJECT_ROOT / "data" / "catalog" / "entity-overrides.json")
    return {
        (entry["entityType"], int(entry["gameEntryId"])): entry
        for entry in payload["entities"]
    }


def _entity_override(entity: dict[str, Any]) -> dict[str, Any] | None:
    return _entity_overrides().get((entity["domain"], entity["gameEntryId"]))


def _is_excluded_entity(entity: dict[str, Any]) -> bool:
    override = _entity_override(entity)
    return bool(override and override.get("exclude"))


def _lines(document: dict[str, Any]) -> list[str]:
    return [line.strip() for line in document["content"].splitlines() if line.strip()]


def _documents_for(
    documents: list[dict[str, Any]], section: str
) -> list[dict[str, Any]]:
    return [document for document in documents if document["section"] == section]


def _value_after_label(
    documents: list[dict[str, Any]], section: str, label: str
) -> str | None:
    for document in _documents_for(documents, section):
        lines = _lines(document)
        for index, value in enumerate(lines[:-1]):
            if value == label:
                return lines[index + 1]
    return None


def _parse_number(value: str) -> dict[str, Any] | None:
    normalized = value.replace(",", "").strip()
    match = NUMBER_LABEL.fullmatch(normalized)
    if match is None:
        return None
    number = float(match.group(1))
    parsed: int | float = int(number) if number.is_integer() else number
    return {"value": parsed, "unit": "percent" if match.group(2) else "flat"}


def _parse_integer(value: str) -> int | None:
    parsed = _parse_number(value)
    if parsed is None or parsed["unit"] != "flat":
        return None
    number = parsed["value"]
    return number if isinstance(number, int) else None


@lru_cache(maxsize=None)
def _catalog_entries(filename: str) -> dict[str, dict[str, Any]]:
    path = PROJECT_ROOT / "data" / "catalog" / filename
    payload = _read_json(path)
    result: dict[str, dict[str, Any]] = {}
    for entry in payload["entries"]:
        label = entry.get("labels", {}).get("ko-KR")
        if label:
            result[label] = {
                "id": entry["id"],
                "code": entry["code"],
                "label": label,
            }
    return result


def _stable_taxonomy(
    namespace: str,
    label: str,
    *,
    known: dict[str, dict[str, Any]] | None = None,
    manual: dict[str, tuple[int, str]] | None = None,
) -> dict[str, Any]:
    if known and label in known:
        return dict(known[label])
    if manual and label in manual:
        identifier, code = manual[label]
        return {"id": identifier, "code": code, "label": label}
    if namespace == "gear_set" and label == "세트 없음":
        return {"id": -1, "code": "none", "label": label}
    digest = hashlib.sha256(f"{namespace}:{label}".encode("utf-8")).hexdigest()
    return {
        "id": 100_000 + int(digest[:8], 16),
        "code": f"{namespace}_{digest[:12]}",
        "label": label,
    }


def _element(label: str) -> dict[str, Any]:
    return _stable_taxonomy(
        "element", label, known=_catalog_entries("elements.json")
    )


def _weapon_type(label: str) -> dict[str, Any]:
    return _stable_taxonomy(
        "weapon_type", label, known=_catalog_entries("weapon-types.json")
    )


def _gear_set(label: str) -> dict[str, Any]:
    return _stable_taxonomy(
        "gear_set", label, known=_catalog_entries("gear-sets.json")
    )


def _gear_type(label: str) -> dict[str, Any]:
    return _stable_taxonomy("gear_type", label, manual=GEAR_TYPE_CODES)


def _gear_quality(label: str) -> dict[str, Any]:
    return _stable_taxonomy("gear_quality", label, manual=GEAR_QUALITY_CODES)


def _attribute(label: str) -> dict[str, Any]:
    identifier, code = ATTRIBUTE_CODES[label]
    return {"id": identifier, "code": code, "label": label}


@lru_cache(maxsize=1)
def _canonical_index() -> dict[tuple[str, int], tuple[dict[str, Any], str]]:
    index: dict[tuple[str, int], tuple[dict[str, Any], str]] = {}
    root = PROJECT_ROOT / "data" / "canonical"
    for path in root.rglob("*.json"):
        payload = _read_json(path)
        domain = payload.get("entityType")
        if domain not in {"operator", "weapon", "gear"}:
            continue
        source = payload.get("source", {})
        game_entry_id = source.get("gameEntryId")
        if game_entry_id is None and source.get("url"):
            values = parse_qs(urlsplit(source["url"]).query).get("gameEntryId")
            if values:
                game_entry_id = int(values[0])
        if game_entry_id is None and source.get("entityId"):
            tail = str(source["entityId"]).rsplit(":", 1)[-1]
            if tail.isdigit():
                game_entry_id = int(tail)
        if game_entry_id is not None:
            index[(domain, int(game_entry_id))] = (
                payload,
                _project_ref(path),
            )
    return index


def _canonical_overlay(
    domain: str, game_entry_id: int
) -> tuple[dict[str, Any] | None, str | None]:
    value = _canonical_index().get((domain, game_entry_id))
    return value if value else (None, None)


def _operator_progression(
    documents: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
    list[dict[str, Any]],
]:
    candidates = [
        document
        for document in _documents_for(documents, "progression")
        if "\n업그레이드\n" in document["content"]
        and "\nLV.90\n" in document["content"]
    ]
    if not candidates:
        return [], None, None, []
    lines = _lines(candidates[0])
    rows: dict[str, list[int]] = {}
    primary: dict[str, Any] | None = None
    secondary: dict[str, Any] | None = None
    conflicts: list[dict[str, Any]] = []

    def reconcile(
        label: str, header: list[int], detail: list[int]
    ) -> list[int]:
        if len(detail) != len(LEVELS) or detail == header:
            return header
        if label == "기초 생명력":
            reference = [500, 1566, 2689, 3811, 4934, 5495]
            if header == reference or detail == reference:
                selected = header if header == reference else detail
                conflicts.append(
                    {
                        "field": label,
                        "headerValues": header,
                        "detailValues": detail,
                        "selectedValues": selected,
                        "resolution": "dataset_consensus_reference_selected",
                        "evidenceDocumentId": candidates[0]["documentId"],
                    }
                )
                return selected
        header_increases = all(
            current < following for current, following in zip(header, header[1:])
        )
        detail_increases = all(
            current < following for current, following in zip(detail, detail[1:])
        )
        if detail_increases and not header_increases:
            selected = detail
            resolution = "detail_table_selected_non_monotonic_header"
        elif header_increases and not detail_increases:
            selected = header
            resolution = "header_table_selected_non_monotonic_detail"
        else:
            selected = detail
            resolution = "detail_table_preferred_ambiguous_conflict"
        conflicts.append(
            {
                "field": label,
                "headerValues": header,
                "detailValues": detail,
                "selectedValues": selected,
                "resolution": resolution,
                "evidenceDocumentId": candidates[0]["documentId"],
            }
        )
        return selected

    for label in ATTRIBUTE_LABELS:
        pattern = re.compile(
            rf"^{re.escape(label)}(?: \((주요|보조) 능력치\))?$"
        )
        header: list[int] = []
        detail: list[int] = []
        role: str | None = None
        for index, line in enumerate(lines):
            match = pattern.fullmatch(line)
            if match is None:
                continue
            current_role = match.group(1)
            value_start = index + 1
            if (
                current_role is None
                and value_start < len(lines)
                and lines[value_start] in {"(주요 능력치)", "(보조 능력치)"}
            ):
                current_role = (
                    "주요" if lines[value_start] == "(주요 능력치)" else "보조"
                )
                value_start += 1
            role = role or current_role
            values = [
                _parse_integer(value)
                for value in lines[value_start : value_start + 6]
            ]
            if not header and len(values) == 6 and all(value is not None for value in values):
                header = [int(value) for value in values]
                continue
            value = _parse_integer(lines[value_start])
            if value is not None:
                detail.append(value)
        if header:
            rows[ATTRIBUTE_CODES[label][1]] = reconcile(label, header, detail[:6])
            if role == "주요":
                primary = _attribute(label)
            elif role == "보조":
                secondary = _attribute(label)
    for label, code in (
        ("기초 공격력", "baseAttack"),
        ("기초 생명력", "baseHp"),
    ):
        header: list[int] = []
        detail: list[int] = []
        for index, line in enumerate(lines):
            if line != label:
                continue
            values = [_parse_integer(value) for value in lines[index + 1 : index + 7]]
            if not header and len(values) == 6 and all(value is not None for value in values):
                header = [int(value) for value in values]
                continue
            value = _parse_integer(lines[index + 1])
            if value is not None:
                detail.append(value)
        if header:
            rows[code] = reconcile(label, header, detail[:6])
    required_rows = {
        "strength",
        "agility",
        "intellect",
        "will",
        "baseAttack",
        "baseHp",
    }
    if set(rows) != required_rows:
        return [], primary, secondary, conflicts
    progression = [
        {
            "level": level,
            "stats": {code: values[index] for code, values in rows.items()},
        }
        for index, level in enumerate(LEVELS)
    ]
    return progression, primary, secondary, conflicts


def _rank_labels(document: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for line in _lines(document):
        if RANK_LABEL.fullmatch(line) or MASTERY_LABEL.fullmatch(line):
            labels.append(line.replace(" ", ""))
    return labels


def _operator_skill_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    combat = _documents_for(documents, "combat_skill")
    return {
        "combatSkills": [
            {
                "documentId": document["documentId"],
                "rankLabels": _rank_labels(document),
            }
            for document in combat
        ],
        "operatorTalents": [
            document["documentId"]
            for document in _documents_for(documents, "operator_talent")
        ],
        "infrastructureTalents": [
            document["documentId"]
            for document in _documents_for(documents, "infrastructure_talent")
        ],
        "potentials": [
            document["documentId"]
            for document in _documents_for(documents, "potential")
        ],
    }


def _weapon_progression(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = _documents_for(documents, "progression")
    if not candidates:
        return []
    lines = _lines(candidates[0])
    values: list[int] = []
    for index, line in enumerate(lines[:-1]):
        if line != "기초 공격력":
            continue
        value = _parse_integer(lines[index + 1])
        if value is not None:
            values.append(value)
    if len(values) < len(LEVELS):
        return []
    return [
        {"level": level, "baseAttack": values[index]}
        for index, level in enumerate(LEVELS)
    ]


def _weapon_options(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = _documents_for(documents, "weapon_option")
    if not candidates:
        return []
    lines = _lines(candidates[0])
    try:
        start = lines.index("스킬 상세 및 기질") + 1
        end = next(
            index
            for index in range(start, len(lines))
            if RANK_LABEL.fullmatch(lines[index])
        )
    except (ValueError, StopIteration):
        return []
    names: list[str] = []
    for line in lines[start:end]:
        if line.startswith("·") and names:
            names[-1] = f"{names[-1]} {line}"
        else:
            names.append(line)
    rank_labels = _rank_labels(candidates[0])
    return [
        {
            "slot": index + 1,
            "name": name,
            "rankLabels": rank_labels,
            "evidenceDocumentId": candidates[0]["documentId"],
        }
        for index, name in enumerate(names)
    ]


def _gear_base_stats(documents: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        document
        for document in _documents_for(documents, "profile")
        if "\n장비 정보\n" in document["content"]
        and "\n속성\n" in document["content"]
    ]
    if not candidates:
        return {"level": None, "defense": None, "options": []}
    lines = _lines(candidates[0])
    try:
        start = lines.index("속성") + 1
    except ValueError:
        return {"level": None, "defense": None, "options": []}
    level: int | None = None
    defense: int | None = None
    options: list[dict[str, Any]] = []
    index = start
    while index < len(lines) - 1:
        label = lines[index]
        parsed = _parse_number(lines[index + 1])
        if label == "LV" and parsed and parsed["unit"] == "flat":
            level = int(parsed["value"])
            index += 2
            continue
        if label == "방어력" and parsed and parsed["unit"] == "flat":
            defense = int(parsed["value"])
            index += 2
            continue
        if parsed is not None:
            option: dict[str, Any] = {
                "slot": len(options) + 1,
                "name": label,
                "baseValue": parsed,
            }
            if label in ATTRIBUTE_CODES:
                option["attribute"] = _attribute(label)
            options.append(option)
            index += 2
            continue
        index += 1
    if (
        len(options) == 2
        and "attribute" in options[0]
        and "attribute" not in options[1]
    ):
        options[1]["slot"] = 3
    return {
        "level": level,
        "defense": defense,
        "options": options,
        "evidenceDocumentId": candidates[0]["documentId"],
    }


def _gear_forging(
    documents: list[dict[str, Any]], options: list[dict[str, Any]]
) -> dict[str, Any]:
    candidates = _documents_for(documents, "gear_option")
    if not candidates:
        return {"supported": False, "levels": []}
    lines = _lines(candidates[0])
    try:
        start = lines.index("정밀 단조 단계")
    except ValueError:
        start = 0
    rows: list[dict[str, Any]] = []
    for option in options:
        try:
            option_index = lines.index(option["name"], start)
        except ValueError:
            continue
        values = [
            _parse_number(value)
            for value in lines[option_index + 1 : option_index + 5]
        ]
        if len(values) == 4 and all(value is not None for value in values):
            rows.append(
                {
                    "slot": option["slot"],
                    "name": option["name"],
                    "values": [
                        {"forgeLevel": level, **value}
                        for level, value in enumerate(values)
                        if value is not None
                    ],
                }
            )
    return {
        "supported": True,
        "maxLevel": 3,
        "options": rows,
        "evidenceDocumentId": candidates[0]["documentId"],
    }


def _base_artifact(entity: dict[str, Any]) -> dict[str, Any]:
    documents = _source_documents(entity)
    override = _entity_override(entity)
    identity_override = override.get("identity", {}) if override else {}
    source_name = entity.get("sourceName", entity["name"])
    identity = {
        "gameEntryId": entity["gameEntryId"],
        "name": identity_override.get("name", entity["name"]),
    }
    if identity["name"] != source_name:
        identity["sourceName"] = source_name
    for key in ("canonicalCode", "aliases"):
        if key in identity_override:
            identity[key] = copy.deepcopy(identity_override[key])
    artifact = {
        "schemaVersion": "2.0.0",
        "entityType": entity["domain"],
        "entityId": entity["entityId"],
        "locale": entity["locale"],
        "identity": identity,
        "source": {
            "provider": "wiki.skport.com",
            "url": entity["sourceUrl"],
            "runId": entity.get("sourceRunId"),
            "contentSha256": entity.get("contentSha256"),
            "contentHashAlgorithm": entity.get("contentHashAlgorithm"),
        },
        "documents": documents,
    }
    if override:
        artifact["normalizationOverride"] = {
            "ref": "data/catalog/entity-overrides.json",
            "reason": override["reason"],
        }
    return artifact


def _normalize_operator(entity: dict[str, Any]) -> dict[str, Any]:
    artifact = _base_artifact(entity)
    documents = artifact["documents"]
    element_label = _value_after_label(documents, "profile", "속성")
    weapon_label = _value_after_label(documents, "profile", "무기 유형")
    progression, primary, secondary, conflicts = _operator_progression(documents)
    canonical, canonical_ref = _canonical_overlay(
        "operator", entity["gameEntryId"]
    )
    taxonomy: dict[str, Any] = {}
    if element_label:
        taxonomy["element"] = _element(element_label)
    if weapon_label:
        taxonomy["weaponType"] = _weapon_type(weapon_label)
    if canonical:
        identity = canonical.get("identity", {})
        if identity.get("rarity") is not None:
            artifact["identity"]["rarity"] = identity["rarity"]
        if identity.get("portraitUrl"):
            artifact["identity"]["portraitUrl"] = identity["portraitUrl"]
        if canonical.get("taxonomy", {}).get("class"):
            taxonomy["class"] = canonical["taxonomy"]["class"]
        artifact["canonicalRef"] = canonical_ref
    required = {
        "taxonomy.element": element_label is not None,
        "taxonomy.weaponType": weapon_label is not None,
        "attributes.primary": primary is not None,
        "attributes.secondary": secondary is not None,
        "progression": len(progression) == len(LEVELS),
    }
    unresolved = [key for key, passed in required.items() if not passed]
    for key, present in (
        ("identity.rarity", "rarity" in artifact["identity"]),
        ("identity.portraitUrl", "portraitUrl" in artifact["identity"]),
        ("taxonomy.class", "class" in taxonomy),
        ("progression.materialCosts", False),
        ("skills.structuredValues", False),
    ):
        if not present:
            unresolved.append(key)
    if conflicts:
        unresolved.append("progression.sourceConflicts")
    artifact["taxonomy"] = taxonomy
    artifact["attributes"] = {
        "catalogOrder": [0, 1, 2, 3],
        "primary": primary,
        "secondary": secondary,
    }
    artifact["progression"] = progression
    artifact["progressionSourceConflicts"] = conflicts
    artifact["skills"] = _operator_skill_index(documents)
    artifact["group"] = {
        "axis": "element",
        **(taxonomy.get("element") or {"id": None, "code": "unknown", "label": "미확인"}),
    }
    artifact["quality"] = {
        "status": "query_ready" if all(required.values()) else "incomplete",
        "queryReady": all(required.values()),
        "canonicalComplete": not unresolved,
        "requiredChecks": required,
        "unresolvedFields": sorted(set(unresolved)),
        "sourceConflicts": conflicts,
    }
    return artifact


def _normalize_weapon(entity: dict[str, Any]) -> dict[str, Any]:
    artifact = _base_artifact(entity)
    documents = artifact["documents"]
    weapon_label = _value_after_label(documents, "profile", "유형")
    progression = _weapon_progression(documents)
    options = _weapon_options(documents)
    canonical, canonical_ref = _canonical_overlay("weapon", entity["gameEntryId"])
    taxonomy: dict[str, Any] = {}
    if weapon_label:
        taxonomy["weaponType"] = _weapon_type(weapon_label)
    override = _entity_override(entity)
    override_weapon_label = (
        override.get("taxonomy", {}).get("weaponTypeLabel") if override else None
    )
    if override_weapon_label:
        taxonomy["weaponType"] = _weapon_type(override_weapon_label)
    if canonical:
        identity = canonical.get("identity", {})
        if identity.get("rarity") is not None:
            artifact["identity"]["rarity"] = identity["rarity"]
        if identity.get("imageUrl"):
            artifact["identity"]["imageUrl"] = identity["imageUrl"]
        artifact["canonicalRef"] = canonical_ref
    required = {
        "taxonomy.weaponType": weapon_label is not None,
        "progression": len(progression) == len(LEVELS),
        "options": len(options) >= 2,
    }
    unresolved = [key for key, passed in required.items() if not passed]
    for key, present in (
        ("identity.rarity", "rarity" in artifact["identity"]),
        ("identity.imageUrl", "imageUrl" in artifact["identity"]),
        ("progression.materialCosts", False),
        ("options.structuredValues", False),
    ):
        if not present:
            unresolved.append(key)
    artifact["taxonomy"] = taxonomy
    artifact["progression"] = progression
    artifact["options"] = options
    artifact["group"] = {
        "axis": "weaponType",
        **(taxonomy.get("weaponType") or {"id": None, "code": "unknown", "label": "미확인"}),
    }
    artifact["quality"] = {
        "status": "query_ready" if all(required.values()) else "incomplete",
        "queryReady": all(required.values()),
        "canonicalComplete": not unresolved,
        "requiredChecks": required,
        "unresolvedFields": sorted(set(unresolved)),
    }
    return artifact


def _normalize_gear(entity: dict[str, Any]) -> dict[str, Any]:
    artifact = _base_artifact(entity)
    documents = artifact["documents"]
    set_label = _value_after_label(documents, "profile", "세트")
    type_label = _value_after_label(documents, "profile", "장비 유형")
    quality_label = _value_after_label(documents, "profile", "품질")
    base_stats = _gear_base_stats(documents)
    forging = _gear_forging(documents, base_stats["options"])
    taxonomy: dict[str, Any] = {}
    if set_label:
        taxonomy["gearSet"] = _gear_set(set_label)
    if type_label:
        taxonomy["gearType"] = _gear_type(type_label)
    if quality_label:
        taxonomy["quality"] = _gear_quality(quality_label)
    canonical, canonical_ref = _canonical_overlay("gear", entity["gameEntryId"])
    if canonical:
        artifact["canonicalRef"] = canonical_ref
    required = {
        "taxonomy.gearSet": set_label is not None,
        "taxonomy.gearType": type_label is not None,
        "taxonomy.quality": quality_label is not None,
        "level": base_stats["level"] is not None,
        "defense": base_stats["defense"] is not None,
        "options": len(base_stats["options"]) >= 1,
        "forging": (
            forging["supported"] and len(forging.get("options", [])) >= 1
            if quality_label == "노란색 품질"
            else True
        ),
    }
    unresolved = [key for key, passed in required.items() if not passed]
    unresolved.extend(["crafting.materialCosts", "setEffect.structuredRules"])
    artifact["taxonomy"] = taxonomy
    artifact["level"] = base_stats["level"]
    artifact["defense"] = base_stats["defense"]
    artifact["options"] = base_stats["options"]
    artifact["forging"] = forging
    artifact["setEffectDocumentIds"] = [
        document["documentId"]
        for document in _documents_for(documents, "gear_set_effect")
    ]
    artifact["group"] = {
        "axis": "gearSet",
        **(taxonomy.get("gearSet") or {"id": None, "code": "unknown", "label": "미확인"}),
    }
    artifact["quality"] = {
        "status": "query_ready" if all(required.values()) else "incomplete",
        "queryReady": all(required.values()),
        "canonicalComplete": not unresolved,
        "requiredChecks": required,
        "unresolvedFields": sorted(set(unresolved)),
    }
    return artifact


def normalize_entity(entity: dict[str, Any]) -> dict[str, Any]:
    domain = entity["domain"]
    if domain == "operator":
        return _normalize_operator(entity)
    if domain == "weapon":
        return _normalize_weapon(entity)
    if domain == "gear":
        return _normalize_gear(entity)
    raise ValueError(f"Unsupported RAG domain: {domain}")


def _summary_content(artifact: dict[str, Any]) -> str:
    identity = artifact["identity"]
    lines = [
        f"엔티티 유형: {artifact['entityType']}",
        f"이름: {identity['name']}",
        f"gameEntryId: {identity['gameEntryId']}",
        f"정규화 상태: {artifact['quality']['status']}",
    ]
    if artifact["entityType"] == "operator":
        taxonomy = artifact["taxonomy"]
        attributes = artifact["attributes"]
        lines.extend(
            [
                f"속성: {taxonomy['element']['label']} (id={taxonomy['element']['id']}, code={taxonomy['element']['code']})",
                f"무기 유형: {taxonomy['weaponType']['label']} (id={taxonomy['weaponType']['id']}, code={taxonomy['weaponType']['code']})",
                f"주요 능력치: {attributes['primary']['label']} (id={attributes['primary']['id']}, code={attributes['primary']['code']})",
                f"보조 능력치: {attributes['secondary']['label']} (id={attributes['secondary']['id']}, code={attributes['secondary']['code']})",
            ]
        )
        for row in artifact["progression"]:
            stats = row["stats"]
            lines.append(
                f"LV.{row['level']}: 힘={stats['strength']}, 민첩={stats['agility']}, "
                f"지능={stats['intellect']}, 의지={stats['will']}, "
                f"기초 공격력={stats['baseAttack']}, 기초 생명력={stats['baseHp']}"
            )
    elif artifact["entityType"] == "weapon":
        weapon_type = artifact["taxonomy"].get("weaponType")
        if weapon_type:
            lines.append(
                f"무기 유형: {weapon_type['label']} (id={weapon_type['id']}, code={weapon_type['code']})"
            )
        if artifact["progression"]:
            lines.append(
                "기초 공격력: "
                + ", ".join(
                    f"LV.{row['level']}={row['baseAttack']}"
                    for row in artifact["progression"]
                )
            )
        lines.append(
            "무기 옵션: "
            + "; ".join(
                f"{option['slot']}번={option['name']}"
                for option in artifact["options"]
            )
        )
    else:
        taxonomy = artifact["taxonomy"]
        for key, prefix in (
            ("gearSet", "장비 세트"),
            ("gearType", "장비 유형"),
            ("quality", "품질"),
        ):
            entry = taxonomy.get(key)
            if entry:
                lines.append(
                    f"{prefix}: {entry['label']} (id={entry['id']}, code={entry['code']})"
                )
        lines.extend(
            [
                f"LV: {artifact['level']}",
                f"방어력: {artifact['defense']}",
                "장비 옵션: "
                + "; ".join(
                    f"{option['slot']}번={option['name']} {option['baseValue']['value']}{'%' if option['baseValue']['unit'] == 'percent' else ''}"
                    for option in artifact["options"]
                ),
                f"정밀 단조 지원: {'예' if artifact['forging']['supported'] else '아니오'}",
            ]
        )
    if artifact["quality"]["unresolvedFields"]:
        lines.append(
            "현재 원문에서 확정 불가: "
            + ", ".join(artifact["quality"]["unresolvedFields"])
        )
    return "\n".join(lines)


def _entity_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "entityType": artifact["entityType"],
        "entityId": artifact["entityId"],
        "gameEntryId": artifact["identity"]["gameEntryId"],
        "name": artifact["identity"]["name"],
        "group": artifact["group"],
        "ragRef": artifact["ragRef"],
        "queryReady": artifact["quality"]["queryReady"],
        "unresolvedFields": artifact["quality"]["unresolvedFields"],
        "documentCount": len(artifact["documents"]),
    }
    for key in ("canonicalCode", "aliases"):
        if key in artifact["identity"]:
            summary[key] = artifact["identity"][key]
    if artifact["entityType"] == "operator":
        if artifact["taxonomy"].get("element"):
            summary["element"] = artifact["taxonomy"]["element"]
        if artifact["taxonomy"].get("weaponType"):
            summary["weaponType"] = artifact["taxonomy"]["weaponType"]
        if artifact["attributes"].get("primary"):
            summary["primaryAttribute"] = artifact["attributes"]["primary"]
        if artifact["attributes"].get("secondary"):
            summary["secondaryAttribute"] = artifact["attributes"]["secondary"]
    elif artifact["entityType"] == "weapon":
        if artifact["taxonomy"].get("weaponType"):
            summary["weaponType"] = artifact["taxonomy"]["weaponType"]
    else:
        for source_key, target_key in (
            ("gearSet", "gearSet"),
            ("gearType", "gearType"),
            ("quality", "quality"),
        ):
            if artifact["taxonomy"].get(source_key):
                summary[target_key] = artifact["taxonomy"][source_key]
    return summary


def _catalog_payloads(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[tuple[int | None, str], dict[str, Any]]] = {
        "elements": {},
        "weapon-types": {},
        "gear-sets": {},
        "gear-types": {},
        "gear-qualities": {},
    }
    for artifact in artifacts:
        taxonomy = artifact["taxonomy"]
        pairs: list[tuple[str, dict[str, Any]]] = []
        if artifact["entityType"] == "operator":
            if taxonomy.get("element"):
                pairs.append(("elements", taxonomy["element"]))
            if taxonomy.get("weaponType"):
                pairs.append(("weapon-types", taxonomy["weaponType"]))
        elif artifact["entityType"] == "weapon":
            if taxonomy.get("weaponType"):
                pairs.append(("weapon-types", taxonomy["weaponType"]))
        else:
            if taxonomy.get("gearSet"):
                pairs.append(("gear-sets", taxonomy["gearSet"]))
            if taxonomy.get("gearType"):
                pairs.append(("gear-types", taxonomy["gearType"]))
            if taxonomy.get("quality"):
                pairs.append(("gear-qualities", taxonomy["quality"]))
        for catalog, entry in pairs:
            values[catalog][(entry["id"], entry["code"])] = entry
    return {
        name: {
            "schemaVersion": "1.0.0",
            "catalog": name,
            "entries": sorted(entries.values(), key=lambda entry: entry["label"]),
        }
        for name, entries in values.items()
    }


def _quality_report(
    artifacts: list[dict[str, Any]], source_document_count: int
) -> dict[str, Any]:
    by_domain = Counter(artifact["entityType"] for artifact in artifacts)
    by_group: dict[str, Counter[str]] = {
        "operator": Counter(),
        "weapon": Counter(),
        "gear": Counter(),
    }
    unresolved: Counter[str] = Counter()
    source_conflicts: list[dict[str, Any]] = []
    for artifact in artifacts:
        by_group[artifact["entityType"]][artifact["group"]["label"]] += 1
        unresolved.update(artifact["quality"]["unresolvedFields"])
        for conflict in artifact["quality"].get("sourceConflicts", []):
            source_conflicts.append(
                {
                    "entityType": artifact["entityType"],
                    "gameEntryId": artifact["identity"]["gameEntryId"],
                    "name": artifact["identity"]["name"],
                    **conflict,
                }
            )
    query_ready = sum(artifact["quality"]["queryReady"] for artifact in artifacts)
    duplicate_keys = len(artifacts) - len(
        {
            (artifact["entityType"], artifact["identity"]["gameEntryId"])
            for artifact in artifacts
        }
    )
    return {
        "schemaVersion": "1.0.0",
        "dataset": {
            "grain": "one normalized file per locale/domain/gameEntryId",
            "entities": len(artifacts),
            "sourceDocuments": source_document_count,
            "byDomain": dict(sorted(by_domain.items())),
        },
        "checks": {
            "uniqueEntityKeys": {"passed": duplicate_keys == 0, "duplicates": duplicate_keys},
            "queryReady": {
                "passed": query_ready == len(artifacts),
                "entities": query_ready,
                "rate": query_ready / len(artifacts) if artifacts else 0,
            },
            "groupingCoverage": {
                "passed": all(artifact["group"]["code"] != "unknown" for artifact in artifacts),
                "byDomainAndLabel": {
                    domain: dict(sorted(counts.items()))
                    for domain, counts in by_group.items()
                },
            },
            "unresolvedFields": dict(sorted(unresolved.items())),
            "sourceConflicts": {
                "count": len(source_conflicts),
                "entities": len(
                    {
                        (conflict["entityType"], conflict["gameEntryId"])
                        for conflict in source_conflicts
                    }
                ),
                "details": source_conflicts,
            },
        },
        "verdict": "query_ready" if query_ready == len(artifacts) and duplicate_keys == 0 else "incomplete",
    }


def materialize_normalized_snapshot(
    snapshot_path: Path,
    *,
    normalized_root: Path = NORMALIZED_RAG_ROOT,
    query_index_root: Path | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    """Turn a published rendered-text snapshot into durable, grouped RAG files."""

    snapshot_path = snapshot_path.resolve()
    query_index_root = query_index_root or snapshot_path.parent
    snapshot = _read_json(snapshot_path)
    locale = snapshot["locale"]
    excluded_entity_count = sum(
        bool(override.get("exclude")) for override in _entity_overrides().values()
    )
    artifacts = [
        normalize_entity(entity)
        for entity in snapshot["entities"]
        if not _is_excluded_entity(entity)
    ]
    source_document_count = sum(len(artifact["documents"]) for artifact in artifacts)
    locale_root = normalized_root / locale
    if replace and locale_root.exists():
        shutil.rmtree(locale_root)
    locale_root.mkdir(parents=True, exist_ok=True)

    for artifact in artifacts:
        group_segment = safe_path_segment(
            artifact["group"]["label"], fallback="미확인"
        )
        filename = (
            safe_entity_file_stem(
                artifact["identity"]["gameEntryId"], artifact["identity"]["name"]
            )
            + ".json"
        )
        target = (
            locale_root
            / artifact["entityType"]
            / group_segment
            / filename
        )
        normalized_ref = _project_ref(target)
        artifact["ragRef"] = normalized_ref
        evidence_ids = [
            document["documentId"] for document in artifact["documents"]
        ]
        summary_document = {
            "documentId": (
                f"normalized.{artifact['entityType']}_{artifact['identity']['gameEntryId']}"
                f".profile.{locale.lower()}"
            ),
            "section": "normalized_profile",
            "content": _summary_content(artifact),
            "metadata": {
                "entityType": artifact["entityType"],
                "entityId": artifact["entityId"],
                "gameEntryId": artifact["identity"]["gameEntryId"],
                "locale": locale,
                "sourceUrl": artifact["source"]["url"],
                "normalizedRef": normalized_ref,
                "normalizationMethod": "rendered_label_v1",
                "contentStatus": "normalized",
                "groupAxis": artifact["group"]["axis"],
                "groupId": artifact["group"]["id"],
                "groupCode": artifact["group"]["code"],
                "groupLabel": artifact["group"]["label"],
                "evidenceDocumentIds": evidence_ids,
            },
        }
        for document in artifact["documents"]:
            metadata = document.setdefault("metadata", {})
            metadata.pop("rawRef", None)
            metadata["normalizedRef"] = normalized_ref
            metadata["entityName"] = artifact["identity"]["name"]
            if artifact["identity"].get("canonicalCode"):
                metadata["canonicalCode"] = artifact["identity"]["canonicalCode"]
            metadata["normalizationStatus"] = artifact["quality"]["status"]
            metadata["groupAxis"] = artifact["group"]["axis"]
            metadata["groupCode"] = artifact["group"]["code"]
            metadata["groupLabel"] = artifact["group"]["label"]
        artifact["documents"].insert(0, summary_document)
        write_json_atomic(target, artifact)

    summaries = [_entity_summary(artifact) for artifact in artifacts]
    quality = _quality_report(artifacts, source_document_count)
    group_counts: dict[str, dict[str, int]] = {}
    for domain in ("operator", "weapon", "gear"):
        counts = Counter(
            artifact["group"]["label"]
            for artifact in artifacts
            if artifact["entityType"] == domain
        )
        group_counts[domain] = dict(sorted(counts.items()))
    manifest = {
        "schemaVersion": "2.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "locale": locale,
        "storageGrain": "one file per entity",
        "grouping": {
            "operator": "element",
            "weapon": "weaponType",
            "gear": "gearSet",
        },
        "stats": {
            "inputEntities": len(snapshot["entities"]),
            "entities": len(artifacts),
            "excludedEntities": excluded_entity_count,
            "sourceDocuments": source_document_count,
            "documents": sum(len(artifact["documents"]) for artifact in artifacts),
            "byDomain": dict(
                sorted(Counter(artifact["entityType"] for artifact in artifacts).items())
            ),
            "byGroup": group_counts,
        },
        "qualityReportRef": _project_ref(
            normalized_root / f"quality-report.{locale}.json"
        ),
        "entities": summaries,
    }
    write_json_atomic(normalized_root / f"manifest.{locale}.json", manifest)
    write_json_atomic(normalized_root / f"quality-report.{locale}.json", quality)
    for name, payload in _catalog_payloads(artifacts).items():
        write_json_atomic(normalized_root / "catalogs" / f"{name}.json", payload)

    artifact_index = {
        (artifact["entityType"], artifact["identity"]["gameEntryId"]): artifact
        for artifact in artifacts
    }
    updated_entities: list[dict[str, Any]] = []
    for source_entity in snapshot["entities"]:
        if _is_excluded_entity(source_entity):
            continue
        artifact = artifact_index[
            (source_entity["domain"], source_entity["gameEntryId"])
        ]
        updated = {
            key: value
            for key, value in source_entity.items()
            if key not in {"rawRef", "ragRef", "documents", "normalization"}
        }
        updated.update(
            {
                "name": artifact["identity"]["name"],
                "ragRef": artifact["ragRef"],
                "group": artifact["group"],
                "structured": {
                    key: value
                    for key, value in artifact.items()
                    if key
                    not in {
                        "schemaVersion",
                        "entityType",
                        "entityId",
                        "locale",
                        "source",
                        "documents",
                        "ragRef",
                        "group",
                        "quality",
                    }
                },
                "normalization": {
                    "passed": artifact["quality"]["queryReady"],
                    "canonicalComplete": artifact["quality"]["canonicalComplete"],
                    "missingEntityMetadata": artifact["quality"]["unresolvedFields"],
                    "detailDocumentsWithGaps": 0,
                },
                "documents": artifact["documents"],
            }
        )
        if artifact["identity"].get("sourceName"):
            updated["sourceName"] = artifact["identity"]["sourceName"]
        if artifact["identity"].get("canonicalCode"):
            updated["canonicalCode"] = artifact["identity"]["canonicalCode"]
        updated_entities.append(updated)
    query_ready = sum(
        entity["normalization"]["passed"] for entity in updated_entities
    )
    canonical_complete = sum(
        entity["normalization"]["canonicalComplete"] for entity in updated_entities
    )
    updated_snapshot = copy.deepcopy(snapshot)
    updated_snapshot["schemaVersion"] = "2.0.0"
    updated_snapshot["publicationStatus"] = (
        "query_ready" if query_ready == len(updated_entities) else "incomplete"
    )
    updated_snapshot["entities"] = updated_entities
    updated_snapshot["quality"].update(
        {
            "normalizationPassed": query_ready == len(updated_entities),
            "normalizedEntities": query_ready,
            "entitiesNeedingNormalization": len(updated_entities) - query_ready,
            "canonicalComplete": canonical_complete == len(updated_entities),
            "canonicalCompleteEntities": canonical_complete,
        }
    )
    updated_snapshot["stats"].update(
        {
            "entities": len(updated_entities),
            "excludedEntities": excluded_entity_count,
            "byDomain": dict(
                sorted(Counter(entity["domain"] for entity in updated_entities).items())
            ),
            "sourceDocuments": source_document_count,
            "normalizedSummaryDocuments": len(updated_entities),
            "documents": sum(len(entity["documents"]) for entity in updated_entities),
        }
    )
    updated_snapshot["runs"] = [
        {key: value for key, value in run.items() if key != "runRef"}
        for run in updated_snapshot.get("runs", [])
    ]
    write_json_atomic(snapshot_path, updated_snapshot)
    query_index_path = query_index_root / f"query-index.{locale}.json"
    write_json_atomic(query_index_path, manifest)

    published_manifest_path = query_index_root / "manifest.json"
    if published_manifest_path.exists():
        published_manifest = _read_json(published_manifest_path)
        snapshots = [
            entry
            for entry in published_manifest.get("snapshots", [])
            if entry.get("locale") != locale
        ]
        snapshots.append(
            {
                "locale": locale,
                "snapshotRef": _project_ref(snapshot_path),
                "publicationStatus": updated_snapshot["publicationStatus"],
                "normalizationManifestRef": _project_ref(
                    normalized_root / f"manifest.{locale}.json"
                ),
                "queryIndexRef": _project_ref(query_index_path),
                "stats": updated_snapshot["stats"],
            }
        )
        published_manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()
        published_manifest["snapshots"] = sorted(
            snapshots, key=lambda entry: entry["locale"]
        )
        write_json_atomic(published_manifest_path, published_manifest)
    return {
        "locale": locale,
        "snapshot": updated_snapshot,
        "manifest": manifest,
        "quality": quality,
        "manifestRef": _project_ref(normalized_root / f"manifest.{locale}.json"),
        "queryIndexRef": _project_ref(query_index_path),
    }
