"""Classifier heuristic coverage — repos and gists."""

from __future__ import annotations

from garak.classifier import (
    Reason,
    classify_gist,
    classify_with_readme,
    classify_without_readme,
)
from garak.github import Gist, Repo

KEYWORDS = ("dundermifflin", "paper")


def _repo(**kwargs) -> Repo:
    defaults = dict(
        owner="someone",
        name="thing",
        full_name="someone/thing",
        description="",
        topics=[],
        fork=False,
        archived=False,
        visibility="public",
        html_url="https://github.com/someone/thing",
        pushed_at="2026-06-01T00:00:00Z",
        stargazers_count=0,
        default_branch="main",
    )
    defaults.update(kwargs)
    return Repo(**defaults)


def _gist(**kwargs) -> Gist:
    defaults = dict(
        id="abc123",
        owner="someone",
        description="",
        filenames=[],
        html_url="https://gist.github.com/someone/abc123",
        updated_at="2026-06-01T00:00:00Z",
        public=True,
    )
    defaults.update(kwargs)
    return Gist(**defaults)


def test_name_match():
    cr = classify_without_readme(_repo(name="dundermifflin-tools"), KEYWORDS, set())
    assert cr.flagged
    assert Reason.NAME_MATCH in cr.reasons


def test_name_match_case_insensitive():
    cr = classify_without_readme(_repo(name="MyDUNDERMIFFLINPlugin"), KEYWORDS, set())
    assert Reason.NAME_MATCH in cr.reasons


def test_description_match():
    cr = classify_without_readme(
        _repo(description="Internal DunderMifflin utility"), KEYWORDS, set(),
    )
    assert Reason.DESCRIPTION_MATCH in cr.reasons


def test_topic_match():
    cr = classify_without_readme(_repo(topics=["sales", "DunderMifflin"]), KEYWORDS, set())
    assert Reason.TOPIC_MATCH in cr.reasons


def test_basename_overlap():
    """Name must not contain any keyword — otherwise we'd also get NAME_MATCH."""
    cr = classify_without_readme(
        _repo(name="sarcasm-detector"),
        KEYWORDS,
        private_basenames={"sarcasm-detector", "secret-thing"},
    )
    assert cr.reasons == [Reason.BASENAME_OVERLAP]


def test_no_match():
    cr = classify_without_readme(
        _repo(name="random-side-project", description="just a thing"),
        KEYWORDS,
        private_basenames={"actual-private"},
    )
    assert not cr.flagged


def test_readme_pass_adds_reason():
    cr = classify_without_readme(_repo(name="benign"), KEYWORDS, set())
    cr = classify_with_readme(cr, "This thing was originally built at DunderMifflin.", KEYWORDS)
    assert Reason.README_MATCH in cr.reasons


def test_readme_pass_empty_readme():
    cr = classify_without_readme(_repo(name="benign"), KEYWORDS, set())
    cr = classify_with_readme(cr, "", KEYWORDS)
    assert not cr.flagged


def test_readme_pass_idempotent():
    cr = classify_without_readme(_repo(name="benign"), KEYWORDS, set())
    cr = classify_with_readme(cr, "dundermifflin reference", KEYWORDS)
    cr = classify_with_readme(cr, "dundermifflin reference", KEYWORDS)
    assert cr.reasons.count(Reason.README_MATCH) == 1


def test_multiple_reasons_collected():
    cr = classify_without_readme(
        _repo(
            name="dundermifflin-poc",
            description="exploit for DunderMifflin",
            topics=["dundermifflin"],
        ),
        KEYWORDS,
        private_basenames={"dundermifflin-poc"},
    )
    assert {
        Reason.NAME_MATCH,
        Reason.DESCRIPTION_MATCH,
        Reason.TOPIC_MATCH,
        Reason.BASENAME_OVERLAP,
    } <= set(cr.reasons)


def test_keywords_are_configurable():
    """Classifier should react to any configured keyword set."""
    cr = classify_without_readme(
        _repo(name="acme-internal-tool"), ("acme",), set(),
    )
    assert Reason.NAME_MATCH in cr.reasons


def test_gist_description_match():
    cg = classify_gist(_gist(description="my DunderMifflin scratch script"), KEYWORDS)
    assert cg.flagged
    assert Reason.GIST_DESCRIPTION_MATCH in cg.reasons


def test_gist_filename_match():
    cg = classify_gist(_gist(filenames=["dundermifflin_dump.json"]), KEYWORDS)
    assert Reason.GIST_FILENAME_MATCH in cg.reasons


def test_gist_no_match():
    cg = classify_gist(
        _gist(description="random snippet", filenames=["misc.py"]), KEYWORDS,
    )
    assert not cg.flagged


def test_gist_case_insensitive():
    cg = classify_gist(_gist(filenames=["DUNDERMIFFLIN-keys.txt"]), KEYWORDS)
    assert Reason.GIST_FILENAME_MATCH in cg.reasons
