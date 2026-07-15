from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from epwiki_crawler.config import (
    SKPORT_DOMAIN_SUB_TYPE_IDS,
    SUPPORTED_LOCALES,
    Locale,
    build_detail_url_for_sub_type,
    domain_for_sub_type,
)
from epwiki_crawler.core.contracts import CrawlJob, CrawlTarget


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Target manifest does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid target manifest JSON: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("Target manifest root must be an object")
    return payload


def load_manifest_targets(path: Path, base_url: str) -> tuple[CrawlTarget, ...]:
    """Load subType groups while rejecting duplicate or invalid entry IDs."""

    payload = _load_json(path)
    if payload.get("schemaVersion") != "1.0.0":
        raise ValueError("Target manifest schemaVersion must be 1.0.0")
    groups = payload.get("targets")
    if not isinstance(groups, list):
        raise ValueError("Target manifest must contain a targets array")

    targets: list[CrawlTarget] = []
    seen: set[tuple[int, int]] = set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("Each target group must be an object")
        sub_type_id = group.get("subTypeId")
        game_entry_ids = group.get("gameEntryIds")
        if isinstance(sub_type_id, bool) or not isinstance(sub_type_id, int):
            raise ValueError(f"subTypeId must be an integer: {sub_type_id}")
        domain = domain_for_sub_type(sub_type_id)
        if not isinstance(game_entry_ids, list) or not game_entry_ids:
            raise ValueError(f"subTypeId {sub_type_id} requires gameEntryIds")
        for game_entry_id in game_entry_ids:
            if isinstance(game_entry_id, bool) or not isinstance(game_entry_id, int):
                raise ValueError(f"gameEntryId must be an integer: {game_entry_id}")
            key = (sub_type_id, game_entry_id)
            if key in seen:
                raise ValueError(
                    f"Duplicate target: subTypeId={sub_type_id}, "
                    f"gameEntryId={game_entry_id}"
                )
            seen.add(key)
            targets.append(
                CrawlTarget(
                    domain=domain,
                    sub_type_id=sub_type_id,
                    game_entry_id=game_entry_id,
                    source_url=build_detail_url_for_sub_type(
                        base_url, sub_type_id, game_entry_id
                    ),
                )
            )
    return tuple(targets)


def direct_targets(
    base_url: str, domain: str, game_entry_ids: Iterable[int]
) -> tuple[CrawlTarget, ...]:
    """Create targets for one domain without duplicating its subTypeId in CLI input."""

    try:
        sub_type_id = SKPORT_DOMAIN_SUB_TYPE_IDS[domain]
    except KeyError as error:
        raise ValueError(f"Unsupported crawler domain: {domain}") from error
    unique_ids = tuple(dict.fromkeys(game_entry_ids))
    if not unique_ids:
        raise ValueError("At least one gameEntryId is required")
    return tuple(
        CrawlTarget(
            domain=domain,
            sub_type_id=sub_type_id,
            game_entry_id=game_entry_id,
            source_url=build_detail_url_for_sub_type(
                base_url, sub_type_id, game_entry_id
            ),
        )
        for game_entry_id in unique_ids
    )


def range_targets(
    base_url: str,
    sub_type_id: int,
    start: int,
    end: int,
) -> tuple[CrawlTarget, ...]:
    """Create an inclusive sparse-ID scan range for one SKPort subType."""

    domain = domain_for_sub_type(sub_type_id)
    if isinstance(start, bool) or isinstance(end, bool) or start < 1 or end < 1:
        raise ValueError("--start and --end must be positive integers")
    if start > end:
        raise ValueError("--start must be less than or equal to --end")
    return tuple(
        CrawlTarget(
            domain=domain,
            sub_type_id=sub_type_id,
            game_entry_id=game_entry_id,
            source_url=build_detail_url_for_sub_type(
                base_url, sub_type_id, game_entry_id
            ),
        )
        for game_entry_id in range(start, end + 1)
    )


def auto_range_targets(
    base_url: str,
    start: int,
    end: int,
) -> tuple[CrawlTarget, ...]:
    """Probe each global ID once; content decides operator, weapon, gear, or skip."""

    if isinstance(start, bool) or isinstance(end, bool) or start < 1 or end < 1:
        raise ValueError("--start and --end must be positive integers")
    if start > end:
        raise ValueError("--start must be less than or equal to --end")
    probe_sub_type_id = SKPORT_DOMAIN_SUB_TYPE_IDS["operator"]
    return tuple(
        CrawlTarget(
            domain="auto",
            sub_type_id=probe_sub_type_id,
            game_entry_id=game_entry_id,
            source_url=build_detail_url_for_sub_type(
                base_url, probe_sub_type_id, game_entry_id
            ),
        )
        for game_entry_id in range(start, end + 1)
    )


def select_targets(
    manifest_path: Path,
    base_url: str,
    domain: str,
    game_entry_ids: Iterable[int] | None = None,
) -> tuple[CrawlTarget, ...]:
    if game_entry_ids is not None:
        if domain == "all":
            raise ValueError("--entry-id requires one explicit --domain")
        return direct_targets(base_url, domain, game_entry_ids)
    targets = load_manifest_targets(manifest_path, base_url)
    selected = targets if domain == "all" else tuple(
        target for target in targets if target.domain == domain
    )
    if not selected:
        raise ValueError(f"No crawl targets selected for domain: {domain}")
    return selected


def build_jobs(
    targets: Iterable[CrawlTarget], locales: Iterable[Locale]
) -> tuple[CrawlJob, ...]:
    locale_values = tuple(locales)
    if any(locale not in SUPPORTED_LOCALES for locale in locale_values):
        raise ValueError(f"Unsupported locale in: {locale_values}")
    return tuple(
        CrawlJob(target=target, locale=locale)
        for locale in locale_values
        for target in targets
    )
