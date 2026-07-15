# Security policy

## Supported versions

Security fixes are applied to the latest published release. Older versions may
be asked to upgrade before a fix is provided.

## Reporting a vulnerability

Do not disclose vulnerabilities in a public issue, discussion, or pull request.
Use GitHub's private vulnerability reporting form:

<https://github.com/airmang/python-hwpx/security/advisories/new>

Include the affected version, a minimal reproducer, impact, and any suggested
mitigation. We aim to acknowledge a report within 3 business days and provide a
status update within 10 business days. Timelines for a fix depend on severity
and coordinated-disclosure needs.

If the private form is unavailable, open a public issue containing no sensitive
details and ask the maintainer for a private reporting channel.

## Release security

Release workflows use PyPI trusted publishing. GitHub Actions are pinned to full
commit SHAs, dependencies are monitored by Dependabot, pull requests receive
dependency review, and CodeQL scans Python sources. Release SBOMs use CycloneDX
JSON and are attached to GitHub releases.
