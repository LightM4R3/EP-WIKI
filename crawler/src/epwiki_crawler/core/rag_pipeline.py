from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from epwiki_crawler.config import (
    SKPORT_DOMAIN_SUB_TYPE_IDS,
    canonicalize_detail_url,
)
from epwiki_crawler.core.contracts import RawRecord


MAX_CHUNK_CHARACTERS = 2400
INFRASTRUCTURE_MARKERS = {
    "ko-KR": "인프라 스킬",
    "en-US": "Base Skill",
    "ja-JP": "配属スキル",
    "zh-TW": "後勤技能",
}
DOMAIN_INFO_MARKERS = {
    "operator": {
        "오퍼레이터 정보",
        "Operator Information",
        "オペレーター情報",
        "幹員資料",
    },
    "weapon": {"무기 정보", "Weapon Information", "武器記録", "武器資料"},
    "gear": {"장비 정보", "Gear Information", "装備情報", "裝備屬性"},
}
GEAR_TYPE_MARKERS = {"장비 유형", "Gear Type", "装備タイプ", "裝備類型"}


class CategoryMismatchError(RuntimeError):
    """Raised when a global gameEntryId belongs to another SKPort category."""


class SourceDataUnavailableError(RuntimeError):
    """Raised when an announced entry has no published in-game data yet."""


@dataclass(frozen=True, slots=True)
class SectionSource:
    section: str
    chapter_index: int
    widget_index: int | None
    segments: tuple[str, ...]


def _segments(value: dict[str, Any]) -> tuple[str, ...]:
    return tuple(segment for segment in value.get("textSegments", []) if segment)


def extract_entity_name(record: RawRecord) -> str:
    return next(
        (
            segment
            for chapter in record.payload["chapters"]
            for segment in chapter.get("textSegments", [])
            if segment
        ),
        record.entity_id,
    )


def detect_page_domain(record: RawRecord) -> str | None:
    chapters = sorted(record.payload["chapters"], key=lambda item: item["index"])
    if len(chapters) < 2:
        return None
    info_label = next(iter(_segments(chapters[1])), "").removeprefix("//").strip()
    for domain, markers in DOMAIN_INFO_MARKERS.items():
        if info_label in markers:
            return domain
    if GEAR_TYPE_MARKERS.intersection(_segments(chapters[0])):
        return "gear"
    return None


def classify_record(record: RawRecord, expected_domain: str) -> RawRecord:
    """Assign the page's real category after one global-ID probe."""

    detected_domain = detect_page_domain(record)
    if detected_domain is None:
        raise CategoryMismatchError(
            f"gameEntryId={record.payload['gameEntryId']} is not operator, weapon, or gear"
        )
    if expected_domain != "auto" and detected_domain != expected_domain:
        raise CategoryMismatchError(
            f"gameEntryId={record.payload['gameEntryId']} belongs to "
            f"{detected_domain}, not {expected_domain}"
        )
    payload = dict(record.payload)
    payload["requestedSubTypeId"] = payload["subTypeId"]
    payload["domain"] = detected_domain
    payload["subTypeId"] = SKPORT_DOMAIN_SUB_TYPE_IDS[detected_domain]
    source_url = canonicalize_detail_url(
        record.source_url,
        payload["subTypeId"],
        payload["gameEntryId"],
    )
    return RawRecord(
        entity_id=f"{detected_domain}_{payload['gameEntryId']}",
        locale=record.locale,
        source_url=source_url,
        payload=payload,
    )


def _chapter_source(chapter: dict[str, Any], section: str) -> SectionSource:
    return SectionSource(
        section=section,
        chapter_index=chapter["index"],
        widget_index=None,
        segments=_segments(chapter),
    )


def _widget_source(
    chapter: dict[str, Any], widget_index: int, section: str
) -> SectionSource:
    widget = chapter["widgets"][widget_index]
    return SectionSource(
        section=section,
        chapter_index=chapter["index"],
        widget_index=widget_index,
        segments=_segments(widget),
    )


def _operator_sources(
    chapters: list[dict[str, Any]], locale: str
) -> list[SectionSource]:
    if len(chapters) < 5:
        return []
    ability_position = next(
        (
            index
            for index in range(2, len(chapters) - 1)
            if len(chapters[index].get("widgets", [])) == 3
            and len(chapters[index + 1].get("widgets", [])) == 1
        ),
        None,
    )
    if ability_position is None:
        return []

    ability = chapters[ability_position]
    talent_segments = list(_segments(ability["widgets"][1]))
    marker = INFRASTRUCTURE_MARKERS[locale]
    infra_start = next(
        (index for index, segment in enumerate(talent_segments) if segment == marker),
        len(talent_segments),
    )
    sources = [
        _chapter_source(chapters[0], "profile"),
        _chapter_source(chapters[1], "profile"),
        _chapter_source(chapters[ability_position - 1], "progression"),
        _widget_source(ability, 0, "combat_skill"),
        SectionSource(
            section="operator_talent",
            chapter_index=ability["index"],
            widget_index=1,
            segments=tuple(talent_segments[:infra_start]),
        ),
        _widget_source(ability, 2, "progression"),
        _chapter_source(chapters[ability_position + 1], "potential"),
    ]
    if infra_start < len(talent_segments):
        sources.insert(
            5,
            SectionSource(
                section="infrastructure_talent",
                chapter_index=ability["index"],
                widget_index=1,
                segments=tuple(talent_segments[infra_start:]),
            ),
        )
    return sources


def _weapon_sources(chapters: list[dict[str, Any]]) -> list[SectionSource]:
    if len(chapters) < 5:
        return []
    return [
        _chapter_source(chapters[0], "profile"),
        _chapter_source(chapters[1], "profile"),
        _chapter_source(chapters[2], "progression"),
        _chapter_source(chapters[3], "weapon_option"),
        _chapter_source(chapters[4], "potential"),
    ]


def _gear_sources(chapters: list[dict[str, Any]]) -> list[SectionSource]:
    if len(chapters) < 2:
        return []
    sources = [
        _chapter_source(chapters[0], "profile"),
        _chapter_source(chapters[1], "profile"),
    ]
    if len(chapters) == 2:
        return sources
    if len(chapters) >= 4:
        sources.append(_chapter_source(chapters[2], "gear_option"))
    sources.append(
        _chapter_source(chapters[3] if len(chapters) >= 4 else chapters[2], "gear_set_effect")
    )
    return sources


def _section_sources(record: RawRecord) -> list[SectionSource]:
    chapters = sorted(record.payload["chapters"], key=lambda item: item["index"])
    if record.payload["domain"] == "operator":
        return _operator_sources(chapters, record.locale)
    if record.payload["domain"] == "weapon":
        return _weapon_sources(chapters)
    if record.payload["domain"] == "gear":
        return _gear_sources(chapters)
    raise ValueError(f"Unsupported RAG domain: {record.payload['domain']}")


def _chunk_segments(segments: tuple[str, ...]) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for segment in segments:
        segment_parts = [
            segment[index : index + MAX_CHUNK_CHARACTERS]
            for index in range(0, len(segment), MAX_CHUNK_CHARACTERS)
        ]
        for part in segment_parts:
            additional = len(part) + (1 if current else 0)
            if current and current_length + additional > MAX_CHUNK_CHARACTERS:
                chunks.append("\n".join(current))
                current = []
                current_length = 0
            current.append(part)
            current_length += len(part) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append("\n".join(current))
    return chunks


def build_auto_rag(record: RawRecord, raw_ref: str) -> dict[str, Any]:
    """Convert the necessary rendered sections into category-aware RAG chunks."""

    detected_domain = detect_page_domain(record)
    requested_domain = record.payload["domain"]
    if detected_domain != requested_domain:
        raise CategoryMismatchError(
            f"gameEntryId={record.payload['gameEntryId']} belongs to "
            f"{detected_domain or 'another category'}, not {requested_domain}"
        )

    entity_name = extract_entity_name(record)
    documents: list[dict[str, Any]] = []
    locale_slug = record.locale.lower()
    section_sources = _section_sources(record)
    if not section_sources:
        raise SourceDataUnavailableError(
            f"In-game data is not published for {record.entity_id}"
        )
    observed_sections = {source.section for source in section_sources}
    required_sections = {
        "operator": {
            "profile",
            "progression",
            "combat_skill",
            "operator_talent",
            "potential",
        },
        "weapon": {"profile", "progression", "weapon_option", "potential"},
        "gear": {"profile"},
    }[record.payload["domain"]]
    content_status = (
        "raw_rendered"
        if required_sections.issubset(observed_sections)
        else "has_source_gaps"
    )
    for source_index, source in enumerate(section_sources):
        for chunk_index, chunk in enumerate(_chunk_segments(source.segments)):
            widget_token = (
                f"w{source.widget_index}" if source.widget_index is not None else "chapter"
            )
            content = "\n".join(
                [
                    f"entity: {entity_name}",
                    f"category: {record.payload['domain']}",
                    f"section: {source.section}",
                    chunk,
                ]
            )
            documents.append(
                {
                    "documentId": (
                        f"auto.{record.entity_id}.{source.section}.c{source.chapter_index}."
                        f"{widget_token}.s{source_index}.p{chunk_index}.{locale_slug}"
                    ),
                    "section": source.section,
                    "content": content,
                    "metadata": {
                        "entityType": record.payload["domain"],
                        "entityId": record.entity_id,
                        "sourceUrl": record.source_url,
                        "rawRef": raw_ref,
                        "contentStatus": content_status,
                        "extractionMode": "rendered_section",
                        "subTypeId": record.payload["subTypeId"],
                        "gameEntryId": record.payload["gameEntryId"],
                        "chapterIndex": source.chapter_index,
                        "widgetIndex": source.widget_index,
                        "chunkIndex": chunk_index,
                        "observedAt": record.payload["observedAt"],
                        "contentHashAlgorithm": record.payload.get(
                            "contentHashAlgorithm", "legacy_page_source_v0"
                        ),
                        "contentSha256": record.payload["contentSha256"],
                    },
                }
            )
    if not documents:
        raise ValueError(f"No RAG sections extracted from {record.entity_id}")
    return {
        "schemaVersion": "1.0.0",
        "entityId": record.entity_id,
        "locale": record.locale,
        "documents": documents,
    }
