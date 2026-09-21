from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from steam.ingest.s3_compat import (
    S3CompatibleObjectStoreClient,
    S3CompatibleObjectStoreConfig,
    S3CompatibleObjectStorePreconditionFailed,
)


class _FakeResponse:
    def __init__(self, body: bytes = b"") -> None:
        self.status = 200
        self._body = body
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            result = self._body[self._offset :]
            self._offset = len(self._body)
            return result
        result = self._body[self._offset : self._offset + size]
        self._offset += len(result)
        return result

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


def test_put_file_streams_conditional_signed_request(tmp_path: Path) -> None:
    source = tmp_path / "recovery.dump"
    source.write_bytes(b"bounded-file-body")
    seen: dict[str, object] = {}

    def fake_transport(request: Request, *, context: object) -> _FakeResponse:
        del context
        seen["headers"] = dict(request.header_items())
        seen["data_type"] = type(request.data)
        assert request.data is not None
        seen["body"] = b"".join(request.data)
        return _FakeResponse()

    client = S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig(
            endpoint_url="https://storage.example.test",
            bucket="portable-cache",
            region="test-region",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
        transport=fake_transport,
    )

    client.put_file(
        object_key="postgres-recovery/v1/generation/recovery.dump",
        source_path=source,
        content_type="application/octet-stream",
        if_none_match=True,
        now=datetime(2026, 9, 4, 1, 2, 3, tzinfo=UTC),
        chunk_size=4,
    )

    headers = seen["headers"]
    assert seen["data_type"] is not bytes
    assert seen["body"] == b"bounded-file-body"
    assert headers["If-none-match"] == "*"
    assert headers["Content-length"] == "17"
    assert headers["X-amz-content-sha256"] == (
        "39ca1d75c84c599129fbec385306d69528109870f37148e2d2b83e1c609b02df"
    )
    assert "content-length" in headers["Authorization"]
    assert "if-none-match" in headers["Authorization"]


def test_conditional_put_exposes_structured_precondition_failure() -> None:
    def fake_transport(request: Request, *, context: object) -> _FakeResponse:
        del context
        raise HTTPError(
            request.full_url,
            412,
            "Precondition Failed",
            hdrs=None,
            fp=BytesIO(b"provider response body"),
        )

    client = S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig(
            endpoint_url="https://storage.example.test",
            bucket="portable-cache",
            region="test-region",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
        transport=fake_transport,
    )

    with pytest.raises(S3CompatibleObjectStorePreconditionFailed):
        client.put_bytes(
            object_key="postgres-recovery/v1/generation/manifest.json",
            payload=b"{}\n",
            content_type="application/json",
            if_none_match=True,
        )


def test_get_file_streams_to_new_destination(tmp_path: Path) -> None:
    destination = tmp_path / "downloaded.dump"

    def fake_transport(request: Request, *, context: object) -> _FakeResponse:
        del request, context
        return _FakeResponse(b"remote-file-body")

    client = S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig(
            endpoint_url="https://storage.example.test",
            bucket="portable-cache",
            region="test-region",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
        transport=fake_transport,
    )

    client.get_file(
        object_key="postgres-recovery/v1/generation/recovery.dump",
        destination_path=destination,
        chunk_size=3,
        max_bytes=16,
    )

    assert destination.read_bytes() == b"remote-file-body"


def _list_xml(*, token: str | None = None, prefix: str = "team/postgres-recovery/v1/") -> bytes:
    from xml.sax.saxutils import escape

    continuation = (f"<ContinuationToken>{escape(token)}</ContinuationToken>"
                    if token is not None else "")
    return (
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        '<Name>portable-cache</Name>'
        f'<Prefix>{prefix}</Prefix><MaxKeys>10</MaxKeys><KeyCount>1</KeyCount>'
        '<IsTruncated>true</IsTruncated>'
        '<NextContinuationToken>next+/= token</NextContinuationToken>'
        f'{continuation}<Contents><Key>{prefix}g/appdb.dump</Key><Size>12</Size>'
        '<ETag>opaque-etag</ETag><LastModified>2026-01-01T00:00:00.000Z</LastModified>'
        '</Contents></ListBucketResult>'
    ).encode()


@pytest.mark.parametrize("path_style", [True, False])
def test_list_page_signs_bucket_query_and_preserves_opaque_tokens(path_style):
    from urllib.parse import parse_qs, urlsplit

    seen = []
    token = "opaque+/=& space%token"

    def transport(request, *, context):
        seen.append(request)
        assert request.method == "GET" and request.data is None
        return _FakeResponse(_list_xml(token=token))

    client = S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig(
            "https://storage.example.test", "portable-cache", "test-region",
            "test-access", "test-secret", key_prefix="team", use_path_style=path_style,
        ), transport=transport,
    )
    result = client.list_objects_v2_page(
        prefix="postgres-recovery/v1/", continuation_token=token, max_keys=10,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    request = seen[0]
    parsed = urlsplit(request.full_url)
    assert parsed.path == ("/portable-cache/" if path_style else "/")
    assert parsed.netloc == ("storage.example.test" if path_style
                             else "portable-cache.storage.example.test")
    assert parse_qs(parsed.query) == {
        "list-type": ["2"], "prefix": ["team/postgres-recovery/v1/"],
        "max-keys": ["10"], "continuation-token": [token],
    }
    assert parsed.query == (
        "continuation-token=opaque%2B%2F%3D%26%20space%25token&list-type=2&max-keys=10"
        "&prefix=team%2Fpostgres-recovery%2Fv1%2F"
    )
    # Independently reconstruct the literal canonical request to check query signing.
    import hashlib
    import hmac

    body_hash = hashlib.sha256(b"").hexdigest()
    canonical = (f"GET\n{parsed.path}\n{parsed.query}\nhost:{parsed.netloc}\n"
                 f"x-amz-content-sha256:{body_hash}\nx-amz-date:20260101T000000Z\n\n"
                 f"host;x-amz-content-sha256;x-amz-date\n{body_hash}")
    key = b"AWS4test-secret"
    for component in (b"20260101", b"test-region", b"s3", b"aws4_request"):
        key = hmac.digest(key, component, "sha256")
    to_sign = ("AWS4-HMAC-SHA256\n20260101T000000Z\n20260101/test-region/s3/aws4_request\n"
               + hashlib.sha256(canonical.encode()).hexdigest())
    expected = hmac.new(key, to_sign.encode(), "sha256").hexdigest()
    assert request.get_header("Authorization").endswith("Signature=" + expected)
    assert result.objects[0].key == "postgres-recovery/v1/g/appdb.dump"
    assert result.objects[0].size == 12
    assert result.is_truncated and result.next_continuation_token == "next+/= token"


@pytest.mark.parametrize("change", [
    lambda b: b"<broken",
    lambda b: b.decode().encode("utf-16"),
    lambda b: b.replace(b"2026-01-01T00:00:00.000Z", b"invalid-date"),
    lambda b: b.replace(b"<KeyCount>1", b"<KeyCount>0"),
    lambda b: b.replace(b"<IsTruncated>true", b"<IsTruncated>yes"),
    lambda b: b.replace(b"NextContinuationToken", b"Ignored"),
    lambda b: b.replace(b"<Prefix>team/", b"<Prefix>wrong/"),
    lambda b: b.replace(b"<Size>12", b"<Size>-1"),
    lambda b: b.replace(b"<Size>12</Size>", b"<Size>12</Size><Size>12</Size>"),
    lambda b: b.replace(b"<Name>portable-cache", b"<Name>wrong"),
    lambda b: b.replace(b"<Key>team/", b"<Key>foreign/"),
    lambda b: b.replace(b"<IsTruncated>true", b"<IsTruncated>false"),
    lambda b: b.replace(b"<Contents>", b"<CommonPrefixes>"),
    lambda b: b"<!DOCTYPE x [<!ENTITY y 'value'>]>" + b,
    lambda b: b.replace(b"</ListBucketResult>",
                        b"<StartAfter>skipped</StartAfter></ListBucketResult>"),
    lambda b: b.replace(b"</ListBucketResult>",
                        b'<Contents xmlns="foreign"/></ListBucketResult>'),
])
def test_list_rejects_malformed_or_unaccountable_page(change):
    from steam.ingest.s3_compat import S3CompatibleObjectStoreError

    client = S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig(
            "https://storage.example.test", "portable-cache", "test-region",
            "test-access", "test-secret", key_prefix="team",
        ), transport=lambda request, **kwargs: _FakeResponse(change(_list_xml())),
    )
    with pytest.raises(S3CompatibleObjectStoreError, match="^list_objects_v2_page failed$"):
        client.list_objects_v2_page(prefix="postgres-recovery/v1/", max_keys=10)


def test_list_transport_failure_does_not_expose_provider_detail():
    from steam.ingest.s3_compat import S3CompatibleObjectStoreError

    def transport(request, **kwargs):
        raise HTTPError(request.full_url, 403, "PRIVATE_MARKER", None, BytesIO(b"PRIVATE_BODY"))

    client = S3CompatibleObjectStoreClient(
        S3CompatibleObjectStoreConfig("https://example.invalid", "bucket", "region",
                                      "test-access", "test-secret"), transport=transport,
    )
    with pytest.raises(S3CompatibleObjectStoreError) as error:
        client.list_objects_v2_page(prefix="postgres-recovery/v1/")
    assert str(error.value) == "list_objects_v2_page failed"
    assert error.value.__suppress_context__
