# Template Automation Regression Suite

## Goal

This suite is for **repeatable template automation patterns that the project explicitly covers**.
It is not a claim that every arbitrary HWPX template is safe to automate.

The regression cases focus on four questions:

1. Is the automation step reproducible?
2. Does it validate after modification?
3. Does it preserve structure closely enough to avoid obvious package/layout drift?
4. Does it make silent failure visible through explicit counts or explicit errors?

## Fixture Layout

Fixtures live under `tests/template_automation/fixtures/<fixture-id>/`.

Each fixture contains:

- `scenario.json`
- `package/` - a pack-ready extracted HWPX workspace with `.hwpx-pack-metadata.json`

The suite repacks these workspaces with `hwpx-pack` behavior during tests instead of storing opaque `.hwpx` binaries directly. That keeps fixture diffs reviewable and exercises the real pack/unpack path.

To regenerate the extracted fixture packages:

```bash
PYTHONPATH=src python3 tests/template_automation/generate_fixtures.py
```

## Covered Fixture Categories

- `simple-placeholder`: single token in a normal body paragraph
- `repeated-placeholder`: one logical value repeated across multiple locations
- `split-run-placeholder`: token split across runs, where exact token replacement must not silently pretend success
- `whitespace-variant`: uneven internal spacing that only matches when normalized replacement is requested explicitly
- `table-placeholder`: token inside a table cell
- `header-footer-placeholder`: header/footer token handling
- `multi-section-placeholder`: section-targeted replacement
- `checkbox-toggle`: explicit checkbox/symbol toggles
- `extract-repack`: analyze -> extract -> patch -> repack workflow
- `nonstandard-rootfile`: engine-openable package with a nondefault rootfile path

## What The Suite Protects Against

- Exact token replacement returning success when nothing actually matched
- Split-run placeholders being mistaken for normal contiguous tokens
- Missing-token operations silently doing no work when the caller required a replacement
- Multi-location replacement losing count information
- Table/header/footer/section-specific automation accidentally being tested only against top-level body text
- Extracted workspaces that repack into invalid or engine-unopenable archives
- Simple text substitutions causing unexpected structural drift according to `hwpx-page-guard`

## What The Suite Does Not Guarantee

- Correct final rendering in Hancom Office
- True rendered page counts
- Safety for arbitrary real-world templates with unknown controls, fields, or editor-specific behaviors
- Semantic correctness of a template beyond the covered operation contract

`hwpx-page-guard` is used here exactly as documented: a **layout-drift proxy**, not a renderer.

## Operation Terms

### Exact Replacement

Literal search and replacement against explicit target surfaces such as body paragraphs, table paragraphs, headers, or footers.
This is the safest covered mode when the placeholder is actually contiguous text.

### Normalized-Text Replacement

Matches a logical phrase after removing whitespace differences.
This is broader than exact token replacement and should only be used when the caller explicitly wants whitespace tolerance.

### Token-Based Replacement

An exact replacement flow aimed at explicit placeholders such as `{{NAME}}`.
It is intentionally conservative: if the token is split across runs, the suite expects zero matches or an explicit error, not magical reconstruction.

### Structural Safety vs Semantic Template Correctness

Structural safety means the package still opens, validates, and stays within expected structure/layout-drift thresholds.
Semantic template correctness is a stronger claim about whether the template still means the right thing to a human reader. This suite does not try to prove the latter in the general case.

## Adding A New Regression From A Bug Report

1. Reduce the bug to the smallest template pattern that still reproduces the failure.
2. Add a new fixture directory under `tests/template_automation/fixtures/`.
3. Capture the package in extracted form with the smallest possible synthetic content.
4. Add one or more scenarios to `scenario.json` that describe:
   - the operation
   - the expected replacement count or expected explicit failure
   - the postconditions that should stay true
5. If you need a new automation mode in the helper layer, keep it narrow and evidence-driven.
6. Regenerate the fixture package workspace if the source builder changed.
7. Run the targeted template automation tests plus validators/type checks you touched.

If a bug only reproduces for one very specific document, do not describe the fix as “general template support” unless the operation truly generalizes.
