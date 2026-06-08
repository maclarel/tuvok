"""Allowlist of repos and gists to exclude from classification and scanning.

File format — one entry per line, `#` for comments, blanks ignored:

    repo: owner/repo-name
    gist: <gist-id>

Repo full names and gist IDs are normalized to lowercase. Unknown / malformed
lines are logged at WARNING and skipped (the rest of the file still loads).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Allowlist:
    repos: frozenset[str] = field(default_factory=frozenset)
    gists: frozenset[str] = field(default_factory=frozenset)
    source: Path | None = None

    @property
    def entry_count(self) -> int:
        return len(self.repos) + len(self.gists)

    def __bool__(self) -> bool:
        return self.entry_count > 0

    def contains_repo(self, full_name: str) -> bool:
        return full_name.lower() in self.repos

    def contains_gist(self, gist_id: str) -> bool:
        return gist_id.lower() in self.gists


def empty() -> Allowlist:
    return Allowlist()


def load(path: Path) -> Allowlist:
    """Parse an allowlist file. Caller is responsible for existence checks."""
    repos: set[str] = set()
    gists: set[str] = set()
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        prefix, sep, value = line.partition(":")
        value = value.strip()
        if not sep or not value:
            log.warning("allowlist %s:%d malformed (no prefix): %r", path, lineno, raw)
            continue
        kind = prefix.strip().lower()
        if kind == "repo":
            if "/" not in value:
                log.warning(
                    "allowlist %s:%d repo entry must be owner/name: %r",
                    path, lineno, raw,
                )
                continue
            repos.add(value.lower())
        elif kind == "gist":
            gists.add(value.lower())
        else:
            log.warning(
                "allowlist %s:%d unknown entry type %r (expected repo: or gist:)",
                path, lineno, prefix.strip(),
            )
    return Allowlist(
        repos=frozenset(repos),
        gists=frozenset(gists),
        source=path,
    )
