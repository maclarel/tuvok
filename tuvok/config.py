"""Environment configuration. All values required — fail fast on missing inputs."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


DEFAULT_MAX_PAGES = 50


@dataclass(frozen=True)
class Config:
    github_token: str
    org: str
    keywords: tuple[str, ...]
    max_pages: int = DEFAULT_MAX_PAGES

    @classmethod
    def from_env(cls, env_path: str | None = None) -> Config:
        load_dotenv(env_path)
        token = os.environ.get("TUVOK_TOKEN", "")
        org = os.environ.get("TUVOK_ORG", "").strip()
        keywords_raw = os.environ.get("TUVOK_KEYWORDS", "")
        keywords = tuple(
            k.strip().lower() for k in keywords_raw.split(",") if k.strip()
        )
        max_pages_raw = os.environ.get("TUVOK_MAX_PAGES", "").strip()
        try:
            max_pages = int(max_pages_raw) if max_pages_raw else DEFAULT_MAX_PAGES
        except ValueError:
            raise EnvironmentError(
                f"TUVOK_MAX_PAGES must be an integer, got: {max_pages_raw!r}"
            )
        if max_pages < 1:
            raise EnvironmentError("TUVOK_MAX_PAGES must be >= 1")

        missing: list[str] = []
        if not token:
            missing.append("TUVOK_TOKEN")
        if not org:
            missing.append("TUVOK_ORG")
        if not keywords:
            missing.append("TUVOK_KEYWORDS")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return cls(
            github_token=token,
            org=org,
            keywords=keywords,
            max_pages=max_pages,
        )
