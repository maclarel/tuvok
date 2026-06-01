"""Markdown report rendering — purely deterministic templating."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tuvok.classifier import ClassifiedGist, ClassifiedRepo, Reason
from tuvok.trufflehog import ScanResult

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    """Aggregate of one full pipeline run."""

    started_at: datetime
    org: str
    keywords: list[str]
    users_scanned: list[str]
    flagged_repos: list[ClassifiedRepo] = field(default_factory=list)
    flagged_gists: list[ClassifiedGist] = field(default_factory=list)
    repo_scans: dict[str, ScanResult] = field(default_factory=dict)
    gist_scans: dict[str, ScanResult] = field(default_factory=dict)

    @property
    def repos_with_secrets(self) -> int:
        return sum(1 for s in self.repo_scans.values() if s.secrets)

    @property
    def gists_with_secrets(self) -> int:
        return sum(1 for s in self.gist_scans.values() if s.secrets)

    @property
    def total_secrets(self) -> int:
        return (
            sum(len(s.secrets) for s in self.repo_scans.values())
            + sum(len(s.secrets) for s in self.gist_scans.values())
        )


def _md_cell(value: str) -> str:
    """Escape a string for safe use inside a GFM table cell.

    Repo descriptions, file paths, and even redacted secrets can contain
    `|`, backslashes, newlines, or backticks — any of which would corrupt
    or inject content into the surrounding table.
    """
    if not value:
        return "—"
    return (
        value.replace("\\", "\\\\")
             .replace("|", "\\|")
             .replace("`", "\\`")
             .replace("\r", " ")
             .replace("\n", " ")
    )


def _md_inline(value: str) -> str:
    """Escape a string for safe use inline in prose / link text.

    Free-form fields like description and gist filenames can contain
    characters that would prematurely terminate the surrounding markdown
    construct (e.g. `]` collapsing a link).
    """
    if not value:
        return ""
    return (
        value.replace("\\", "\\\\")
             .replace("\r", " ")
             .replace("\n", " ")
             .replace("`", "\\`")
             .replace("[", "\\[")
             .replace("]", "\\]")
             .replace("<", "\\<")
             .replace(">", "\\>")
    )


def _format_reasons(reasons: list[Reason]) -> str:
    return ", ".join(r.value for r in reasons) or "_(none)_"


def _format_secrets_table(scan: ScanResult) -> str:
    if not scan.secrets:
        return "_No secrets detected._"
    lines = [
        "| Detector | File | Line | Commit | Redacted |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in scan.secrets:
        commit_disp = _md_cell(s.commit) if s.commit else "—"
        if s.link and s.commit:
            link = f"[{commit_disp}]({s.link})"
        else:
            link = commit_disp
        lines.append(
            f"| {_md_cell(s.detector)} | `{_md_cell(s.file)}` | "
            f"{_md_cell(s.line)} | {link} | `{_md_cell(s.redacted)}` |"
        )
    return "\n".join(lines)


def _format_scan_status(scan: ScanResult | None) -> list[str]:
    if scan is None:
        return ["_Trufflehog did not run._"]
    if scan.timed_out:
        out = [f"_Trufflehog timed out. Partial results: {len(scan.secrets)} secret(s)._"]
        if scan.secrets:
            out.append("")
            out.append(_format_secrets_table(scan))
        return out
    if scan.error:
        return [f"_Trufflehog error: {scan.error}_"]
    return [_format_secrets_table(scan)]


def _render_repo_section(cr: ClassifiedRepo, scan: ScanResult | None) -> list[str]:
    r = cr.repo
    out: list[str] = []
    out.append(f"### [{_md_inline(r.full_name)}]({r.html_url})")
    out.append("")
    out.append(f"- **Owner:** `{_md_inline(r.owner)}`")
    out.append(f"- **Why flagged:** {_format_reasons(cr.reasons)}")
    description = _md_inline(r.description) if r.description else "_(none)_"
    out.append(f"- **Description:** {description}")
    visibility = r.visibility
    if r.fork:
        visibility += " (fork)"
    if r.archived:
        visibility += " (archived)"
    out.append(f"- **Visibility:** {_md_inline(visibility)}")
    out.append(
        f"- **Stars:** {r.stargazers_count} | **Default branch:** "
        f"`{_md_inline(r.default_branch) or '—'}` | "
        f"**Last push:** {_md_inline(r.pushed_at) or '—'}"
    )
    if r.topics:
        out.append(
            f"- **Topics:** {', '.join(_md_inline(t) for t in r.topics)}"
        )
    out.append("")
    out.extend(_format_scan_status(scan))
    out.append("")
    return out


def _render_gist_section(cg: ClassifiedGist, scan: ScanResult | None) -> list[str]:
    g = cg.gist
    out: list[str] = []
    out.append(f"### [gist {_md_inline(g.id)}]({g.html_url})")
    out.append("")
    out.append(f"- **Owner:** `{_md_inline(g.owner)}`")
    out.append(f"- **Why flagged:** {_format_reasons(cg.reasons)}")
    description = _md_inline(g.description) if g.description else "_(none)_"
    out.append(f"- **Description:** {description}")
    if g.filenames:
        out.append(
            f"- **Files:** {', '.join(f'`{_md_inline(f)}`' for f in g.filenames)}"
        )
    out.append(f"- **Updated:** {_md_inline(g.updated_at) or '—'}")
    out.append("")
    out.extend(_format_scan_status(scan))
    out.append("")
    return out


def render(report: RunReport) -> str:
    ts = report.started_at.strftime("%Y-%m-%d %H:%M UTC")

    repos_with = [
        c for c in report.flagged_repos
        if report.repo_scans.get(c.repo.full_name)
        and report.repo_scans[c.repo.full_name].secrets
    ]
    repos_clean = [c for c in report.flagged_repos if c not in repos_with]
    gists_with = [
        c for c in report.flagged_gists
        if report.gist_scans.get(c.gist.id)
        and report.gist_scans[c.gist.id].secrets
    ]
    gists_clean = [c for c in report.flagged_gists if c not in gists_with]

    lines: list[str] = []
    lines.append("# Tuvok Daily Report")
    lines.append("")
    lines.append(f"- **Run:** {ts}")
    lines.append(f"- **Org:** {report.org}")
    lines.append(f"- **Keywords:** {', '.join(report.keywords)}")
    lines.append(f"- **Users scanned:** {len(report.users_scanned)}")
    lines.append(f"- **Repos flagged:** {len(report.flagged_repos)}")
    lines.append(f"- **Gists flagged:** {len(report.flagged_gists)}")
    lines.append(f"- **Flagged repos with secrets:** {report.repos_with_secrets}")
    lines.append(f"- **Flagged gists with secrets:** {report.gists_with_secrets}")
    lines.append(f"- **Total secret findings:** {report.total_secrets}")
    lines.append("")

    if repos_with:
        lines.append("## Repositories with detected secrets")
        lines.append("")
        for cr in repos_with:
            lines.extend(
                _render_repo_section(cr, report.repo_scans.get(cr.repo.full_name))
            )
    if gists_with:
        lines.append("## Gists with detected secrets")
        lines.append("")
        for cg in gists_with:
            lines.extend(
                _render_gist_section(cg, report.gist_scans.get(cg.gist.id))
            )
    if repos_clean:
        lines.append("## Flagged repositories without detected secrets")
        lines.append("")
        for cr in repos_clean:
            lines.extend(
                _render_repo_section(cr, report.repo_scans.get(cr.repo.full_name))
            )
    if gists_clean:
        lines.append("## Flagged gists without detected secrets")
        lines.append("")
        for cg in gists_clean:
            lines.extend(
                _render_gist_section(cg, report.gist_scans.get(cg.gist.id))
            )

    if not report.flagged_repos and not report.flagged_gists:
        lines.append("_No keyword-related public repos or gists identified this run._")
        lines.append("")

    return "\n".join(lines) + "\n"


def report_filename(started_at: datetime) -> str:
    return started_at.strftime("%Y-%m-%d-%H-%M-report.md")


def save(report: RunReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / report_filename(report.started_at)
    path.write_text(render(report))
    log.info("Report written to %s", path)
    return path


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
