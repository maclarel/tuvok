# Contributing

PRs are welcome. To keep review tractable, please follow the guidance below.

## What we're looking for

In rough order of preference:

1. **PRs that close an open issue.** Link the issue in the PR body so it auto-closes on merge.
2. **PRs that meaningfully extend coverage** — new classifier heuristics, additional secret-scanner integrations, gist content scanning (see `TODO.md`), better fork handling, etc.
3. **Bug fixes** with a test that reproduces the bug.
4. **Documentation fixes.**

PRs that are purely stylistic (renaming, reformatting unaffected code, churn refactors) will likely be closed unless they accompany a substantive change. The maintainers' time is the bottleneck — please direct it at things that move the project forward.

If you're considering a significant change, open an issue first so we can align on the approach before you spend time on it.

## AI disclosure

If you used an AI assistant (Claude, ChatGPT, Copilot, Cursor, etc.) for any meaningful portion of the contribution — code, tests, commit messages, or documentation — disclose it in the PR description. Include:

- Which tool(s) you used
- What scope: e.g. *"Claude drafted the markdown-escape helpers; I reviewed and rewrote the gist parser by hand."*
- Whether you reviewed and validated the generated content

This isn't a filter — AI-assisted contributions are absolutely welcome. The disclosure lets reviewers calibrate their attention.

## Quality bar

- **Tests required for new behavior.** `uv run pytest` must pass before requesting review.
- **Deterministic only.** Garak is deliberately free of runtime LLM calls. Don't introduce them.
- **Minimal dependencies.** New top-level deps need a justification in the PR; pin exact versions.
- **One logical change per PR.** Don't bundle unrelated fixes.
- **Match the existing code style.** Type hints on public functions, dataclasses for structured records, no unnecessary abstraction.

## Reporting

- **Security issues:** see [`SECURITY.md`](SECURITY.md). Use GitHub's private vulnerability reporting; do not open a public issue.
- **Bugs and feature requests:** open a GitHub issue with a clear reproduction or motivation.

Thanks for contributing!
