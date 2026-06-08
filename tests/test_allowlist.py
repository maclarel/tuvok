"""Allowlist parsing, pipeline filtering, and CLI resolution."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuvok.allowlist import Allowlist, empty, load
from tuvok.cli import _resolve_allowlist
from tuvok.github import Gist, Repo
from tuvok.pipeline import _classify_user_gists, _classify_user_repos


# ---------- helpers ----------

def _repo(full_name: str) -> Repo:
    owner, name = full_name.split("/", 1)
    return Repo(
        owner=owner,
        name=name,
        full_name=full_name,
        description="",
        topics=[],
        fork=False,
        archived=False,
        visibility="public",
        html_url=f"https://github.com/{full_name}",
        pushed_at="2026-06-01T00:00:00Z",
        stargazers_count=0,
        default_branch="main",
    )


def _gist(gid: str, owner: str = "alice") -> Gist:
    return Gist(
        id=gid,
        owner=owner,
        description="",
        filenames=[],
        html_url=f"https://gist.github.com/{owner}/{gid}",
        updated_at="2026-06-01T00:00:00Z",
        public=True,
    )


# ---------- parser ----------

def test_parse_basic(tmp_path: Path):
    p = tmp_path / "allowlist"
    p.write_text(
        "# header comment\n"
        "repo: alice/their-fork\n"
        "repo: BOB/MIXEDCASE\n"
        "gist: aabbccdd11223344\n"
        "\n"
        "  # indented comment\n"
        "gist: FEEDFACE  # trailing comment\n"
    )
    al = load(p)
    assert al.source == p
    assert al.entry_count == 4
    # Repo full names are case-normalized.
    assert al.contains_repo("alice/their-fork")
    assert al.contains_repo("Alice/Their-Fork")
    assert al.contains_repo("bob/mixedcase")
    # Gist IDs are case-normalized.
    assert al.contains_gist("AABBCCDD11223344")
    assert al.contains_gist("feedface")
    # Negative.
    assert not al.contains_repo("alice/other")
    assert not al.contains_gist("00000000")


def test_parse_empty_and_whitespace(tmp_path: Path):
    p = tmp_path / "allowlist"
    p.write_text("\n\n   \n# only comments\n")
    al = load(p)
    assert al.entry_count == 0
    assert not al
    assert al.source == p


def test_parse_malformed_lines_warn_but_continue(tmp_path: Path, caplog):
    p = tmp_path / "allowlist"
    p.write_text(
        "repo: alice/good\n"
        "junk-no-colon\n"
        "user: noisycontractor\n"      # unsupported type
        "repo: not-a-full-name\n"      # missing slash
        "repo:\n"                       # empty value
        "gist: deadbeef\n"
    )
    with caplog.at_level(logging.WARNING):
        al = load(p)
    assert al.contains_repo("alice/good")
    assert al.contains_gist("deadbeef")
    assert al.entry_count == 2
    # Exactly four malformed lines should have warned.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 4


def test_empty_constructor():
    al = empty()
    assert not al
    assert al.entry_count == 0
    assert al.source is None
    assert not al.contains_repo("anything/here")
    assert not al.contains_gist("anything")


# ---------- pipeline filtering ----------

def test_classify_user_repos_skips_allowlisted():
    repos = [_repo("alice/keep"), _repo("alice/skip")]
    gh = MagicMock()
    gh.list_public_repos.return_value = repos
    al = Allowlist(repos=frozenset({"alice/skip"}))

    # 'keep' has no match against this keyword set; classifier would skip it
    # via README fetch. To keep this hermetic, ensure README fetch returns "".
    gh.fetch_readme.return_value = ""

    flagged, skipped = _classify_user_repos(
        gh, "alice", keywords=("nomatch",), private_basenames=set(), allowlist=al,
    )
    assert skipped == 1
    # 'keep' should not appear (no keyword hit), 'skip' should be allowlisted
    # before classify_one_repo is even called.
    assert flagged == []
    # README was only fetched for the non-allowlisted repo.
    gh.fetch_readme.assert_called_once_with("alice", "keep")


def test_classify_user_repos_allowlist_case_insensitive():
    repos = [_repo("Alice/MyRepo")]
    gh = MagicMock()
    gh.list_public_repos.return_value = repos
    gh.fetch_readme.return_value = ""
    al = Allowlist(repos=frozenset({"alice/myrepo"}))

    flagged, skipped = _classify_user_repos(
        gh, "Alice", keywords=("nomatch",), private_basenames=set(), allowlist=al,
    )
    assert skipped == 1
    assert flagged == []
    # No README fetch should happen for an allowlisted repo.
    gh.fetch_readme.assert_not_called()


def test_classify_user_gists_skips_allowlisted():
    gists = [_gist("keepid"), _gist("skipid")]
    # Make 'keep' actually flag via filename match so we can verify filtering.
    gists[0].filenames = ["dundermifflin_keys.txt"]
    gh = MagicMock()
    gh.list_user_gists.return_value = gists
    al = Allowlist(gists=frozenset({"skipid"}))

    flagged, skipped = _classify_user_gists(
        gh, "alice", keywords=("dundermifflin",), allowlist=al,
    )
    assert skipped == 1
    assert len(flagged) == 1
    assert flagged[0].gist.id == "keepid"


def test_classify_user_gists_no_allowlist_passthrough():
    gists = [_gist("g1")]
    gists[0].description = "dundermifflin dump"
    gh = MagicMock()
    gh.list_user_gists.return_value = gists

    flagged, skipped = _classify_user_gists(
        gh, "alice", keywords=("dundermifflin",), allowlist=empty(),
    )
    assert skipped == 0
    assert len(flagged) == 1


# ---------- CLI resolution ----------

def _args(**kwargs) -> argparse.Namespace:
    defaults = {"allowlist": None, "no_allowlist": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_resolve_explicit_path(tmp_path: Path):
    p = tmp_path / "list.txt"
    p.write_text("repo: alice/one\n")
    al = _resolve_allowlist(_args(allowlist=p))
    assert al.contains_repo("alice/one")
    assert al.source == p


def test_resolve_explicit_missing_path_errors(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        _resolve_allowlist(_args(allowlist=missing))


def test_resolve_no_allowlist_disables(tmp_path: Path, monkeypatch):
    # Even if a default file is present in cwd, --no-allowlist must skip it.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "allowlist").write_text("repo: alice/should-be-ignored\n")
    al = _resolve_allowlist(_args(no_allowlist=True))
    assert al.entry_count == 0
    assert al.source is None


def test_resolve_default_path_present(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "allowlist").write_text("gist: deadbeef\n")
    al = _resolve_allowlist(_args())
    assert al.contains_gist("deadbeef")
    assert al.source == Path("allowlist")


def test_resolve_default_path_absent_is_silent(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    al = _resolve_allowlist(_args())
    assert al.entry_count == 0
    assert al.source is None
