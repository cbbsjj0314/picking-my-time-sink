"""Small S3-compatible HTTP client for portable shared-artifact exchange."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import SplitResult, quote, urlsplit
from urllib.request import Request, urlopen


class SupportsRead(Protocol):
    """Minimal response protocol used by the object-store client."""

    status: int

    def read(self) -> bytes: ...

    def __enter__(self) -> SupportsRead: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool | None: ...


def _bool_from_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _require_env(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def _normalize_key_prefix(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip().strip("/")
    if not normalized:
        return ""
    for segment in normalized.split("/"):
        if not segment:
            raise ValueError("STEAM_SHARED_S3_KEY_PREFIX must not contain empty segments")
    return normalized


def _quote_uri_path(path: str) -> str:
    segments = [quote(segment, safe="-_.~") for segment in path.split("/")]
    return "/".join(segments)


def _sign(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def _to_signed_headers(headers: Mapping[str, str]) -> tuple[str, str]:
    canonical_pairs: list[tuple[str, str]] = []
    for name, value in headers.items():
        normalized_name = name.strip().lower()
        normalized_value = " ".join(value.strip().split())
        canonical_pairs.append((normalized_name, normalized_value))
    canonical_pairs.sort(key=lambda item: item[0])
    canonical_headers = "".join(f"{name}:{value}\n" for name, value in canonical_pairs)
    signed_headers = ";".join(name for name, _ in canonical_pairs)
    return canonical_headers, signed_headers


@dataclass(frozen=True, slots=True)
class S3CompatibleObjectStoreConfig:
    """Environment-backed config for one S3-compatible bucket boundary."""

    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    session_token: str | None = None
    key_prefix: str = ""
    use_path_style: bool = True
    verify_tls: bool = True

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> S3CompatibleObjectStoreConfig:
        """Build config from the local shared-snapshot environment contract."""

        resolved_env = environ if environ is not None else os.environ
        return cls(
            endpoint_url=_require_env(resolved_env, "STEAM_SHARED_S3_ENDPOINT_URL").rstrip("/"),
            bucket=_require_env(resolved_env, "STEAM_SHARED_S3_BUCKET"),
            region=_require_env(resolved_env, "STEAM_SHARED_S3_REGION"),
            access_key_id=_require_env(resolved_env, "STEAM_SHARED_S3_ACCESS_KEY_ID"),
            secret_access_key=_require_env(resolved_env, "STEAM_SHARED_S3_SECRET_ACCESS_KEY"),
            session_token=resolved_env.get("STEAM_SHARED_S3_SESSION_TOKEN") or None,
            key_prefix=_normalize_key_prefix(resolved_env.get("STEAM_SHARED_S3_KEY_PREFIX")),
            use_path_style=_bool_from_env(
                resolved_env.get("STEAM_SHARED_S3_PATH_STYLE"),
                default=True,
            ),
            verify_tls=_bool_from_env(
                resolved_env.get("STEAM_SHARED_S3_VERIFY_TLS"),
                default=True,
            ),
        )

    def resolve_remote_key(self, object_key: str) -> str:
        """Map one portable contract object key into the bucket-local remote key."""

        normalized_object_key = object_key.strip().strip("/")
        if not normalized_object_key:
            raise ValueError("object_key is empty")
        if self.key_prefix:
            return f"{self.key_prefix}/{normalized_object_key}"
        return normalized_object_key


class S3CompatibleObjectStoreError(RuntimeError):
    """Raised when one signed S3-compatible request fails."""


class S3CompatibleObjectStoreClient:
    """Tiny signed client that supports the PUT/GET flow used in this slice."""

    def __init__(
        self,
        config: S3CompatibleObjectStoreConfig,
        *,
        transport: Any | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or self._default_transport

    @property
    def config(self) -> S3CompatibleObjectStoreConfig:
        return self._config

    def _default_transport(
        self,
        request: Request,
        *,
        context: ssl.SSLContext | None,
    ) -> SupportsRead:
        return urlopen(request, context=context)

    def _build_url_and_host(self, object_key: str) -> tuple[str, str, str]:
        remote_key = self._config.resolve_remote_key(object_key)
        endpoint = urlsplit(self._config.endpoint_url)
        if not endpoint.scheme or not endpoint.netloc:
            raise ValueError(f"Invalid endpoint URL: {self._config.endpoint_url}")

        quoted_remote_key = _quote_uri_path(remote_key)
        if self._config.use_path_style:
            canonical_path = f"/{self._config.bucket}/{quoted_remote_key}"
            return (
                SplitResult(
                    scheme=endpoint.scheme,
                    netloc=endpoint.netloc,
                    path=canonical_path,
                    query="",
                    fragment="",
                ).geturl(),
                endpoint.netloc,
                canonical_path,
            )

        canonical_path = f"/{quoted_remote_key}"
        host = f"{self._config.bucket}.{endpoint.netloc}"
        return (
            SplitResult(
                scheme=endpoint.scheme,
                netloc=host,
                path=canonical_path,
                query="",
                fragment="",
            ).geturl(),
            host,
            canonical_path,
        )

    def _build_headers(
        self,
        *,
        method: str,
        object_key: str,
        payload: bytes,
        content_type: str | None,
        now: datetime,
    ) -> tuple[str, dict[str, str]]:
        url, host, canonical_path = self._build_url_and_host(object_key)
        payload_hash = hashlib.sha256(payload).hexdigest()
        amz_date = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        datestamp = amz_date[:8]
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type:
            headers["content-type"] = content_type
        if self._config.session_token:
            headers["x-amz-security-token"] = self._config.session_token

        canonical_headers, signed_headers = _to_signed_headers(headers)
        canonical_request = "\n".join(
            [
                method,
                canonical_path,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = (
            f"{datestamp}/{self._config.region}/s3/aws4_request"
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _sign(
            _sign(
                _sign(
                    _sign(
                        f"AWS4{self._config.secret_access_key}".encode(),
                        datestamp,
                    ),
                    self._config.region,
                ),
                "s3",
            ),
            "aws4_request",
        )
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["Authorization"] = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self._config.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return url, headers

    def _ssl_context(self) -> ssl.SSLContext | None:
        endpoint = urlsplit(self._config.endpoint_url)
        if endpoint.scheme != "https" or self._config.verify_tls:
            return None
        return ssl._create_unverified_context()

    def request_bytes(
        self,
        *,
        method: str,
        object_key: str,
        payload: bytes = b"",
        content_type: str | None = None,
        now: datetime | None = None,
    ) -> bytes:
        """Send one signed request and return the raw response bytes."""

        timestamp = now or datetime.now(UTC)
        url, headers = self._build_headers(
            method=method,
            object_key=object_key,
            payload=payload,
            content_type=content_type,
            now=timestamp,
        )
        request = Request(
            url=url,
            data=payload if method in {"PUT", "POST"} else None,
            method=method,
            headers=headers,
        )
        try:
            with self._transport(request, context=self._ssl_context()) as response:
                return response.read()
        except HTTPError as exc:
            body_excerpt = exc.read().decode("utf-8", errors="replace").strip()
            raise S3CompatibleObjectStoreError(
                f"{method} {url} failed with HTTP {exc.code}: {body_excerpt}"
            ) from exc

    def put_bytes(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        now: datetime | None = None,
    ) -> None:
        """Upload one whole object body."""

        self.request_bytes(
            method="PUT",
            object_key=object_key,
            payload=payload,
            content_type=content_type,
            now=now,
        )

    def put_json(
        self,
        *,
        object_key: str,
        payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> None:
        """Upload one JSON object with the stable formatting used elsewhere."""

        body = json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self.put_bytes(
            object_key=object_key,
            payload=body.encode("utf-8"),
            content_type="application/json",
            now=now,
        )

    def get_bytes(self, *, object_key: str, now: datetime | None = None) -> bytes:
        """Download one full object by portable object key."""

        return self.request_bytes(method="GET", object_key=object_key, now=now)
