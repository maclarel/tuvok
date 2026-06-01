"""Trufflehog v3 subprocess wrapper.

Two scan modes:
- scan_repo: `trufflehog github --repo` for owner/name pairs.
- scan_gist: `trufflehog git --uri` against the gist's `.git` URL, because
  the github subcommand has no single-gist target flag.

Both produce a normalized list of `Secret` records with the matched value
redacted.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 600


@dataclass
class Secret:
    detector: str
    file: str
    commit: str
    line: str
    link: str
    redacted: str


@dataclass
class ScanResult:
    target: str
    secrets: list[Secret] = field(default_factory=list)
    timed_out: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.timed_out and not self.error


def _redact(raw: str) -> str:
    """Show only the last 8 chars; mask everything before.

    Secrets of 8 or fewer chars are fully masked. Showing both ends would
    leak too much for short tokens, and 4-char tails collide more often
    than is comfortable for grepping reports.
    """
    if not raw:
        return ""
    raw = raw.strip()
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{'*' * (len(raw) - 8)}{raw[-8:]}"


def _parse_line(line: str) -> Secret | None:
    """Parse one JSON line of trufflehog output into a Secret, or None.

    Trufflehog emits non-JSON status lines to stdout occasionally; those
    are skipped silently rather than aborting the scan. The source metadata
    block lives under `Github` or `Git` depending on the source.
    """
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    data = obj.get("SourceMetadata", {}).get("Data", {})
    src = data.get("Github") or data.get("Git") or {}
    return Secret(
        detector=obj.get("DetectorName") or str(obj.get("DetectorType", "unknown")),
        file=src.get("file", ""),
        commit=str(src.get("commit", ""))[:12],
        line=str(src.get("line", "")),
        link=src.get("link", ""),
        redacted=_redact(obj.get("Raw", "")),
    )


def _execute(
    cmd: list[str], target: str, timeout: int, extra_env: dict[str, str] | None = None,
) -> ScanResult:
    log.info("trufflehog scan: %s", target)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        log.warning("trufflehog timed out on %s after %ds", target, timeout)
        partial = (
            exc.stdout if isinstance(exc.stdout, str)
            else exc.stdout.decode("utf-8", errors="replace") if exc.stdout
            else ""
        )
        secrets = [s for s in (_parse_line(l) for l in partial.splitlines()) if s]
        return ScanResult(target=target, secrets=secrets, timed_out=True)
    except FileNotFoundError:
        return ScanResult(target=target, error="trufflehog binary not found on PATH")

    secrets = [s for s in (_parse_line(l) for l in proc.stdout.splitlines()) if s]
    if proc.returncode != 0 and not secrets:
        log.warning(
            "trufflehog %s exited %d: %s",
            target, proc.returncode, proc.stderr[:500],
        )
        return ScanResult(
            target=target,
            error=f"exit {proc.returncode}: {proc.stderr.strip()[:200]}",
        )
    log.info("trufflehog %s: %d secret(s)", target, len(secrets))
    return ScanResult(target=target, secrets=secrets)


def scan_repo(
    full_name: str,
    timeout: int = DEFAULT_TIMEOUT_S,
    token: str | None = None,
) -> ScanResult:
    """Run trufflehog against `owner/name`.

    Token is passed via the GITHUB_TOKEN env var rather than `--token` so it
    is not visible in the process arg list (ps).
    """
    cmd = [
        "trufflehog", "github",
        "--repo", f"https://github.com/{full_name}",
        "--no-verification",
        "--json",
        "--no-update",
    ]
    extra_env = {"GITHUB_TOKEN": token} if token else None
    return _execute(cmd, target=full_name, timeout=timeout, extra_env=extra_env)


def scan_gist(gist_id: str, timeout: int = DEFAULT_TIMEOUT_S) -> ScanResult:
    """Run trufflehog against a public gist via its git URL.

    `trufflehog github` doesn't expose a single-gist target, but every gist
    is reachable as a plain git repo at https://gist.github.com/<id>.git.
    """
    uri = f"https://gist.github.com/{gist_id}.git"
    cmd = [
        "trufflehog", "git",
        "--no-verification",
        "--json",
        "--no-update",
        uri,
    ]
    return _execute(cmd, target=f"gist:{gist_id}", timeout=timeout)
