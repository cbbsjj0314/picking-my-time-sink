"""Fetch Steam rankings payloads and parse ranking rows."""

from __future__ import annotations

import argparse
import json
import logging
import re
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from steam.probe.common import (
    add_common_probe_arguments,
    configure_logging,
    decode_json_payload,
    request_with_retry,
    runtime_config_from_args,
    text_excerpt,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_RUNTIME_OUT_DIR = Path("tmp/steam/rankings")
GLOBAL_COUNTRY_CODE = "US"
TOPSELLERS_SERVICE_URL = "https://api.steampowered.com/IStoreTopSellersService/GetWeeklyTopSellers/v1/"
MOSTPLAYED_SERVICE_URL = (
    "https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
)
APP_LINK_RE = re.compile(
    r"(?:https?://store\.steampowered\.com)?/app/(\d+)(?:/([^\"'?#<>]*))?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RankingTarget:
    chart: str
    region: str
    url: str
    service_url: str
    country_code: str

    @property
    def probe_name(self) -> str:
        return f"rankings_{self.chart}_{self.region.lower()}"

    @property
    def artifact_key(self) -> str:
        return f"{self.chart}_{self.region.lower()}"

    @property
    def payload_basename(self) -> str:
        return f"{self.artifact_key}.payload.json"

    @property
    def default_output_path(self) -> Path:
        return DEFAULT_RUNTIME_OUT_DIR / self.payload_basename


TARGETS = (
    RankingTarget(
        chart="topsellers",
        region="global",
        url="https://store.steampowered.com/charts/topsellers/global",
        service_url=TOPSELLERS_SERVICE_URL,
        country_code=GLOBAL_COUNTRY_CODE,
    ),
    RankingTarget(
        chart="topsellers",
        region="KR",
        url="https://store.steampowered.com/charts/topsellers/KR",
        service_url=TOPSELLERS_SERVICE_URL,
        country_code="KR",
    ),
    RankingTarget(
        chart="mostplayed",
        region="global",
        url="https://store.steampowered.com/charts/mostplayed/global",
        service_url=MOSTPLAYED_SERVICE_URL,
        country_code=GLOBAL_COUNTRY_CODE,
    ),
    RankingTarget(
        chart="mostplayed",
        region="KR",
        url="https://store.steampowered.com/charts/mostplayed/KR",
        service_url=MOSTPLAYED_SERVICE_URL,
        country_code="KR",
    ),
)

DEFAULT_TOPSELLERS_GLOBAL_PATH = TARGETS[0].default_output_path
DEFAULT_TOPSELLERS_KR_PATH = TARGETS[1].default_output_path
DEFAULT_MOSTPLAYED_GLOBAL_PATH = TARGETS[2].default_output_path
DEFAULT_MOSTPLAYED_KR_PATH = TARGETS[3].default_output_path


class SteamChartsHTMLParser(HTMLParser):
    """Collect Steam app links and infer ranking rows from document order."""

    def __init__(self, *, max_rows: int) -> None:
        super().__init__()
        self.max_rows = max_rows
        self.rows: list[dict[str, int | str]] = []
        self._seen_app_ids: set[int] = set()
        self._current: dict[str, int | str | list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or len(self.rows) >= self.max_rows:
            return

        href = dict(attrs).get("href")
        if not href:
            return

        match = APP_LINK_RE.search(href)
        if not match:
            return

        app_id = int(match.group(1))
        slug = match.group(2) or ""

        self._current = {
            "app_id": app_id,
            "slug": slug,
            "chunks": [],
        }

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        self._current["chunks"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current is None:
            return

        app_id = int(self._current["app_id"])
        slug = str(self._current["slug"])
        chunks = [str(chunk) for chunk in self._current["chunks"]]
        self._current = None

        if app_id in self._seen_app_ids:
            return

        title = infer_title_from_chunks(chunks=chunks, slug=slug, app_id=app_id)
        row = {
            "rank": len(self.rows) + 1,
            "app_id": app_id,
            "title": title,
        }
        self.rows.append(row)
        self._seen_app_ids.add(app_id)


def infer_title_from_chunks(*, chunks: list[str], slug: str, app_id: int) -> str:
    """Infer a readable title from chart anchor text or fallback to URL slug."""

    combined = " ".join(chunk.strip() for chunk in chunks if chunk.strip())
    combined = re.sub(r"\s+", " ", combined).strip()
    combined = re.sub(r"^#?\d+\s*", "", combined)

    if combined and not combined.isdigit():
        return combined

    if slug:
        slug_text = urllib.parse.unquote(slug)
        slug_text = slug_text.replace("_", " ").replace("-", " ")
        slug_text = re.sub(r"\s+", " ", slug_text).strip()
        if slug_text:
            return slug_text

    return f"app_{app_id}"


def parse_rankings_html(html_text: str, *, max_rows: int = 100) -> list[dict[str, int | str]]:
    """Parse app ranking rows from Steam chart HTML."""

    parser = SteamChartsHTMLParser(max_rows=max_rows)
    parser.feed(html_text)
    parser.close()
    return parser.rows


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _title_from_payload_item(*, item: object, app_id: int) -> str:
    if isinstance(item, dict):
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

        store_url_path = item.get("store_url_path")
        if isinstance(store_url_path, str) and store_url_path.strip():
            store_url_path = store_url_path.strip().lstrip("/")
            match = APP_LINK_RE.search(f"/{store_url_path}")
            if match:
                return infer_title_from_chunks(
                    chunks=[],
                    slug=match.group(2) or "",
                    app_id=app_id,
                )

    return f"app_{app_id}"


def parse_rankings_payload(
    payload: object,
    *,
    max_rows: int = 100,
) -> list[dict[str, int | str]]:
    """Parse rank rows from machine-readable Steam rankings payloads."""

    if not isinstance(payload, dict):
        return []

    response = payload.get("response")
    if not isinstance(response, dict):
        return []

    ranks = response.get("ranks")
    if not isinstance(ranks, list):
        return []

    rows: list[dict[str, int | str]] = []
    seen_app_ids: set[int] = set()

    for rank_entry in ranks:
        if len(rows) >= max_rows or not isinstance(rank_entry, dict):
            break

        app_id = _coerce_int(rank_entry.get("appid"))
        item = rank_entry.get("item")
        if app_id is None and isinstance(item, dict):
            app_id = _coerce_int(item.get("appid"))
        if app_id is None and isinstance(item, dict):
            app_id = _coerce_int(item.get("id"))
        if app_id is None or app_id in seen_app_ids:
            continue

        rank = _coerce_int(rank_entry.get("rank")) or len(rows) + 1
        rows.append(
            {
                "rank": rank,
                "app_id": app_id,
                "title": _title_from_payload_item(item=item, app_id=app_id),
            }
        )
        seen_app_ids.add(app_id)

    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Steam probe: chart rankings")
    add_common_probe_arguments(parser)
    parser.set_defaults(out_dir=DEFAULT_RUNTIME_OUT_DIR)
    parser.add_argument("--max-rows", type=int, default=100)
    return parser


def _request_params_for_target(target: RankingTarget) -> dict[str, str]:
    input_json = {
        # Steam requires a country context to enrich ranking rows with store item data.
        "context": {
            "country_code": target.country_code,
            "language": "english",
        },
        "data_request": {
            "include_basic_info": True,
        },
    }
    return {"input_json": json.dumps(input_json, separators=(",", ":"))}


def _decode_rankings_payload(*, body: bytes, target: RankingTarget) -> dict[str, object]:
    payload = decode_json_payload(body)
    if isinstance(payload, dict):
        return payload

    excerpt = text_excerpt(body, max_chars=200)
    raise ValueError(
        f"Steam rankings payload decode failed for {target.probe_name}: "
        f"{excerpt or '<empty body>'}"
    )


def _write_payload(*, path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _resolved_output_paths(*, out_dir: Path | None = None) -> dict[str, Path]:
    if out_dir is None:
        return {target.artifact_key: target.default_output_path for target in TARGETS}
    return {target.artifact_key: out_dir / target.payload_basename for target in TARGETS}


def run(
    *,
    topsellers_global_path: Path = DEFAULT_TOPSELLERS_GLOBAL_PATH,
    topsellers_kr_path: Path = DEFAULT_TOPSELLERS_KR_PATH,
    mostplayed_global_path: Path = DEFAULT_MOSTPLAYED_GLOBAL_PATH,
    mostplayed_kr_path: Path = DEFAULT_MOSTPLAYED_KR_PATH,
    timeout_seconds: float = 10.0,
    max_attempts: int = 4,
    backoff_base_seconds: float = 0.5,
    jitter_max_seconds: float = 0.3,
    max_backoff_seconds: float = 8.0,
    max_rows: int = 100,
) -> list[Path]:
    """Fetch the four Steam ranking payloads and write stable runtime artifacts."""

    output_paths = {
        "topsellers_global": topsellers_global_path,
        "topsellers_kr": topsellers_kr_path,
        "mostplayed_global": mostplayed_global_path,
        "mostplayed_kr": mostplayed_kr_path,
    }
    saved_paths: list[Path] = []

    for target in TARGETS:
        result = request_with_retry(
            url=target.service_url,
            params=_request_params_for_target(target),
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            backoff_base_seconds=backoff_base_seconds,
            jitter_max_seconds=jitter_max_seconds,
            max_backoff_seconds=max_backoff_seconds,
            logger=LOGGER,
        )
        if result.error:
            raise ValueError(f"Steam rankings fetch failed for {target.probe_name}: {result.error}")

        payload = _decode_rankings_payload(body=result.body, target=target)
        parsed_rows = parse_rankings_payload(payload, max_rows=max_rows)
        if not parsed_rows:
            raise ValueError(f"Steam rankings payload produced zero rows for {target.probe_name}")

        output_path = _write_payload(path=output_paths[target.artifact_key], payload=payload)
        saved_paths.append(output_path)
        LOGGER.info(
            "Saved %s payload to %s (rows=%s)",
            target.probe_name,
            output_path,
            len(parsed_rows),
        )

    return saved_paths


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    runtime = runtime_config_from_args(args)
    output_paths = _resolved_output_paths(out_dir=runtime.out_dir)
    saved_paths = run(
        topsellers_global_path=output_paths["topsellers_global"],
        topsellers_kr_path=output_paths["topsellers_kr"],
        mostplayed_global_path=output_paths["mostplayed_global"],
        mostplayed_kr_path=output_paths["mostplayed_kr"],
        timeout_seconds=runtime.timeout_seconds,
        max_attempts=runtime.max_attempts,
        backoff_base_seconds=runtime.backoff_base_seconds,
        jitter_max_seconds=runtime.jitter_max_seconds,
        max_backoff_seconds=runtime.max_backoff_seconds,
        max_rows=args.max_rows,
    )
    LOGGER.info("Saved %s ranking payload artifacts", len(saved_paths))


if __name__ == "__main__":
    main()
