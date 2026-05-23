from __future__ import annotations

from pathlib import Path

CATEGORY_MAPPING_CONTRACT = Path("docs/decisions/category-to-game-mapping-contract.md")
CANDIDATE_GENERATION_GATE = Path(
    "docs/decisions/category-to-game-candidate-generation-gate.md"
)
REAL_DATA_PROPOSAL_SMOKE_GATE = Path(
    "docs/decisions/category-to-game-real-data-proposal-smoke-gate.md"
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


def test_real_data_proposal_smoke_gate_is_read_only_sanitized_and_non_serving() -> None:
    text = _read_lower(REAL_DATA_PROPOSAL_SMOKE_GATE)

    decision_context = _near(
        text,
        "the next implementation may be opened only as a read-only, no-write, "
        "sanitized real observed-data proposal smoke",
        span=900,
    )
    future_ticket_context = _near(
        text,
        "category-mapping-candidate-real-data-proposal-smoke-001",
        span=1400,
    )
    matching_context = _near(text, "allowed normalization", span=1200)
    output_context = _near(text, "future smoke output은 아래 항목을 포함할 수 없다", span=1200)

    assert "이 gate는 실제 smoke를 실행하지 않는다" in text
    assert "api call" in text
    assert "db query" in text
    assert "data capture" in text

    assert "read-only" in decision_context
    assert "no-write" in decision_context
    assert "sanitized" in decision_context
    assert "arbitrary local data access를 승인하지 않는다" in decision_context
    assert "read-only command" in decision_context
    assert "read-only path" in decision_context

    assert "future ticket에 명시된 read-only command" in future_ticket_context
    assert "already 실행 중인 read-only `/chzzk/categories/overview`" not in text
    assert "이미 실행 중인 read-only `/chzzk/categories/overview`" in text
    assert "service를 새로 시작하거나 변경하지 않는다" in text
    assert "sanitized aggregate proposal summary only" in text

    assert "db write" in text
    assert "insert into `chzzk_category_game_candidate`" in text
    assert "trusted mapping" in text
    assert "`game_external_id`" in text
    assert "tracked_universe" in text
    assert "app catalog" in text
    assert "api/web/serving exposure" in text
    assert "`combined`" in text
    assert "live fetch" in text
    assert "scheduler mutation" in text
    assert "schema/ddl changes" in text

    assert "raw category names" in output_context
    assert "raw game names" in output_context
    assert "channel names" in output_context
    assert "display names" in output_context
    assert "live titles" in output_context
    assert "thumbnails" in output_context
    assert "raw provider payloads" in output_context
    assert "raw api response" in output_context
    assert "raw sql output" in output_context
    assert "credentials or `.env` values" in output_context

    assert "strip" in matching_context
    assert "casefold" in matching_context
    assert "whitespace collapse" in matching_context
    assert "fuzzy matching" in matching_context
    assert "alias matching" in matching_context
    assert "partial matching" in matching_context
    assert "punctuation-insensitive matching" in matching_context
    assert "similarity score" in matching_context
    assert "manual hints" in matching_context
    assert "`candidate`: exactly one normalized exact match" in text
    assert "`unresolved`: zero matches or two or more matches" in text
    assert "`rejected`: not generated automatically" in text
    assert "`category_type=game`은 provider category type evidence only" in text
