# GitHub Actions pinning policy

Every third-party `uses:` entry must reference a full 40-character commit SHA.
Keep the upstream release or major line in a trailing comment so Dependabot can
propose updates without making the executed revision mutable.

The public-hygiene check enforces this rule. Before accepting an update, confirm
the commit belongs to the named upstream repository and review its release notes.
Local actions referenced with `./` are exempt.
