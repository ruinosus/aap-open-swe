"""Tests for GitHub Reviews API poster."""

import json


def test_parse_review_output_valid_json():
    from agent.review_poster import parse_review_output

    raw = json.dumps(
        {
            "skill_output_type": "review",
            "summary": "Found 1 issue",
            "score": "8/10",
            "comments": [
                {"file": "src/main.py", "line": 10, "message": "Bug here", "severity": "high"}
            ],
        }
    )
    result = parse_review_output(raw)
    assert result is not None
    assert result["summary"] == "Found 1 issue"
    assert len(result["comments"]) == 1


def test_parse_review_output_no_json():
    from agent.review_poster import parse_review_output

    result = parse_review_output("Just a plain text response with no JSON")
    assert result is None


def test_parse_review_output_wrong_type():
    from agent.review_poster import parse_review_output

    raw = json.dumps({"skill_output_type": "pr", "summary": "test"})
    result = parse_review_output(raw)
    assert result is None


def test_format_review_summary():
    from agent.review_poster import format_review_summary

    review = {
        "summary": "Found 2 issues",
        "score": "7/10",
        "comments": [
            {"file": "a.py", "line": 1, "message": "Bug", "severity": "high"},
            {"file": "b.py", "line": 2, "message": "Style", "severity": "low"},
        ],
    }
    md = format_review_summary(review, "code-review")
    assert "### AAP Open SWE — Code Review" in md
    assert "7/10" in md
    assert "high" in md.lower()
