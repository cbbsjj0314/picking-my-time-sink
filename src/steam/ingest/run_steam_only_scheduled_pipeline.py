"""Run the Steam-only scheduled pipeline in the current manual handoff order."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from steam.ingest import (
    fetch_ccu_30m,
    fetch_price_1h,
    fetch_reviews_daily,
    run_tracked_universe_scheduled,
)
from steam.normalize import (
    bronze_to_silver_ccu,
    bronze_to_silver_price,
    bronze_to_silver_reviews,
    payload_to_gold_rankings,
    silver_to_gold_ccu,
    silver_to_gold_price,
    silver_to_gold_reviews,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_TRACKED_UNIVERSE_RESULT_PATH = (
    run_tracked_universe_scheduled.tracked_universe_core.DEFAULT_RESULT_PATH
)
DEFAULT_RANKINGS_RESULT_PATH = payload_to_gold_rankings.DEFAULT_RESULT_PATH
DEFAULT_PRICE_BRONZE_PATH = Path("tmp/steam/handoff/price.bronze.jsonl")
DEFAULT_PRICE_SILVER_PATH = Path("tmp/steam/handoff/price.silver.jsonl")
DEFAULT_PRICE_GOLD_RESULT_PATH = Path("tmp/steam/handoff/price.gold-result.jsonl")
DEFAULT_REVIEWS_BRONZE_PATH = Path("tmp/steam/handoff/reviews.bronze.jsonl")
DEFAULT_REVIEWS_SILVER_PATH = Path("tmp/steam/handoff/reviews.silver.jsonl")
DEFAULT_REVIEWS_GOLD_RESULT_PATH = Path("tmp/steam/handoff/reviews.gold-result.jsonl")
DEFAULT_CCU_BRONZE_PATH = Path("tmp/steam/handoff/ccu.bronze.jsonl")
DEFAULT_CCU_SILVER_PATH = Path("tmp/steam/handoff/ccu.silver.jsonl")
DEFAULT_CCU_GOLD_RESULT_PATH = Path("tmp/steam/handoff/ccu.gold-result.jsonl")


def configure_logging() -> None:
    """Use the compact logger format shared by the existing scripts."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build a zero-argument parser for the single-command wrapper."""

    return argparse.ArgumentParser(
        description="Run the Steam-only scheduled pipeline with the runbook's fixed order"
    )


def build_fetch_run_kwargs(module: Any, *, output_path: Path) -> dict[str, Any]:
    """Reuse each fetch module's parser defaults when calling its run() helper."""

    args = module.build_parser().parse_args(["--output-path", str(output_path)])
    return {
        "output_path": args.output_path,
        "timeout_seconds": args.timeout_sec,
        "max_attempts": args.max_attempts,
        "backoff_base_seconds": args.backoff_base_sec,
        "jitter_max_seconds": args.jitter_max_sec,
        "max_backoff_seconds": args.max_backoff_sec,
        "meta_path": args.meta_path,
    }


def run(
    *,
    tracked_universe_result_path: Path = DEFAULT_TRACKED_UNIVERSE_RESULT_PATH,
    rankings_result_path: Path = DEFAULT_RANKINGS_RESULT_PATH,
    price_bronze_path: Path = DEFAULT_PRICE_BRONZE_PATH,
    price_silver_path: Path = DEFAULT_PRICE_SILVER_PATH,
    price_gold_result_path: Path = DEFAULT_PRICE_GOLD_RESULT_PATH,
    reviews_bronze_path: Path = DEFAULT_REVIEWS_BRONZE_PATH,
    reviews_silver_path: Path = DEFAULT_REVIEWS_SILVER_PATH,
    reviews_gold_result_path: Path = DEFAULT_REVIEWS_GOLD_RESULT_PATH,
    ccu_bronze_path: Path = DEFAULT_CCU_BRONZE_PATH,
    ccu_silver_path: Path = DEFAULT_CCU_SILVER_PATH,
    ccu_gold_result_path: Path = DEFAULT_CCU_GOLD_RESULT_PATH,
) -> dict[str, list[dict[str, Any]]]:
    """Run the current manual handoff sequence as one fixed-order command."""

    LOGGER.info("Step 1/5: refreshing ranking payloads and updating tracked universe")
    tracked_universe_rows = run_tracked_universe_scheduled.run(
        result_path=tracked_universe_result_path,
    )

    LOGGER.info("Step 2/5: loading ranking payloads into gold")
    rankings_rows = payload_to_gold_rankings.run(
        result_path=rankings_result_path,
    )

    LOGGER.info("Step 3/5: running price fetch -> silver -> gold")
    price_bronze_rows = fetch_price_1h.run(
        **build_fetch_run_kwargs(fetch_price_1h, output_path=price_bronze_path),
    )
    price_silver_rows = bronze_to_silver_price.run(
        input_path=price_bronze_path,
        output_path=price_silver_path,
    )
    price_gold_rows = silver_to_gold_price.run(
        input_path=price_silver_path,
        result_path=price_gold_result_path,
    )

    LOGGER.info("Step 4/5: running reviews fetch -> silver -> gold")
    reviews_bronze_rows = fetch_reviews_daily.run(
        **build_fetch_run_kwargs(fetch_reviews_daily, output_path=reviews_bronze_path),
    )
    reviews_silver_rows = bronze_to_silver_reviews.run(
        input_path=reviews_bronze_path,
        output_path=reviews_silver_path,
    )
    reviews_gold_rows = silver_to_gold_reviews.run(
        input_path=reviews_silver_path,
        result_path=reviews_gold_result_path,
    )

    LOGGER.info("Step 5/5: running CCU fetch -> silver -> gold")
    ccu_bronze_rows = fetch_ccu_30m.run(
        **build_fetch_run_kwargs(fetch_ccu_30m, output_path=ccu_bronze_path),
    )
    ccu_silver_rows = bronze_to_silver_ccu.run(
        input_path=ccu_bronze_path,
        output_path=ccu_silver_path,
    )
    ccu_gold_rows = silver_to_gold_ccu.run(
        input_path=ccu_silver_path,
        result_path=ccu_gold_result_path,
    )

    return {
        "tracked_universe": tracked_universe_rows,
        "rankings": rankings_rows,
        "price_bronze": price_bronze_rows,
        "price_silver": price_silver_rows,
        "price_gold": price_gold_rows,
        "reviews_bronze": reviews_bronze_rows,
        "reviews_silver": reviews_silver_rows,
        "reviews_gold": reviews_gold_rows,
        "ccu_bronze": ccu_bronze_rows,
        "ccu_silver": ccu_silver_rows,
        "ccu_gold": ccu_gold_rows,
    }


def main() -> None:
    """CLI entrypoint for the single-command Steam-only scheduled pipeline."""

    configure_logging()
    build_parser().parse_args()
    results = run()
    LOGGER.info(
        (
            "Completed scheduled pipeline with tracked_universe=%s rankings=%s "
            "price_gold=%s reviews_gold=%s ccu_gold=%s"
        ),
        len(results["tracked_universe"]),
        len(results["rankings"]),
        len(results["price_gold"]),
        len(results["reviews_gold"]),
        len(results["ccu_gold"]),
    )


if __name__ == "__main__":
    main()
