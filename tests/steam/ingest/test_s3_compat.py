from __future__ import annotations

from datetime import UTC, datetime
from urllib.request import Request

from steam.ingest.s3_compat import (
    S3CompatibleObjectStoreClient,
    S3CompatibleObjectStoreConfig,
)


class _FakeResponse:
    def __init__(self, body: bytes = b"") -> None:
        self.status = 200
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


def test_put_bytes_signs_path_style_request_and_prefix() -> None:
    seen: dict[str, object] = {}

    def fake_transport(request: Request, *, context: object) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["body"] = request.data
        return _FakeResponse()

    client = S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig(
            endpoint_url="https://storage.example.test",
            bucket="portable-cache",
            region="test-region",
            access_key_id="test-access",
            secret_access_key="test-secret",
            key_prefix="local/dev",
            use_path_style=True,
        ),
        transport=fake_transport,
    )

    client.put_bytes(
        object_key="steam/authority/jobs/ccu-30m/latest/manifest.json",
        payload=b'{"ok":true}\n',
        content_type="application/json",
        now=datetime(2026, 4, 22, 1, 2, 3, tzinfo=UTC),
    )

    assert seen["url"] == (
        "https://storage.example.test/portable-cache/local/dev/"
        "steam/authority/jobs/ccu-30m/latest/manifest.json"
    )
    headers = seen["headers"]
    assert headers["Host"] == "storage.example.test"
    assert headers["Content-type"] == "application/json"
    assert headers["X-amz-date"] == "20260422T010203Z"
    assert headers["X-amz-content-sha256"] == (
        "e5f1eb4d806641698a35efe20e098efd20d7d57a9b90ee69079d5bb650920726"
    )
    assert headers["Authorization"] == (
        "AWS4-HMAC-SHA256 "
        "Credential=test-access/20260422/test-region/s3/aws4_request, "
        "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date, "
        "Signature=9ce02945d383d561a8469158b434ade4342197fe245f381e26988c91c26d9ba4"
    )
    assert seen["body"] == b'{"ok":true}\n'


def test_from_env_reads_minimal_shared_snapshot_contract() -> None:
    config = S3CompatibleObjectStoreConfig.from_env(
        {
            "STEAM_SHARED_S3_ENDPOINT_URL": "https://example.invalid",
            "STEAM_SHARED_S3_BUCKET": "portable-cache",
            "STEAM_SHARED_S3_REGION": "test-region",
            "STEAM_SHARED_S3_ACCESS_KEY_ID": "key-id",
            "STEAM_SHARED_S3_SECRET_ACCESS_KEY": "secret",
            "STEAM_SHARED_S3_KEY_PREFIX": "team/dev",
            "STEAM_SHARED_S3_PATH_STYLE": "false",
            "STEAM_SHARED_S3_VERIFY_TLS": "true",
        }
    )

    assert config.endpoint_url == "https://example.invalid"
    assert config.bucket == "portable-cache"
    assert config.region == "test-region"
    assert config.access_key_id == "key-id"
    assert config.secret_access_key == "secret"
    assert config.key_prefix == "team/dev"
    assert config.use_path_style is False
    assert config.verify_tls is True
