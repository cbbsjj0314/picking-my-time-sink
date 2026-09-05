"""Validate and publish one recovery generation through the gated R2 boundary."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

from recovery import r2_publish
from recovery.postgres_artifact import verify_generation
from steam.ingest.s3_compat import (
    S3CompatibleObjectStoreClient,
    S3CompatibleObjectStoreConfig,
)

_REQUIRED_ENVIRONMENT_KEYS = (
    "PMTS_RECOVERY_R2_ENDPOINT_URL",
    "PMTS_RECOVERY_R2_BUCKET",
    "PMTS_RECOVERY_R2_REGION",
    "PMTS_RECOVERY_R2_ACCESS_KEY_ID",
    "PMTS_RECOVERY_R2_SECRET_ACCESS_KEY",
)
_R2_ENDPOINT_HOST = re.compile(
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.(?:eu|us|fedramp))?\.r2\.cloudflarestorage\.com\Z"
)
_R2_BUCKET = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])\Z")
_SAFE_GENERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_R2_MAX_OBJECT_KEY_BYTES = 1024


class RecoveryActivationFailure(StrEnum):
    """Sanitized failure categories exposed by the operator CLI."""

    INVALID_CONFIG = "invalid_config"
    INVALID_ARGUMENTS = "invalid_arguments"
    INVALID_LOCAL_GENERATION = "invalid_local_generation"
    UNSUPPORTED_OBJECT_SIZE = "unsupported_object_size"
    REMOTE_VERIFICATION_FAILURE = "remote_verification_failure"


class RecoveryActivationError(RuntimeError):
    """An activation failure without provider, credential, or path detail."""

    def __init__(self, category: RecoveryActivationFailure) -> None:
        super().__init__(category.value)
        self.category = category


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise RecoveryActivationError(RecoveryActivationFailure.INVALID_ARGUMENTS)


@dataclass(frozen=True, slots=True)
class RecoveryActivationPreflight:
    """Sanitized local readiness for one completed A1 generation."""

    generation_id: str
    dump_size_bytes: int
    object_keys: tuple[str, str, str]


ClientFactory = Callable[
    [S3CompatibleObjectStoreConfig],
    r2_publish.RecoveryObjectStore,
]
PublishFunction = Callable[..., r2_publish.VerifiedRemoteGeneration]


def _invalid_config() -> RecoveryActivationError:
    return RecoveryActivationError(RecoveryActivationFailure.INVALID_CONFIG)


def _required_value(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _invalid_config()
    normalized = value.strip()
    if any(character.isspace() for character in normalized):
        raise _invalid_config()
    return normalized


def _normalize_endpoint(value: str) -> str:
    endpoint = value.rstrip("/")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        raise _invalid_config() from None
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or _R2_ENDPOINT_HOST.fullmatch(parsed.hostname) is None
    ):
        raise _invalid_config()
    return endpoint


def _normalize_key_prefix(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip().strip("/")
    if not normalized:
        return ""
    if "\\" in normalized:
        raise _invalid_config()
    for segment in normalized.split("/"):
        if (
            not segment
            or segment in {".", ".."}
            or segment != segment.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in segment)
        ):
            raise _invalid_config()
    return normalized


def load_recovery_r2_config(
    environ: Mapping[str, str] | None = None,
) -> S3CompatibleObjectStoreConfig:
    """Load the recovery-only R2 environment contract without network access."""

    resolved_env = environ if environ is not None else os.environ
    values = {key: _required_value(resolved_env, key) for key in _REQUIRED_ENVIRONMENT_KEYS}
    endpoint = _normalize_endpoint(values["PMTS_RECOVERY_R2_ENDPOINT_URL"])
    bucket = values["PMTS_RECOVERY_R2_BUCKET"]
    if _R2_BUCKET.fullmatch(bucket) is None:
        raise _invalid_config()
    region = values["PMTS_RECOVERY_R2_REGION"]
    if region != "auto":
        raise _invalid_config()
    return S3CompatibleObjectStoreConfig(
        endpoint_url=endpoint,
        bucket=bucket,
        region=region,
        access_key_id=values["PMTS_RECOVERY_R2_ACCESS_KEY_ID"],
        secret_access_key=values["PMTS_RECOVERY_R2_SECRET_ACCESS_KEY"],
        key_prefix=_normalize_key_prefix(resolved_env.get("PMTS_RECOVERY_R2_KEY_PREFIX")),
        use_path_style=True,
        verify_tls=True,
    )


def preflight_verified_generation(generation_dir: Path) -> RecoveryActivationPreflight:
    """Verify local A1 evidence and the current A2 single-upload boundary."""

    generation_dir = Path(generation_dir)
    try:
        verification = verify_generation(generation_dir)
    except (OSError, ValueError):
        verification = None
    if verification is None or not verification.passed:
        raise RecoveryActivationError(RecoveryActivationFailure.INVALID_LOCAL_GENERATION)

    try:
        manifest = json.loads((generation_dir / "manifest.json").read_text(encoding="utf-8"))
        generation_id = manifest["generation_id"]
        dump_filename = manifest["dump_filename"]
        dump_size = (generation_dir / dump_filename).stat().st_size
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise RecoveryActivationError(
            RecoveryActivationFailure.INVALID_LOCAL_GENERATION
        ) from None
    if (
        not isinstance(generation_id, str)
        or _SAFE_GENERATION_ID.fullmatch(generation_id) is None
        or generation_id != generation_dir.name
        or not isinstance(dump_filename, str)
        or manifest.get("dump_size_bytes") != dump_size
    ):
        raise RecoveryActivationError(RecoveryActivationFailure.INVALID_LOCAL_GENERATION)
    if dump_size > r2_publish.MAX_SINGLE_PUT_BYTES:
        raise RecoveryActivationError(RecoveryActivationFailure.UNSUPPORTED_OBJECT_SIZE)

    base_key = f"{r2_publish.PORTABLE_KEY_ROOT}/{generation_id}"
    return RecoveryActivationPreflight(
        generation_id=generation_id,
        dump_size_bytes=dump_size,
        object_keys=(
            f"{base_key}/{dump_filename}",
            f"{base_key}/{dump_filename}.sha256",
            f"{base_key}/manifest.json",
        ),
    )


def _validate_resolved_object_keys(
    config: S3CompatibleObjectStoreConfig,
    object_keys: tuple[str, str, str],
) -> None:
    try:
        resolved_keys = tuple(config.resolve_remote_key(key) for key in object_keys)
    except ValueError:
        raise _invalid_config() from None
    if any(len(key.encode("utf-8")) > _R2_MAX_OBJECT_KEY_BYTES for key in resolved_keys):
        raise _invalid_config()


def run_preflight(
    *,
    generation_dir: Path,
    environ: Mapping[str, str] | None = None,
) -> RecoveryActivationPreflight:
    """Validate recovery config and local readiness without remote access."""

    config = load_recovery_r2_config(environ)
    result = preflight_verified_generation(generation_dir)
    _validate_resolved_object_keys(config, result.object_keys)
    return result


def publish_generation(
    *,
    generation_dir: Path,
    environ: Mapping[str, str] | None = None,
    client_factory: ClientFactory | None = None,
    publisher: PublishFunction | None = None,
) -> r2_publish.VerifiedRemoteGeneration:
    """Compose the recovery config/client boundary with the A2 publisher."""

    config = load_recovery_r2_config(environ)
    preflight = preflight_verified_generation(generation_dir)
    _validate_resolved_object_keys(config, preflight.object_keys)
    client = (client_factory or S3CompatibleObjectStoreClient)(config)
    result = (publisher or r2_publish.publish_verified_generation)(
        client=client,
        generation_dir=Path(generation_dir),
    )
    if (
        not result.verified
        or _SAFE_GENERATION_ID.fullmatch(result.generation_id) is None
        or result.generation_id != Path(generation_dir).name
    ):
        raise RecoveryActivationError(
            RecoveryActivationFailure.REMOTE_VERIFICATION_FAILURE
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the gated recovery R2 operator CLI."""

    parser = _SanitizedArgumentParser(
        description="Preflight or publish one PostgreSQL recovery generation to R2"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight", help="validate local activation readiness")
    preflight.add_argument("generation_dir", type=Path)
    publish = commands.add_parser("publish", help="publish through the verified A2 boundary")
    publish.add_argument("generation_dir", type=Path)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    client_factory: ClientFactory | None = None,
    publisher: PublishFunction | None = None,
) -> int:
    """Run the sanitized recovery R2 activation CLI."""

    try:
        args = build_parser().parse_args(argv)
        if args.command == "preflight":
            result = run_preflight(generation_dir=args.generation_dir, environ=environ)
            print(f"generation={result.generation_id}")
            print(f"dump_size_bytes={result.dump_size_bytes}")
            print("local_verification=PASS")
            print("single_upload_preflight=PASS")
            print("activation_preflight=PASS")
            return 0

        result = publish_generation(
            generation_dir=args.generation_dir,
            environ=environ,
            client_factory=client_factory,
            publisher=publisher,
        )
        print(f"generation={result.generation_id}")
        print("remote_verification=PASS")
        return 0
    except RecoveryActivationError as exc:
        category = exc.category.value
    except r2_publish.RecoveryPublishError as exc:
        category = exc.category.value
    except Exception:
        category = "internal_error"
    print(f"ERROR: recovery R2 activation failed: {category}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
