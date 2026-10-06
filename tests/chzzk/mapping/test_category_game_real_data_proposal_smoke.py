"""Synthetic-only evidence: every database connection is replaced with a fake."""

import importlib
import json
import runpy
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import psycopg
import pytest

from chzzk.mapping import category_game_real_data_proposal_smoke as smoke

ENV = {
    "POSTGRES_HOST": "synthetic-private-host",
    "POSTGRES_DB": "synthetic-private-db",
    "POSTGRES_USER": "synthetic-private-user",
    "POSTGRES_PASSWORD": "synthetic-secret",
}
NOW = datetime(2026, 10, 7, tzinfo=UTC)
PRIVATE = "synthetic-private-row"


class FakeConnection:
    def __init__(self):
        self.read_only = False
        self.isolation_level = None
        self.in_transaction = False
        self.transaction_count = 0
        self.queries = []
        self.settings = ("on", "repeatable read")
        self.fail_sql = None
        self.fail_exit = False
        self.observed = [
            ("trusted", PRIVATE, "GAME", NOW),
            ("one", "  SYNTHETIC\t Alpha  ", "ETC", NOW),
            ("none", "Synthetic-Al pha", "GAME", NOW),
            ("many", "Synthetic Beta", None, NOW),
        ]
        self.games = [(1, "Synthetic Alpha"), (2, "Synthetic Beta"), (3, "SYNTHETIC beta")]
        self.trusted = [("trusted",), ("unobserved",)]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.fail_exit:
            raise RuntimeError(PRIVATE)

    @contextmanager
    def transaction(self):
        assert self.read_only is True
        assert self.isolation_level == psycopg.IsolationLevel.REPEATABLE_READ
        assert not self.in_transaction
        self.transaction_count += 1
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False

    @contextmanager
    def cursor(self):
        assert self.in_transaction
        yield self

    def execute(self, sql):
        assert self.in_transaction
        assert sql.lstrip().startswith("SELECT ")
        assert sql in (
            smoke.TRANSACTION_SQL, smoke.OBSERVED_SQL, smoke.GAMES_SQL, smoke.TRUSTED_SQL,
        )
        self.queries.append(sql)
        if sql == self.fail_sql:
            raise RuntimeError(PRIVATE)

    def fetchone(self):
        assert self.queries[-1] == smoke.TRANSACTION_SQL
        return self.settings

    def fetchall(self):
        return {
            smoke.OBSERVED_SQL: self.observed,
            smoke.GAMES_SQL: self.games,
            smoke.TRUSTED_SQL: self.trusted,
        }[self.queries[-1]]


@pytest.fixture
def database(monkeypatch):
    connection = FakeConnection()
    connect = Mock(return_value=connection)
    monkeypatch.setattr(smoke.psycopg, "connect", connect)
    return connection, connect


def test_snapshot_partition_builder_reuse_and_output_allowlist(database, monkeypatch):
    connection, connect = database
    builder = Mock(wraps=smoke.build_category_game_candidate_dry_run_proposals)
    monkeypatch.setattr(smoke, "build_category_game_candidate_dry_run_proposals", builder)
    result = smoke.run_smoke(environ=ENV)
    assert result == {
        "result_status": "success",
        "observed_input_category_count": 4,
        "canonical_game_input_count": 3,
        "already_trusted_category_count": 1,
        "not_currently_trusted_category_count": 3,
        "candidate_count": 1,
        "unresolved_no_match_count": 1,
        "unresolved_ambiguous_count": 1,
        "latest_observed_evidence_timestamp": NOW.isoformat(),
        **smoke.NO_WRITES,
    }
    assert connection.transaction_count == 1
    assert connection.queries == [
        smoke.TRANSACTION_SQL, smoke.OBSERVED_SQL, smoke.GAMES_SQL, smoke.TRUSTED_SQL,
    ]
    assert connect.call_args.kwargs["autocommit"] is False
    assert builder.call_args.kwargs["alias_hints"] is None
    assert [c.chzzk_category_id for c in builder.call_args.kwargs["categories"]] == [
        "one", "none", "many",
    ]
    output = json.dumps(result)
    for value in (*ENV.values(), PRIVATE, "Synthetic", "normalized", "canonical_game_id"):
        assert value not in output
    assert "LIMIT" not in smoke.OBSERVED_SQL
    assert "category_type =" not in smoke.OBSERVED_SQL
    assert "bucket_time DESC, collected_at DESC, ingested_at DESC" in smoke.OBSERVED_SQL


@pytest.mark.parametrize("source", ["observed", "games", "trusted"])
@pytest.mark.parametrize("mutation", ["blank", "duplicate", "shape", "wrong_type"])
def test_invalid_source_rows_fail_closed_even_when_trusted(database, source, mutation):
    connection, _ = database
    rows = getattr(connection, source)
    row = list(rows[0])
    if mutation == "blank":
        row[1 if source == "games" else 0] = " \t "
    elif mutation == "duplicate":
        rows.append(tuple(row))
    elif mutation == "shape":
        row.append(PRIVATE)
    else:
        row[0] = True if source == "games" else None
    if mutation != "duplicate":
        rows[0] = tuple(row)
    result = smoke.run_smoke(environ=ENV)
    assert result == {
        "result_status": "failed",
        "failure_reason_category": "invalid_input",
        "invalid_input_count": 1,
        **smoke.NO_WRITES,
    }


@pytest.mark.parametrize("index,value", [(1, None), (1, " "), (2, 3), (3, None),
                                         (3, datetime(2026, 10, 7))])
def test_invalid_trusted_observed_evidence_is_not_skipped(database, index, value):
    connection, _ = database
    row = list(connection.observed[0])
    row[index] = value
    connection.observed[0] = tuple(row)
    assert smoke.run_smoke(environ=ENV)["invalid_input_count"] == 1


@pytest.mark.parametrize("game_id", [False, 0, -1, "1"])
def test_invalid_game_id(database, game_id):
    database[0].games[0] = (game_id, "Synthetic Alpha")
    assert smoke.run_smoke(environ=ENV)["result_status"] == "failed"


@pytest.mark.parametrize("settings", [("off", "repeatable read"), ("on", "read committed")])
def test_transaction_mismatch_stops_before_source_reads(database, settings):
    connection, _ = database
    connection.settings = settings
    result = smoke.run_smoke(environ=ENV)
    assert result["failure_reason_category"] == "transaction_condition_failed"
    assert connection.queries == [smoke.TRANSACTION_SQL]


@pytest.mark.parametrize("sql", [smoke.OBSERVED_SQL, smoke.GAMES_SQL, smoke.TRUSTED_SQL])
def test_source_failure_has_no_partial_success_or_private_exception(database, sql):
    database[0].fail_sql = sql
    result = smoke.run_smoke(environ=ENV)
    assert result == {
        "result_status": "failed",
        "failure_reason_category": "approved_source_unavailable",
        **smoke.NO_WRITES,
    }


def test_transaction_exit_failure_cannot_publish_success(database):
    database[0].fail_exit = True
    assert smoke.run_smoke(environ=ENV)["failure_reason_category"] == "transaction_condition_failed"


def test_partition_invariant_failure(database, monkeypatch):
    monkeypatch.setattr(smoke, "build_category_game_candidate_dry_run_proposals", lambda **kw: [])
    assert smoke.run_smoke(environ=ENV)["failure_reason_category"] == "partition_invariant_failed"


def test_empty_sources_are_valid_zero_population(database):
    connection, _ = database
    connection.observed = connection.games = connection.trusted = []
    result = smoke.run_smoke(environ=ENV)
    assert result["result_status"] == "success"
    assert result["observed_input_category_count"] == 0
    assert result["latest_observed_evidence_timestamp"] is None


def test_identity_membership_is_exact_before_label_normalization(database):
    connection, _ = database
    connection.observed = [(" trusted ", "Synthetic Alpha", "SPORTS", NOW)]
    assert smoke.run_smoke(environ=ENV)["candidate_count"] == 1


def test_cli_failures_sanitize_arguments_and_connection_errors(database, monkeypatch, capsys):
    _, connect = database
    assert smoke.main([PRIVATE]) == 1
    connect.assert_not_called()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    connect.side_effect = RuntimeError(" ".join(ENV.values()))
    assert smoke.main([]) == 1
    output = capsys.readouterr()
    assert output.err == ""
    assert PRIVATE not in output.out
    for value in ENV.values():
        assert value not in output.out
    assert "database_access_failed" in output.out


def test_missing_configuration_never_connects(database):
    assert smoke.run_smoke(environ={})["result_status"] == "failed"
    database[1].assert_not_called()


def test_import_is_inert_and_module_command_uses_mock_only(database, monkeypatch, capsys):
    importlib.reload(smoke)
    database[1].assert_not_called()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["category_game_real_data_proposal_smoke"])
    monkeypatch.delitem(sys.modules, smoke.__name__)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module(smoke.__name__, run_name="__main__")
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["result_status"] == "success"
