from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from epwiki_crawler.core.contracts import RawRecord


def write_raw_records(path: Path, records: list[RawRecord]) -> None:
    """Atomically write raw records without touching frontend seed files."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps([asdict(record) for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def write_json_atomic(path: Path, payload: Any) -> None:
    """Write a JSON-compatible value atomically under the crawler output tree."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    value = asdict(payload) if is_dataclass(payload) else payload
    temporary_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def write_raw_record(path: Path, record: RawRecord) -> None:
    write_json_atomic(path, record)
