"""Deterministic classifier — flags repos and gists by keyword match.

A repo is flagged if ANY of these are true (case-insensitive, substring):
  - any configured keyword appears in name, description, or topics
  - name (basename) matches a known org private-repo basename
  - any configured keyword appears in the README

A gist is flagged if ANY of these are true:
  - any keyword appears in description
  - any keyword appears in a filename

Gist file CONTENTS are not classified in v1 (see TODO.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from tuvok.github import Gist, Repo


class Reason(str, Enum):
    NAME_MATCH = "name_keyword_match"
    DESCRIPTION_MATCH = "description_keyword_match"
    TOPIC_MATCH = "topic_keyword_match"
    BASENAME_OVERLAP = "basename_matches_org_private_repo"
    README_MATCH = "readme_keyword_match"
    GIST_DESCRIPTION_MATCH = "gist_description_keyword_match"
    GIST_FILENAME_MATCH = "gist_filename_keyword_match"


@dataclass
class ClassifiedRepo:
    repo: Repo
    reasons: list[Reason] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(self.reasons)


@dataclass
class ClassifiedGist:
    gist: Gist
    reasons: list[Reason] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(self.reasons)


def _any_in(needles: tuple[str, ...], haystack: str) -> bool:
    lowered = haystack.lower()
    return any(n in lowered for n in needles)


def _name_reasons(repo: Repo, keywords: tuple[str, ...]) -> list[Reason]:
    reasons: list[Reason] = []
    if _any_in(keywords, repo.name):
        reasons.append(Reason.NAME_MATCH)
    if repo.description and _any_in(keywords, repo.description):
        reasons.append(Reason.DESCRIPTION_MATCH)
    if any(_any_in(keywords, t) for t in repo.topics):
        reasons.append(Reason.TOPIC_MATCH)
    return reasons


def _basename_reasons(repo: Repo, private_basenames: set[str]) -> list[Reason]:
    if repo.name.lower() in private_basenames:
        return [Reason.BASENAME_OVERLAP]
    return []


def _readme_reasons(readme: str, keywords: tuple[str, ...]) -> list[Reason]:
    if readme and _any_in(keywords, readme):
        return [Reason.README_MATCH]
    return []


def classify_without_readme(
    repo: Repo,
    keywords: tuple[str, ...],
    private_basenames: set[str],
) -> ClassifiedRepo:
    """First pass: cheap heuristics; no extra GitHub calls."""
    reasons = (
        _name_reasons(repo, keywords)
        + _basename_reasons(repo, private_basenames)
    )
    return ClassifiedRepo(repo=repo, reasons=reasons)


def classify_with_readme(
    classified: ClassifiedRepo,
    readme: str,
    keywords: tuple[str, ...],
) -> ClassifiedRepo:
    """Second pass: add README-content reason if applicable. Idempotent."""
    if Reason.README_MATCH in classified.reasons:
        return classified
    extra = _readme_reasons(readme, keywords)
    if extra:
        classified.reasons.extend(extra)
    return classified


def classify_gist(gist: Gist, keywords: tuple[str, ...]) -> ClassifiedGist:
    """Cheap gist classification: description + filenames only.

    Per TODO.md, a future iteration may add an opt-in content scan.
    """
    reasons: list[Reason] = []
    if gist.description and _any_in(keywords, gist.description):
        reasons.append(Reason.GIST_DESCRIPTION_MATCH)
    if any(_any_in(keywords, fn) for fn in gist.filenames):
        reasons.append(Reason.GIST_FILENAME_MATCH)
    return ClassifiedGist(gist=gist, reasons=reasons)
