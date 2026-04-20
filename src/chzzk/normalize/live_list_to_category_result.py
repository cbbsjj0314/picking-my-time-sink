"""Dry-run Chzzk live-list payloads into category result JSONL artifacts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from chzzk.normalize.category_lives import aggregate_category_lives, build_result_row


def load_payload(path: Path) -> object:
    """Load one local Chzzk live-list JSON payload."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}") from exc


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write deterministic category result JSONL."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def run(
    *,
    input_path: Path,
    output_path: Path,
    bucket_time: str,
    collected_at: str,
) -> list[dict[str, Any]]:
    """Build category result rows from a local payload and write JSONL."""

    payload = load_payload(input_path)
    rows = aggregate_category_lives(
        payload,
        bucket_time=bucket_time,
        collected_at=collected_at,
    )
    result_rows = [build_result_row(row) for row in rows]
    write_jsonl(output_path, result_rows)
    return result_rows


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for local Chzzk category artifact dry runs."""

    parser = argparse.ArgumentParser(
        description="Dry-run a local Chzzk live-list JSON payload into category result JSONL"
    )
    parser.add_argument("--input", "--input-path", dest="input_path", type=Path, required=True)
    parser.add_argument("--output", "--output-path", dest="output_path", type=Path, required=True)
    parser.add_argument("--bucket-time", required=True)
    parser.add_argument("--collected-at", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    run(
        input_path=args.input_path,
        output_path=args.output_path,
        bucket_time=args.bucket_time,
        collected_at=args.collected_at,
    )


if __name__ == "__main__":
    main()
