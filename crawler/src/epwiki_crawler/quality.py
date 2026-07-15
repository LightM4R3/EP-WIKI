from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from epwiki_crawler.config import PROJECT_ROOT, SKPORT_DOMAIN_SUB_TYPE_IDS
from epwiki_crawler.core.storage import write_json_atomic


REQUIRED_SECTIONS = {
    "operator": {"profile", "progression", "combat_skill", "operator_talent", "potential"},
    "weapon": {"profile", "progression", "weapon_option", "potential"},
    "gear": {"profile"},
}
REQUIRED_ENTITY_METADATA = {
    "operator": {
        "rarity",
        "classId",
        "classCode",
        "elementId",
        "elementCode",
        "weaponTypeId",
        "weaponTypeCode",
        "primaryAttributeId",
        "secondaryAttributeId",
    },
    "weapon": {"rarity", "weaponTypeId", "weaponTypeCode"},
    "gear": {
        "gearTypeId",
        "gearTypeCode",
        "qualityId",
        "qualityCode",
        "gearSetId",
        "gearSetCode",
        "gearLevel",
        "forgingSupported",
    },
}
REQUIRED_DETAIL_METADATA = {
    "operator": ("combat_skill", {"skillId", "skillTypeId"}),
    "weapon": (
        "weapon_option",
        {
            "optionId",
            "optionCode",
            "optionCategoryId",
            "optionCategoryCode",
            "optionSlot",
            "optionLevelCount",
        },
    ),
    "gear": (
        "gear_option",
        {"optionId", "optionCode", "optionSlot", "forgeLevelCount"},
    ),
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def validate_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    summary_path = run_dir / "summary.json"
    summary = _read_json(summary_path)
    schema = _read_json(PROJECT_ROOT / "schemas" / "rag-document.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    rag_paths = sorted((run_dir / "rag").rglob("*.json"))
    raw_paths = sorted((run_dir / "raw").rglob("*.json"))
    schema_errors: list[dict[str, str]] = []
    consistency_errors: list[dict[str, str]] = []
    missing_pairs: list[str] = []
    missing_sections: list[dict[str, Any]] = []
    semantic_gaps: list[dict[str, Any]] = []
    normalized_gaps: list[dict[str, Any]] = []
    detail_gaps: list[dict[str, Any]] = []
    entity_ids: list[str] = []
    document_ids: list[str] = []
    domains: Counter[str] = Counter()
    sections: dict[str, Counter[str]] = defaultdict(Counter)
    content_statuses: Counter[str] = Counter()
    hash_algorithms: Counter[str] = Counter()

    for rag_path in rag_paths:
        rag = _read_json(rag_path)
        for error in validator.iter_errors(rag):
            schema_errors.append(
                {"file": _relative(rag_path), "message": error.message}
            )

        relative_rag = rag_path.relative_to(run_dir / "rag")
        raw_path = run_dir / "raw" / relative_rag
        if not raw_path.exists():
            missing_pairs.append(_relative(rag_path))
            continue
        raw = _read_json(raw_path)
        payload = raw["payload"]
        domain = payload["domain"]
        domains[domain] += 1
        entity_ids.append(rag["entityId"])

        expected_entity_id = f"{domain}_{payload['gameEntryId']}"
        if rag["entityId"] != expected_entity_id:
            consistency_errors.append(
                {
                    "file": _relative(rag_path),
                    "message": "RAG entityId does not match raw domain/gameEntryId",
                }
            )

        entity_sections: set[str] = set()
        entity_metadata: set[str] = set()
        for document in rag["documents"]:
            metadata = document["metadata"]
            document_ids.append(document["documentId"])
            entity_sections.add(document["section"])
            sections[domain][document["section"]] += 1
            entity_metadata.update(metadata)
            content_statuses[metadata["contentStatus"]] += 1
            hash_algorithms[metadata.get("contentHashAlgorithm", "missing")] += 1

            expected_values = {
                "entityType": domain,
                "entityId": expected_entity_id,
                "subTypeId": SKPORT_DOMAIN_SUB_TYPE_IDS[domain],
                "gameEntryId": payload["gameEntryId"],
                "contentSha256": payload["contentSha256"],
            }
            for key, expected in expected_values.items():
                if metadata.get(key) != expected:
                    consistency_errors.append(
                        {
                            "file": _relative(rag_path),
                            "message": f"metadata.{key} does not match raw data",
                        }
                    )
            raw_ref = metadata.get("rawRef")
            if not raw_ref or not (PROJECT_ROOT / raw_ref).resolve().exists():
                consistency_errors.append(
                    {
                        "file": _relative(rag_path),
                        "message": "metadata.rawRef does not resolve to a raw file",
                    }
                )

        absent_sections = REQUIRED_SECTIONS[domain] - entity_sections
        if absent_sections:
            missing_sections.append(
                {
                    "entityId": expected_entity_id,
                    "missing": sorted(absent_sections),
                }
            )
        if rag["locale"] == "ko-KR":
            combined_content = "\n".join(
                document["content"] for document in rag["documents"]
            )
            required_markers = {
                "operator": {
                    "무기 유형",
                    "속성",
                    "업그레이드",
                    "재능",
                    "잠재능력",
                },
                "weapon": {"무기 정보", "기초 공격력", "RANK 1", "RANK 9"},
                "gear": {"품질", "장비 유형", "세트", "LV", "방어력"},
            }[domain]
            if "gear_option" in entity_sections:
                required_markers.update(
                    {"정밀 단조", "기본", "1단계", "2단계", "3단계"}
                )
            if "gear_set_effect" in entity_sections:
                required_markers.add("세트 효과")
            absent_markers = sorted(
                marker for marker in required_markers if marker not in combined_content
            )
            if domain == "operator" and not any(
                marker in combined_content for marker in ("RANK1", "RANK 1")
            ):
                absent_markers.append("RANK1|RANK 1")
            if absent_markers:
                semantic_gaps.append(
                    {"entityId": expected_entity_id, "missing": absent_markers}
                )
        absent_metadata = REQUIRED_ENTITY_METADATA[domain] - entity_metadata
        if absent_metadata:
            normalized_gaps.append(
                {
                    "entityId": expected_entity_id,
                    "missing": sorted(absent_metadata),
                }
            )

        detail_section, detail_fields = REQUIRED_DETAIL_METADATA[domain]
        detail_documents = [
            document
            for document in rag["documents"]
            if document["section"] == detail_section
        ]
        for document in detail_documents:
            absent_detail = detail_fields - set(document["metadata"])
            if absent_detail:
                detail_gaps.append(
                    {
                        "documentId": document["documentId"],
                        "missing": sorted(absent_detail),
                    }
                )

    raw_relative = {
        path.relative_to(run_dir / "raw").as_posix() for path in raw_paths
    }
    rag_relative = {
        path.relative_to(run_dir / "rag").as_posix() for path in rag_paths
    }
    raw_without_rag = sorted(raw_relative - rag_relative)
    duplicate_entities = sorted(
        entity_id for entity_id, count in Counter(entity_ids).items() if count > 1
    )
    duplicate_documents = sorted(
        document_id
        for document_id, count in Counter(document_ids).items()
        if count > 1
    )
    successful = summary["succeeded"]
    structural_pass = not any(
        (
            summary["failed"],
            schema_errors,
            consistency_errors,
            missing_pairs,
            raw_without_rag,
            duplicate_entities,
            duplicate_documents,
            missing_sections,
            semantic_gaps,
        )
    ) and len(rag_paths) == successful
    normalized_pass = not normalized_gaps and not detail_gaps
    verified_documents = sum(
        count
        for status, count in content_statuses.items()
        if status in {"verified", "cross_checked"}
    )

    findings: list[dict[str, Any]] = []
    if not structural_pass:
        findings.append(
            {
                "severity": "high",
                "code": "structural_validation_failed",
                "message": "At least one crawl, schema, pairing, uniqueness, or section check failed.",
            }
        )
    if not normalized_pass:
        findings.append(
            {
                "severity": "high",
                "code": "normalized_metadata_missing",
                "affectedEntities": len(normalized_gaps),
                "affectedDetailDocuments": len(detail_gaps),
                "message": "Rendered text exists, but stable IDs/codes required for exact filtering are absent.",
            }
        )
    if verified_documents != len(document_ids):
        findings.append(
            {
                "severity": "medium",
                "code": "content_not_verified",
                "verifiedDocuments": verified_documents,
                "totalDocuments": len(document_ids),
                "message": "Documents are raw rendered chunks rather than canonical cross-checked RAG.",
            }
        )

    return {
        "schemaVersion": "1.0.0",
        "runId": summary["runId"],
        "dataset": {
            "grain": "one RAG file per locale/domain/gameEntryId",
            "jobs": summary["total"],
            "succeeded": successful,
            "skipped": summary["skipped"],
            "failed": summary["failed"],
            "entities": len(rag_paths),
            "documents": len(document_ids),
            "entitiesByDomain": dict(sorted(domains.items())),
            "documentsBySection": {
                domain: dict(sorted(counter.items()))
                for domain, counter in sorted(sections.items())
            },
        },
        "checks": {
            "structural": {
                "passed": structural_pass,
                "schemaErrors": schema_errors,
                "consistencyErrors": consistency_errors,
                "ragWithoutRaw": missing_pairs,
                "rawWithoutRag": raw_without_rag,
                "duplicateEntityIds": duplicate_entities,
                "duplicateDocumentIds": duplicate_documents,
                "missingSections": missing_sections,
                "missingVisibleFieldMarkers": semantic_gaps,
            },
            "hashing": {
                "algorithms": dict(sorted(hash_algorithms.items())),
                "allUseStableRenderedHash": set(hash_algorithms)
                == {"rendered_chapters_v1"},
            },
            "normalization": {
                "passed": normalized_pass,
                "entityMetadataGaps": normalized_gaps,
                "detailMetadataGaps": detail_gaps,
            },
            "verification": {
                "contentStatuses": dict(sorted(content_statuses.items())),
                "verifiedDocuments": verified_documents,
            },
        },
        "findings": findings,
        "verdict": (
            "ready_for_structured_rag"
            if structural_pass and normalized_pass and verified_documents == len(document_ids)
            else "raw_rendered_rag_only"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one EP-WIKI crawler run")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_run(args.run_dir)
    output = args.output or args.run_dir / "quality-report.json"
    write_json_atomic(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["checks"]["structural"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
