from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from xml.sax.saxutils import escape

import pytest

from recovery import postgres_artifact, r2_publish
from recovery import rotation_collect as collect
from recovery.rotation_dryrun import MilestonePin, PinSnapshot
from steam.ingest.s3_compat import (
    S3CompatibleObjectStoreClient,
    S3CompatibleObjectStoreConfig,
)

PINS = PinSnapshot("synthetic:human-pins", True, ())
AUTHORITY = collect.CollectionAuthority(
    "synthetic:handoff",
    "synthetic:target",
    "synthetic:r2-read-only",
    "synthetic:local-identity",
    False,
)
LIMITS = collect.CollectionLimits(100, 1024, 100_000, 100, 1000, page_size=2)


class Response(BytesIO):
    status = 200


class Transport:
    def __init__(self, objects):
        self.objects = objects
        self.calls = []
        self.starts = 0
        self.hook = None
        self.edit_page = None

    def __call__(self, request, *, context):
        assert request.get_method() == "GET"
        assert request.data is None
        url = urlsplit(request.full_url)
        query = parse_qs(url.query)
        if "list-type" not in query:
            key = unquote(url.path).removeprefix("/bucket/")
            self.calls.append(("GET", key))
            if self.hook:
                self.hook("GET", self)
            return Response(self.objects[key])
        token = query.get("continuation-token", [None])[0]
        if token is None:
            self.starts += 1
        self.calls.append(("LIST", token))
        if self.hook:
            self.hook("LIST", self)
        prefix = query["prefix"][0]
        assert prefix == collect.PREFIX
        offset = int(token.split(":")[1].split("+")[0]) if token is not None else 0
        count = int(query["max-keys"][0])
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        page_keys = keys[offset : offset + count]
        truncated = offset + count < len(keys)
        next_token = f"opaque:{offset + count}+/= space"
        xml = (
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<Name>bucket</Name><Prefix>{prefix}</Prefix><MaxKeys>{count}</MaxKeys>"
            f"<KeyCount>{len(page_keys)}</KeyCount>"
            f"<IsTruncated>{str(truncated).lower()}</IsTruncated>"
        )
        if token is not None:
            xml += f"<ContinuationToken>{escape(token)}</ContinuationToken>"
        if truncated:
            xml += f"<NextContinuationToken>{escape(next_token)}</NextContinuationToken>"
        for key in page_keys:
            body = self.objects[key]
            xml += (
                f"<Contents><Key>{escape(key)}</Key><Size>{len(body)}</Size>"
                f"<ETag>{hashlib.md5(body).hexdigest()}</ETag>"
                "<LastModified>2026-01-01T00:00:00.000Z</LastModified></Contents>"
            )
        xml += "</ListBucketResult>"
        if self.edit_page:
            xml = self.edit_page(xml, token)
        return Response(xml.encode())


def generation(root, name, hour=0):
    path = root / "completed" / name
    path.mkdir(parents=True)
    dump = b"synthetic-custom-dump"
    digest = hashlib.sha256(dump).hexdigest()
    manifest = {
        "checksum_algorithm": "sha256",
        "checksum_value": digest,
        "created_at_utc": f"2026-01-01T{hour:02}:00:00Z",
        "completed_at_utc": f"2026-01-01T{hour:02}:00:01Z",
        "contract_version": "postgres-recovery-artifact/v1",
        "database_logical_name": "appdb",
        "dump_filename": "appdb.dump",
        "dump_format": "custom",
        "dump_size_bytes": len(dump),
        "generation_id": name,
        "generator": "recovery.postgres_artifact",
        "verification_status": "PASS",
    }
    (path / "manifest.json").write_text(json.dumps(manifest))
    (path / "appdb.dump").write_bytes(dump)
    (path / "appdb.dump.sha256").write_text(digest + "\n")
    return path


@pytest.fixture
def setup(tmp_path):
    root = tmp_path.resolve() / "source"
    objects = {}
    for i in range(10):
        path = generation(root, f"manual-{i:02}", i)
        for file in path.iterdir():
            objects[f"{collect.PREFIX}{path.name}/{file.name}"] = file.read_bytes()
    (root / "staging" / "pending").mkdir(parents=True)
    transport = Transport(objects)
    client = S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig(
            "https://example.invalid", "bucket", "test-region", "test-access", "test-secret"
        ),
        transport=transport,
    )
    return root, client, transport


def run(setup, **kwargs):
    root, client, _ = setup
    return collect.collect_inventory(
        recovery_root=root,
        attempt_dir=root.parent / "attempt",
        client=client,
        authority=AUTHORITY,
        limits=kwargs.pop("limits", LIMITS),
        pins=kwargs.pop("pins", PINS),
        snapshot_id="synthetic-attempt",
        evidence_ref="synthetic:attempt/evidence.json",
        **kwargs,
    )


def blocked(result):
    report = json.loads(result.report_json)
    assert report["candidate_set_status"] == "blocked"
    assert report["advisory_candidates"] == []
    return report


def test_actual_a1_a2_capture_binding_stability_replay_and_no_source_mutation(setup, monkeypatch):
    root, _, transport = setup
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    a1, a2 = postgres_artifact.verify_generation, r2_publish.verify_remote_generation
    verified_paths, remote_paths = [], []

    def verify(path):
        assert not path.is_relative_to(root)
        verified_paths.append(path)
        return a1(path)

    def remote(**kwargs):
        remote_paths.append(kwargs["generation_dir"])
        return a2(**kwargs)

    monkeypatch.setattr(postgres_artifact, "verify_generation", verify)
    monkeypatch.setattr(r2_publish, "verify_generation", verify)
    monkeypatch.setattr(r2_publish, "verify_remote_generation", remote)
    result = run(setup)
    report = json.loads(result.report_json)
    assert (
        result.inventory.local_complete and result.inventory.r2_complete and result.inventory.stable
    )
    assert [row["generation_id"] for row in report["advisory_candidates"]] == [
        "manual-00",
        "manual-01",
    ]
    assert len(verified_paths) == 30
    assert len(remote_paths) == 10
    for row in result.inventory.generations:
        expected = before[f"completed/{row.generation_id}/manifest.json"]
        assert row.manifest_sha256 == hashlib.sha256(expected).hexdigest()
        assert row.local.status == row.r2.status == "PASS"
        assert row.local.completed_at_utc == row.r2.completed_at_utc == row.completed_at_utc
        assert row.local.verified_at_utc >= row.completed_at_utc
        assert row.r2.verified_at_utc >= row.completed_at_utc
    evidence = json.loads(result.evidence_json)
    assert evidence["sequence"] == ["L0", "R0", "V", "R1", "L1"]
    assert evidence["L0"]["staging"][0]["name"] == "pending"
    assert transport.starts == 2
    assert [op for op, _ in transport.calls] == ["LIST"] * 15 + ["GET"] * 30 + ["LIST"] * 15
    assert before == {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    assert (root.parent / "attempt" / "input.json").read_text() == result.input_json
    assert (root.parent / "attempt" / "report.json").read_text() == result.report_json
    assert (root.parent / "attempt" / "evidence.json").read_text() == result.evidence_json

    def forbidden(*args, **kwargs):
        raise AssertionError("replay must not perform I/O or consult the clock")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(collect, "_stamp", forbidden)
    monkeypatch.setattr(S3CompatibleObjectStoreClient, "list_objects_v2_page", forbidden)
    monkeypatch.setattr(S3CompatibleObjectStoreClient, "get_bytes", forbidden)
    assert collect.replay_frozen_input(result.input_json) == result.report_json


@pytest.mark.parametrize(
    "damage",
    [
        "extra",
        "missing",
        "symlink",
        "fifo",
        "duplicate_json",
        "malformed",
        "bad_id",
        "checksum",
        "timestamp",
        "inaccessible",
        "unsafe_id",
        "directory_symlink",
    ],
)
def test_local_uncertainty_blocks_all_candidates(setup, monkeypatch, damage):
    root, _, _ = setup
    path = root / "completed" / "manual-09"
    if damage == "extra":
        (path / "extra").write_bytes(b"unexpected")
    elif damage == "missing":
        (path / "appdb.dump").unlink()
    elif damage == "symlink":
        (path / "appdb.dump").unlink()
        (path / "appdb.dump").symlink_to(root / "completed/manual-08/appdb.dump")
    elif damage == "fifo":
        (path / "appdb.dump").unlink()
        os.mkfifo(path / "appdb.dump")
    elif damage == "duplicate_json":
        manifest = path / "manifest.json"
        manifest.write_text(manifest.read_text().replace("{", '{"generation_id":"other",', 1))
    elif damage == "malformed":
        (path / "manifest.json").write_bytes(b"{bad")
    elif damage in {"bad_id", "timestamp"}:
        manifest = path / "manifest.json"
        content = json.loads(manifest.read_text())
        content["generation_id" if damage == "bad_id" else "completed_at_utc"] = "invalid"
        manifest.write_text(json.dumps(content))
    elif damage == "checksum":
        (path / "appdb.dump.sha256").write_text("bad")
    elif damage == "unsafe_id":
        (root / "completed" / "unsafe id").mkdir()
    elif damage == "directory_symlink":
        (root / "completed" / "linked").symlink_to(path, target_is_directory=True)
    else:
        original = collect._read_file

        def denied(fd, name, **kwargs):
            if name == "appdb.dump":
                raise PermissionError("PRIVATE_MARKER")
            return original(fd, name, **kwargs)

        monkeypatch.setattr(collect, "_read_file", denied)
    result = run(setup)
    blocked(result)
    assert "required_verification_authority_missing" in result.inventory.limitations
    assert "PRIVATE_MARKER" not in result.evidence_json


@pytest.mark.parametrize(
    "damage",
    [
        "remote_only",
        "local_only",
        "partial",
        "extra",
        "foreign",
        "bad_dump",
        "bad_manifest",
        "bad_checksum",
        "wrong_shape",
    ],
)
def test_remote_uncertainty_and_actual_readback_fail_closed(setup, damage):
    _, _, transport = setup
    base = collect.PREFIX + "manual-09/"
    if damage == "remote_only":
        for key, value in list(transport.objects.items()):
            if key.startswith(base):
                transport.objects[key.replace("manual-09", "remote-only")] = value
    elif damage == "local_only":
        transport.objects = {k: v for k, v in transport.objects.items() if not k.startswith(base)}
    elif damage == "partial":
        del transport.objects[base + "appdb.dump"]
    elif damage == "extra":
        transport.objects[base + "unknown"] = b"extra"
    elif damage == "foreign":
        transport.objects[collect.PREFIX + "not/a/generation"] = b"extra"
    elif damage == "wrong_shape":
        for suffix in ("appdb.dump", "appdb.dump.sha256"):
            transport.objects[base + suffix.replace("appdb", "other")] = transport.objects.pop(
                base + suffix
            )
    else:
        suffix = {
            "bad_dump": "appdb.dump",
            "bad_manifest": "manifest.json",
            "bad_checksum": "appdb.dump.sha256",
        }[damage]
        transport.objects[base + suffix] = b"invalid"
    result = run(setup)
    report = blocked(result)
    if damage == "remote_only":
        row = next(r for r in report["generations"] if r["generation_id"] == "remote-only")
        assert row["r2"] is None and row["verification"] == "unverified"
    if damage.startswith("bad_"):
        row = next(r for r in report["generations"] if r["generation_id"] == "manual-09")
        assert row["local"]["status"] == "PASS" and row["r2"]["status"] == "FAIL"


@pytest.mark.parametrize("where", ["local_add", "local_bytes", "r2_add", "r2_bytes", "staging"])
def test_concurrent_change_two_passes_no_retry_or_snapshot_merge(setup, where):
    root, _, transport = setup
    changed = False

    def hook(operation, transport):
        nonlocal changed
        if operation != "GET" or changed:
            return
        changed = True
        if where == "local_add":
            generation(root, "new-generation", 12)
        elif where == "local_bytes":
            (root / "completed/manual-00/appdb.dump").write_bytes(b"changed")
        elif where == "r2_add":
            transport.objects[collect.PREFIX + "new-generation/manifest.json"] = b"{}"
        elif where == "r2_bytes":
            transport.objects[collect.PREFIX + "manual-00/appdb.dump"] = b"changed"
        else:
            (root / "staging/new-staging").mkdir()

    transport.hook = hook
    result = run(setup)
    if where == "staging":
        assert result.inventory.stable
        assert len(json.loads(result.evidence_json)["L1"]["staging"]) == 2
    else:
        blocked(result)
        assert not result.inventory.stable
    assert transport.starts == 2
    assert "new-generation" not in [g.generation_id for g in result.inventory.generations]


@pytest.mark.parametrize("fault", ["missing_token", "cycle", "malformed", "duplicate", "error"])
def test_incomplete_pagination_blocks_candidates(setup, fault):
    _, _, transport = setup

    def edit(xml, token):
        if fault == "malformed":
            return "<broken"
        if fault == "error":
            raise OSError("PRIVATE_MARKER")
        if fault == "missing_token":
            return xml.replace("NextContinuationToken", "Ignored")
        if fault == "cycle" and token is not None:
            import re

            return re.sub(
                r"<NextContinuationToken>.*?</NextContinuationToken>",
                f"<NextContinuationToken>{escape(token)}</NextContinuationToken>",
                xml,
            )
        if fault == "duplicate" and token is not None:
            import re

            return re.sub(
                r"<Key>.*?</Key>", f"<Key>{collect.PREFIX}manual-00/appdb.dump</Key>", xml
            )
        return xml

    transport.edit_page = edit
    result = run(setup)
    blocked(result)
    assert not result.inventory.r2_complete
    assert transport.starts == 2
    assert "PRIVATE_MARKER" not in result.evidence_json


@pytest.mark.parametrize(
    "limits",
    [
        replace(LIMITS, max_pages=1),
        replace(LIMITS, max_objects=1),
        replace(LIMITS, max_page_bytes=1),
        replace(LIMITS, max_local_entries=1),
        replace(LIMITS, max_dump_bytes=1),
        replace(LIMITS, max_local_bytes=1),
    ],
)
def test_explicit_budgets_fail_closed(setup, limits):
    blocked(run(setup, limits=limits))


@pytest.mark.parametrize(
    "pins",
    [
        None,
        PinSnapshot("human", False, ()),
        PinSnapshot("human", True, (MilestonePin("manual-00", "0" * 64),)),
    ],
)
def test_pin_authority_remains_phase_one_owned(setup, pins):
    report = blocked(run(setup, pins=pins))
    assert any(reason.startswith("pin_") for reason in report["candidate_set_blocking_reasons"])


def test_matching_milestone_pin_keeps_old_generation(setup):
    root, _, _ = setup
    digest = hashlib.sha256((root / "completed/manual-00/manifest.json").read_bytes()).hexdigest()
    report = json.loads(
        run(
            setup, pins=PinSnapshot("human", True, (MilestonePin("manual-00", digest),))
        ).report_json
    )
    assert report["candidate_set_status"] == "advisory"
    assert [g["generation_id"] for g in report["advisory_candidates"]] == ["manual-01"]


def test_missing_authority_and_existing_or_overlapping_destination_do_no_io(setup):
    root, client, transport = setup
    options = dict(
        recovery_root=root,
        attempt_dir=root / "attempt",
        client=client,
        authority=AUTHORITY,
        limits=LIMITS,
        pins=PINS,
        snapshot_id="test",
        evidence_ref="synthetic:evidence",
    )
    with pytest.raises(ValueError):
        collect.collect_inventory(**options)
    options["attempt_dir"] = root.parent / "existing"
    options["attempt_dir"].mkdir()
    with pytest.raises(FileExistsError):
        collect.collect_inventory(**options)
    options["authority"] = replace(AUTHORITY, r2_read_only_ref="")
    with pytest.raises(ValueError):
        collect.collect_inventory(**options)
    assert not transport.calls


def test_root_symlink_is_not_followed(setup):
    root, client, transport = setup
    alias = root.parent / "alias"
    alias.symlink_to(root, target_is_directory=True)
    result = run((alias, client, transport))
    blocked(result)
    assert not result.inventory.local_complete
    assert not any(op == "GET" for op, _ in transport.calls)


def test_replay_rejects_duplicate_keys_and_unsupported_contract(setup):
    result = run(setup)
    with pytest.raises(ValueError):
        collect.replay_frozen_input(result.input_json.replace("{", '{"pins":null,', 1))
    with pytest.raises(ValueError):
        collect.replay_frozen_input(result.input_json.replace(collect._FORMAT, "unknown"))


def test_empty_inventory_is_advisory_not_operational_pass(setup):
    root, client, transport = setup
    empty = root.parent / "empty-source"
    (empty / "completed").mkdir(parents=True)
    transport.objects = {}
    result = run((empty, client, transport))
    report = json.loads(result.report_json)
    assert (
        result.inventory.stable and result.inventory.local_complete and result.inventory.r2_complete
    )
    assert report["candidate_set_status"] == "advisory"
    assert report["advisory_candidates"] == []
    assert "PASS" not in result.report_json
    assert transport.calls == [("LIST", None), ("LIST", None)]


def test_local_capture_detects_change_during_read(setup, monkeypatch):
    root, _, _ = setup
    original = collect._read_file
    changed = False

    def mutate(fd, name, **kwargs):
        nonlocal changed
        result = original(fd, name, **kwargs)
        if name == "manifest.json" and not changed:
            changed = True
            generation(root, "arrived-during-l0", 15)
        return result

    monkeypatch.setattr(collect, "_read_file", mutate)
    result = run(setup)
    blocked(result)
    assert not result.inventory.local_complete
    assert "arrived-during-l0" not in [row.generation_id for row in result.inventory.generations]


def test_duplicate_local_enumeration_is_not_silently_collapsed(setup, monkeypatch):
    original = collect.os.scandir

    class DuplicateEntries:
        def __init__(self, fd):
            with original(fd) as entries:
                self.entries = list(entries)

        def __enter__(self):
            return iter(self.entries + self.entries)

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(collect.os, "scandir", DuplicateEntries)
    result = run(setup)
    blocked(result)
    assert not result.inventory.local_complete


def test_replay_permutation_does_not_change_report(setup):
    result = run(setup)
    frozen = json.loads(result.input_json)
    frozen["inventory"]["generations"].reverse()
    frozen["inventory"]["limitations"].reverse()
    assert collect.replay_frozen_input(json.dumps(frozen)) == result.report_json


def test_list_metadata_never_substitutes_for_a2_get(setup):
    _, _, transport = setup

    # Both LIST passes remain complete and identical; actual GET independently fails.
    def deny_get(operation, transport):
        if operation == "GET":
            raise OSError("PRIVATE_PROVIDER_DETAIL")

    transport.hook = deny_get
    result = run(setup)
    blocked(result)
    assert (
        result.inventory.local_complete and result.inventory.r2_complete and result.inventory.stable
    )
    assert all(row.r2.status == "FAIL" for row in result.inventory.generations)
    assert "PRIVATE_PROVIDER_DETAIL" not in result.evidence_json


def test_no_process_scheduler_lock_or_source_write_calls(setup, monkeypatch):
    import fcntl
    import subprocess

    root, _, _ = setup
    before = {str(p.relative_to(root)): p.stat() for p in root.rglob("*")}
    original = os.open

    def open_guard(path, flags, *args, **kwargs):
        if kwargs.get("dir_fd") is not None:
            assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        return original(path, flags, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("prohibited operation")

    monkeypatch.setattr(os, "open", open_guard)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(fcntl, "flock", forbidden)
    monkeypatch.setattr(os, "chmod", forbidden)
    monkeypatch.setattr(os, "chown", forbidden)
    result = run(setup)
    assert json.loads(result.report_json)["candidate_set_status"] == "advisory"
    after = {str(p.relative_to(root)): p.stat() for p in root.rglob("*")}
    assert before.keys() == after.keys()
    assert all(collect._identity(before[p]) == collect._identity(after[p]) for p in before)
