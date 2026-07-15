from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epwiki_crawler.config import (
    PROJECT_ROOT,
    SUPPORTED_LOCALES,
    Locale,
    canonicalize_detail_url,
)
from epwiki_crawler.core.storage import write_json_atomic
from epwiki_crawler.normalizer import (
    NORMALIZED_RAG_ROOT,
    materialize_normalized_snapshot,
)
from epwiki_crawler.quality import validate_run
from epwiki_crawler.retrieval import build_retrieval_corpus


PUBLISHED_RAG_ROOT = PROJECT_ROOT / "data" / "rag" / "published"
QualityValidator = Callable[[Path], dict[str, Any]]


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


def _entity_name(rag: dict[str, Any], fallback: str) -> str:
    for document in rag["documents"]:
        for line in document["content"].splitlines():
            if line.startswith("entity: "):
                return line.removeprefix("entity: ").strip() or fallback
    return fallback


def _load_existing_entities(
    publish_root: Path, locale: Locale
) -> dict[tuple[str, int], dict[str, Any]]:
    path = publish_root / f"latest.{locale}.json"
    if not path.exists():
        return {}
    snapshot = _read_json(path)
    return {
        (entity["domain"], entity["gameEntryId"]): entity
        for entity in snapshot.get("entities", [])
    }


def publish_runs(
    run_dirs: Iterable[Path],
    *,
    publish_root: Path = PUBLISHED_RAG_ROOT,
    locales: Iterable[Locale] | None = None,
    merge_existing: bool = True,
    require_normalized: bool = False,
    quality_validator: QualityValidator = validate_run,
) -> dict[str, Any]:
    """Publish structurally valid run artifacts as an inspectable latest snapshot."""

    selected_locales = tuple(locales or SUPPORTED_LOCALES)
    invalid_locales = set(selected_locales) - set(SUPPORTED_LOCALES)
    if invalid_locales:
        raise ValueError(f"Unsupported publish locales: {sorted(invalid_locales)}")

    run_values = tuple(path.resolve() for path in run_dirs)
    if not run_values:
        raise ValueError("At least one run directory is required")

    published_at = datetime.now(timezone.utc).isoformat()
    run_reports: list[dict[str, Any]] = []
    entities_by_locale: dict[
        Locale, dict[tuple[str, int], dict[str, Any]]
    ] = {
        locale: (
            _load_existing_entities(publish_root, locale)
            if merge_existing
            else {}
        )
        for locale in selected_locales
    }

    for run_dir in run_values:
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            raise ValueError(f"Run summary does not exist: {summary_path}")
        summary = _read_json(summary_path)
        quality = quality_validator(run_dir)
        if not quality["checks"]["structural"]["passed"]:
            raise ValueError(
                f"Run failed structural quality checks: {summary['runId']}"
            )
        if require_normalized and not quality["checks"]["normalization"]["passed"]:
            raise ValueError(
                f"Run is not normalized and cannot be published: {summary['runId']}"
            )
        write_json_atomic(run_dir / "quality-report.json", quality)

        result_index = {
            (
                result["locale"],
                result["domain"],
                result["gameEntryId"],
            ): result
            for result in summary["results"]
            if result["status"] == "succeeded"
        }
        normalization_gaps = {
            gap["entityId"]: gap["missing"]
            for gap in quality["checks"]["normalization"][
                "entityMetadataGaps"
            ]
        }
        rag_records = [
            (rag_path, _read_json(rag_path))
            for rag_path in sorted((run_dir / "rag").rglob("*.json"))
        ]
        document_entities = {
            document["documentId"]: rag["entityId"]
            for _rag_path, rag in rag_records
            for document in rag["documents"]
        }
        detail_gap_count: dict[str, int] = {}
        for gap in quality["checks"]["normalization"]["detailMetadataGaps"]:
            entity_id = document_entities.get(gap["documentId"], "")
            if entity_id:
                detail_gap_count[entity_id] = detail_gap_count.get(entity_id, 0) + 1

        for rag_path, rag in rag_records:
            relative = rag_path.relative_to(run_dir / "rag")
            if len(relative.parts) < 3:
                continue
            locale, domain = relative.parts[:2]
            if locale not in selected_locales:
                continue
            first_metadata = rag["documents"][0]["metadata"]
            game_entry_id = first_metadata["gameEntryId"]
            source_url = canonicalize_detail_url(
                first_metadata["sourceUrl"],
                first_metadata["subTypeId"],
                game_entry_id,
            )
            for document in rag["documents"]:
                document["metadata"]["sourceUrl"] = source_url
            result = result_index.get((locale, domain, game_entry_id), {})
            entity_id = rag["entityId"]
            content_statuses = sorted(
                {
                    document["metadata"]["contentStatus"]
                    for document in rag["documents"]
                }
            )
            entity = {
                "entityId": entity_id,
                "domain": domain,
                "locale": locale,
                "subTypeId": first_metadata["subTypeId"],
                "gameEntryId": game_entry_id,
                "name": result.get("entityName")
                or _entity_name(rag, entity_id),
                "sourceUrl": source_url,
                "rawRef": first_metadata.get("rawRef"),
                "ragRef": _project_ref(rag_path),
                "contentStatuses": content_statuses,
                "contentHashAlgorithm": first_metadata.get(
                    "contentHashAlgorithm", "legacy_page_source_v0"
                ),
                "contentSha256": first_metadata.get("contentSha256"),
                "normalization": {
                    "passed": entity_id not in normalization_gaps
                    and detail_gap_count.get(entity_id, 0) == 0,
                    "missingEntityMetadata": normalization_gaps.get(
                        entity_id, []
                    ),
                    "detailDocumentsWithGaps": detail_gap_count.get(entity_id, 0),
                },
                "documents": rag["documents"],
                "sourceRunId": summary["runId"],
            }
            entities_by_locale[locale][(domain, game_entry_id)] = entity

        run_reports.append(
            {
                "runId": summary["runId"],
                "runRef": _project_ref(run_dir),
                "total": summary["total"],
                "succeeded": summary["succeeded"],
                "skipped": summary["skipped"],
                "failed": summary["failed"],
                "qualityVerdict": quality["verdict"],
                "structuralPassed": quality["checks"]["structural"]["passed"],
                "normalizationPassed": quality["checks"]["normalization"]["passed"],
                "stableHash": quality["checks"]["hashing"][
                    "allUseStableRenderedHash"
                ],
            }
        )

    publish_root.mkdir(parents=True, exist_ok=True)
    snapshots: list[dict[str, Any]] = []
    for locale, entity_map in entities_by_locale.items():
        entities = sorted(
            entity_map.values(),
            key=lambda entity: (
                entity["domain"],
                entity["gameEntryId"],
            ),
        )
        if not entities:
            continue
        domain_counts: dict[str, int] = {}
        document_count = 0
        normalized_count = 0
        for entity in entities:
            domain_counts[entity["domain"]] = (
                domain_counts.get(entity["domain"], 0) + 1
            )
            document_count += len(entity["documents"])
            normalized_count += int(entity["normalization"]["passed"])
        snapshot = {
            "schemaVersion": "1.0.0",
            "publicationStatus": (
                "normalized"
                if normalized_count == len(entities)
                else "inspection_ready"
            ),
            "publishedAt": published_at,
            "locale": locale,
            "runIds": [report["runId"] for report in run_reports],
            "quality": {
                "structuralPassed": all(
                    report["structuralPassed"] for report in run_reports
                ),
                "normalizationPassed": normalized_count == len(entities),
                "stableHash": all(
                    entity["contentHashAlgorithm"] == "rendered_chapters_v1"
                    for entity in entities
                ),
                "normalizedEntities": normalized_count,
                "entitiesNeedingNormalization": len(entities) - normalized_count,
            },
            "stats": {
                "entities": len(entities),
                "documents": document_count,
                "byDomain": dict(sorted(domain_counts.items())),
            },
            "runs": run_reports,
            "entities": entities,
        }
        snapshot_path = publish_root / f"latest.{locale}.json"
        write_json_atomic(snapshot_path, snapshot)
        normalized_root = (
            NORMALIZED_RAG_ROOT
            if publish_root.resolve() == PUBLISHED_RAG_ROOT.resolve()
            else publish_root.parent / "normalized"
        )
        normalized = materialize_normalized_snapshot(
            snapshot_path,
            normalized_root=normalized_root,
            query_index_root=publish_root,
            replace=True,
        )
        snapshot = normalized["snapshot"]
        snapshot_entry = {
            "locale": locale,
            "snapshotRef": _project_ref(snapshot_path),
            "publicationStatus": snapshot["publicationStatus"],
            "normalizationManifestRef": normalized["manifestRef"],
            "queryIndexRef": normalized["queryIndexRef"],
            **snapshot["stats"],
        }
        if publish_root.resolve() == PUBLISHED_RAG_ROOT.resolve():
            retrieval = build_retrieval_corpus(
                locale,
                normalized_root=normalized_root,
                retrieval_root=publish_root.parent / "retrieval",
            )
            snapshot_entry.update(
                {
                    "retrievalManifestRef": retrieval["manifestRef"],
                    "retrievalReleaseId": retrieval["manifest"]["releaseId"],
                    "retrievalDocuments": retrieval["manifest"]["stats"]["documents"],
                    "retrievalVerdict": retrieval["quality"]["verdict"],
                }
            )
        snapshots.append(snapshot_entry)

    manifest = {
        "schemaVersion": "1.0.0",
        "publishedAt": published_at,
        "snapshots": snapshots,
    }
    write_json_atomic(publish_root / "manifest.json", manifest)
    return manifest
