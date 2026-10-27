from __future__ import annotations

import json

from steam.probe.probe_reviews import summarize_reviews_payload


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
    assert summary["response_keys"] == [
        "cursor",
        "day_range_used",
        "query_summary",
        "reviews",
        "total_matching",
    ]
    assert summary["day_range_used"] == 0
    assert summary["total_matching"] == 100
    assert summary["cursor_present"] is True
    assert summary["query_summary"] == response["query_summary"]
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

    assert summary == {"top_level_keys": ["reviews"]}
