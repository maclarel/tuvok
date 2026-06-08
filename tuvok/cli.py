"""tuvok CLI.

Subcommands:
  scan  — full pipeline (enumerate -> classify -> trufflehog -> report)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tuvok.allowlist import Allowlist, empty as empty_allowlist, load as load_allowlist
from tuvok.config import Config
from tuvok.pipeline import run
from tuvok.reporting import save
from tuvok.trufflehog import DEFAULT_TIMEOUT_S

logger = logging.getLogger("tuvok")

DEFAULT_ALLOWLIST_PATH = Path("allowlist")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuvok",
        description=(
            "Scan public repos and gists owned by GitHub org members for "
            "leaked secrets in keyword-matching content."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run the full pipeline.")
    scan.add_argument("--env", default=None, help="Path to .env file")
    scan.add_argument(
        "--output-dir", default="reports",
        help="Directory for markdown reports (default: ./reports)",
    )
    scan.add_argument(
        "--trufflehog-timeout", type=int, default=DEFAULT_TIMEOUT_S,
        help=f"Per-target trufflehog timeout in seconds (default: {DEFAULT_TIMEOUT_S})",
    )
    scan.add_argument(
        "--user-limit", type=int, default=None,
        help="Cap the number of users scanned (useful for smoke tests).",
    )
    scan.add_argument(
        "--users-file", type=Path, default=None,
        help="Read user logins from a plain-text file (one per line, # for "
             "comments) instead of enumerating org members from GitHub.",
    )
    scan.add_argument(
        "--users-out", type=Path, default=None,
        help="Optional path to dump the enumerated user list (skipped when "
             "--users-file is in use).",
    )
    scan.add_argument(
        "--basenames-out", type=Path, default=None,
        help="Optional path to dump the enumerated private-repo basename list.",
    )
    scan.add_argument(
        "--no-trufflehog", action="store_true",
        help="Skip trufflehog scans; report just lists flagged targets.",
    )
    allow_group = scan.add_mutually_exclusive_group()
    allow_group.add_argument(
        "--allowlist", type=Path, default=None,
        help=f"Path to an allowlist file (default: ./{DEFAULT_ALLOWLIST_PATH} "
             "if present). Format: 'repo: owner/name' or 'gist: <id>' per "
             "line; '#' for comments. Allowlisted items are excluded from "
             "classification and trufflehog.",
    )
    allow_group.add_argument(
        "--no-allowlist", action="store_true",
        help="Disable allowlist loading even if the default file is present.",
    )
    return parser


def _resolve_allowlist(args: argparse.Namespace) -> Allowlist:
    if args.no_allowlist:
        logger.debug("Allowlist disabled by --no-allowlist")
        return empty_allowlist()
    if args.allowlist is not None:
        if not args.allowlist.is_file():
            raise FileNotFoundError(
                f"Allowlist file not found: {args.allowlist}"
            )
        return load_allowlist(args.allowlist)
    if DEFAULT_ALLOWLIST_PATH.is_file():
        logger.debug("Loading default allowlist at %s", DEFAULT_ALLOWLIST_PATH)
        return load_allowlist(DEFAULT_ALLOWLIST_PATH)
    logger.debug("No allowlist file at default path %s", DEFAULT_ALLOWLIST_PATH)
    return empty_allowlist()


def _run_scan(args: argparse.Namespace) -> int:
    config = Config.from_env(args.env)
    logger.info("Org: %s | Keywords: %s", config.org, ", ".join(config.keywords))
    if args.users_file:
        logger.info("User source: %s", args.users_file)
    allowlist = _resolve_allowlist(args)

    report = run(
        config,
        trufflehog_timeout=args.trufflehog_timeout,
        user_limit=args.user_limit,
        users_file=args.users_file,
        run_trufflehog=not args.no_trufflehog,
        users_out=args.users_out,
        basenames_out=args.basenames_out,
        allowlist=allowlist,
    )
    path = save(report, Path(args.output_dir))

    print(
        f"\nTuvok run complete: {len(report.users_scanned)} user(s) scanned | "
        f"{len(report.flagged_repos)} repo(s) flagged ({report.repos_with_secrets} w/ secrets) | "
        f"{len(report.flagged_gists)} gist(s) flagged ({report.gists_with_secrets} w/ secrets) | "
        f"{report.total_secrets} total finding(s). "
        f"Report: {path}",
        file=sys.stderr,
    )
    return 0


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.command == "scan":
        sys.exit(_run_scan(args))


if __name__ == "__main__":
    main()
