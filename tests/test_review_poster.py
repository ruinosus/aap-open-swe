"""Tests for GitHub Reviews API poster."""

import json


def test_parse_review_output_valid_json():
    from agent.skills.review.poster import parse_review_output

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
    from agent.skills.review.poster import parse_review_output

    result = parse_review_output("Just a plain text response with no JSON")
    assert result is None


def test_parse_review_output_wrong_type():
    from agent.skills.review.poster import parse_review_output

    raw = json.dumps({"skill_output_type": "pr", "summary": "test"})
    result = parse_review_output(raw)
    assert result is None


def test_parse_review_output_markdown_code_block():
    from agent.skills.review.poster import parse_review_output

    raw = """Here is my analysis of the code:

```json
{"skill_output_type": "review", "summary": "Found issues", "score": "6/10", "comments": [{"file": "a.py", "line": 1, "message": "Bug", "severity": "high"}]}
```

That's my review."""
    result = parse_review_output(raw)
    assert result is not None
    assert result["summary"] == "Found issues"
    assert len(result["comments"]) == 1


def test_parse_review_output_prose_before_json():
    from agent.skills.review.poster import parse_review_output

    raw = """I've analyzed the code and found several issues.

{"skill_output_type": "review", "summary": "3 issues found", "score": "5/10", "comments": [{"file": "b.py", "line": 10, "message": "SQL injection", "severity": "critical"}]}"""
    result = parse_review_output(raw)
    assert result is not None
    assert result["score"] == "5/10"


def test_parse_review_output_lenient_no_skill_output_type():
    from agent.skills.review.poster import parse_review_output

    # Some models may omit skill_output_type but still have the right structure
    raw = json.dumps(
        {
            "summary": "All good",
            "score": "9/10",
            "comments": [],
        }
    )
    result = parse_review_output(raw)
    assert result is not None
    assert result["summary"] == "All good"


def test_parse_review_output_empty_string():
    from agent.skills.review.poster import parse_review_output

    assert parse_review_output("") is None
    assert parse_review_output("   ") is None


def test_format_review_summary():
    from agent.skills.review.poster import format_review_summary

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
