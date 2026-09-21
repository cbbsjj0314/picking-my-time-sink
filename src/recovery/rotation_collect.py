"""One bounded read-only inventory attempt, separate from pure retention replay."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from recovery import postgres_artifact, r2_publish
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
from steam.ingest.s3_compat import ListObjectsV2Page

PREFIX = r2_publish.PORTABLE_KEY_ROOT + "/"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DUMP = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\.dump\Z")
_FORMAT = "postgres-recovery-rotation-collection/v1"
_LIMITATION = "bounded observations are not a transactional snapshot; undetected ABA is possible"


class InventoryStore(Protocol):
    """No publish or destructive operation is exposed to the collector."""

    def list_objects_v2_page(
        self,
        *,
        prefix: str,
        continuation_token: str | None,
        max_keys: int,
        max_response_bytes: int,
    ) -> ListObjectsV2Page: ...

    def get_bytes(self, *, object_key: str, max_bytes: int | None = None) -> bytes: ...

    def get_file(
        self,
        *,
        object_key: str,
        destination_path: Path,
        chunk_size: int,
        max_bytes: int | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class CollectionAuthority:
    """Human-reviewed references, never credentials or inferred provider permissions."""

    handoff_ref: str
    target_ref: str
    r2_read_only_ref: str
    local_identity_ref: str
    local_write_capable: bool


@dataclass(frozen=True)
class CollectionLimits:
    max_local_entries: int
    max_dump_bytes: int
    max_local_bytes: int
    max_pages: int
    max_objects: int
    page_size: int = 1000
    max_page_bytes: int = 1024 * 1024

    def validate(self) -> None:
        if any(type(value) is not int or value <= 0 for value in asdict(self).values()):
            raise ValueError("collection limits must be explicit positive integers")
        if self.page_size > 1000 or self.max_dump_bytes > r2_publish.MAX_SINGLE_PUT_BYTES:
            raise ValueError("collection limits exceed supported bounds")


@dataclass(frozen=True)
class CollectionResult:
    inventory: InventorySnapshot
    input_json: str
    report_json: str
    evidence_json: str


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode(payload: str | bytes) -> dict:
    value = json.loads(payload, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    # Resolve each lexical component with dir_fd; no ancestor symlink traversal.
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("recovery root must be an absolute lexical path")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _names(descriptor: int, limit: int) -> list[str]:
    names = []
    with os.scandir(descriptor) as entries:
        for entry in entries:
            names.append(entry.name)
            if len(names) > limit:
                raise ValueError("local_entry_budget_exhausted")
    if len(names) != len(set(names)):
        raise ValueError("duplicate_local_entry")
    return sorted(names)


def _read_file(
    descriptor: int,
    name: str,
    *,
    limit: int,
    remaining: list[int],
    destination: Path | None = None,
    retain: bool = False,
) -> tuple[dict, bytes]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > min(limit, remaining[0]):
            raise ValueError("unsafe_or_oversized_local_file")
        digest, payload, count = hashlib.sha256(), bytearray(), 0
        output = destination.open("xb") if destination is not None else None
        try:
            while chunk := source.read(min(1024 * 1024, limit + 1 - count)):
                count += len(chunk)
                remaining[0] -= len(chunk)
                if count > limit or remaining[0] < 0:
                    raise ValueError("local_byte_budget_exhausted")
                digest.update(chunk)
                if retain:
                    payload.extend(chunk)
                if output is not None:
                    output.write(chunk)
        finally:
            if output is not None:
                output.close()
        after = os.fstat(source.fileno())
        current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if _identity(before) != _identity(after) or _identity(after) != _identity(current):
            raise ValueError("local_file_changed")
        if count != before.st_size:
            raise ValueError("local_file_changed")
        return {"identity": _identity(after), "sha256": digest.hexdigest()}, bytes(payload)


def _local_pass(root: Path, limits: CollectionLimits, capture: Path | None) -> dict:
    observation: dict = {"complete": True, "completed": {}, "staging": [], "issues": []}
    observation["started_at_utc"] = _stamp()
    remaining = [limits.max_local_bytes]
    try:
        with _directory(root) as root_fd:
            root_stat = os.fstat(root_fd)
            observation["root_identity"] = (root_stat.st_dev, root_stat.st_ino)
            completed_fd = os.open(
                "completed", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
            )
            try:
                before = _identity(os.fstat(completed_fd))
                names = _names(completed_fd, limits.max_local_entries)
                for name in names:
                    row: dict = {"files": {}, "captured": False}
                    observation["completed"][name] = row
                    try:
                        entry = os.stat(name, dir_fd=completed_fd, follow_symlinks=False)
                        row["identity"] = _identity(entry)
                        if not _ID.fullmatch(name) or not stat.S_ISDIR(entry.st_mode):
                            raise ValueError("unsafe_local_generation")
                        fd = os.open(
                            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=completed_fd
                        )
                        try:
                            if _identity(os.fstat(fd)) != row["identity"]:
                                raise ValueError("local_generation_changed")
                            children = _names(fd, limits.max_local_entries)
                            row["children"] = children
                            target = capture / name if capture is not None else None
                            if target is not None:
                                target.mkdir()
                            fingerprint, payload = _read_file(
                                fd,
                                "manifest.json",
                                limit=64 * 1024,
                                remaining=remaining,
                                destination=target / "manifest.json" if target else None,
                                retain=True,
                            )
                            row["files"]["manifest.json"] = fingerprint
                            manifest = _decode(payload)
                            filename = manifest.get("dump_filename")
                            if not isinstance(filename, str) or not _DUMP.fullmatch(filename):
                                raise ValueError("invalid_manifest_filename")
                            expected = sorted(["manifest.json", filename, filename + ".sha256"])
                            if children != expected:
                                raise ValueError("local_generation_file_set_mismatch")
                            for child, bound in (
                                (filename, limits.max_dump_bytes),
                                (filename + ".sha256", 256),
                            ):
                                fingerprint, _ = _read_file(
                                    fd,
                                    child,
                                    limit=bound,
                                    remaining=remaining,
                                    destination=target / child if target else None,
                                )
                                row["files"][child] = fingerprint
                            if (
                                _identity(os.fstat(fd)) != row["identity"]
                                or _identity(
                                    os.stat(name, dir_fd=completed_fd, follow_symlinks=False)
                                )
                                != row["identity"]
                                or _names(fd, limits.max_local_entries) != children
                            ):
                                raise ValueError("local_generation_changed")
                            row["captured"] = True
                        finally:
                            os.close(fd)
                    except (OSError, ValueError, UnicodeError):
                        row["issue"] = "local_generation_unaccountable"
                        observation["complete"] = False
                observation["completed_identity"] = before
                if before != _identity(os.fstat(completed_fd)) or names != _names(
                    completed_fd, limits.max_local_entries
                ):
                    raise ValueError("completed_inventory_changed")
            finally:
                os.close(completed_fd)
            try:
                staging_fd = os.open(
                    "staging", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
                )
            except FileNotFoundError:
                observation["staging_state"] = "absent"
            else:
                try:
                    observation["staging_state"] = "observed"
                    observation["staging"] = [
                        {
                            "name": name,
                            "identity": _identity(
                                os.stat(name, dir_fd=staging_fd, follow_symlinks=False)
                            ),
                        }
                        for name in _names(staging_fd, limits.max_local_entries)
                    ]
                finally:
                    os.close(staging_fd)
    except (OSError, ValueError):
        observation["complete"] = False
        observation["issues"].append("local_inventory_unaccountable_or_budget_exhausted")
    observation["finished_at_utc"] = _stamp()
    return observation


def _remote_pass(client: InventoryStore, limits: CollectionLimits) -> dict:
    observation: dict = {"complete": False, "objects": {}, "pages": [], "issues": []}
    observation["started_at_utc"] = _stamp()
    token: str | None = None
    tokens: set[str] = set()
    try:
        for _ in range(limits.max_pages):
            page = client.list_objects_v2_page(
                prefix=PREFIX,
                continuation_token=token,
                max_keys=limits.page_size,
                max_response_bytes=limits.max_page_bytes,
            )
            observation["pages"].append(
                {
                    "continuation_token": token,
                    "next_continuation_token": page.next_continuation_token,
                    "is_truncated": page.is_truncated,
                }
            )
            if type(page.is_truncated) is not bool or len(page.objects) > limits.page_size:
                raise ValueError("malformed_list_page")
            for obj in page.objects:
                if obj.key in observation["objects"]:
                    raise ValueError("duplicate_remote_key")
                observation["objects"][obj.key] = asdict(obj)
                if len(observation["objects"]) > limits.max_objects:
                    raise ValueError("remote_object_budget_exhausted")
            if not page.is_truncated:
                if page.next_continuation_token is not None:
                    raise ValueError("malformed_list_page")
                observation["complete"] = True
                observation["finished_at_utc"] = _stamp()
                return observation
            token = page.next_continuation_token
            if not isinstance(token, str) or not token or token in tokens:
                raise ValueError("missing_or_cyclic_continuation_token")
            tokens.add(token)
        observation["issues"].append("remote_page_budget_exhausted")
    except Exception:
        observation["issues"].append("remote_listing_incomplete")
    observation["finished_at_utc"] = _stamp()
    return observation


def _remote_groups(observation: dict) -> tuple[dict[str, set[str]], list[str]]:
    groups: dict[str, set[str]] = {}
    issues = []
    for key in observation["objects"]:
        parts = key.removeprefix(PREFIX).split("/")
        if not key.startswith(PREFIX) or len(parts) != 2 or not _ID.fullmatch(parts[0]):
            issues.append("unaccountable_remote_key")
            continue
        groups.setdefault(parts[0], set()).add(parts[1])
    for files in groups.values():
        dumps = [name for name in files if _DUMP.fullmatch(name)]
        if len(dumps) != 1 or files != {"manifest.json", dumps[0], dumps[0] + ".sha256"}:
            issues.append("partial_or_ambiguous_remote_generation")
    return groups, issues


def _verification(
    name: str,
    row: dict,
    capture: Path,
    client: InventoryStore,
    evidence_ref: str,
) -> GenerationSnapshot:
    digest = row.get("files", {}).get("manifest.json", {}).get("sha256", "")
    completed, local, remote = "", None, None
    if row.get("captured"):
        generation = capture / name
        # The capture is private and exclusively created; A1/A2 never read the live root.
        manifest = _decode((generation / "manifest.json").read_bytes())
        claimed_completed = manifest.get("completed_at_utc")
        try:
            result = postgres_artifact.verify_generation(generation)
            passed = result.passed is True
        except (OSError, ValueError, UnicodeError):
            passed = False
        completed = claimed_completed if passed and isinstance(claimed_completed, str) else ""
        local = VerificationEvidence(
            LOCAL_VERIFIER,
            "PASS" if passed else "FAIL",
            f"{evidence_ref}#V/{name}/local",
            name,
            digest,
            completed,
            _stamp(),
            () if passed else ("a1_verification_failed",),
        )
        if passed:
            try:
                result = r2_publish.verify_remote_generation(
                    client=client,
                    generation_dir=generation,
                )
                remote_passed = result.verified is True and result.generation_id == name
            except r2_publish.RecoveryPublishError:
                remote_passed = False
            remote = VerificationEvidence(
                REMOTE_VERIFIER,
                "PASS" if remote_passed else "FAIL",
                f"{evidence_ref}#V/{name}/r2",
                name,
                digest,
                completed,
                _stamp(),
                () if remote_passed else ("a2_verification_failed",),
            )
    return GenerationSnapshot(name, digest, completed, local, remote)


def freeze_input(inventory: InventorySnapshot, pins: PinSnapshot | None) -> str:
    return render_report(
        {
            "contract_version": _FORMAT,
            "inventory": asdict(inventory),
            "pins": asdict(pins) if pins is not None else None,
            "policy": asdict(RetentionPolicy()),
        }
    )


def replay_frozen_input(payload: str) -> str:
    """Replay serialized attestations without filesystem, transport or clock access."""
    document = _decode(payload)
    if set(document) != {"contract_version", "inventory", "pins", "policy"}:
        raise ValueError("invalid frozen input fields")
    if document["contract_version"] != _FORMAT:
        raise ValueError("unsupported frozen input contract")
    inventory = dict(document["inventory"])
    generations = []
    for value in inventory.pop("generations"):
        row = dict(value)
        for side in ("local", "r2"):
            if row[side] is not None:
                evidence = dict(row[side])
                evidence["issues"] = tuple(evidence["issues"])
                row[side] = VerificationEvidence(**evidence)
        generations.append(GenerationSnapshot(**row))
    inventory["limitations"] = tuple(inventory["limitations"])
    frozen = InventorySnapshot(**inventory, generations=tuple(generations))
    pins = document["pins"]
    if pins is not None:
        pins = dict(pins)
        pins["pins"] = tuple(MilestonePin(**pin) for pin in pins["pins"])
        pins = PinSnapshot(**pins)
    return render_report(
        classify_snapshot(frozen, pins=pins, policy=RetentionPolicy(**document["policy"]))
    )


def collect_inventory(
    *,
    recovery_root: Path,
    attempt_dir: Path,
    client: InventoryStore,
    authority: CollectionAuthority,
    limits: CollectionLimits,
    pins: PinSnapshot | None,
    snapshot_id: str,
    evidence_ref: str,
) -> CollectionResult:
    """Collect once into a new private directory outside the authoritative root."""
    limits.validate()
    refs = (
        authority.handoff_ref,
        authority.target_ref,
        authority.r2_read_only_ref,
        authority.local_identity_ref,
        snapshot_id,
        evidence_ref,
    )
    if not all(isinstance(ref, str) and ref.strip() for ref in refs):
        raise ValueError("explicit collection authority and evidence references required")
    if type(authority.local_write_capable) is not bool:
        raise ValueError("effective local write capability must be explicit")
    recovery_root, attempt_dir = Path(recovery_root), Path(attempt_dir)
    if (
        not recovery_root.is_absolute()
        or not attempt_dir.is_absolute()
        or attempt_dir.resolve().is_relative_to(recovery_root.resolve())
        or recovery_root.resolve().is_relative_to(attempt_dir.resolve())
    ):
        raise ValueError("private attempt directory must be separate from the recovery root")
    attempt_dir.mkdir(mode=0o700)
    capture = attempt_dir / "captures"
    capture.mkdir()
    l0 = _local_pass(recovery_root, limits, capture)
    r0 = _remote_pass(client, limits)
    groups, remote_issues = _remote_groups(r0)
    for name, row in l0["completed"].items():
        if row.get("captured") and set(row["files"]) != groups.get(name, set()):
            remote_issues.append("local_remote_file_set_mismatch")
        for filename, fingerprint in row["files"].items():
            obj = r0["objects"].get(f"{PREFIX}{name}/{filename}")
            if obj is not None and obj["size"] != fingerprint["identity"][3]:
                remote_issues.append("local_remote_size_mismatch")
    generations = [
        _verification(name, row, capture, client, evidence_ref)
        for name, row in sorted(l0["completed"].items())
    ]
    generations.extend(
        GenerationSnapshot(name, "", "", None, None)
        for name in sorted(groups.keys() - l0["completed"].keys())
    )
    r1 = _remote_pass(client, limits)
    l1 = _local_pass(recovery_root, limits, None)
    _, second_issues = _remote_groups(r1)
    local_complete = l0["complete"] and l1["complete"]
    r2_complete = r0["complete"] and r1["complete"] and not (remote_issues or second_issues)
    stable = bool(
        local_complete
        and r2_complete
        and all(
            l0.get(key) == l1.get(key)
            for key in ("root_identity", "completed_identity", "completed")
        )
        and r0["objects"] == r1["objects"]
    )
    issues = sorted(
        set(
            remote_issues
            + second_issues
            + l0["issues"]
            + l1["issues"]
            + r0["issues"]
            + r1["issues"]
        )
    )
    if not local_complete:
        issues.append("local_inventory_incomplete")
    if not stable:
        issues.append("inventory_unstable")
    # Phase 1 semantics remain unchanged. Withhold the collector attestation if any
    # required A1/A2 authority is absent; completeness still describes enumeration.
    verified = all(
        g.local is not None
        and g.local.status == "PASS"
        and g.r2 is not None
        and g.r2.status == "PASS"
        for g in generations
    )
    if not verified:
        issues.append("required_verification_authority_missing")
    inventory = InventorySnapshot(
        snapshot_id,
        authority.handoff_ref if verified else None,
        tuple(generations),
        bool(local_complete),
        bool(r2_complete),
        stable,
        f"{evidence_ref}#completeness",
        f"{evidence_ref}#stability",
        tuple(sorted(set(issues + [_LIMITATION]))),
    )
    frozen = freeze_input(inventory, pins)
    report = replay_frozen_input(frozen)
    evidence = render_report(
        {
            "contract_version": _FORMAT,
            "authority": asdict(authority),
            "limits": asdict(limits),
            "snapshot_id": snapshot_id,
            "evidence_ref": evidence_ref,
            "recovery_root": str(recovery_root),
            "capture_root": str(capture),
            "sequence": ["L0", "R0", "V", "R1", "L1"],
            "L0": l0,
            "R0": r0,
            "V": [asdict(g) for g in generations],
            "R1": r1,
            "L1": l1,
            "issues": issues,
            "limitations": [_LIMITATION],
            "input_sha256": hashlib.sha256(frozen.encode()).hexdigest(),
            "report_sha256": hashlib.sha256(report.encode()).hexdigest(),
        }
    )
    for name, content in (
        ("input.json", frozen),
        ("report.json", report),
        ("evidence.json", evidence),
    ):
        with (attempt_dir / name).open("x", encoding="utf-8") as destination:
            destination.write(content)
    return CollectionResult(inventory, frozen, report, evidence)
