# Tuvok

Scans public repositories and gists owned by members of a GitHub organization for keyword matches against the org's brand/private-repo names, then runs trufflehog against the flagged set to surface leaked secrets. Output is a markdown report per run. Be mindful of API rate limiting for larger organizations.

## Prerequisites

- Python 3.11+ and `uv`
- `trufflehog` v3 on `$PATH` (`brew install trufflesecurity/trufflehog/trufflehog`)
- A fine-grained GitHub PAT scoped to the target org with:
  - **Org permissions:** Members: read
  - **Repo permissions:** Metadata: read, Contents: read

## Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Purpose |
| --- | --- |
| `TUVOK_TOKEN` | The PAT described above |
| `TUVOK_ORG` | GitHub org name (e.g. `dundermifflin`) |
| `TUVOK_KEYWORDS` | Comma-separated, case-insensitive substrings checked against repo name/description/topics/README and gist description/filenames |
| `TUVOK_MAX_PAGES` | Optional. Hard cap on paginated GitHub API calls per endpoint (default `50`, i.e. up to 5,000 items per listing). Raise only if an org outgrows the default. |

## Install

```sh
uv sync
```

## Usage

```sh
# Full pipeline: enumerate -> classify -> trufflehog -> report
uv run tuvok scan

# Scan a curated user list (skip org-member enumeration)
uv run tuvok scan --users-file path/to/users.txt

# Classification only — skip trufflehog
uv run tuvok scan --no-trufflehog

# Smoke test against the first N members
uv run tuvok scan --user-limit 5

# Dump the enumerated user/basename lists to disk for inspection or reuse
uv run tuvok scan --users-out reports/users.txt --basenames-out reports/basenames.txt
```

Other flags: `--output-dir`, `--trufflehog-timeout`, `--env`, `-v/--verbose`.

By default the enumerated user and NWO lists are held in memory only — they are not written to disk unless `--users-out` / `--basenames-out` are provided. User-list files are plain text, one login per line, `#` for comments.

## Output

Reports are written to `reports/YYYY-MM-DD-HH-MM-report.md` (UTC). If `--users-out` and/or `--basenames-out` are passed, those files are written to the paths you specify.

## Tests

```sh
uv run pytest
```

## Future planned work
- Conversion to GitHub App
- Inspection of repository README files and Gist content
