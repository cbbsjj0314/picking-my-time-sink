"""Synthetic-only dry-run Chzzk category-to-game candidate proposal builder."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

ProposalStatus = Literal["candidate", "unresolved"]
AliasHintKind = Literal["alias", "manual_hint"]


@dataclass(frozen=True, slots=True)
class SyntheticChzzkCategoryInput:
    """Synthetic Chzzk category input for dry-run proposal tests."""

    chzzk_category_id: str
    category_label: str
    category_type: str | None = None


@dataclass(frozen=True, slots=True)
class SyntheticSteamGameInput:
    """Synthetic dim_game-like input for dry-run proposal tests."""

    canonical_game_id: int
    canonical_name: str


@dataclass(frozen=True, slots=True)
class SyntheticAliasHintInput:
    """Synthetic alias/manual hint input for dry-run proposal tests."""

    hint_kind: str
    synthetic_chzzk_category_label: str
    synthetic_canonical_game_name: str
    reason: str
    source_note: str


@dataclass(frozen=True, slots=True)
class CategoryGameCandidateDryRunProposal:
    """Dry-run proposal output; not a storage row shape."""

    chzzk_category_id: str
    status: ProposalStatus
    canonical_game_id: int | None
    match_count: int
    normalized_category_label: str
    category_type: str | None
    caveats: tuple[str, ...]


def _normalize_exact_match_value(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _normalize_category_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("blank_chzzk_category_id")
    return normalized


def _normalize_category_label(value: str) -> str:
    normalized = _normalize_exact_match_value(value)
    if not normalized:
        raise ValueError("blank_category_label")
    return normalized


def _normalize_category_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_canonical_name(value: str) -> str:
    normalized = _normalize_exact_match_value(value)
    if not normalized:
        raise ValueError("blank_canonical_name")
    return normalized


def _normalize_canonical_game_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("invalid_canonical_game_id")
    if value <= 0:
        raise ValueError("invalid_canonical_game_id")
    return value


def _normalize_hint_kind(value: str) -> AliasHintKind:
    if not isinstance(value, str):
        raise ValueError("invalid_hint_kind")
    normalized = value.strip()
    if normalized not in {"alias", "manual_hint"}:
        raise ValueError("invalid_hint_kind")
    return normalized


def _normalize_synthetic_chzzk_category_label(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("blank_synthetic_chzzk_category_label")
    normalized = _normalize_exact_match_value(value)
    if not normalized:
        raise ValueError("blank_synthetic_chzzk_category_label")
    return normalized


def _normalize_synthetic_canonical_game_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("blank_synthetic_canonical_game_name")
    normalized = _normalize_exact_match_value(value)
    if not normalized:
        raise ValueError("blank_synthetic_canonical_game_name")
    return normalized


def _normalize_required_synthetic_note(value: str, *, error: str) -> str:
    if not isinstance(value, str):
        raise ValueError(error)
    normalized = value.strip()
    if not normalized:
        raise ValueError(error)
    return normalized


def _category_type_caveats(category_type: str | None) -> tuple[str, ...]:
    if category_type is None:
        return ()
    return ("category_type_is_provider_evidence_only",)


def build_category_game_candidate_dry_run_proposals(
    *,
    categories: Sequence[SyntheticChzzkCategoryInput],
    games: Sequence[SyntheticSteamGameInput],
    alias_hints: Sequence[SyntheticAliasHintInput] | None = None,
) -> list[CategoryGameCandidateDryRunProposal]:
    """Build synthetic dry-run proposals with deterministic review-only hints."""

    game_ids_by_normalized_name: dict[str, list[int]] = {}
    for game in games:
        canonical_game_id = _normalize_canonical_game_id(game.canonical_game_id)
        normalized_name = _normalize_canonical_name(game.canonical_name)
        game_ids_by_normalized_name.setdefault(normalized_name, []).append(
            canonical_game_id
        )

    hinted_game_names_by_category_label: dict[str, set[str]] = {}
    for hint in alias_hints or ():
        _normalize_hint_kind(hint.hint_kind)
        normalized_category_label = _normalize_synthetic_chzzk_category_label(
            hint.synthetic_chzzk_category_label
        )
        normalized_game_name = _normalize_synthetic_canonical_game_name(
            hint.synthetic_canonical_game_name
        )
        _normalize_required_synthetic_note(hint.reason, error="blank_reason")
        _normalize_required_synthetic_note(hint.source_note, error="blank_source_note")
        hinted_game_names_by_category_label.setdefault(
            normalized_category_label,
            set(),
        ).add(normalized_game_name)

    proposals: list[CategoryGameCandidateDryRunProposal] = []
    for category in categories:
        chzzk_category_id = _normalize_category_id(category.chzzk_category_id)
        normalized_label = _normalize_category_label(category.category_label)
        category_type = _normalize_category_type(category.category_type)
        exact_matches = game_ids_by_normalized_name.get(normalized_label, [])
        hinted_names = hinted_game_names_by_category_label.get(normalized_label, set())
        hinted_matches: list[int] = []
        hint_has_unresolved_target = False
        for hinted_name in hinted_names:
            target_matches = game_ids_by_normalized_name.get(hinted_name, [])
            if len(target_matches) != 1:
                hint_has_unresolved_target = True
            hinted_matches.extend(target_matches)

        matches = sorted({*exact_matches, *hinted_matches})
        match_count = len(matches)

        has_hint_conflict = (
            len(hinted_names) > 1
            or hint_has_unresolved_target
            or len(exact_matches) > 1
            or (
                len(exact_matches) == 1
                and bool(hinted_names)
                and matches != exact_matches
            )
        )
        status: ProposalStatus = (
            "candidate" if match_count == 1 and not has_hint_conflict else "unresolved"
        )
        canonical_game_id = matches[0] if status == "candidate" else None

        proposals.append(
            CategoryGameCandidateDryRunProposal(
                chzzk_category_id=chzzk_category_id,
                status=status,
                canonical_game_id=canonical_game_id,
                match_count=match_count,
                normalized_category_label=normalized_label,
                category_type=category_type,
                caveats=_category_type_caveats(category_type),
            )
        )

    return proposals
