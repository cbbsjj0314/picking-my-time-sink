"""Candidate-only Chzzk category-to-game storage helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

CandidateStatus = Literal["candidate", "unresolved", "rejected"]

ALLOWED_CANDIDATE_STATUSES: frozenset[str] = frozenset(
    {"candidate", "unresolved", "rejected"}
)

INSERT_CHZZK_CATEGORY_GAME_CANDIDATE_SQL = """
INSERT INTO chzzk_category_game_candidate (
    chzzk_category_id,
    canonical_game_id,
    status
)
VALUES (%s, %s, %s)
RETURNING candidate_id
"""


@dataclass(frozen=True, slots=True)
class ChzzkCategoryGameCandidateRow:
    """Review-only candidate row input for Chzzk category-to-game storage."""

    chzzk_category_id: str
    status: CandidateStatus
    canonical_game_id: int | None = None


def _normalize_category_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("blank_chzzk_category_id")
    return normalized


def _normalize_status(value: str) -> CandidateStatus:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_CANDIDATE_STATUSES:
        raise ValueError("invalid_candidate_status")
    return cast(CandidateStatus, normalized)


def _normalize_canonical_game_id(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("invalid_canonical_game_id")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_canonical_game_id") from exc
    if normalized <= 0:
        raise ValueError("invalid_canonical_game_id")
    return normalized


def build_chzzk_category_game_candidate_row(
    *,
    chzzk_category_id: str,
    status: str,
    canonical_game_id: int | None = None,
) -> ChzzkCategoryGameCandidateRow:
    """Validate and build one candidate-only storage row."""

    normalized_status = _normalize_status(status)
    normalized_game_id = _normalize_canonical_game_id(canonical_game_id)

    if normalized_status in {"candidate", "rejected"} and normalized_game_id is None:
        raise ValueError("specific_candidate_requires_canonical_game_id")

    return ChzzkCategoryGameCandidateRow(
        chzzk_category_id=_normalize_category_id(chzzk_category_id),
        canonical_game_id=normalized_game_id,
        status=normalized_status,
    )


def build_sanitized_candidate_summary(
    rows: list[ChzzkCategoryGameCandidateRow],
) -> dict[str, object]:
    """Return aggregate-only row counts without provider display values."""

    return {
        "candidate_row_count": len(rows),
        "category_count": len({row.chzzk_category_id for row in rows}),
        "specific_candidate_count": sum(
            1 for row in rows if row.canonical_game_id is not None
        ),
        "unresolved_without_game_count": sum(
            1
            for row in rows
            if row.status == "unresolved" and row.canonical_game_id is None
        ),
        "status_counts": {
            status: sum(1 for row in rows if row.status == status)
            for status in sorted(ALLOWED_CANDIDATE_STATUSES)
        },
    }


def insert_chzzk_category_game_candidate_row(
    cursor: Any,
    *,
    row: ChzzkCategoryGameCandidateRow,
) -> int | None:
    """Insert one already-validated candidate row through an injected cursor."""

    cursor.execute(
        INSERT_CHZZK_CATEGORY_GAME_CANDIDATE_SQL,
        (row.chzzk_category_id, row.canonical_game_id, row.status),
    )
    inserted = cursor.fetchone()
    if inserted is None:
        return None
    if isinstance(inserted, dict):
        return int(inserted["candidate_id"])
    return int(inserted[0])
