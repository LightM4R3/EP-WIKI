from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from epwiki_crawler.config import (
    CrawlerSettings,
    DEFAULT_TARGETS_PATH,
    SKPORT_DETAIL_MAIN_TYPE_ID,
    SKPORT_DOMAIN_SUB_TYPE_IDS,
    SUPPORTED_LOCALES,
)
from epwiki_crawler.core.runner import run_crawl
from epwiki_crawler.core.targets import (
    auto_range_targets,
    build_jobs,
    range_targets,
    select_targets,
)
from epwiki_crawler.normalizer import (
    NORMALIZED_RAG_ROOT,
    PUBLISHED_RAG_ROOT,
    materialize_normalized_snapshot,
)
from epwiki_crawler.publisher import publish_runs
from epwiki_crawler.registry import DOMAIN_NAMES
from epwiki_crawler.retrieval import (
    RETRIEVAL_RAG_ROOT,
    RetrievalBuildError,
    build_retrieval_corpus,
    validate_retrieval_corpus,
)


def _add_crawl_selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--domain", choices=(*DOMAIN_NAMES, "all"), default="all")
    parser.add_argument("--locale", choices=(*SUPPORTED_LOCALES, "all"), default="all")
    parser.add_argument(
        "--targets",
        type=Path,
        default=DEFAULT_TARGETS_PATH,
        help="subTypeId별 gameEntryIds가 저장된 JSON 파일",
    )
    parser.add_argument(
        "--entry-id",
        type=int,
        action="append",
        help="단일 --domain을 대상으로 직접 지정하며 여러 번 사용할 수 있습니다.",
    )
    parser.add_argument(
        "--sub-type-id",
        type=int,
        choices=(1, 2, 4),
        help="범위 크롤링 카테고리: 1=오퍼레이터, 2=무기, 4=장비",
    )
    parser.add_argument("--start", type=int, help="포함되는 시작 gameEntryId")
    parser.add_argument("--end", type=int, help="포함되는 마지막 gameEntryId")


def _print_progress(result: dict[str, object]) -> None:
    print(
        (
            f"[{result['status']}] {result['locale']} "
            f"subTypeId={result['subTypeId']} gameEntryId={result['gameEntryId']}"
        ),
        file=sys.stderr,
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epwiki-crawler",
        description="EP-WIKI Selenium range crawler and automatic RAG builder",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("domains", help="등록된 데이터 도메인을 출력합니다.")

    plan_parser = subparsers.add_parser(
        "plan",
        help="브라우저를 실행하지 않고 예정된 수집 작업을 출력합니다.",
    )
    _add_crawl_selection_arguments(plan_parser)

    crawl_parser = subparsers.add_parser(
        "crawl",
        help="타깃의 gameEntryId를 순회하며 렌더링된 원본 데이터를 저장합니다.",
    )
    _add_crawl_selection_arguments(crawl_parser)
    crawl_parser.add_argument(
        "--run-id",
        help="출력 폴더 이름입니다. 생략하면 UTC 시각으로 생성합니다.",
    )
    crawl_parser.add_argument(
        "--save-html",
        action="store_true",
        help="RAG용 텍스트 외에 렌더 HTML도 함께 보존합니다.",
    )
    crawl_parser.add_argument(
        "--publish",
        action="store_true",
        help="완료 후 검증된 결과를 data/rag/published 최신 snapshot으로 반영합니다.",
    )

    publish_parser = subparsers.add_parser(
        "publish",
        help="완료된 crawl run을 프론트 검증용 최신 RAG snapshot으로 반영합니다.",
    )
    publish_parser.add_argument(
        "--run-id",
        action="append",
        required=True,
        help="반영할 output run ID이며 여러 번 사용할 수 있습니다.",
    )
    publish_parser.add_argument(
        "--locale",
        choices=(*SUPPORTED_LOCALES, "all"),
        default="all",
    )
    publish_parser.add_argument(
        "--replace",
        action="store_true",
        help="기존 최신 snapshot과 병합하지 않고 지정 run만 반영합니다.",
    )
    publish_parser.add_argument(
        "--require-normalized",
        action="store_true",
        help="canonical 정규화가 완료되지 않은 run은 반영하지 않습니다.",
    )

    normalize_parser = subparsers.add_parser(
        "normalize",
        help="published snapshot을 data/rag/normalized의 질의용 개별 파일로 가공합니다.",
    )
    normalize_parser.add_argument(
        "--locale",
        choices=(*SUPPORTED_LOCALES, "all"),
        default="ko-KR",
    )

    retrieval_parser = subparsers.add_parser(
        "retrieval",
        help="정규화 원장에서 LLM 검색 전용 corpus를 생성하거나 검증합니다.",
    )
    retrieval_subparsers = retrieval_parser.add_subparsers(
        dest="retrieval_command", required=True
    )
    retrieval_build = retrieval_subparsers.add_parser(
        "build",
        help="의미 단위 문서를 생성하고 엄격 검증 통과 시 현재 release로 승격합니다.",
    )
    retrieval_build.add_argument(
        "--locale",
        choices=(*SUPPORTED_LOCALES, "all"),
        default="ko-KR",
    )
    retrieval_validate = retrieval_subparsers.add_parser(
        "validate",
        help="승격된 retrieval manifest, 문서 스키마와 해시를 다시 검증합니다.",
    )
    retrieval_validate.add_argument(
        "--locale",
        choices=(*SUPPORTED_LOCALES, "all"),
        default="ko-KR",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "domains":
        for domain in DOMAIN_NAMES:
            print(domain)
        return 0

    if args.command == "retrieval":
        locales = SUPPORTED_LOCALES if args.locale == "all" else (args.locale,)
        results: list[dict[str, object]] = []
        try:
            for locale in locales:
                if args.retrieval_command == "build":
                    normalized_manifest = (
                        NORMALIZED_RAG_ROOT / f"manifest.{locale}.json"
                    )
                    if not normalized_manifest.exists():
                        continue
                    result = build_retrieval_corpus(locale)
                    results.append(
                        {
                            "locale": locale,
                            "releaseId": result["manifest"]["releaseId"],
                            "manifestRef": result["manifestRef"],
                            "qualityReportRef": result["qualityReportRef"],
                            "stats": result["manifest"]["stats"],
                            "verdict": result["quality"]["verdict"],
                        }
                    )
                else:
                    manifest_path = RETRIEVAL_RAG_ROOT / f"manifest.{locale}.json"
                    if not manifest_path.exists():
                        continue
                    results.append(validate_retrieval_corpus(locale))
        except RetrievalBuildError as error:
            parser.error(str(error))
        if not results:
            parser.error("No source manifest exists for the selected locale")
        print(json.dumps({"retrieval": results}, ensure_ascii=False, indent=2))
        return 0 if all(result["verdict"] == "indexable" for result in results) else 1

    if args.command == "normalize":
        locales = SUPPORTED_LOCALES if args.locale == "all" else (args.locale,)
        results: list[dict[str, object]] = []
        for locale in locales:
            snapshot_path = PUBLISHED_RAG_ROOT / f"latest.{locale}.json"
            if not snapshot_path.exists():
                continue
            normalized = materialize_normalized_snapshot(snapshot_path)
            retrieval = build_retrieval_corpus(locale)
            results.append(
                {
                    "locale": locale,
                    "manifestRef": normalized["manifestRef"],
                    "queryIndexRef": normalized["queryIndexRef"],
                    "stats": normalized["manifest"]["stats"],
                    "qualityVerdict": normalized["quality"]["verdict"],
                    "retrievalManifestRef": retrieval["manifestRef"],
                    "retrievalReleaseId": retrieval["manifest"]["releaseId"],
                    "retrievalDocuments": retrieval["manifest"]["stats"]["documents"],
                    "retrievalVerdict": retrieval["quality"]["verdict"],
                }
            )
        if not results:
            parser.error("No published snapshots exist for the selected locale")
        print(json.dumps({"normalized": results}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "publish":
        settings = CrawlerSettings.from_env()
        locales = SUPPORTED_LOCALES if args.locale == "all" else (args.locale,)
        try:
            manifest = publish_runs(
                [settings.output_dir / run_id for run_id in args.run_id],
                locales=locales,
                merge_existing=not args.replace,
                require_normalized=args.require_normalized,
            )
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command in {"plan", "crawl"}:
        settings = CrawlerSettings.from_env()
        locales = SUPPORTED_LOCALES if args.locale == "all" else (args.locale,)
        try:
            uses_range = any(
                value is not None for value in (args.sub_type_id, args.start, args.end)
            )
            if uses_range:
                if args.start is None or args.end is None:
                    raise ValueError("Range crawl requires --start and --end")
                if args.entry_id is not None:
                    raise ValueError("Range options cannot be combined with --entry-id")
                if args.sub_type_id is None and args.domain == "all":
                    targets = auto_range_targets(
                        settings.base_url, args.start, args.end
                    )
                else:
                    sub_type_id = args.sub_type_id
                    if sub_type_id is None:
                        sub_type_id = SKPORT_DOMAIN_SUB_TYPE_IDS[args.domain]
                    targets = range_targets(
                        settings.base_url, sub_type_id, args.start, args.end
                    )
                    if args.domain not in {"all", targets[0].domain}:
                        raise ValueError(
                            "--domain conflicts with the selected --sub-type-id"
                        )
            else:
                targets = select_targets(
                    manifest_path=args.targets,
                    base_url=settings.base_url,
                    domain=args.domain,
                    game_entry_ids=args.entry_id,
                )
            jobs = build_jobs(targets, locales)
        except ValueError as error:
            parser.error(str(error))

        if args.command == "plan":
            payload = {
                "jobs": [
                    {
                        "domain": job.target.domain,
                        "mainTypeId": SKPORT_DETAIL_MAIN_TYPE_ID,
                        "subTypeId": (
                            "auto"
                            if job.target.domain == "auto"
                            else job.target.sub_type_id
                        ),
                        "probeSubTypeId": job.target.sub_type_id,
                        "gameEntryId": job.target.game_entry_id,
                        "locale": job.locale,
                        "url": job.target.source_url,
                    }
                    for job in jobs
                ]
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.save_html:
            settings = replace(settings, save_html=True)
        summary = run_crawl(
            jobs, settings, args.run_id, progress_callback=_print_progress
        )
        if args.publish and not summary["failed"]:
            summary["publication"] = publish_runs(
                [settings.output_dir / summary["runId"]],
                locales=locales,
                merge_existing=True,
            )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if summary["failed"] else 0

    return 2
