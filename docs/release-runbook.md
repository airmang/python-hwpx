# Release runbook

core (`python-hwpx`) ships on its own cadence, independent of `python-hwpx-
automation`'s three-state promotion machine (that runbook lives in the
automation repo: `docs/release-runbook.md` there). This document exists
because the 6.1.0 release train (2026-08-15) almost shipped a public version
regression: a 112-commit feature branch had forked from `main` *before* a
security patch (6.0.3, GHSA-8g8m-xpm4-wxvx) published independently on
`origin/main`, and nobody checked the remote until the tag was about to be
pushed. Had it shipped as-is, users upgrading from 6.0.3 to 6.1.0 would have
silently lost a published security fix — a worse regression than either
version alone. `git fetch` at the very start of release prep would have
caught it a day earlier, with a small merge instead of a near-miss.

## 0. Before anything else: check origin

**The first action of any release-prep task, and of any long-lived branch's
work session, is `git fetch origin` followed by a diff against the branch's
own base** — not the last step, not something the branch owner remembers to
do "eventually." A branch that forks and then lives for many commits (a
multi-cycle train, in this project's own vocabulary) is exactly the shape
that lets a fork-point drift unnoticed.

```
git fetch origin
git log --oneline <branch>..origin/main
```

If that list is non-empty:

- **Read every commit**, not just the subject lines — a security release, a
  hygiene fix, or a coordinate change can hide behind an innocuous-looking
  subject.
- **Merge, do not rebase**, onto the feature branch (this project's own
  history convention — see the 2026-08-15 merge commit `2e87583` for the
  shape: resolve conflicts preserving both sides, verify with a defect-
  resurrection proof on anything security-relevant, re-run the full pre-tag
  checklist below on the merged tree before any tag).
- If any upstream commit is itself a release (a version bump + tag), the
  version coordinate for the branch's own release must still order correctly
  above it (semver comparison, not date) and the CHANGELOG must fold the
  upstream release's own entry in, not overwrite or omit it.

This applies at **cycle start**, not only at release-prep time — the earlier
a divergence is caught, the smaller the merge.

## Pre-tag checklist

Run all of these locally before any tag is pushed. This is the exact
sequence used for the 6.1.0 and 6.1.0-merge trains; skipping any single gate
locally while it still runs in CI is how a tag gets burned (see `CHANGELOG.md`
for the preserved-failed-tag record of trains that skipped one).

1. **Confirm the checkout.** `git rev-parse --abbrev-ref HEAD` and
   `git log --oneline -1` against the train's own branch — stale sibling
   worktrees in this workspace have produced wrong conclusions before.
2. **Origin check** (§0 above), merge if needed.
3. Both ruff gates: `ruff check --select E9,F .` (repo-wide) and
   `ruff check --select E4,E7,E9,F` against the specific scoped file list in
   `.github/workflows/release.yml`.
4. `python scripts/check_typing_generics_scope.py`.
5. `mypy` and `pyright --pythonpath <venv>/bin/python` — **both**, and pyright
   needs the explicit `--pythonpath` flag or it silently checks against the
   wrong interpreter and under-reports.
6. `python scripts/check_public_hygiene.py` — catches internal codename
   leakage and private-origin markers baked into committed `.hwpx` gold
   fixtures (real-Hancom-captured fixtures can carry the capturing machine's
   own username in `opf:metadata/lastsaveby`; scrub by rewriting only that
   ZIP member's bytes, never touch the fixture's structural content).
7. The three `--check` scripts: `scripts/error_code_census.py --check`,
   `scripts/coverage_ledger.py --check`, `scripts/editor_surface_inventory.py
   --check`, plus `scripts/sync_contract_docs.py --check`.
8. `python -m hwpx.capabilities --verify`.
9. Full test suite: `pytest -q --cov=hwpx --cov-report=term-missing
   --cov-fail-under=80`.
10. Local build + install smoke: `python -m build`, `twine check dist/*`,
    then install the built wheel into a throwaway venv (`uv venv` / `uv pip
    install`) and exercise a real round trip (author something, save, reopen)
    plus an import of anything the train specifically changed — this is the
    closest local proxy to the actual PyPI artifact users will get, and has
    caught issues neither the source-tree test suite nor `twine check` alone
    would.

## Cross-repo coordinate propagation (when this train touches automation/skill)

If core's version moves, decide — do not assume — whether `python-hwpx-
automation`'s `MIN_PYTHON_HWPX` floor and `hwpx-skill`'s pinned core version
need to move too. Both questions are answered by *reading the actual gate
code*, not by the field names:

- automation's skew check (`quality.py`) is a strict `<` comparison against
  the floor — a newer core satisfies an unmoved floor without triggering
  anything.
- automation's `identity.json` also carries `releaseState.candidate` /
  `currentPublic.pythonHwpx`, which is a *separate* concept from the floor:
  it is "the currently externally-observed installable coordinate," and it
  legitimately advances on a core-only train even when automation's own
  version does not move (`scripts/release_coordinates.py`'s own docstring in
  the automation repo documents two such precedents). Whether to promote it
  is a judgment call informed by that module, not a mechanical copy.
- skill's core-version pin is derived from automation's own synced floor
  (`tests/test_tool_contract_sync.py`'s hard-link assertion in the skill
  repo), not from core's latest release directly — it only moves when
  automation's floor moves.

Whichever way the judgment lands, state the reasoning and the file:line
evidence in the commit message, not just the conclusion.
