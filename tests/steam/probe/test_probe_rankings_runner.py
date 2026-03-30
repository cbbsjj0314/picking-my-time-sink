from __future__ import annotations

import json
from pathlib import Path

import pytest

from steam.probe import probe_rankings
from steam.probe.common import RequestResult

FIXTURE_DIR = Path("tests/fixtures/steam/rankings")


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _request_result(url: str, payload: dict[str, object]) -> RequestResult:
    return RequestResult(
        final_url=url,
        status_code=200,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
        attempts=[{"attempt": 1, "error": None, "sleep_seconds": 0.0, "status_code": 200}],
        error=None,
    )


def test_run_writes_fixture_compatible_payload_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_payloads = {
        ("topsellers", "US"): _load_fixture("topsellers_global.payload.json"),
        ("topsellers", "KR"): _load_fixture("topsellers_kr.payload.json"),
        ("mostplayed", "US"): _load_fixture("mostplayed_global.payload.json"),
        ("mostplayed", "KR"): _load_fixture("mostplayed_kr.payload.json"),
    }
    captured_inputs: list[tuple[str, dict[str, object]]] = []

    def fake_request_with_retry(*, url: str, params: dict[str, str], **_: object) -> RequestResult:
        input_json = json.loads(params["input_json"])
        captured_inputs.append((url, input_json))

        chart = "topsellers" if url == probe_rankings.TOPSELLERS_SERVICE_URL else "mostplayed"
        country_code = str(input_json["context"]["country_code"])
        payload = fixture_payloads[(chart, country_code)]
        return _request_result(url, payload)

    monkeypatch.setattr(probe_rankings, "request_with_retry", fake_request_with_retry)

    topsellers_global_path = tmp_path / "topsellers_global.payload.json"
    topsellers_kr_path = tmp_path / "topsellers_kr.payload.json"
    mostplayed_global_path = tmp_path / "mostplayed_global.payload.json"
    mostplayed_kr_path = tmp_path / "mostplayed_kr.payload.json"

    saved_paths = probe_rankings.run(
        topsellers_global_path=topsellers_global_path,
        topsellers_kr_path=topsellers_kr_path,
        mostplayed_global_path=mostplayed_global_path,
        mostplayed_kr_path=mostplayed_kr_path,
    )

    assert saved_paths == [
        topsellers_global_path,
        topsellers_kr_path,
        mostplayed_global_path,
        mostplayed_kr_path,
    ]
    assert [path.name for path in saved_paths] == [
        "topsellers_global.payload.json",
        "topsellers_kr.payload.json",
        "mostplayed_global.payload.json",
        "mostplayed_kr.payload.json",
    ]
    assert captured_inputs == [
        (
            probe_rankings.TOPSELLERS_SERVICE_URL,
            {
                "context": {"country_code": "US", "language": "english"},
                "data_request": {"include_basic_info": True},
            },
        ),
        (
            probe_rankings.TOPSELLERS_SERVICE_URL,
            {
                "context": {"country_code": "KR", "language": "english"},
                "data_request": {"include_basic_info": True},
            },
        ),
        (
            probe_rankings.MOSTPLAYED_SERVICE_URL,
            {
                "context": {"country_code": "US", "language": "english"},
                "data_request": {"include_basic_info": True},
            },
        ),
        (
            probe_rankings.MOSTPLAYED_SERVICE_URL,
            {
                "context": {"country_code": "KR", "language": "english"},
                "data_request": {"include_basic_info": True},
            },
        ),
    ]

    for path in saved_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = probe_rankings.parse_rankings_payload(payload, max_rows=10)

        assert rows
        assert rows[0]["title"]
