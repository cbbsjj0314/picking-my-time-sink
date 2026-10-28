from __future__ import annotations

import json

import pytest

from steam.probe.common import RequestResult
from steam.probe.probe_reviews import build_probe_snapshot, summarize_reviews_payload

MARKER = "PRIVATE-TEXT-MARKER"
# Identifier-shaped, so it passes a key-name or language syntax check.
IDENTIFIER_MARKER = "private_review_text"


def make_result(body: bytes) -> RequestResult:
    return RequestResult(
        final_url="https://example.com",
        status_code=200,
        headers={"Content-Type": "application/json"},
        body=body,
        attempts=[{"attempt": 1, "error": None, "sleep_seconds": 0.0, "status_code": 200}],
        error=None,
    )


def persisted_snapshot(body: bytes) -> tuple[dict[str, object], str]:
    snapshot = build_probe_snapshot(
        result=make_result(body),
        timeout_seconds=10.0,
        request_url="https://example.com",
        request_params={"input_json": "{}"},
    )
    return snapshot, json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)


def test_summarize_reviews_payload_redacts_third_party_review_content() -> None:
    response = {
        "cursor": "CURSOR-SECRET",
        "day_range_used": 0,
        "query_summary": {
            "num_reviews": 20,
            "review_score": 8,
            "review_score_desc": "Very Positive",
            "total_negative": 10,
            "total_positive": 90,
            "total_reviews": 100,
        },
        "reviews": [
            {
                "author": {
                    "num_reviews": 2,
                    "personaname": "user-secret",
                    "profile_url": "https://community.example.invalid/profiles/STEAMID-SECRET/",
                    "steamid": "STEAMID-SECRET",
                },
                "comment_count": 10,
                "language": "english",
                "primarily_steam_deck": False,
                "reactions": [{"count": 1, "reaction_type": 24}],
                "received_for_free": False,
                "recommendationid": "RID-SECRET",
                "refunded": False,
                "review": "REVIEW-TEXT-SECRET",
                "steam_purchase": True,
                "success": 1,
                "timestamp_created": 1770258718,
                "timestamp_updated": 1770258718,
                "voted_up": True,
                "votes_funny": 27,
                "votes_up": 464,
                "weighted_vote_score": "0.960129141807556152",
                "written_during_early_access": False,
            }
        ],
        "total_matching": 100,
    }
    payload = {"response": response}

    summary = summarize_reviews_payload(payload, excerpt_count=1)
    excerpt = summary["reviews_excerpt"][0]
    serialized = json.dumps(summary, sort_keys=True)

    assert summary["top_level_keys"] == ["response"]
    assert summary["top_level_unknown_key_count"] == 0
    assert summary["response_keys"] == [
        "cursor",
        "day_range_used",
        "query_summary",
        "reviews",
        "total_matching",
    ]
    assert summary["response_unknown_key_count"] == 0
    # The review entry's `success` field is not a known review field.
    assert summary["review_unknown_key_count"] == 1
    assert "success" not in summary["review_fields_present"]
    assert summary["author_unknown_key_count"] == 0
    assert summary["day_range_used"] == 0
    assert summary["total_matching"] == 100
    assert summary["cursor_present"] is True
    assert summary["query_summary"] == {
        "num_reviews": 20,
        "review_score": 8,
        "total_negative": 10,
        "total_positive": 90,
        "total_reviews": 100,
    }
    assert "review_score_desc" not in summary["query_summary"]
    assert summary["reviews_count"] == 1
    assert "cursor" not in summary
    assert excerpt["author_summary_redacted"] is True
    assert excerpt["review_text_redacted"] is True
    assert excerpt["review_text_length"] == len("REVIEW-TEXT-SECRET")
    assert excerpt["recommendationid_redacted"] is True
    assert excerpt["author_fields_present"] == [
        "num_reviews",
        "personaname",
        "profile_url",
        "steamid",
    ]
    assert excerpt["weighted_vote_score"] == "0.960129141807556152"
    assert excerpt["author_unknown_key_count"] == 0
    assert excerpt["language_redacted"] is True
    assert "language" not in excerpt
    assert "english" not in serialized
    assert "excerpt_fields_dropped" not in excerpt
    assert "author" not in excerpt
    assert "review" not in excerpt
    assert "recommendationid" not in excerpt
    assert "CURSOR-SECRET" not in serialized
    assert "RID-SECRET" not in serialized
    assert "REVIEW-TEXT-SECRET" not in serialized
    assert "user-secret" not in serialized
    assert "STEAMID-SECRET" not in serialized
    assert "community.example.invalid" not in serialized


def test_probe_uses_ingest_request_contract() -> None:
    from steam.ingest import fetch_reviews_daily
    from steam.probe import probe_reviews

    assert probe_reviews.REQUEST_URL == fetch_reviews_daily.REQUEST_URL
    assert probe_reviews.build_request_params is fetch_reviews_daily.build_request_params


def test_summarize_reviews_payload_without_response_envelope_stays_bounded() -> None:
    summary = summarize_reviews_payload({"reviews": [{"review": "REVIEW-TEXT-SECRET"}]})

    assert summary == {"top_level_keys": ["reviews"], "top_level_unknown_key_count": 0}


def test_malformed_json_stores_only_a_non_json_marker() -> None:
    snapshot, serialized = persisted_snapshot(b'{"response": "' + MARKER.encode() + b' broken')

    assert snapshot["response"]["payload_excerpt_or_json"] == {"non_json": True}
    assert snapshot["response"]["body_size"] > 0
    assert MARKER not in serialized


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        pytest.param([MARKER], "array", id="array"),
        pytest.param(MARKER, "string", id="string"),
        pytest.param(42, "number", id="number"),
    ],
)
def test_non_dict_payload_keeps_only_its_type(payload: object, expected_type: str) -> None:
    snapshot, serialized = persisted_snapshot(json.dumps(payload).encode("utf-8"))

    assert snapshot["response"]["payload_excerpt_or_json"] == {"payload_type": expected_type}
    assert MARKER not in serialized


def test_non_dict_review_entries_keep_only_their_type() -> None:
    body = {"response": {"reviews": [MARKER, [MARKER], None]}}

    snapshot, serialized = persisted_snapshot(json.dumps(body).encode("utf-8"))

    assert snapshot["response"]["payload_excerpt_or_json"]["reviews_excerpt"] == [
        {"entry_type": "string"},
        {"entry_type": "array"},
        {"entry_type": "null"},
    ]
    assert MARKER not in serialized


def test_query_summary_keeps_only_allowlisted_integer_counts() -> None:
    body = {
        "response": {
            "query_summary": {
                "num_reviews": 20,
                "review_score": MARKER,
                "review_score_desc": MARKER,
                "total_negative": 20,
                "total_positive": True,
                "total_reviews": 100.0,
                "unexpected": MARKER,
            }
        }
    }

    snapshot, serialized = persisted_snapshot(json.dumps(body).encode("utf-8"))

    assert snapshot["response"]["payload_excerpt_or_json"]["query_summary"] == {
        "num_reviews": 20,
        "total_negative": 20,
    }
    assert MARKER not in serialized


def test_unexpected_value_types_in_allowed_review_fields_are_dropped() -> None:
    review = {
        "comment_count": MARKER,
        "language": [MARKER],
        "steam_purchase": MARKER,
        "timestamp_created": 1770258718,
        "voted_up": 1,
        "votes_up": {"nested": MARKER},
        "weighted_vote_score": MARKER,
        "written_during_early_access": False,
        MARKER + " key": "value",
    }
    body = {"response": {"reviews": [review]}}

    snapshot, serialized = persisted_snapshot(json.dumps(body).encode("utf-8"))
    summary = snapshot["response"]["payload_excerpt_or_json"]
    excerpt = summary["reviews_excerpt"][0]

    assert excerpt == {
        "excerpt_fields_dropped": [
            "comment_count",
            "language",
            "steam_purchase",
            "voted_up",
            "votes_up",
            "weighted_vote_score",
        ],
        "timestamp_created": 1770258718,
        "written_during_early_access": False,
    }
    assert MARKER not in serialized


def test_valid_sanitized_envelope_keeps_bounded_structure() -> None:
    body = {
        "response": {
            "cursor": MARKER,
            "day_range_used": 0,
            "query_summary": {
                "review_score_desc": MARKER,
                "total_negative": 20,
                "total_positive": 80,
                "total_reviews": 100,
            },
            "reviews": [
                {
                    "author": {"personaname": MARKER, "steamid": MARKER},
                    "language": "schinese",
                    "recommendationid": MARKER,
                    "review": MARKER,
                    "voted_up": True,
                    "weighted_vote_score": 0.5,
                }
            ],
            "total_matching": 100,
        }
    }

    snapshot, serialized = persisted_snapshot(json.dumps(body).encode("utf-8"))
    summary = snapshot["response"]["payload_excerpt_or_json"]

    assert summary["query_summary"] == {
        "total_negative": 20,
        "total_positive": 80,
        "total_reviews": 100,
    }
    assert summary["cursor_present"] is True
    assert summary["author_fields_present"] == ["personaname", "steamid"]
    assert summary["reviews_excerpt"][0] == {
        "author_fields_present": ["personaname", "steamid"],
        "author_summary_redacted": True,
        "author_unknown_key_count": 0,
        "language_redacted": True,
        "recommendationid_redacted": True,
        "review_text_length": len(MARKER),
        "review_text_redacted": True,
        "voted_up": True,
        "weighted_vote_score": 0.5,
    }
    assert MARKER not in serialized


def test_unknown_identifier_shaped_keys_and_language_are_never_persisted() -> None:
    body = {
        IDENTIFIER_MARKER: 1,
        "response": {
            IDENTIFIER_MARKER: 1,
            "query_summary": {"total_negative": 20, "total_positive": 80, "total_reviews": 100},
            "reviews": [
                {
                    IDENTIFIER_MARKER: 1,
                    "author": {IDENTIFIER_MARKER: 1, "steamid": MARKER},
                    "language": IDENTIFIER_MARKER,
                    "voted_up": True,
                },
                {
                    IDENTIFIER_MARKER: 2,
                    "other_unknown_field": 1,
                    "author": {IDENTIFIER_MARKER: 2, "playtime_forever": 10},
                    "votes_up": 3,
                },
            ],
        },
    }

    snapshot, serialized = persisted_snapshot(json.dumps(body).encode("utf-8"))
    summary = snapshot["response"]["payload_excerpt_or_json"]

    assert IDENTIFIER_MARKER not in serialized
    assert "other_unknown_field" not in serialized
    assert MARKER not in serialized
    assert summary["top_level_keys"] == ["response"]
    assert summary["top_level_unknown_key_count"] == 1
    assert summary["response_keys"] == ["query_summary", "reviews"]
    assert summary["response_unknown_key_count"] == 1
    assert summary["review_fields_present"] == ["author", "language", "voted_up", "votes_up"]
    # Distinct unknown names across all reviews, not occurrences.
    assert summary["review_unknown_key_count"] == 2
    assert summary["author_fields_present"] == ["playtime_forever", "steamid"]
    assert summary["author_unknown_key_count"] == 1
    assert summary["query_summary"] == {
        "total_negative": 20,
        "total_positive": 80,
        "total_reviews": 100,
    }
    assert summary["reviews_count"] == 2
    assert summary["reviews_excerpt"] == [
        {
            "author_fields_present": ["steamid"],
            "author_summary_redacted": True,
            "author_unknown_key_count": 1,
            "language_redacted": True,
            "voted_up": True,
        },
        {
            "author_fields_present": ["playtime_forever"],
            "author_summary_redacted": True,
            "author_unknown_key_count": 1,
            "votes_up": 3,
        },
    ]
