from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import get_args

import pytest

from chzzk.mapping.category_game_candidate_generation import (
    CategoryGameCandidateDryRunProposal,
    ProposalStatus,
    SyntheticAliasHintInput,
    SyntheticChzzkCategoryInput,
    SyntheticSteamGameInput,
    build_category_game_candidate_dry_run_proposals,
)

MODULE_PATH = Path("src/chzzk/mapping/category_game_candidate_generation.py")


def build_proposals(
    *,
    categories: list[SyntheticChzzkCategoryInput],
    games: list[SyntheticSteamGameInput],
    alias_hints: list[SyntheticAliasHintInput] | None = None,
) -> list[CategoryGameCandidateDryRunProposal]:
    return build_category_game_candidate_dry_run_proposals(
        categories=categories,
        games=games,
        alias_hints=alias_hints,
    )


def build_alias_hint(
    *,
    hint_kind: str = "alias",
    category_label: str = "Synthetic Alias A",
    game_name: str = "Synthetic Game A",
    reason: str = "Synthetic Reason A",
    source_note: str = "Synthetic Source Note A",
) -> SyntheticAliasHintInput:
    return SyntheticAliasHintInput(
        hint_kind=hint_kind,
        synthetic_chzzk_category_label=category_label,
        synthetic_canonical_game_name=game_name,
        reason=reason,
        source_note=source_note,
    )


def test_exact_normalized_match_emits_candidate_with_canonical_game_id() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id=" synthetic-category-alpha ",
                category_label="Synthetic Alpha",
            )
        ],
        games=[
            SyntheticSteamGameInput(
                canonical_game_id=1001,
                canonical_name="Synthetic Alpha",
            )
        ],
    )

    assert proposals == [
        CategoryGameCandidateDryRunProposal(
            chzzk_category_id="synthetic-category-alpha",
            status="candidate",
            canonical_game_id=1001,
            match_count=1,
            normalized_category_label="synthetic alpha",
            category_type=None,
            caveats=(),
        )
    ]


def test_no_match_emits_unresolved_without_canonical_game_id() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alpha",
                category_label="Synthetic Alpha",
            )
        ],
        games=[
            SyntheticSteamGameInput(
                canonical_game_id=1002,
                canonical_name="Synthetic Beta",
            )
        ],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None
    assert proposals[0].match_count == 0


def test_ambiguous_duplicate_exact_matches_emit_unresolved_without_selected_id() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-duplicate",
                category_label="Synthetic Duplicate",
            )
        ],
        games=[
            SyntheticSteamGameInput(
                canonical_game_id=1001,
                canonical_name="Synthetic Duplicate",
            ),
            SyntheticSteamGameInput(
                canonical_game_id=1002,
                canonical_name=" synthetic   duplicate ",
            ),
        ],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None
    assert proposals[0].match_count == 2


def test_normalization_uses_strip_casefold_and_whitespace_collapse_only() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alpha",
                category_label="  SYNTHETIC    ALPHA  ",
            )
        ],
        games=[
            SyntheticSteamGameInput(
                canonical_game_id=1001,
                canonical_name="synthetic alpha",
            )
        ],
    )

    assert proposals[0].status == "candidate"
    assert proposals[0].canonical_game_id == 1001
    assert proposals[0].normalized_category_label == "synthetic alpha"


@pytest.mark.parametrize(
    "category_label",
    [
        "Synthetic",
        "Synthetic Alpha Alias",
        "Synthetic-AlphA",
        "Synthetic Alpha!",
        "Alpha Synthetic",
    ],
)
def test_no_fuzzy_alias_partial_or_punctuation_insensitive_matching(
    category_label: str,
) -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alpha",
                category_label=category_label,
            )
        ],
        games=[
            SyntheticSteamGameInput(
                canonical_game_id=1001,
                canonical_name="Synthetic Alpha",
            )
        ],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None


def test_alias_hint_can_emit_untrusted_candidate_with_synthetic_inputs() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alias-a",
                category_label="Synthetic Alias A",
            )
        ],
        games=[SyntheticSteamGameInput(1001, "Synthetic Game A")],
        alias_hints=[build_alias_hint()],
    )

    assert proposals == [
        CategoryGameCandidateDryRunProposal(
            chzzk_category_id="synthetic-category-alias-a",
            status="candidate",
            canonical_game_id=1001,
            match_count=1,
            normalized_category_label="synthetic alias a",
            category_type=None,
            caveats=(),
        )
    ]


def test_manual_hint_can_emit_untrusted_candidate_with_synthetic_inputs() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-manual-hint-a",
                category_label="Synthetic Manual Hint A",
            )
        ],
        games=[SyntheticSteamGameInput(1001, "Synthetic Game A")],
        alias_hints=[
            build_alias_hint(
                hint_kind="manual_hint",
                category_label="Synthetic Manual Hint A",
            )
        ],
    )

    assert proposals[0].status == "candidate"
    assert proposals[0].canonical_game_id == 1001
    assert proposals[0].match_count == 1


def test_alias_hint_pointing_to_missing_synthetic_game_stays_unresolved() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alias-a",
                category_label="Synthetic Alias A",
            )
        ],
        games=[SyntheticSteamGameInput(1001, "Synthetic Game B")],
        alias_hints=[build_alias_hint(game_name="Synthetic Game A")],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None
    assert proposals[0].match_count == 0


def test_multiple_distinct_alias_hint_targets_stay_unresolved() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alias-a",
                category_label="Synthetic Alias A",
            )
        ],
        games=[
            SyntheticSteamGameInput(1001, "Synthetic Game A"),
            SyntheticSteamGameInput(1002, "Synthetic Game B"),
        ],
        alias_hints=[
            build_alias_hint(game_name="Synthetic Game A"),
            build_alias_hint(
                hint_kind="manual_hint",
                game_name="Synthetic Game B",
            ),
        ],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None
    assert proposals[0].match_count == 2


def test_exact_match_and_alias_hint_disagreement_stays_unresolved() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-a",
                category_label="Synthetic Game A",
            )
        ],
        games=[
            SyntheticSteamGameInput(1001, "Synthetic Game A"),
            SyntheticSteamGameInput(1002, "Synthetic Game B"),
        ],
        alias_hints=[
            build_alias_hint(
                category_label="Synthetic Game A",
                game_name="Synthetic Game B",
            )
        ],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None
    assert proposals[0].match_count == 2


def test_exact_match_and_alias_hint_agreement_preserves_candidate() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-a",
                category_label="Synthetic Game A",
            )
        ],
        games=[SyntheticSteamGameInput(1001, "Synthetic Game A")],
        alias_hints=[
            build_alias_hint(
                category_label="Synthetic Game A",
                game_name="Synthetic Game A",
            )
        ],
    )

    assert proposals[0].status == "candidate"
    assert proposals[0].canonical_game_id == 1001
    assert proposals[0].match_count == 1


def test_duplicate_synthetic_game_names_do_not_auto_select_hint_winner() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alias-a",
                category_label="Synthetic Alias A",
            )
        ],
        games=[
            SyntheticSteamGameInput(1001, "Synthetic Game A"),
            SyntheticSteamGameInput(1002, "Synthetic Game A"),
        ],
        alias_hints=[build_alias_hint(game_name="Synthetic Game A")],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None
    assert proposals[0].match_count == 2


def test_category_type_game_does_not_create_identity() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alpha",
                category_label="Synthetic Alpha",
                category_type="GAME",
            )
        ],
        games=[
            SyntheticSteamGameInput(
                canonical_game_id=1002,
                canonical_name="Synthetic Beta",
            )
        ],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None
    assert proposals[0].match_count == 0
    assert proposals[0].category_type == "GAME"
    assert proposals[0].caveats == ("category_type_is_provider_evidence_only",)


def test_non_game_category_type_is_not_silently_filtered_or_reclassified() -> None:
    non_game = SyntheticChzzkCategoryInput(
        chzzk_category_id="synthetic-category-alpha",
        category_label="Synthetic Alpha",
        category_type="ENTERTAINMENT",
    )
    game = SyntheticChzzkCategoryInput(
        chzzk_category_id="synthetic-category-beta",
        category_label="Synthetic Alpha",
        category_type="GAME",
    )

    proposals = build_proposals(
        categories=[non_game, game],
        games=[
            SyntheticSteamGameInput(
                canonical_game_id=1001,
                canonical_name="Synthetic Alpha",
            )
        ],
    )

    assert [proposal.status for proposal in proposals] == ["candidate", "candidate"]
    assert [proposal.canonical_game_id for proposal in proposals] == [1001, 1001]
    assert [proposal.match_count for proposal in proposals] == [1, 1]
    assert proposals[0].category_type == "ENTERTAINMENT"
    assert proposals[1].category_type == "GAME"


def test_blank_category_type_is_reported_as_none_without_caveat() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alpha",
                category_label="Synthetic Alpha",
                category_type="   ",
            )
        ],
        games=[
            SyntheticSteamGameInput(
                canonical_game_id=1001,
                canonical_name="Synthetic Alpha",
            )
        ],
    )

    assert proposals[0].category_type is None
    assert proposals[0].caveats == ()


def test_rejected_is_not_a_dry_run_generation_status() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alpha",
                category_label="Synthetic Alpha",
            ),
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-beta",
                category_label="Synthetic Beta",
            ),
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-duplicate",
                category_label="Synthetic Duplicate",
            ),
        ],
        games=[
            SyntheticSteamGameInput(1001, "Synthetic Alpha"),
            SyntheticSteamGameInput(1002, "Synthetic Duplicate"),
            SyntheticSteamGameInput(1003, "Synthetic Duplicate"),
        ],
    )

    assert set(get_args(ProposalStatus)) == {"candidate", "unresolved"}
    assert {proposal.status for proposal in proposals} == {"candidate", "unresolved"}
    assert all(proposal.status != "rejected" for proposal in proposals)


def test_trusted_and_approved_never_appear_in_dry_run_outputs() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alias-a",
                category_label="Synthetic Alias A",
            )
        ],
        games=[SyntheticSteamGameInput(1001, "Synthetic Game A")],
        alias_hints=[build_alias_hint()],
    )

    assert set(get_args(ProposalStatus)) == {"candidate", "unresolved"}
    serialized = repr(proposals).casefold()
    assert "trusted" not in serialized
    assert "approved" not in serialized
    assert all(proposal.status not in {"trusted", "approved"} for proposal in proposals)


def test_alias_hint_input_metadata_is_required_but_not_exposed_in_output() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alias-a",
                category_label="Synthetic Alias A",
            )
        ],
        games=[SyntheticSteamGameInput(1001, "Synthetic Game A")],
        alias_hints=[
            build_alias_hint(
                reason="Synthetic Reason A",
                source_note="Synthetic Source Note A",
            )
        ],
    )

    output_field_names = {
        field.name for field in fields(CategoryGameCandidateDryRunProposal)
    }
    output_repr = repr(proposals)
    assert "reason" not in output_field_names
    assert "source_note" not in output_field_names
    assert "Synthetic Reason A" not in output_repr
    assert "Synthetic Source Note A" not in output_repr


def test_alias_manual_hint_output_remains_untrusted_review_evidence_only() -> None:
    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alias-a",
                category_label="Synthetic Alias A",
            )
        ],
        games=[SyntheticSteamGameInput(1001, "Synthetic Game A")],
        alias_hints=[build_alias_hint()],
    )

    assert proposals[0].status == "candidate"
    assert proposals[0].caveats == ()
    assert set(get_args(ProposalStatus)) == {"candidate", "unresolved"}


@pytest.mark.parametrize(
    ("category", "error"),
    [
        (
            SyntheticChzzkCategoryInput(
                chzzk_category_id=" ",
                category_label="Synthetic Alpha",
            ),
            "blank_chzzk_category_id",
        ),
        (
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alpha",
                category_label=" ",
            ),
            "blank_category_label",
        ),
    ],
)
def test_invalid_synthetic_category_input_is_rejected(
    category: SyntheticChzzkCategoryInput,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        build_proposals(
            categories=[category],
            games=[SyntheticSteamGameInput(1001, "Synthetic Alpha")],
        )


@pytest.mark.parametrize(
    ("game", "error"),
    [
        (SyntheticSteamGameInput(1001, " "), "blank_canonical_name"),
        (SyntheticSteamGameInput(0, "Synthetic Alpha"), "invalid_canonical_game_id"),
        (SyntheticSteamGameInput(-1, "Synthetic Alpha"), "invalid_canonical_game_id"),
        (
            SyntheticSteamGameInput(None, "Synthetic Alpha"),  # type: ignore[arg-type]
            "invalid_canonical_game_id",
        ),
        (
            SyntheticSteamGameInput(True, "Synthetic Alpha"),
            "invalid_canonical_game_id",
        ),
        (
            SyntheticSteamGameInput("1001", "Synthetic Alpha"),  # type: ignore[arg-type]
            "invalid_canonical_game_id",
        ),
        (
            SyntheticSteamGameInput(1001.0, "Synthetic Alpha"),  # type: ignore[arg-type]
            "invalid_canonical_game_id",
        ),
    ],
)
def test_invalid_synthetic_game_input_is_rejected(
    game: SyntheticSteamGameInput,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        build_proposals(
            categories=[
                SyntheticChzzkCategoryInput(
                    chzzk_category_id="synthetic-category-alpha",
                    category_label="Synthetic Alpha",
                )
            ],
            games=[game],
        )


@pytest.mark.parametrize(
    ("hint", "error"),
    [
        (build_alias_hint(hint_kind="synthetic_other"), "invalid_hint_kind"),
        (
            build_alias_hint(category_label=" "),
            "blank_synthetic_chzzk_category_label",
        ),
        (
            build_alias_hint(game_name=" "),
            "blank_synthetic_canonical_game_name",
        ),
        (build_alias_hint(reason=" "), "blank_reason"),
        (build_alias_hint(source_note=" "), "blank_source_note"),
        (
            SyntheticAliasHintInput(
                hint_kind=1,  # type: ignore[arg-type]
                synthetic_chzzk_category_label="Synthetic Alias A",
                synthetic_canonical_game_name="Synthetic Game A",
                reason="Synthetic Reason A",
                source_note="Synthetic Source Note A",
            ),
            "invalid_hint_kind",
        ),
        (
            SyntheticAliasHintInput(
                hint_kind="alias",
                synthetic_chzzk_category_label=1,  # type: ignore[arg-type]
                synthetic_canonical_game_name="Synthetic Game A",
                reason="Synthetic Reason A",
                source_note="Synthetic Source Note A",
            ),
            "blank_synthetic_chzzk_category_label",
        ),
        (
            SyntheticAliasHintInput(
                hint_kind="alias",
                synthetic_chzzk_category_label="Synthetic Alias A",
                synthetic_canonical_game_name=1,  # type: ignore[arg-type]
                reason="Synthetic Reason A",
                source_note="Synthetic Source Note A",
            ),
            "blank_synthetic_canonical_game_name",
        ),
        (
            SyntheticAliasHintInput(
                hint_kind="alias",
                synthetic_chzzk_category_label="Synthetic Alias A",
                synthetic_canonical_game_name="Synthetic Game A",
                reason=1,  # type: ignore[arg-type]
                source_note="Synthetic Source Note A",
            ),
            "blank_reason",
        ),
        (
            SyntheticAliasHintInput(
                hint_kind="alias",
                synthetic_chzzk_category_label="Synthetic Alias A",
                synthetic_canonical_game_name="Synthetic Game A",
                reason="Synthetic Reason A",
                source_note=1,  # type: ignore[arg-type]
            ),
            "blank_source_note",
        ),
    ],
)
def test_invalid_synthetic_alias_hint_input_is_rejected(
    hint: SyntheticAliasHintInput,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        build_proposals(
            categories=[
                SyntheticChzzkCategoryInput(
                    chzzk_category_id="synthetic-category-alias-a",
                    category_label="Synthetic Alias A",
                )
            ],
            games=[SyntheticSteamGameInput(1001, "Synthetic Game A")],
            alias_hints=[hint],
        )


def test_no_fuzzy_or_automatic_alias_discovery_fields_or_behavior_exists() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden_needles = [
        "similarity",
        "score",
        "phonetic",
        "transliteration",
        "levenshtein",
        "rapidfuzz",
        "difflib",
        "automatic alias discovery",
    ]
    for needle in forbidden_needles:
        assert needle not in source

    proposals = build_proposals(
        categories=[
            SyntheticChzzkCategoryInput(
                chzzk_category_id="synthetic-category-alias-a",
                category_label="Synthetic Alias A",
            )
        ],
        games=[SyntheticSteamGameInput(1001, "Synthetic Game A")],
    )

    assert proposals[0].status == "unresolved"
    assert proposals[0].canonical_game_id is None


def test_builder_source_has_no_db_api_runtime_service_or_serving_coupling() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    lowered = source.lower()

    forbidden_needles = [
        "insert_chzzk_category_game_candidate_row",
        "insert into chzzk_category_game_candidate",
        "insert_chzzk_category_game_candidate_sql",
        "psycopg",
        "cursor",
        "connection",
        "build_pg_conninfo_from_env",
        "api.",
        "router",
        "service",
        "scheduler",
        "runtime",
        "provider/live",
        "live fetch",
        "game_external_id",
        "tracked_universe",
        "app catalog",
        "combined",
        "web/",
        "raw_provider_payload",
    ]
    for needle in forbidden_needles:
        assert needle not in lowered


def test_builder_source_contains_only_synthetic_public_safe_example_terms() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8").lower()

    forbidden_needles = [
        "channel_name",
        "display",
        "live_title",
        "thumbnail",
        "raw api response",
        "credential",
        "secret",
        ".env",
        "private path",
    ]
    for needle in forbidden_needles:
        assert needle not in source
