from __future__ import annotations

from pathlib import Path

CATEGORY_MAPPING_CONTRACT = Path("docs/decisions/category-to-game-mapping-contract.md")
CANDIDATE_GENERATION_GATE = Path(
    "docs/decisions/category-to-game-candidate-generation-gate.md"
)
REAL_DATA_PROPOSAL_SMOKE_GATE = Path(
    "docs/decisions/category-to-game-real-data-proposal-smoke-gate.md"
)
NON_EXACT_MATCHING_GATE = Path(
    "docs/decisions/category-to-game-non-exact-matching-gate.md"
)
ALIAS_HINT_CONTRACT_GATE = Path(
    "docs/decisions/category-to-game-alias-hint-contract-gate.md"
)
ALIAS_HINT_REAL_DATA_GATE = Path(
    "docs/decisions/category-to-game-alias-hint-real-data-gate.md"
)
ALIAS_HINT_SEEDING_ASSIST_GATE = Path(
    "docs/decisions/category-to-game-alias-hint-seeding-assist-gate.md"
)
COMBINED_READINESS_CONTRACT = Path(
    "docs/decisions/combined-source-view-readiness-contract.md"
)
DATA_GOVERNANCE = Path("docs/data-governance.md")
DATA_MODEL_SPEC = Path("docs/data-model-spec.md")
SOURCE_INVENTORY = Path("docs/source-inventory.md")
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


def test_mapping_contract_scopes_trusted_schema_update_without_serving() -> None:
    text = _read_lower(CATEGORY_MAPPING_CONTRACT)

    context = _near(text, "`trusted` / `approved`")
    update_context = _near(
        text,
        "category-mapping-trusted-storage-contract-001 이후에도",
        span=900,
    )

    assert "future" in context
    assert "persisted state" in context
    assert "schema value" in context
    assert "api field" in context
    assert "ui field" in context

    assert "chzzk_category_game_mapping.mapping_status" in update_context
    assert "chzzk_category_game_candidate.status" in update_context
    assert "api/ui/serving exposure" in update_context
    assert "serving" in update_context
    assert "exposure" in update_context


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


def test_trusted_mapping_storage_contract_is_separate_and_has_minimal_api_surface() -> None:
    text = "\n".join(
        [
            _read_lower(DATA_MODEL_SPEC),
            _read_lower(DATA_GOVERNANCE),
            _read_lower(STORAGE_CONTRACT),
            _read_lower(CATEGORY_MAPPING_CONTRACT),
        ]
    )

    context = _near(text, "chzzk_category_game_mapping", span=1800)

    assert "trusted mapping storage contract" in context
    assert "mapping_status" in context
    assert "trusted" in context
    assert "source_kind" in context
    assert "chzzk_category_game_candidate.status" in context
    assert "candidate" in context
    assert "unresolved" in context
    assert "rejected" in context
    assert "category-game-mappings" in text
    assert "serving" in context
    assert "combined" in context
    assert "`chzzk_category_id` 하나당 trusted mapping 1개" in text
    assert "dim_game(canonical_game_id)" in text
    assert "빈 값일 수 없다" in text
    assert "trusted mapping을 insert하지 않고" in text
    assert "local candidate를 promotion하지 않" in text
    assert "현재 local 17개 candidate" in text


def test_trusted_mapping_serving_view_contract_pins_minimal_api_and_deferrals() -> None:
    text = "\n".join(
        [
            _read_lower(DATA_MODEL_SPEC),
            _read_lower(DATA_GOVERNANCE),
            _read_lower(STORAGE_CONTRACT),
            _read_lower(CATEGORY_MAPPING_CONTRACT),
            _read_lower(COMBINED_READINESS_CONTRACT),
        ]
    )

    context = text

    assert "internal read-only db serving view contract" in context
    assert "chzzk_category_game_mapping" in context
    assert "mapping_status = 'trusted'" in context
    assert "dim_game" in context
    assert "fact_chzzk_category_30m" in context
    assert "chzzk_category_game_candidate" in context
    assert "`chzzk_category_game_candidate`는 읽지 않으며" in text
    assert "노출하지 않는다" in text or "노출하지 않으며" in text
    assert "reviewed_by" in text
    assert "get /chzzk/category-game-mappings" in text
    assert "trusted mapping identity rows" in text
    assert "web exposure" in text or "web 노출" in text
    assert "product serving behavior" in context
    assert "ranking/kpi semantics" in text
    assert "combined" in context
    assert "readiness gate" in text


def test_combined_source_view_contract_is_docs_tests_only_and_future_gated() -> None:
    text = _read_lower(COMBINED_READINESS_CONTRACT)
    update_context = _near(
        text,
        "updated by category-mapping-combined-source-view-contract-001",
        span=3200,
    )

    assert "docs/tests-only planning contract" in update_context
    assert "`combined` api route" in update_context
    assert "sql serving view" in update_context
    assert "web data surface" in update_context
    assert "web fetch/hook" in update_context
    assert "mapping coverage panel" in update_context
    assert "product ranking" in update_context
    assert "kpi" in update_context
    assert "score" in update_context
    assert "recommendation behavior" in update_context
    assert "does not create" not in update_context
    assert "구현하지 않는다" in update_context or "not merged" in update_context

    assert "proposed future `combined` row grain" in update_context
    assert "one row per `dim_game.canonical_game_id`" in update_context
    assert "future implementation gate" in update_context
    assert "현재 api, sql, web, runtime behavior가 아니다" in update_context

    assert "candidate steam source contract" in update_context
    assert "none is selected or implemented" in update_context
    assert "future gated identity input" in update_context


def test_combined_source_view_contract_blocks_premature_identity_and_kpi_unlocks() -> None:
    text = "\n".join(
        [
            _read_lower(COMBINED_READINESS_CONTRACT),
            _read_lower(DATA_MODEL_SPEC),
            _read_lower(DATA_GOVERNANCE),
            _read_lower(SOURCE_INVENTORY),
        ]
    )

    assert "candidate/unresolved/rejected" in text
    assert "`categorytype=game`" in text or "`categorytype=game`" in text.replace(
        "`categorytype=game`", "`categorytype=game`"
    )
    assert "inferred mapping" in text
    assert "guessed mapping" in text
    assert "hidden fallback mapping" in text
    assert "synthetic joins" in text or "synthetic join" in text
    assert "not valid `combined` identity" in text or "invalid as `combined` identity" in text

    assert "chzzk viewer metrics" in text
    assert "full live-list population" in text
    assert "current unbounded viewers" in text
    assert "steam-equivalent chzzk baseline" in text
    assert "recommendation quality" in text
    assert "ranking readiness" in text or "ranking/kpi/score semantics" in text
    assert "kpi readiness" in text or "ranking/kpi/score semantics" in text


def test_combined_source_view_contract_keeps_steam_source_candidate_only() -> None:
    text = "\n".join(
        [
            _read_lower(COMBINED_READINESS_CONTRACT),
            _read_lower(DATA_MODEL_SPEC),
            _read_lower(SOURCE_INVENTORY),
            _read_lower(DATA_GOVERNANCE),
        ]
    )

    assert "candidate steam source contract" in text
    assert "candidate inputs only" in text or "candidate inputs to compare" in text
    assert "candidate steam source contract options" in text
    assert (
        "not implemented `combined` inputs" in text
        or "not current `combined` runtime lineage" in text
    )
    assert (
        "no current steam endpoint, service, or serving view is implemented "
        "as the `combined` source"
        in text
    )
    assert "srv_game_explore_period_metrics" in text
    assert "/games/explore/overview" in text


def test_combined_source_view_contract_keeps_mapping_identity_future_only() -> None:
    text = "\n".join(
        [
            _read_lower(COMBINED_READINESS_CONTRACT),
            _read_lower(DATA_MODEL_SPEC),
            _read_lower(SOURCE_INVENTORY),
            _read_lower(DATA_GOVERNANCE),
        ]
    )

    assert "future gated identity input" in text
    assert "get /chzzk/category-game-mappings" in text
    assert "srv_chzzk_category_game_mapping" in text
    assert "trusted mapping identity rows" in text
    assert "not current `combined` runtime lineage" in text
    assert "not be merged into `combined` product semantics" in text


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


def test_non_exact_gate_allows_only_future_synthetic_alias_hint_contract() -> None:
    text = _read_lower(NON_EXACT_MATCHING_GATE)

    decision_context = _near(
        text,
        "exact normalized matching remains safe but insufficient for useful proposal signal",
        span=900,
    )
    alias_context = _near(text, "`alias`는 사람이 curated한 alternate label", span=1200)
    fuzzy_context = _near(text, "fuzzy matching은 계속 forbidden", span=900)
    discovery_context = _near(
        text,
        "automatic alias discovery는 계속 forbidden",
        span=900,
    )
    classification_context = _near(
        text,
        "현재 proposal state semantics는 유지한다",
        span=1200,
    )
    next_ticket_context = _near(
        text,
        "category-mapping-alias-hint-contract-gate-001",
        span=1000,
    )

    assert "candidate proposal count: `0`" in text
    assert "unresolved proposal count: `200`" in text
    assert "db write performed: `false`" in text
    assert "candidate insert performed: `false`" in text

    assert (
        "curated alias/manual hint policy only as untrusted review evidence"
        in decision_context
    )
    assert "fuzzy matching and automatic alias discovery remain forbidden" in decision_context
    assert "automatic trusted mapping은 계속 금지한다" in decision_context

    assert "review-only evidence" in alias_context
    assert "`manual hint`는 사람이 제공한 review hint" in alias_context
    assert "`trusted mapping`은 future human gate" in alias_context
    assert "synthetic/test-first" in alias_context
    assert "no direct promotion to `trusted` / `approved`" in alias_context
    assert "no db write" in alias_context
    assert "no api/web/serving/`combined`" in alias_context
    assert "alias/manual hint implementation is not approved by this ticket" in text

    assert "false positive" in fuzzy_context
    assert "score threshold" in fuzzy_context
    assert "fuzzy matching" in fuzzy_context
    assert "similarity score" in fuzzy_context
    assert "punctuation-insensitive matching" in fuzzy_context
    assert "phonetic matching" in fuzzy_context
    assert "transliteration" in fuzzy_context
    assert "approximate string matching" in fuzzy_context

    assert "hidden identity assumption" in discovery_context
    assert "provider-to-game mapping evidence" in discovery_context
    assert "provenance" in discovery_context
    assert "conflict handling" in discovery_context
    assert "synthetic/test-only alias/manual hint contract gate" in discovery_context

    assert "`candidate`: untrusted review proposal only" in classification_context
    assert "`unresolved`: untrusted unresolved evidence only" in classification_context
    assert "`rejected`: not generated automatically" in classification_context
    assert (
        "`trusted` / `approved`: future human gate terminology only"
        in classification_context
    )
    assert "serving truth" in classification_context
    assert "`combined` semantics" in classification_context

    assert "normalization: `strip`, `casefold`, whitespace collapse only" in text
    assert "must not silently change exact-match behavior" in text
    assert "insert into `chzzk_category_game_candidate`" in text
    assert "`game_external_id`" in text
    assert "tracked_universe" in text
    assert "app catalog" in text
    assert "no implementation" in next_ticket_context
    assert "no trusted mapping" in next_ticket_context
    assert "no api/web/serving/`combined`" in next_ticket_context
    assert "do not recommend an implementation ticket" in text


def test_alias_hint_contract_gate_keeps_future_work_synthetic_review_only() -> None:
    text = _read_lower(ALIAS_HINT_CONTRACT_GATE)

    decision_context = _near(
        text,
        "alias and manual hint belong to one future synthetic/test-only contract family",
        span=700,
    )
    input_context = _near(text, "synthetic/test-only input contract", span=1400)
    conflict_context = _near(text, "conflict / ambiguity boundary", span=1200)
    output_context = _near(text, "proposal output boundary", span=1200)
    fuzzy_context = _near(text, "fuzzy and automatic alias discovery boundary", span=1200)
    next_ticket_context = _near(text, "the next implementation must remain", span=900)

    assert 'hint_kind = "alias" | "manual_hint"' in decision_context
    assert "does not approve implementation" in decision_context

    assert "`hint_kind`" in input_context
    assert "`synthetic_chzzk_category_label`" in input_context
    assert "`synthetic_canonical_game_name`" in input_context
    assert "`reason`" in input_context
    assert "`source_note`" in input_context
    assert "storage schema" in input_context
    assert "api shape" in input_context
    assert "db table shape" in input_context
    assert "runtime contract" in input_context

    assert "untrusted review evidence" in text
    assert "serving truth" in text
    assert "review를 skip할 수 없다" in text
    assert "`trusted` / `approved`를 직접 만들 수 없다" in text

    assert "same synthetic category hinting multiple synthetic games" in conflict_context
    assert "same synthetic alias pointing to multiple synthetic games" in conflict_context
    assert "must not auto-select a winner" in conflict_context
    assert "`rejected` is not generated automatically" in conflict_context
    assert "future human gate terminology only" in conflict_context

    assert "untrusted `candidate` proposals" in output_context
    assert "untrusted `unresolved` proposals" in output_context
    assert "`rejected` automatically" in output_context
    assert "api/web-visible mapping fields" in output_context
    assert "`combined` rows/kpi/sorting/ranking" in output_context

    assert "fuzzy matching remains forbidden" in fuzzy_context
    assert "automatic alias discovery remains forbidden" in fuzzy_context
    assert "approximate matching" in fuzzy_context
    assert "similarity score" in fuzzy_context
    assert "phonetic/transliteration matching" in fuzzy_context
    assert "partial/punctuation-insensitive matching" in fuzzy_context

    assert "candidate proposal count: `0`" in text
    assert "unresolved proposal count: `200`" in text
    assert "db write performed: `false`" in text
    assert "candidate insert performed: `false`" in text

    assert "no real raw values in public artifacts" in next_ticket_context
    assert "no db write" in next_ticket_context
    assert "no candidate insert" in next_ticket_context
    assert "no trusted mapping" in next_ticket_context
    assert "no api/web/serving/`combined`" in next_ticket_context


def test_alias_hint_real_data_gate_allows_only_read_only_sanitized_smoke() -> None:
    text = _read_lower(ALIAS_HINT_REAL_DATA_GATE)

    decision_context = _near(
        text,
        "real-data alias/manual hint work may be opened only as a future read-only",
        span=900,
    )
    source_context = _near(text, "## real-data source boundary", span=2600)
    public_context = _near(text, "## public artifact boundary", span=2000)
    private_context = _near(text, "## private / local evidence boundary", span=2000)
    alias_context = _near(text, "`alias` is a curated alternate label", span=1200)
    proposal_context = _near(text, "## proposal output boundary", span=1800)
    fuzzy_context = _near(text, "## explicit non-goals", span=1500)
    validation_context = _near(
        text,
        "future `category-mapping-alias-hint-real-data-smoke-001` must",
        span=1300,
    )
    stop_context = _near(text, "future smoke must stop if", span=1500)
    next_ticket_context = _near(
        text,
        "recommended next ticket",
        span=1400,
    )

    assert "이 gate는 real-data smoke를 실행하지 않는다" in text
    assert "api call" in text
    assert "db query" in text
    assert "service start/stop/restart" in text
    assert "scheduler action" in text
    assert "live fetch" in text

    assert "read-only" in decision_context
    assert "no-write" in decision_context
    assert "sanitized aggregate smoke" in decision_context
    assert "real category/game names and real hint rows" in decision_context
    assert "private/local evidence" in decision_context
    assert "arbitrary local data access를 승인하지 않는다" in decision_context

    assert "candidate proposal count: `0`" in text
    assert "unresolved proposal count: `200`" in text
    assert "db write performed: `false`" in text
    assert "candidate insert performed: `false`" in text

    assert "local/private operator-controlled evidence" in source_context
    assert "public fixture" in source_context
    assert "tracked public docs table" in source_context
    assert "serving contract" in source_context
    assert "automatic" in source_context
    assert "discovery output" in source_context
    assert "explicitly approved read-only local/private source path" in source_context
    assert "source shape가 ambiguous하면 smoke를 중단" in source_context

    assert "public artifacts include" in public_context
    assert "pr body" in public_context
    assert "public docs" in public_context
    assert "tests" in public_context
    assert "fixtures/examples" in public_context
    assert "codex completion reports" in public_context
    assert "sanitized aggregate output" in public_context
    assert "real category names" in public_context
    assert "real game names" in public_context
    assert "real alias names" in public_context
    assert "real manual hint rows" in public_context
    assert "raw provider payloads" in public_context
    assert "raw api responses" in public_context
    assert "raw sql output" in public_context
    assert "credentials" in public_context
    assert "`.env` values" in public_context

    assert (
        "private/local evidence must not be copied into public docs or tests"
        in private_context
    )
    assert "source class, not by" in private_context
    assert "value" in private_context
    assert "aggregate counts only" in private_context
    assert "aggregate-only reporting cannot be guaranteed" in private_context

    assert "manual_hint" in alias_context
    assert "untrusted review evidence" in alias_context
    assert "neither creates trusted mapping" in alias_context
    assert "neither creates serving truth" in alias_context
    assert "neither bypasses review" in alias_context
    assert "neither directly produces `trusted` / `approved`" in alias_context

    assert (
        "future smoke may publicly report only aggregate proposal counts"
        in proposal_context
    )
    assert "db write" in proposal_context
    assert "insert into `chzzk_category_game_candidate`" in proposal_context
    assert "trusted mapping" in proposal_context
    assert "promotion/demotion" in proposal_context
    assert "api/web exposure" in proposal_context
    assert "serving changes" in proposal_context
    assert "`combined`" in proposal_context
    assert (
        "writing rows would make private/local evidence look like durable candidate state"
        in proposal_context
    )

    assert "fuzzy matching" in fuzzy_context
    assert "automatic alias discovery" in fuzzy_context
    assert "automatic matching" in fuzzy_context
    assert "trusted mapping" in fuzzy_context
    assert "`game_external_id`" in fuzzy_context
    assert "tracked_universe" in fuzzy_context
    assert "app catalog" in fuzzy_context
    assert "serving semantics" in fuzzy_context
    assert "`combined`" in fuzzy_context

    assert "be read-only" in validation_context
    assert "be no-write" in validation_context
    assert "explicitly approved source commands/paths only" in validation_context
    assert "not start/stop/restart services" in validation_context
    assert "not mutate scheduler/runtime" in validation_context
    assert "not inspect or print credentials/`.env` values" in validation_context
    assert "sanitized aggregate output only" in validation_context

    assert "raw provider payload printing" in stop_context
    assert "real category/game names in public output" in stop_context
    assert "credentials or `.env` value inspection" in stop_context
    assert "db write or candidate insert" in stop_context
    assert "api/web/serving changes" in stop_context
    assert "`combined`" in stop_context
    assert "fuzzy matching or automatic alias discovery" in stop_context
    assert "row-level output that cannot be sanitized" in stop_context

    assert "recommended next ticket" in next_ticket_context
    assert "read-only, no-write, sanitized aggregate smoke" in next_ticket_context
    assert "useful untrusted candidate proposal signal exists" in next_ticket_context
    assert "aggregate-only public output" in next_ticket_context
    assert "no real names in public artifacts" in next_ticket_context
    assert "no db write" in next_ticket_context
    assert "no candidate insert" in next_ticket_context
    assert "no trusted mapping" in next_ticket_context
    assert "no api/web/serving/`combined`" in next_ticket_context
    assert "fuzzy matching forbidden" in next_ticket_context
    assert "automatic alias discovery forbidden" in next_ticket_context


def test_alias_hint_seeding_assist_gate_keeps_review_seeds_private_untrusted() -> None:
    text = _read_lower(ALIAS_HINT_SEEDING_ASSIST_GATE)

    decision_context = _near(
        text,
        "private/local review seeding assist may be considered only as a future",
        span=1100,
    )
    seed_boundary_context = _near(text, "review seed ≠ alias/manual_hint", span=1200)
    allowed_context = _near(text, "## allowed future assist direction", span=1700)
    forbidden_context = _near(text, "## forbidden interpretation", span=1200)
    public_context = _near(text, "## public artifact boundary", span=1800)
    private_context = _near(text, "## private / local evidence boundary", span=1200)
    alias_context = _near(text, "## relationship to alias / manual hint", span=1600)
    storage_context = _near(text, "## relationship to candidate storage", span=1500)
    stop_context = _near(text, "## stop conditions for future work", span=1500)
    next_ticket_context = _near(
        text,
        "category-mapping-review-seeding-assist-gate-001",
        span=1200,
    )

    assert "이 gate는 review seeding assist를 구현하지 않는다" in text
    assert "alias/manual hint source: absent" in text
    assert "result status: unknown / insufficient approved source" in text
    assert "db write performed: false" in text
    assert "candidate insert performed: false" in text
    assert "raw values printed: false" in text

    assert "read-only" in decision_context
    assert "no-write" in decision_context
    assert "human-review aid" in decision_context
    assert "`alias`" in decision_context
    assert "`manual_hint`" in decision_context
    assert "`candidate`" in decision_context
    assert "`trusted`" in decision_context
    assert "`approved`" in decision_context
    assert "serving truth" in decision_context
    assert "human curation" in decision_context

    assert "review seed ≠ alias/manual_hint" in seed_boundary_context
    assert "review seed ≠ candidate" in seed_boundary_context
    assert "review seed ≠ trusted mapping" in seed_boundary_context
    assert "review seed ≠ serving truth" in seed_boundary_context
    assert "review seed is not an alias" in seed_boundary_context
    assert "review seed is not a manual hint" in seed_boundary_context
    assert "review seed is not a candidate proposal" in seed_boundary_context
    assert "review seed is not `combined`" in seed_boundary_context
    assert "human adoption is required" in seed_boundary_context

    assert "normalized token overlap" in allowed_context
    assert "substring containment" in allowed_context
    assert "punctuation/spacing normalization" in allowed_context
    assert "casefold/whitespace normalization" in allowed_context
    assert "known suffix/prefix trimming" in allowed_context
    assert "top-n private/local review seed report" in allowed_context
    assert "aggregate-only public completion report" in allowed_context
    assert "these methods are not implemented by this ticket" in allowed_context
    assert "automatic matching" in allowed_context
    assert "fuzzy matching" in allowed_context
    assert "automatic alias discovery" in allowed_context
    assert "candidate generation for storage" in allowed_context

    assert "fuzzy matching" in forbidden_context
    assert "automatic alias discovery" in forbidden_context
    assert "automatic matching" in forbidden_context
    assert "trusted mapping" in forbidden_context
    assert "automatic candidate generation for storage" in forbidden_context
    assert "automatic `alias` generation" in forbidden_context
    assert "automatic `manual_hint` generation" in forbidden_context
    assert "promotion/demotion workflow" in forbidden_context
    assert "api/web/serving change" in forbidden_context
    assert "`combined`" in forbidden_context

    assert "public artifacts include" in public_context
    assert "sanitized aggregate output" in public_context
    assert "review seed row count" in public_context
    assert "real category names" in public_context
    assert "real game names" in public_context
    assert "real review seed rows" in public_context
    assert "raw provider payloads" in public_context
    assert "raw api responses" in public_context
    assert "raw sql output" in public_context
    assert "credentials" in public_context
    assert "`.env` values" in public_context

    assert "private/local seed rows must not be copied" in private_context
    assert "source class, not by value" in private_context
    assert "aggregate counts only" in private_context
    assert "aggregate-only reporting cannot be guaranteed" in private_context

    assert "review seed output is neither of these" in alias_context
    assert "human curation" in alias_context
    assert 'hint_kind = "alias" | "manual_hint"' in alias_context
    assert "must not be assigned automatically" in alias_context

    assert "no db write" in storage_context
    assert "no insert into `chzzk_category_game_candidate`" in storage_context
    assert "no candidate write smoke" in storage_context
    assert "no durable candidate state" in storage_context
    assert "no trusted mapping" in storage_context
    assert "no serving truth" in storage_context
    assert "no api/web/serving/`combined`" in storage_context
    assert "separate write policy, audit trail, and human gate" in storage_context

    assert "raw provider payload printing" in stop_context
    assert "real category/game names in public output" in stop_context
    assert "credentials or `.env` value inspection" in stop_context
    assert "db write or candidate insert" in stop_context
    assert "api/web/serving changes" in stop_context
    assert "`combined`" in stop_context
    assert "fuzzy matching or automatic alias discovery" in stop_context
    assert "row-level output that cannot be sanitized" in stop_context
    assert "without human curation" in stop_context
    assert "trusted mapping" in stop_context
    assert "persisted without a separate write gate" in stop_context

    assert "category-mapping-review-seeding-assist-gate-001" in next_ticket_context
    assert "review-seed generation, not alias/hint generation" in next_ticket_context
    assert "docs/decision first" in next_ticket_context
    assert "generated seed rows are not alias/manual_hint until human curated" in text
