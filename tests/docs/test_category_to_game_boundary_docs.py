from __future__ import annotations

from pathlib import Path

CATEGORY_MAPPING_CONTRACT = Path("docs/decisions/category-to-game-mapping-contract.md")
CANDIDATE_GENERATION_GATE = Path(
    "docs/decisions/category-to-game-candidate-generation-gate.md"
)
COMBINED_READINESS_CONTRACT = Path(
    "docs/decisions/combined-source-view-readiness-contract.md"
)
DATA_GOVERNANCE = Path("docs/data-governance.md")
DATA_MODEL_SPEC = Path("docs/data-model-spec.md")
IMPLEMENTATION_SURFACE_REVIEW = Path(
    "docs/decisions/category-to-game-implementation-surface-review.md"
)
STORAGE_CONTRACT = Path("docs/decisions/category-to-game-storage-contract-planning.md")


def _read_lower(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def _near(text: str, needle: str, *, span: int = 360) -> str:
    index = text.index(needle.lower())
    return text[max(0, index - span) : index + len(needle) + span]


def _state_definition_context(text: str, state: str) -> str:
    return _near(text, f"- `{state}`:", span=360)


def test_mapping_contract_keeps_review_states_untrusted() -> None:
    text = _read_lower(CATEGORY_MAPPING_CONTRACT)

    candidate_context = _state_definition_context(text, "candidate")
    unresolved_context = _state_definition_context(text, "unresolved")
    rejected_context = _state_definition_context(text, "rejected")

    assert "trusted mapping" in candidate_context
    assert "combined kpi" in candidate_context
    assert "canonical game semantics" in candidate_context

    assert "guessed mapping" in unresolved_context
    assert "automatic matching" in unresolved_context
    assert "auto-promotion" in unresolved_context

    assert "trusted mapping" in rejected_context


def test_mapping_contract_keeps_trusted_approved_future_only() -> None:
    text = _read_lower(CATEGORY_MAPPING_CONTRACT)

    context = _near(text, "`trusted` / `approved`")

    assert "future" in context
    assert "persisted state" in context
    assert "schema value" in context
    assert "api field" in context
    assert "ui field" in context


def test_candidate_evidence_is_blocked_from_combined_and_serving_semantics() -> None:
    mapping_text = _read_lower(CATEGORY_MAPPING_CONTRACT)
    combined_text = _read_lower(COMBINED_READINESS_CONTRACT)

    mapping_context = _near(mapping_text, "candidate evidence")
    combined_context = _near(combined_text, "`candidate`, `unresolved`, `rejected`")

    assert "combined kpi" in mapping_context
    assert "canonical game semantics" in mapping_context
    assert "serving semantics" in mapping_context

    assert "combined" in combined_context
    assert "kpi" in combined_context
    assert "ranking" in combined_context
    assert "sorting" in combined_context
    assert "game identity" in combined_context


def test_public_docs_keep_raw_runtime_evidence_out_of_contract_boundary() -> None:
    text = "\n".join(
        [
            _read_lower(CATEGORY_MAPPING_CONTRACT),
            _read_lower(IMPLEMENTATION_SURFACE_REVIEW),
            _read_lower(DATA_GOVERNANCE),
        ]
    )

    assert "public docs" in text
    assert "local/private" in text
    assert "raw provider" in text
    assert "credentials" in text
    assert "private runtime" in text
    assert "row-level ugc" in text


def test_candidate_storage_foundation_remains_untrusted_and_non_serving() -> None:
    text = "\n".join(
        [
            _read_lower(DATA_MODEL_SPEC),
            _read_lower(DATA_GOVERNANCE),
            _read_lower(STORAGE_CONTRACT),
        ]
    )

    context = _near(text, "chzzk_category_game_candidate", span=1200)

    assert "candidate-only" in context
    assert "review" in context
    assert "candidate" in context
    assert "unresolved" in context
    assert "rejected" in context
    assert "untrusted" in context
    assert "trusted mapping" in context
    assert "automatic matching" in context
    assert "promotion/demotion" in context
    assert "serving semantics" in context
    assert "combined" in context
    assert "game_external_id" in context


def test_candidate_generation_gate_allows_only_synthetic_dry_run_builder() -> None:
    text = _read_lower(CANDIDATE_GENERATION_GATE)

    decision_context = _near(text, "first implementation may proceed", span=900)
    category_type_context = _near(text, "`category_type=game`", span=720)
    normalization_context = _near(text, "allowed normalization", span=720)
    next_ticket_context = _near(
        text,
        "category-mapping-candidate-generation-dry-run-001",
        span=520,
    )

    assert "db-write-free synthetic/test-only dry-run proposal builder" in text
    assert "real observed chzzk data read는 하지 않는다" in text
    assert "chzzk_category_game_candidate" in text
    assert "insert하지 않는다" in text

    assert "normalized exact match count가 정확히 1개" in text
    assert "0개이거나 2개 이상" in text
    assert "rejected" in text
    assert "자동 생성하지 않는다" in text

    assert "strip" in text
    assert "casefold" in text
    assert "whitespace collapse" in text
    assert "fuzzy matching" in normalization_context
    assert "alias matching" in normalization_context
    assert "partial matching" in normalization_context
    assert "similarity score" in normalization_context
    assert "manual hints" in normalization_context

    assert "provider category type evidence" in category_type_context
    assert "canonical identity" in category_type_context
    assert "non-identity caveat/counter" in category_type_context
    assert "조용히 filter" in category_type_context

    assert "api/web response shape를 정의하지 않는다" in text
    assert "serving semantics를 정의하지 않는다" in text
    assert "`combined` semantics를 정의하지 않는다" in text
    assert "synthetic/test-only dry-run proposal builder" in next_ticket_context
