"""Markdown reporting — verify key sections render correctly."""

from __future__ import annotations

from datetime import datetime, timezone

from tuvok.classifier import ClassifiedGist, ClassifiedRepo, Reason
from tuvok.github import Gist, Repo
from tuvok.reporting import RunReport, render, report_filename
from tuvok.trufflehog import ScanResult, Secret


def _repo(name="thing", owner="someone") -> Repo:
    return Repo(
        owner=owner,
        name=name,
        full_name=f"{owner}/{name}",
        description="",
        topics=[],
        fork=False,
        archived=False,
        visibility="public",
        html_url=f"https://github.com/{owner}/{name}",
        pushed_at="2026-06-01T00:00:00Z",
        stargazers_count=0,
        default_branch="main",
    )


def _gist(gid="abc123", owner="someone") -> Gist:
    return Gist(
        id=gid,
        owner=owner,
        description="",
        filenames=[],
        html_url=f"https://gist.github.com/{owner}/{gid}",
        updated_at="2026-06-01T00:00:00Z",
        public=True,
    )


def _ts() -> datetime:
    return datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc)


def test_filename_format():
    assert report_filename(_ts()) == "2026-06-01-14-30-report.md"


def test_render_summary_counts():
    repo_a = _repo(name="dundermifflin-tool")
    repo_b = _repo(name="other-thing")
    scan_a = ScanResult(
        target=repo_a.full_name,
        secrets=[
            Secret(
                detector="AWS",
                file="env.sh",
                commit="abc123",
                line="5",
                link="https://github.com/x/y/blob/abc123/env.sh#L5",
                redacted="************90ABCDEF",
            )
        ],
    )
    scan_b = ScanResult(target=repo_b.full_name, secrets=[])

    report = RunReport(
        started_at=_ts(),
        org="dundermifflin",
        keywords=["dundermifflin"],
        users_scanned=["alice", "bob"],
        flagged_repos=[
            ClassifiedRepo(repo=repo_a, reasons=[Reason.NAME_MATCH]),
            ClassifiedRepo(repo=repo_b, reasons=[Reason.BASENAME_OVERLAP]),
        ],
        repo_scans={repo_a.full_name: scan_a, repo_b.full_name: scan_b},
    )

    md = render(report)
    assert "Org:** dundermifflin" in md
    assert "Keywords:** dundermifflin" in md
    assert "Users scanned:** 2" in md
    assert "Repos flagged:** 2" in md
    assert "Flagged repos with secrets:** 1" in md
    assert "Total secret findings:** 1" in md
    assert "Repositories with detected secrets" in md
    assert "Flagged repositories without detected secrets" in md
    assert "name_keyword_match" in md
    assert "basename_matches_org_private_repo" in md
    assert "************90ABCDEF" in md
    assert "No secrets detected" in md


def test_render_empty_run():
    report = RunReport(
        started_at=_ts(),
        org="dundermifflin",
        keywords=["dundermifflin"],
        users_scanned=["alice"],
    )
    md = render(report)
    assert "No keyword-related public repos or gists" in md


def test_render_timeout_partial():
    repo = _repo(name="dundermifflin-large")
    scan = ScanResult(
        target=repo.full_name,
        secrets=[
            Secret(
                detector="Slack",
                file="bot.py",
                commit="def456",
                line="42",
                link="",
                redacted="************xoxbabcd",
            )
        ],
        timed_out=True,
    )
    report = RunReport(
        started_at=_ts(),
        org="dundermifflin",
        keywords=["dundermifflin"],
        users_scanned=["alice"],
        flagged_repos=[ClassifiedRepo(repo=repo, reasons=[Reason.NAME_MATCH])],
        repo_scans={repo.full_name: scan},
    )
    md = render(report)
    assert "Trufflehog timed out" in md
    assert "************xoxbabcd" in md


def test_render_gist_section_with_secret():
    gist = _gist(gid="g999")
    classified = ClassifiedGist(
        gist=Gist(
            id="g999",
            owner="alice",
            description="dundermifflin backup",
            filenames=["dump.json"],
            html_url="https://gist.github.com/alice/g999",
            updated_at="2026-06-01T00:00:00Z",
            public=True,
        ),
        reasons=[Reason.GIST_DESCRIPTION_MATCH, Reason.GIST_FILENAME_MATCH],
    )
    scan = ScanResult(
        target="gist:g999",
        secrets=[
            Secret(
                detector="GenericAPIKey",
                file="dump.json",
                commit="0a0a0a0",
                line="3",
                link="",
                redacted="************abcdwxyz",
            )
        ],
    )
    report = RunReport(
        started_at=_ts(),
        org="dundermifflin",
        keywords=["dundermifflin"],
        users_scanned=["alice"],
        flagged_gists=[classified],
        gist_scans={"g999": scan},
    )
    md = render(report)
    assert "Gists with detected secrets" in md
    assert "gist g999" in md
    assert "gist_description_keyword_match" in md
    assert "gist_filename_keyword_match" in md
    assert "************abcdwxyz" in md
    assert "Gists flagged:** 1" in md
    assert "Flagged gists with secrets:** 1" in md


def test_render_escapes_pipe_in_redacted():
    """A pipe in the redacted value must be escaped inside the table cell."""
    repo = _repo(name="weird")
    scan = ScanResult(
        target=repo.full_name,
        secrets=[
            Secret(
                detector="GenericAPIKey",
                file="ok.txt",
                commit="abc123",
                line="1",
                link="",
                redacted="abc|def|ghi",
            )
        ],
    )
    report = RunReport(
        started_at=_ts(),
        org="dundermifflin",
        keywords=["dundermifflin"],
        users_scanned=["alice"],
        flagged_repos=[ClassifiedRepo(repo=repo, reasons=[Reason.NAME_MATCH])],
        repo_scans={repo.full_name: scan},
    )
    md = render(report)
    # Raw pipes must NOT appear unescaped (would break table layout).
    assert "abc|def" not in md
    assert "abc\\|def\\|ghi" in md


def test_render_escapes_brackets_in_full_name_link():
    """A `]` in a repo full name must not collapse the markdown link."""
    repo = _repo()
    repo.full_name = "alice/we]rd-name"
    repo.html_url = "https://github.com/alice/weird"
    classified = ClassifiedRepo(repo=repo, reasons=[Reason.NAME_MATCH])
    report = RunReport(
        started_at=_ts(),
        org="dundermifflin",
        keywords=["dundermifflin"],
        users_scanned=["alice"],
        flagged_repos=[classified],
        repo_scans={},
    )
    md = render(report)
    # Bracket must be escaped so the link text doesn't terminate early.
    assert "alice/we\\]rd-name" in md
    assert "[alice/we]rd-name]" not in md


def test_render_escapes_backticks_in_file_path():
    """A backtick in a file path would break the surrounding code span."""
    repo = _repo(name="weird")
    scan = ScanResult(
        target=repo.full_name,
        secrets=[
            Secret(
                detector="Generic",
                file="paths/with`backtick.txt",
                commit="0a0a0a0",
                line="2",
                link="",
                redacted="abcdefgh",
            )
        ],
    )
    report = RunReport(
        started_at=_ts(),
        org="dundermifflin",
        keywords=["dundermifflin"],
        users_scanned=["alice"],
        flagged_repos=[ClassifiedRepo(repo=repo, reasons=[Reason.NAME_MATCH])],
        repo_scans={repo.full_name: scan},
    )
    md = render(report)
    assert "paths/with\\`backtick.txt" in md


def test_render_gist_section_clean():
    classified = ClassifiedGist(
        gist=Gist(
            id="g000",
            owner="alice",
            description="dundermifflin-related scratch",
            filenames=["notes.md"],
            html_url="https://gist.github.com/alice/g000",
            updated_at="2026-06-01T00:00:00Z",
            public=True,
        ),
        reasons=[Reason.GIST_DESCRIPTION_MATCH],
    )
    scan = ScanResult(target="gist:g000", secrets=[])
    report = RunReport(
        started_at=_ts(),
        org="dundermifflin",
        keywords=["dundermifflin"],
        users_scanned=["alice"],
        flagged_gists=[classified],
        gist_scans={"g000": scan},
    )
    md = render(report)
    assert "Flagged gists without detected secrets" in md
    assert "No secrets detected" in md
