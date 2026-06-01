"""GitHub REST client — org members, repos (public + private), user repos, gists.

PAT auth required. Exits on auth or rate-limit failures with a clear message.
"""

from __future__ import annotations

import base64
import logging
import sys
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


@dataclass
class Repo:
    owner: str
    name: str
    full_name: str
    description: str
    topics: list[str] = field(default_factory=list)
    fork: bool = False
    archived: bool = False
    visibility: str = "public"
    html_url: str = ""
    pushed_at: str = ""
    stargazers_count: int = 0
    default_branch: str = ""


@dataclass
class Gist:
    id: str
    owner: str
    description: str
    filenames: list[str] = field(default_factory=list)
    html_url: str = ""
    updated_at: str = ""
    public: bool = True


DEFAULT_MAX_PAGES = 50


class GitHubClient:
    def __init__(
        self, token: str, timeout: float = 30.0, max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self._http = httpx.Client(
            base_url=API_BASE,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Tuvok/0.1.0",
            },
        )
        self._max_pages = max_pages

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    def _check_rate_limit(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            log.error("GitHub auth failed (401). Refresh TUVOK_TOKEN.")
            sys.exit(2)
        if response.status_code == 403 and response.headers.get(
            "x-ratelimit-remaining"
        ) == "0":
            reset = response.headers.get("x-ratelimit-reset", "?")
            log.error(
                "GitHub rate limit exhausted. Resets at unix timestamp %s.",
                reset,
            )
            sys.exit(2)

    def _paginate(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Walk `path` page-by-page, returning the concatenated list.

        Hard-caps at `self._max_pages` requests (default 50, override via
        TUVOK_MAX_PAGES) so a misbehaving API can't cause an unbounded
        request loop. Logs a warning if the cap is hit so partial-result
        truncation is visible.
        """
        results: list[dict] = []
        params = dict(params or {})
        params.setdefault("per_page", 100)
        for page in range(1, self._max_pages + 1):
            params["page"] = page
            response = self._http.get(path, params=params)
            self._check_rate_limit(response)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                return results
            results.extend(batch)
            if len(batch) < params["per_page"]:
                return results
        log.warning(
            "Pagination cap (%d pages) hit on %s — results may be truncated. "
            "Increase TUVOK_MAX_PAGES if this is expected.",
            self._max_pages, path,
        )
        return results

    def list_org_members(self, org: str) -> list[str]:
        """Return all member logins of `org`. Requires Members: Read."""
        items = self._paginate(f"/orgs/{org}/members")
        logins = sorted({item["login"] for item in items if item.get("login")})
        log.info("Org %s: %d member(s)", org, len(logins))
        return logins

    def list_org_repos(self, org: str) -> list[str]:
        """Return all repo basenames (lowercase) belonging to `org`,
        including private. Requires Contents: Read.
        """
        items = self._paginate(f"/orgs/{org}/repos", params={"type": "all"})
        basenames = {
            item["name"].lower()
            for item in items
            if item.get("name")
        }
        log.info("Org %s: %d repo basename(s) (incl. private)", org, len(basenames))
        return sorted(basenames)

    def list_public_repos(self, login: str) -> list[Repo]:
        """List public repos owned by `login` (paginated)."""
        items = self._paginate(
            f"/users/{login}/repos", params={"type": "owner"}
        )
        repos: list[Repo] = []
        for item in items:
            if item.get("private") or item.get("visibility") != "public":
                continue
            repos.append(
                Repo(
                    owner=item["owner"]["login"],
                    name=item["name"],
                    full_name=item["full_name"],
                    description=item.get("description") or "",
                    topics=item.get("topics") or [],
                    fork=bool(item.get("fork")),
                    archived=bool(item.get("archived")),
                    visibility=item.get("visibility", "public"),
                    html_url=item.get("html_url", ""),
                    pushed_at=item.get("pushed_at", ""),
                    stargazers_count=int(item.get("stargazers_count", 0)),
                    default_branch=item.get("default_branch", ""),
                )
            )
        return repos

    def list_user_gists(self, login: str) -> list[Gist]:
        """List public gists owned by `login`."""
        items = self._paginate(f"/users/{login}/gists")
        gists: list[Gist] = []
        for item in items:
            if not item.get("public", True):
                continue
            files = item.get("files") or {}
            gists.append(
                Gist(
                    id=item.get("id", ""),
                    owner=login,
                    description=item.get("description") or "",
                    filenames=sorted(files.keys()),
                    html_url=item.get("html_url", ""),
                    updated_at=item.get("updated_at", ""),
                    public=True,
                )
            )
        return gists

    def fetch_readme(self, owner: str, repo: str) -> str:
        """Return decoded README text, or empty string."""
        response = self._http.get(f"/repos/{owner}/{repo}/readme")
        self._check_rate_limit(response)
        if response.status_code == 404:
            return ""
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content", "")
        encoding = payload.get("encoding", "")
        if encoding != "base64" or not content:
            return ""
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            return ""
