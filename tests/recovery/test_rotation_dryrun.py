from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
import random
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from recovery import rotation_dryrun
from recovery.rotation_dryrun import (
    LOCAL_VERIFIER,
    REMOTE_VERIFIER,
    GenerationSnapshot,
    InventorySnapshot,
    MilestonePin,
    PinSnapshot,
    RetentionPolicy,
    VerificationEvidence,
    classify_snapshot,
    render_report,
)

POLICY = RetentionPolicy()
EMPTY_PINS = PinSnapshot("synthetic-human-pin-confirmation", True, ())


def generation(generation_id: str, completed: str) -> GenerationSnapshot:
    digest = hashlib.sha256(generation_id.encode()).hexdigest()
    local = VerificationEvidence(
        verifier=LOCAL_VERIFIER,
        status="PASS",
        evidence_ref=f"synthetic-a1-{generation_id}",
        generation_id=generation_id,
        manifest_sha256=digest,
        completed_at_utc=completed,
        verified_at_utc=completed,
    )
    remote = replace(local, verifier=REMOTE_VERIFIER, evidence_ref=f"synthetic-a2-{generation_id}")
    return GenerationSnapshot(generation_id, digest, completed, local, remote)


def inventory(*generations: GenerationSnapshot) -> InventorySnapshot:
    return InventorySnapshot(
        snapshot_id="synthetic-inventory-001",
        authority_ref="synthetic-inventory-authority",
        generations=generations,
        local_complete=True,
        r2_complete=True,
        stable=True,
        completeness_evidence_ref="synthetic-complete-local-and-r2",
        stability_evidence_ref="synthetic-stability",
        limitations=("synthetic only; no current inventory observation",),
    )


def dense_inventory() -> InventorySnapshot:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    return inventory(
        *(
            generation(
                f"generation-{index:02}",
                (start + timedelta(hours=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            for index in range(10)
        )
    )


def classify(snapshot: InventorySnapshot, pins: PinSnapshot | None = EMPTY_PINS) -> dict:
    return classify_snapshot(snapshot, pins=pins, policy=POLICY)


def rows_by_id(report: dict) -> dict[str, dict]:
    return {row["generation_id"]: row for row in report["generations"]}


def kept(report: dict, reason: str) -> set[str]:
    return {
        row["generation_id"] for row in report["generations"] if reason in row["classifications"]
    }


def assert_blocked(report: dict, reason: str) -> None:
    assert report["candidate_set_status"] == "blocked"
    assert reason in report["candidate_set_blocking_reasons"]
    assert report["advisory_candidates"] == []
    assert kept(report, "eligible_for_rotation") == set()


def test_latest_eight_is_count_based_and_overlapping_reasons_are_preserved() -> None:
    snapshot = dense_inventory()
    report = classify(snapshot)

    assert kept(report, "keep_recent") == {f"generation-{index:02}" for index in range(2, 10)}
    assert kept(report, "eligible_for_rotation") == {"generation-00", "generation-01"}
    assert rows_by_id(report)["generation-09"]["classifications"] == [
        "keep_daily",
        "keep_monthly",
        "keep_recent",
        "keep_weekly",
    ]
    assert report["candidate_set_status"] == "advisory"
    assert report["advisory_only"] is True
    assert report["policy"] == {"recent": 8, "daily": 7, "weekly": 4, "monthly": 3}


def test_sparse_observed_buckets_do_not_consume_empty_calendar_quotas() -> None:
    dates = [
        "2018-01-01",
        "2019-03-01",
        "2020-05-01",
        "2021-07-01",
        "2022-09-01",
        "2023-11-01",
        "2025-01-01",
        "2026-04-01",
        "2026-09-01",
    ]
    snapshot = inventory(
        *(generation(f"g-{index}", f"{day}T00:00:00Z") for index, day in enumerate(dates))
    )
    report = classify(snapshot)
    assert kept(report, "keep_recent") == {f"g-{index}" for index in range(1, 9)}
    assert kept(report, "keep_daily") == {f"g-{index}" for index in range(2, 9)}
    assert kept(report, "keep_weekly") == {f"g-{index}" for index in range(5, 9)}
    assert kept(report, "keep_monthly") == {"g-6", "g-7", "g-8"}


def test_calendar_representatives_survive_outside_recent_set() -> None:
    older = tuple(
        generation(f"old-{month}", f"2020-{month:02}-01T00:00:00Z") for month in range(1, 5)
    )
    newest = tuple(generation(f"new-{hour}", f"2020-05-01T{hour:02}:00:00Z") for hour in range(10))
    report = classify(inventory(*older, *newest))
    assert kept(report, "keep_daily") == {"old-1", "old-2", "old-3", "old-4", "new-9"}
    assert kept(report, "keep_weekly") == {"old-2", "old-3", "old-4", "new-9"}
    assert kept(report, "keep_monthly") == {"old-3", "old-4", "new-9"}
    assert "old-1" not in kept(report, "keep_recent")
    assert "old-1" not in kept(report, "eligible_for_rotation")


def test_iso_week_year_and_calendar_year_are_distinct() -> None:
    report = classify(
        inventory(
            generation("december", "2020-12-31T23:59:59Z"),
            generation("january", "2021-01-01T00:00:00Z"),
            generation("next-week", "2021-01-04T00:00:00Z"),
            generation("next-year", "2022-01-03T00:00:00Z"),
        )
    )
    assert kept(report, "keep_weekly") == {"january", "next-week", "next-year"}
    assert kept(report, "keep_monthly") == {"december", "next-week", "next-year"}
    assert len(kept(report, "keep_daily")) == 4


def test_timestamp_ties_use_id_ascending_and_ignore_enumeration_order() -> None:
    snapshot = inventory(
        *(generation(f"g-{index:02}", "2020-01-01T00:00:00Z") for index in range(12))
    )
    pins = replace(
        EMPTY_PINS,
        pins=tuple(
            MilestonePin(item.generation_id, item.manifest_sha256)
            for item in snapshot.generations[-2:]
        ),
    )
    expected = classify(snapshot, pins)
    assert kept(expected, "keep_recent") == {f"g-{index:02}" for index in range(8)}
    assert kept(expected, "keep_daily") == {"g-00"}
    assert kept(expected, "eligible_for_rotation") == {"g-08", "g-09"}
    for seed in range(12):
        shuffled = list(snapshot.generations)
        random.Random(seed).shuffle(shuffled)
        actual = classify(
            replace(snapshot, generations=tuple(shuffled)),
            replace(pins, pins=tuple(reversed(pins.pins))),
        )
        assert render_report(actual) == render_report(expected)


def test_milestone_pins_bind_manifest_and_preserve_overlapping_keep_reasons() -> None:
    snapshot = dense_inventory()
    pins = replace(
        EMPTY_PINS,
        pins=tuple(
            MilestonePin(item.generation_id, item.manifest_sha256)
            for item in (snapshot.generations[0], snapshot.generations[-1])
        ),
    )
    report = classify(snapshot, pins)
    assert kept(report, "keep_milestone") == {"generation-00", "generation-09"}
    assert kept(report, "eligible_for_rotation") == {"generation-01"}
    assert len(rows_by_id(report)["generation-09"]["classifications"]) == 5


@pytest.mark.parametrize(
    "pins",
    [
        None,
        PinSnapshot(None, True, ()),
        PinSnapshot("human", None, ()),
        PinSnapshot("human", False, ()),
    ],
)
def test_missing_pin_authority_is_not_confirmed_empty(pins: PinSnapshot | None) -> None:
    snapshot = dense_inventory()
    assert classify(snapshot)["advisory_candidates"]
    report = classify(snapshot, pins)
    assert_blocked(report, "pin_authority_missing")
    assert kept(report, "rotation_blocked") == {"generation-00", "generation-01"}


@pytest.mark.parametrize(
    ("pins", "reason"),
    [
        ((MilestonePin("missing", "a" * 64),), "pin_generation_missing_or_ambiguous"),
        ((MilestonePin("generation-00", "a" * 64),), "pin_manifest_mismatch"),
        ((MilestonePin("generation-00", "bad"),), "pin_binding_invalid"),
        (
            (MilestonePin("generation-00", "a" * 64), MilestonePin("generation-00", "b" * 64)),
            "conflicting_pins",
        ),
    ],
)
def test_invalid_pins_block_all_candidates(pins: tuple[MilestonePin, ...], reason: str) -> None:
    assert_blocked(classify(dense_inventory(), replace(EMPTY_PINS, pins=pins)), reason)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("local_complete", False, "local_inventory_incomplete"),
        ("local_complete", 1, "local_inventory_incomplete"),
        ("r2_complete", None, "r2_inventory_incomplete"),
        ("stable", False, "inventory_unstable"),
        ("completeness_evidence_ref", None, "inventory_completeness_evidence_missing"),
        ("stability_evidence_ref", " ", "inventory_stability_evidence_missing"),
        ("authority_ref", None, "inventory_authority_missing"),
        ("snapshot_id", "", "inventory_authority_missing"),
    ],
)
def test_inventory_authority_failures_block_all_candidates(
    field: str,
    value: object,
    reason: str,
) -> None:
    assert_blocked(classify(replace(dense_inventory(), **{field: value})), reason)


@pytest.mark.parametrize("location", ["local", "r2"])
@pytest.mark.parametrize(
    ("changes", "reason", "global_block"),
    [
        ({"status": "FAIL"}, "verification_not_pass", False),
        ({"status": "UNKNOWN"}, "verification_not_pass", False),
        ({"verifier": "R2_LIST"}, "verifier_unsupported", False),
        ({"evidence_ref": None}, "evidence_reference_missing", False),
        ({"verified_at_utc": "invalid"}, "invalid_verified_at_utc", False),
        ({"generation_id": "other"}, "binding_mismatch", True),
        ({"manifest_sha256": "b" * 64}, "binding_mismatch", True),
        ({"completed_at_utc": "2020-01-01T00:00:01Z"}, "binding_mismatch", True),
        ({"verified_at_utc": "2019-01-01T00:00:00Z"}, "verification_precedes_completion", True),
        ({"issues": ("checksum_mismatch",)}, "verification_issues", True),
    ],
)
def test_verification_failures_cannot_become_candidates(
    location: str,
    changes: dict,
    reason: str,
    global_block: bool,
) -> None:
    snapshot = dense_inventory()
    original = snapshot.generations[0]
    changed = replace(original, **{location: replace(getattr(original, location), **changes)})
    snapshot = replace(snapshot, generations=(changed, *snapshot.generations[1:]))
    report = classify(snapshot)
    row = rows_by_id(report)[original.generation_id]
    assert row["classifications"] == ["keep_unverified"]
    assert row["verification"] == "unverified"
    assert f"{location}_{reason}" in row["verification_reasons"]
    if global_block:
        assert_blocked(report, "conflicting_verification_evidence")
    else:
        assert kept(report, "eligible_for_rotation") == {"generation-01"}


@pytest.mark.parametrize("location", ["local", "r2"])
def test_missing_required_evidence_and_unverifiable_pins(location: str) -> None:
    snapshot = dense_inventory()
    changed = replace(snapshot.generations[0], **{location: None})
    snapshot = replace(snapshot, generations=(changed, *snapshot.generations[1:]))
    report = classify(snapshot)
    assert kept(report, "keep_unverified") == {changed.generation_id}
    assert f"{location}_evidence_missing" in report["generations"][0]["verification_reasons"]
    pins = replace(EMPTY_PINS, pins=(MilestonePin(changed.generation_id, changed.manifest_sha256),))
    assert_blocked(classify(snapshot, pins), "pin_state_unverifiable")


@pytest.mark.parametrize(
    "timestamp",
    [
        "2020-02-30T00:00:00Z",
        "2020-01-01T00:00:00+00:00",
        "2020-01-01T00:00:00",
        "2020-01-01T00:00:00.5Z",
        "not-a-timestamp",
    ],
)
def test_invalid_utc_timestamp_is_never_inferred_from_generation_name(timestamp: str) -> None:
    report = classify(inventory(generation("scheduled-20200101T000000Z", timestamp)))
    assert report["generations"][0]["classifications"] == ["keep_unverified"]
    assert "invalid_completed_at_utc" in report["generations"][0]["verification_reasons"]


@pytest.mark.parametrize("different_manifest", [False, True])
def test_duplicate_generation_identity_is_ambiguous_and_globally_blocked(
    different_manifest: bool,
) -> None:
    snapshot = dense_inventory()
    duplicate = snapshot.generations[0]
    if different_manifest:
        duplicate = replace(duplicate, manifest_sha256="c" * 64)
    snapshot = replace(snapshot, generations=(*snapshot.generations, duplicate))
    report = classify(snapshot)
    assert_blocked(report, "duplicate_generation_identity")
    assert len(report["generations"]) == 11
    assert kept(report, "keep_unverified") == {"generation-00"}
    assert render_report(report) == render_report(
        classify(replace(snapshot, generations=tuple(reversed(snapshot.generations))))
    )


def test_empty_candidate_set_does_not_turn_blocked_report_into_success() -> None:
    assert classify(inventory())["candidate_set_status"] == "advisory"
    assert_blocked(classify(inventory(), None), "pin_authority_missing")
    assert_blocked(classify(replace(inventory(), stable=None)), "inventory_unstable")


def test_unverified_newest_does_not_displace_verified_retention_representatives() -> None:
    snapshot = dense_inventory()
    latest = replace(generation("newest-unverified", "2026-09-01T00:00:00Z"), r2=None)
    report = classify(replace(snapshot, generations=(*snapshot.generations, latest)))
    expected = classify(snapshot)
    for reason in ("keep_recent", "keep_daily", "keep_weekly", "keep_monthly"):
        assert kept(report, reason) == kept(expected, reason)
    assert kept(report, "keep_unverified") == {latest.generation_id}


def test_report_does_not_read_execution_time(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoClock(datetime):
        @classmethod
        def now(cls, *args: object, **kwargs: object) -> datetime:
            raise AssertionError("execution time must not affect classification")

        @classmethod
        def utcnow(cls) -> datetime:
            raise AssertionError("execution time must not affect classification")

    snapshot = dense_inventory()
    expected = render_report(classify(snapshot))
    monkeypatch.setattr(rotation_dryrun, "datetime", NoClock)
    assert render_report(classify(snapshot)) == expected


def test_report_preserves_evidence_authority_and_input_digest_without_mutating_inputs() -> None:
    snapshot = dense_inventory()
    before = repr(snapshot)
    report = classify(snapshot)
    assert repr(snapshot) == before
    decoded = json.loads(render_report(report))
    assert decoded["inventory"]["limitations"] == list(snapshot.limitations)
    assert decoded["pins"] == {
        "authority_ref": EMPTY_PINS.authority_ref,
        "confirmed": True,
        "pins": [],
    }
    row = decoded["generations"][0]
    assert row["local"]["verifier"] == LOCAL_VERIFIER
    assert row["r2"]["verifier"] == REMOTE_VERIFIER
    assert row["local"]["manifest_sha256"] == row["r2"]["manifest_sha256"]
    assert row["manifest_sha256"] == snapshot.generations[0].manifest_sha256
    assert report["input_sha256"] != classify(replace(snapshot, stable=False))["input_sha256"]
    assert report["input_sha256"] != classify(snapshot, None)["input_sha256"]


def test_valid_pin_reason_is_preserved_even_when_another_pin_blocks_candidates() -> None:
    snapshot = dense_inventory()
    first = snapshot.generations[0]
    pins = replace(
        EMPTY_PINS,
        pins=(
            MilestonePin(first.generation_id, first.manifest_sha256),
            MilestonePin("missing", "a" * 64),
        ),
    )
    report = classify(snapshot, pins)
    assert_blocked(report, "pin_generation_missing_or_ambiguous")
    assert kept(report, "keep_milestone") == {first.generation_id}


@pytest.mark.parametrize(
    "policy",
    [
        RetentionPolicy(recent=0),
        RetentionPolicy(daily=True),
        RetentionPolicy(monthly=3.0),
        RetentionPolicy(weekly=5),
    ],
)
def test_unsupported_policy_is_rejected(policy: RetentionPolicy) -> None:
    with pytest.raises(ValueError, match="8/7/4/3"):
        classify_snapshot(dense_inventory(), pins=EMPTY_PINS, policy=policy)


def test_classifier_and_renderer_perform_zero_external_or_destructive_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = dense_inventory()
    expected = render_report(classify(snapshot))
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("unexpected external operation")
        raise AssertionError("classifier must not perform external operations")

    with monkeypatch.context() as patch:
        for module, names in (
            (builtins, ("open",)),
            (io, ("open",)),
            (
                os,
                (
                    "scandir",
                    "listdir",
                    "open",
                    "stat",
                    "remove",
                    "unlink",
                    "rename",
                    "replace",
                    "truncate",
                    "rmdir",
                    "system",
                ),
            ),
            (subprocess, ("Popen",)),
            (socket, ("socket", "create_connection")),
            (Path, ("read_bytes", "read_text", "write_bytes", "write_text")),
        ):
            for name in names:
                patch.setattr(module, name, forbidden)
        assert render_report(classify(snapshot)) == expected
    assert calls == []
