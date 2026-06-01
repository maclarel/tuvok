# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security findings.

Submit the report through GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository. From the repo, go to **Security → Report a vulnerability** to open a private advisory only the maintainers can see.

Include in your report:
- A short description of the issue
- A reproduction (config, command, expected vs. observed behavior)
- The affected version / commit
- The impact, in your own words

## Scope

In scope:
- Secrets leakage through tuvok's outputs (e.g. redaction bypass in the markdown report)
- Command, argv, or environment injection via fields returned by the GitHub API
- Path traversal or file writes outside the configured output directory
- Token exposure (process arguments, logs, error messages, generated reports)
- Authentication or authorization bypass against an org PAT

Out of scope (report upstream instead):
- Missed detections in trufflehog — report to [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog)
- GitHub API behavior or rate limiting

## Response

Maintainers will acknowledge a valid report within a reasonable window and work with you on a fix and coordinated disclosure. Tuvok is a community project — please be patient on response times, and we will be in turn.
