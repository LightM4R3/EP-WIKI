from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver

from epwiki_crawler.config import CrawlerSettings, Locale
from epwiki_crawler.core.browser import create_chrome_driver
from epwiki_crawler.core.contracts import CrawlContext, CrawlJob, DomainCrawler
from epwiki_crawler.core.detail_page import EntryNotFoundError
from epwiki_crawler.core.naming import safe_entity_file_stem
from epwiki_crawler.core.rag_pipeline import (
    CategoryMismatchError,
    SourceDataUnavailableError,
    build_auto_rag,
    classify_record,
    extract_entity_name,
)
from epwiki_crawler.core.storage import write_json_atomic, write_raw_record
from epwiki_crawler.registry import create_crawler


DriverFactory = Callable[[CrawlerSettings, Locale], WebDriver]
CrawlerFactory = Callable[[str], DomainCrawler]
ProgressCallback = Callable[[dict[str, Any]], None]


def create_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _raw_path(
    output_dir: Path,
    run_id: str,
    job: CrawlJob,
    domain: str,
    file_stem: str,
) -> Path:
    return (
        output_dir
        / run_id
        / "raw"
        / job.locale
        / domain
        / f"{file_stem}.json"
    )


def _error_path(output_dir: Path, run_id: str, job: CrawlJob) -> Path:
    return (
        output_dir
        / run_id
        / "errors"
        / job.locale
        / job.target.domain
        / f"{job.target.game_entry_id}.json"
    )


def _rag_path(
    output_dir: Path,
    run_id: str,
    job: CrawlJob,
    domain: str,
    file_stem: str,
) -> Path:
    return (
        output_dir
        / run_id
        / "rag"
        / job.locale
        / domain
        / f"{file_stem}.json"
    )


def _failure(job: CrawlJob, error: Exception) -> dict[str, Any]:
    return {
        "status": "failed",
        "domain": job.target.domain,
        "subTypeId": job.target.sub_type_id,
        "gameEntryId": job.target.game_entry_id,
        "locale": job.locale,
        "sourceUrl": job.target.source_url,
        "errorType": type(error).__name__,
        "message": str(error),
    }


def _write_progress(
    output_dir: Path,
    run_id: str,
    total: int,
    started_at: str,
    results: list[dict[str, Any]],
    *,
    completed: bool = False,
) -> None:
    succeeded = sum(result["status"] == "succeeded" for result in results)
    skipped = sum(result["status"] == "skipped" for result in results)
    failed = len(results) - succeeded - skipped
    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "runId": run_id,
        "status": "completed" if completed else "running",
        "startedAt": started_at,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "processed": len(results),
        "remaining": total - len(results),
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "lastResult": results[-1] if results else None,
    }
    write_json_atomic(output_dir / run_id / "progress.json", payload)


def run_crawl(
    jobs: Iterable[CrawlJob],
    settings: CrawlerSettings,
    run_id: str | None = None,
    driver_factory: DriverFactory = create_chrome_driver,
    crawler_factory: CrawlerFactory = create_crawler,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run all jobs, reusing one browser per locale and isolating entry failures."""

    run_id = run_id or create_run_id()
    job_values = tuple(jobs)
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    _write_progress(
        settings.output_dir, run_id, len(job_values), started_at, results
    )

    def record_result(result: dict[str, Any]) -> None:
        results.append(result)
        _write_progress(
            settings.output_dir,
            run_id,
            len(job_values),
            started_at,
            results,
        )
        if progress_callback:
            progress_callback(result)

    locale_groups: dict[Locale, list[CrawlJob]] = {}
    for job in job_values:
        locale_groups.setdefault(job.locale, []).append(job)

    for locale, locale_jobs in locale_groups.items():
        try:
            driver = driver_factory(settings, locale)
        except Exception as error:
            for job in locale_jobs:
                failure = _failure(job, error)
                write_json_atomic(
                    _error_path(settings.output_dir, run_id, job), failure
                )
                record_result(failure)
            continue

        context = CrawlContext(
            locale=locale,
            run_id=run_id,
            output_dir=settings.output_dir,
            wait_timeout=settings.wait_timeout,
            missing_entry_timeout=settings.missing_entry_timeout,
            save_html=settings.save_html,
        )
        try:
            for job in locale_jobs:
                try:
                    crawler = crawler_factory(job.target.domain)
                    record = crawler.crawl_entry(driver, context, job.target)
                    record = classify_record(record, job.target.domain)
                    actual_domain = record.payload["domain"]
                    entity_name = extract_entity_name(record)
                    file_stem = safe_entity_file_stem(
                        job.target.game_entry_id, entity_name
                    )
                    output_path = _raw_path(
                        settings.output_dir,
                        run_id,
                        job,
                        actual_domain,
                        file_stem,
                    )
                    rag_path = _rag_path(
                        settings.output_dir,
                        run_id,
                        job,
                        actual_domain,
                        file_stem,
                    )
                    rag = build_auto_rag(record, output_path.as_posix())
                    write_raw_record(output_path, record)
                    write_json_atomic(rag_path, rag)
                    result = {
                        "status": "succeeded",
                        "domain": actual_domain,
                        "subTypeId": record.payload["subTypeId"],
                        "probeSubTypeId": job.target.sub_type_id,
                        "gameEntryId": job.target.game_entry_id,
                        "locale": job.locale,
                        "entityName": entity_name,
                        "fileStem": file_stem,
                        "sourceUrl": job.target.source_url,
                        "outputPath": output_path.as_posix(),
                        "ragOutputPath": rag_path.as_posix(),
                        "ragDocumentCount": len(rag["documents"]),
                        "contentStatus": rag["documents"][0]["metadata"][
                            "contentStatus"
                        ],
                        "contentHashAlgorithm": record.payload.get(
                            "contentHashAlgorithm", "legacy_page_source_v0"
                        ),
                        "contentSha256": record.payload["contentSha256"],
                    }
                    record_result(result)
                except (
                    EntryNotFoundError,
                    CategoryMismatchError,
                    SourceDataUnavailableError,
                ) as error:
                    result = {
                        "status": "skipped",
                        "domain": job.target.domain,
                        "subTypeId": job.target.sub_type_id,
                        "gameEntryId": job.target.game_entry_id,
                        "locale": job.locale,
                        "sourceUrl": job.target.source_url,
                        "reason": str(error),
                    }
                    record_result(result)
                except Exception as error:
                    failure = _failure(job, error)
                    write_json_atomic(
                        _error_path(settings.output_dir, run_id, job), failure
                    )
                    record_result(failure)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    succeeded = sum(result["status"] == "succeeded" for result in results)
    skipped = sum(result["status"] == "skipped" for result in results)
    summary = {
        "schemaVersion": "1.0.0",
        "runId": run_id,
        "startedAt": started_at,
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "total": len(job_values),
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": len(results) - succeeded - skipped,
        "results": results,
    }
    write_json_atomic(settings.output_dir / run_id / "summary.json", summary)
    _write_progress(
        settings.output_dir,
        run_id,
        len(job_values),
        started_at,
        results,
        completed=True,
    )
    return summary
