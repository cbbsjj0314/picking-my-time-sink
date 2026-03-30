"""Run tracked universe updates from explicit ranking artifacts."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import steam.ingest.update_tracked_universe as tracked_universe_core
import steam.probe.probe_rankings as rankings_probe

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the scheduled tracked universe wrapper."""

    parser = argparse.ArgumentParser(
        description="Run tracked universe scheduled updater from ranking artifacts"
    )
    parser.add_argument(
        "--topsellers-global-path",
        type=Path,
        default=rankings_probe.DEFAULT_TOPSELLERS_GLOBAL_PATH,
    )
    parser.add_argument(
        "--topsellers-kr-path",
        type=Path,
        default=rankings_probe.DEFAULT_TOPSELLERS_KR_PATH,
    )
    parser.add_argument(
        "--mostplayed-global-path",
        type=Path,
        default=rankings_probe.DEFAULT_MOSTPLAYED_GLOBAL_PATH,
    )
    parser.add_argument(
        "--mostplayed-kr-path",
        type=Path,
        default=rankings_probe.DEFAULT_MOSTPLAYED_KR_PATH,
    )
    parser.add_argument("--app-catalog-path", type=Path, default=None)
    parser.add_argument(
        "--result-path",
        type=Path,
        default=tracked_universe_core.DEFAULT_RESULT_PATH,
    )
    return parser


def run(
    *,
    topsellers_global_path: Path = rankings_probe.DEFAULT_TOPSELLERS_GLOBAL_PATH,
    topsellers_kr_path: Path = rankings_probe.DEFAULT_TOPSELLERS_KR_PATH,
    mostplayed_global_path: Path = rankings_probe.DEFAULT_MOSTPLAYED_GLOBAL_PATH,
    mostplayed_kr_path: Path = rankings_probe.DEFAULT_MOSTPLAYED_KR_PATH,
    app_catalog_path: Path | None = None,
    result_path: Path = tracked_universe_core.DEFAULT_RESULT_PATH,
) -> list[dict[str, Any]]:
    """Refresh ranking payload artifacts, then delegate to the core updater."""

    rankings_probe.run(
        topsellers_global_path=topsellers_global_path,
        topsellers_kr_path=topsellers_kr_path,
        mostplayed_global_path=mostplayed_global_path,
        mostplayed_kr_path=mostplayed_kr_path,
    )

    return tracked_universe_core.run(
        topsellers_global_path=topsellers_global_path,
        topsellers_kr_path=topsellers_kr_path,
        mostplayed_global_path=mostplayed_global_path,
        mostplayed_kr_path=mostplayed_kr_path,
        app_catalog_path=app_catalog_path,
        result_path=result_path,
    )


def main() -> None:
    tracked_universe_core.configure_logging()
    args = build_parser().parse_args()
    results = run(
        topsellers_global_path=args.topsellers_global_path,
        topsellers_kr_path=args.topsellers_kr_path,
        mostplayed_global_path=args.mostplayed_global_path,
        mostplayed_kr_path=args.mostplayed_kr_path,
        app_catalog_path=args.app_catalog_path,
        result_path=args.result_path,
    )
    LOGGER.info("Wrote %s tracked universe result rows to %s", len(results), args.result_path)


if __name__ == "__main__":
    main()
