"""End-to-end pipeline: enumerate -> list -> classify -> trufflehog -> report."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from garak.classifier import (
    ClassifiedGist,
    ClassifiedRepo,
    Reason,
    classify_gist,
    classify_with_readme,
    classify_without_readme,
)
from garak.config import Config
from garak.github import GitHubClient, Repo
from garak.reporting import RunReport, now_utc
from garak.trufflehog import DEFAULT_TIMEOUT_S, scan_gist, scan_repo

log = logging.getLogger(__name__)

_NAME_REASON_VALUES = {
    Reason.NAME_MATCH.value,
    Reason.DESCRIPTION_MATCH.value,
    Reason.TOPIC_MATCH.value,
}


def read_lines(path: Path) -> list[str]:
    """Read a one-per-line text file; strip whitespace and `#` comments."""
    out: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def run(
    config: Config,
    trufflehog_timeout: int = DEFAULT_TIMEOUT_S,
    user_limit: int | None = None,
    users_file: Path | None = None,
    run_trufflehog: bool = True,
    users_out: Path | None = None,
    basenames_out: Path | None = None,
) -> RunReport:
    started = now_utc()
    report = RunReport(
        started_at=started,
        org=config.org,
        keywords=list(config.keywords),
        users_scanned=[],
    )

    with GitHubClient(config.github_token, max_pages=config.max_pages) as gh:
        if users_file is not None:
            users = read_lines(users_file)
            log.info("Using %d user(s) from %s", len(users), users_file)
        else:
            users = gh.list_org_members(config.org)

        # Basenames are always pulled fresh from GitHub: we want to catch
        # newly-created private repos that may be mirrored personally.
        basenames = gh.list_org_repos(config.org)
        private_basenames = set(basenames)

        # Optional disk dumps — only written when caller passed paths in.
        # Skip the users dump if --users-file was used (we'd be writing back
        # the same content we just read).
        if users_out is not None and users_file is None:
            write_lines(users_out, users)
            log.info("Wrote %d user(s) to %s", len(users), users_out)
        if basenames_out is not None:
            write_lines(basenames_out, basenames)
            log.info("Wrote %d basename(s) to %s", len(basenames), basenames_out)

        if user_limit is not None:
            users = users[:user_limit]
        report.users_scanned = users

        log.info(
            "Pipeline: %d user(s), %d private repo basename(s), keywords=%s",
            len(users), len(private_basenames), list(config.keywords),
        )

        flagged_repos, flagged_gists = _enumerate_and_classify(
            gh, users, config.keywords, private_basenames
        )
        report.flagged_repos = flagged_repos
        report.flagged_gists = flagged_gists

    log.info(
        "Classifier flagged %d repo(s) and %d gist(s)",
        len(flagged_repos), len(flagged_gists),
    )

    if not run_trufflehog:
        log.info("Skipping trufflehog (--no-trufflehog)")
        return report

    for cr in flagged_repos:
        report.repo_scans[cr.repo.full_name] = scan_repo(
            cr.repo.full_name,
            timeout=trufflehog_timeout,
            token=config.github_token,
        )
    for cg in flagged_gists:
        report.gist_scans[cg.gist.id] = scan_gist(
            cg.gist.id, timeout=trufflehog_timeout,
        )

    return report


def _enumerate_and_classify(
    gh: GitHubClient,
    users: Iterable[str],
    keywords: tuple[str, ...],
    private_basenames: set[str],
) -> tuple[list[ClassifiedRepo], list[ClassifiedGist]]:
    flagged_repos: list[ClassifiedRepo] = []
    flagged_gists: list[ClassifiedGist] = []
    for login in users:
        flagged_repos.extend(
            _classify_user_repos(gh, login, keywords, private_basenames)
        )
        flagged_gists.extend(_classify_user_gists(gh, login, keywords))
    return flagged_repos, flagged_gists


def _classify_user_repos(
    gh: GitHubClient,
    login: str,
    keywords: tuple[str, ...],
    private_basenames: set[str],
) -> list[ClassifiedRepo]:
    try:
        repos = gh.list_public_repos(login)
    except Exception as exc:
        log.warning("Listing repos for %s failed: %s", login, exc)
        return []
    log.debug("%s has %d public repo(s)", login, len(repos))
    flagged: list[ClassifiedRepo] = []
    for repo in repos:
        cr = _classify_one_repo(gh, repo, keywords, private_basenames)
        if cr is not None and cr.flagged:
            flagged.append(cr)
    return flagged


def _classify_one_repo(
    gh: GitHubClient,
    repo: Repo,
    keywords: tuple[str, ...],
    private_basenames: set[str],
) -> ClassifiedRepo | None:
    cr = classify_without_readme(repo, keywords, private_basenames)
    if repo.fork:
        # Forks only count if their own name/description/topics name-match.
        # Basename overlap is the default fork shape and uninteresting.
        name_matched = any(r.value in _NAME_REASON_VALUES for r in cr.reasons)
        return cr if name_matched else None
    if cr.flagged:
        return cr
    # Non-fork last-resort README scan.
    try:
        readme = gh.fetch_readme(repo.owner, repo.name)
    except Exception as exc:
        log.debug("README fetch for %s failed: %s", repo.full_name, exc)
        readme = ""
    return classify_with_readme(cr, readme, keywords)


def _classify_user_gists(
    gh: GitHubClient,
    login: str,
    keywords: tuple[str, ...],
) -> list[ClassifiedGist]:
    try:
        gists = gh.list_user_gists(login)
    except Exception as exc:
        log.warning("Listing gists for %s failed: %s", login, exc)
        return []
    log.debug("%s has %d public gist(s)", login, len(gists))
    flagged: list[ClassifiedGist] = []
    for gist in gists:
        cg = classify_gist(gist, keywords)
        if cg.flagged:
            flagged.append(cg)
    return flagged
