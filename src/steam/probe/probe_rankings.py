"""Probe Steam chart pages and store parsed ranking snapshots."""

from __future__ import annotations

import argparse
import logging
import re
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser

from steam.probe.common import (
    add_common_probe_arguments,
    build_snapshot,
    configure_logging,
    request_with_retry,
    runtime_config_from_args,
    save_snapshot,
    utc_now_iso,
)

LOGGER = logging.getLogger(__name__)
APP_LINK_RE = re.compile(
    r"(?:https?://store\.steampowered\.com)?/app/(\d+)(?:/([^\"'?#<>]*))?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RankingTarget:
    chart: str
    region: str
    url: str

    @property
    def probe_name(self) -> str:
        return f"rankings_{self.chart}_{self.region.lower()}"


TARGETS = (
    RankingTarget(
        chart="topsellers",
        region="global",
        url="https://store.steampowered.com/charts/topsellers/global",
    ),
    RankingTarget(
        chart="topsellers",
        region="KR",
        url="https://store.steampowered.com/charts/topsellers/KR",
    ),
    RankingTarget(
        chart="mostplayed",
        region="global",
        url="https://store.steampowered.com/charts/mostplayed/global",
    ),
    RankingTarget(
        chart="mostplayed",
        region="KR",
        url="https://store.steampowered.com/charts/mostplayed/KR",
    ),
)


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
    parser.add_argument("--max-rows", type=int, default=100)
    return parser


def _payload_from_ranking_response(
    *,
    body: bytes,
    target: RankingTarget,
    max_rows: int,
) -> dict[str, object]:
    html_text = body.decode("utf-8", errors="replace") if body else ""
    return {
        "target": {
            "chart": target.chart,
            "region": target.region,
        },
        "raw_html_excerpt": html_text[:4000] if html_text else None,
        "parsed_rows": parse_rankings_html(html_text, max_rows=max_rows),
    }


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()
    runtime = runtime_config_from_args(args)

    saved_paths = []

    for target in TARGETS:
        result = request_with_retry(
            url=target.url,
            params=None,
            timeout_seconds=runtime.timeout_seconds,
            max_attempts=runtime.max_attempts,
            backoff_base_seconds=runtime.backoff_base_seconds,
            jitter_max_seconds=runtime.jitter_max_seconds,
            max_backoff_seconds=runtime.max_backoff_seconds,
            logger=LOGGER,
        )

        if result.status_code is not None and len(result.body) == 0:
            LOGGER.warning("Empty response body from %s", target.url)

        payload = _payload_from_ranking_response(
            body=result.body,
            target=target,
            max_rows=args.max_rows,
        )

        collected_at_utc = utc_now_iso()
        snapshot = build_snapshot(
            probe_name=target.probe_name,
            collected_at_utc=collected_at_utc,
            request_url=target.url,
            request_params=None,
            timeout_seconds=runtime.timeout_seconds,
            result=result,
            payload_excerpt_or_json=payload,
        )

        output_path = save_snapshot(
            out_dir=runtime.out_dir,
            probe_name=target.probe_name,
            snapshot=snapshot,
        )
        saved_paths.append(output_path)

        if result.error:
            LOGGER.error("Probe %s failed: %s", target.probe_name, result.error)
        else:
            parsed_count = len(payload["parsed_rows"])
            LOGGER.info(
                "Saved %s snapshot to %s (rows=%s)",
                target.probe_name,
                output_path,
                parsed_count,
            )

    LOGGER.info("Saved %s ranking snapshots", len(saved_paths))


if __name__ == "__main__":
    main()
