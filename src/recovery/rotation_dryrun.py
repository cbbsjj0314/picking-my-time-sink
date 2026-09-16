"""Classify explicit recovery evidence snapshots without performing I/O."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

LOCAL_VERIFIER = "recovery.postgres_artifact.verify_generation"
REMOTE_VERIFIER = "recovery.r2_publish.verify_remote_generation"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")


@dataclass(frozen=True)
class RetentionPolicy:
    recent: int = 8
    daily: int = 7
    weekly: int = 4
    monthly: int = 3


@dataclass(frozen=True)
class VerificationEvidence:
    """Caller-supplied A1/A2 attestation, not a replacement artifact verifier."""

    verifier: str
    status: str
    evidence_ref: str | None
    generation_id: str
    manifest_sha256: str
    completed_at_utc: str
    verified_at_utc: str
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenerationSnapshot:
    generation_id: str
    manifest_sha256: str
    completed_at_utc: str
    local: VerificationEvidence | None
    r2: VerificationEvidence | None


@dataclass(frozen=True)
class InventorySnapshot:
    snapshot_id: str
    authority_ref: str | None
    generations: tuple[GenerationSnapshot, ...]
    local_complete: bool | None
    r2_complete: bool | None
    stable: bool | None
    completeness_evidence_ref: str | None
    stability_evidence_ref: str | None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class MilestonePin:
    generation_id: str
    manifest_sha256: str


@dataclass(frozen=True)
class PinSnapshot:
    authority_ref: str | None
    confirmed: bool | None
    pins: tuple[MilestonePin, ...]


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _present(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _timestamp(value: object) -> datetime | None:
    if not _matches(_UTC, value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _verification_reasons(generation: GenerationSnapshot) -> tuple[set[str], bool]:
    reasons: set[str] = set()
    conflict = False
    completed = _timestamp(generation.completed_at_utc)
    if not _matches(_ID, generation.generation_id):
        reasons.add("invalid_generation_id")
    if not _matches(_SHA256, generation.manifest_sha256):
        reasons.add("invalid_manifest_sha256")
    if completed is None:
        reasons.add("invalid_completed_at_utc")
    for location, evidence, verifier in (
        ("local", generation.local, LOCAL_VERIFIER),
        ("r2", generation.r2, REMOTE_VERIFIER),
    ):
        if evidence is None:
            reasons.add(f"{location}_evidence_missing")
            continue
        if evidence.verifier != verifier:
            reasons.add(f"{location}_verifier_unsupported")
        if evidence.status != "PASS":
            reasons.add(f"{location}_verification_not_pass")
        if not _present(evidence.evidence_ref):
            reasons.add(f"{location}_evidence_reference_missing")
        if evidence.issues:
            reasons.add(f"{location}_verification_issues")
            if evidence.status == "PASS":
                conflict = True
        if (
            evidence.generation_id != generation.generation_id
            or evidence.manifest_sha256 != generation.manifest_sha256
            or evidence.completed_at_utc != generation.completed_at_utc
        ):
            reasons.add(f"{location}_binding_mismatch")
            conflict = True
        verified = _timestamp(evidence.verified_at_utc)
        if verified is None:
            reasons.add(f"{location}_invalid_verified_at_utc")
        elif completed is not None and verified < completed:
            reasons.add(f"{location}_verification_precedes_completion")
            conflict = True
    return reasons, conflict


def _generation_record(generation: GenerationSnapshot) -> dict:
    record = asdict(generation)
    for location in ("local", "r2"):
        if record[location] is not None:
            record[location]["issues"] = sorted(record[location]["issues"])
    return record


def classify_snapshot(
    inventory: InventorySnapshot,
    *,
    pins: PinSnapshot | None,
    policy: RetentionPolicy,
) -> dict:
    """Return advisory classifications conditional on the supplied evidence authority."""

    if (
        any(type(value) is not int for value in asdict(policy).values())
        or policy != RetentionPolicy()
    ):
        raise ValueError("only the accepted 8/7/4/3 retention policy is supported")

    generations = sorted(
        inventory.generations,
        key=lambda item: (
            item.generation_id,
            item.manifest_sha256,
            _json(_generation_record(item)),
        ),
    )
    inventory_record = asdict(inventory)
    inventory_record["generations"] = [_generation_record(item) for item in generations]
    inventory_record["limitations"] = sorted(inventory.limitations)
    pin_record = asdict(pins) if pins is not None else None
    if pin_record is not None:
        pin_record["pins"] = sorted(pin_record["pins"], key=_json)
    inputs = {"inventory": inventory_record, "pins": pin_record, "policy": asdict(policy)}

    blockers: set[str] = set()
    if not _present(inventory.snapshot_id) or not _present(inventory.authority_ref):
        blockers.add("inventory_authority_missing")
    if inventory.local_complete is not True:
        blockers.add("local_inventory_incomplete")
    if inventory.r2_complete is not True:
        blockers.add("r2_inventory_incomplete")
    if not _present(inventory.completeness_evidence_ref):
        blockers.add("inventory_completeness_evidence_missing")
    if inventory.stable is not True:
        blockers.add("inventory_unstable")
    if not _present(inventory.stability_evidence_ref):
        blockers.add("inventory_stability_evidence_missing")

    counts = Counter(item.generation_id for item in generations)
    if any(count > 1 for count in counts.values()):
        blockers.add("duplicate_generation_identity")
    reasons_by_row: list[set[str]] = []
    verified: dict[str, GenerationSnapshot] = {}
    for generation in generations:
        reasons, conflict = _verification_reasons(generation)
        if counts[generation.generation_id] > 1:
            reasons.add("duplicate_generation_identity")
        if conflict:
            blockers.add("conflicting_verification_evidence")
        reasons_by_row.append(reasons)
        if not reasons:
            verified[generation.generation_id] = generation

    pin_reasons: set[str] = set()
    matched_pins: set[str] = set()
    if pins is None or pins.confirmed is not True or not _present(pins.authority_ref):
        pin_reasons.add("pin_authority_missing")
    if pins is not None:
        hashes_by_id: dict[str, set[str]] = {}
        for pin in pins.pins:
            hashes_by_id.setdefault(pin.generation_id, set()).add(pin.manifest_sha256)
            if not _matches(_ID, pin.generation_id) or not _matches(_SHA256, pin.manifest_sha256):
                pin_reasons.add("pin_binding_invalid")
            matches = [item for item in generations if item.generation_id == pin.generation_id]
            if len(matches) != 1:
                pin_reasons.add("pin_generation_missing_or_ambiguous")
            elif matches[0].manifest_sha256 != pin.manifest_sha256:
                pin_reasons.add("pin_manifest_mismatch")
            elif pin.generation_id not in verified:
                pin_reasons.add("pin_state_unverifiable")
            else:
                matched_pins.add(pin.generation_id)
        if any(len(hashes) > 1 for hashes in hashes_by_id.values()):
            pin_reasons.add("conflicting_pins")
    blockers.update(pin_reasons)

    # A1 timestamps have fixed UTC second precision; lexical order equals time order.
    newest = sorted(verified.values(), key=lambda item: item.generation_id)
    newest.sort(key=lambda item: item.completed_at_utc, reverse=True)
    keep: dict[str, set[str]] = {item.generation_id: set() for item in generations}
    for generation in newest[: policy.recent]:
        keep[generation.generation_id].add("keep_recent")
    for tier in ("daily", "weekly", "monthly"):
        buckets: set[object] = set()
        for generation in newest:
            stamp = _timestamp(generation.completed_at_utc)
            assert stamp is not None
            bucket = {
                "daily": stamp.date(),
                "weekly": stamp.isocalendar()[:2],
                "monthly": (stamp.year, stamp.month),
            }[tier]
            if bucket not in buckets and len(buckets) < getattr(policy, tier):
                buckets.add(bucket)
                keep[generation.generation_id].add(f"keep_{tier}")
    if "pin_authority_missing" not in pin_reasons:
        for generation_id in matched_pins:
            keep[generation_id].add("keep_milestone")

    rows: list[dict] = []
    candidates: list[dict] = []
    for generation, reasons in zip(generations, reasons_by_row, strict=True):
        classifications = set(keep[generation.generation_id])
        if reasons:
            classifications.add("keep_unverified")
        elif not classifications:
            if blockers:
                classifications.add("rotation_blocked")
            else:
                classifications.add("eligible_for_rotation")
                candidates.append(
                    {
                        "generation_id": generation.generation_id,
                        "manifest_sha256": generation.manifest_sha256,
                    }
                )
        rows.append(
            {
                **_generation_record(generation),
                "classifications": sorted(classifications),
                "verification": "unverified" if reasons else "verified",
                "verification_reasons": sorted(reasons),
            }
        )

    return {
        "contract_version": "postgres-recovery-rotation-dryrun/v1",
        "advisory_only": True,
        "input_sha256": hashlib.sha256(_json(inputs).encode("utf-8")).hexdigest(),
        "newest_order": ["completed_at_utc descending", "generation_id ascending"],
        "policy": asdict(policy),
        "inventory": {
            key: value for key, value in inventory_record.items() if key != "generations"
        },
        "pins": pin_record,
        "candidate_set_status": "blocked" if blockers else "advisory",
        "candidate_set_blocking_reasons": sorted(blockers),
        "generations": rows,
        "advisory_candidates": candidates,
    }


def render_report(report: dict) -> str:
    """Serialize without timestamps, filesystem writes, or execution instructions."""

    return _json(report) + "\n"
