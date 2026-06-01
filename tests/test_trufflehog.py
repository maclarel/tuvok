"""Trufflehog output parser + redaction."""

from __future__ import annotations

import json

from garak.trufflehog import _parse_line, _redact


def test_redact_short():
    assert _redact("short") == "*****"


def test_redact_exactly_eight():
    assert _redact("abcdefgh") == "********"


def test_redact_long():
    redacted = _redact("AKIA1234567890ABCDEF")
    # Show only the last 8 chars; everything before is masked.
    assert redacted.endswith("90ABCDEF")
    assert not redacted.startswith("AKIA")
    assert redacted.startswith("*" * 12)
    assert "1234567890AB" not in redacted


def test_parse_line_full():
    line = json.dumps(
        {
            "DetectorName": "AWS",
            "Raw": "AKIA1234567890ABCDEF",
            "SourceMetadata": {
                "Data": {
                    "Github": {
                        "file": "config/secrets.env",
                        "commit": "0123456789abcdef0123456789abcdef01234567",
                        "line": 12,
                        "link": "https://github.com/o/r/blob/01234567/config/secrets.env#L12",
                    }
                }
            },
        }
    )
    secret = _parse_line(line)
    assert secret is not None
    assert secret.detector == "AWS"
    assert secret.file == "config/secrets.env"
    assert secret.commit == "0123456789ab"
    assert secret.line == "12"
    assert secret.redacted.endswith("90ABCDEF")
    assert "1234567890" not in secret.redacted


def test_parse_line_empty():
    assert _parse_line("") is None
    assert _parse_line("   \n") is None


def test_parse_line_non_json():
    assert _parse_line("INFO loading rulesets...") is None


def test_parse_line_missing_github_section():
    line = json.dumps({"DetectorName": "Generic", "Raw": "supersecretvaluexxx"})
    secret = _parse_line(line)
    assert secret is not None
    assert secret.detector == "Generic"
    assert secret.file == ""
    assert secret.commit == ""


def test_parse_line_git_source():
    """Trufflehog git source (used for gists) emits SourceMetadata.Data.Git
    instead of .Github. Parser should handle both."""
    line = json.dumps(
        {
            "DetectorName": "Slack",
            "Raw": "xoxbverysecretxoxb",
            "SourceMetadata": {
                "Data": {
                    "Git": {
                        "file": "snippet.py",
                        "commit": "fedcba9876543210fedcba9876543210fedcba98",
                        "line": 7,
                        "repository": "https://gist.github.com/abc.git",
                    }
                }
            },
        }
    )
    secret = _parse_line(line)
    assert secret is not None
    assert secret.detector == "Slack"
    assert secret.file == "snippet.py"
    assert secret.commit == "fedcba987654"
    assert secret.line == "7"
    # Last 8 chars are shown; "xoxbverysecretxoxb" -> last 8 are "cretxoxb".
    assert secret.redacted.endswith("cretxoxb")
    assert not secret.redacted.startswith("xoxb")
