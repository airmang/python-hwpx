# hwpxskill Gap Audit

## Scope

This audit compares the practical workflow surface of `python-hwpx` against
`Canine89/hwpxskill` without assuming the competitor's README claims are
correct. The goal is to identify real workflow gaps, reuse existing engine
abstractions where possible, and separate reproduced bugs from unverified
assertions.

## Current Repository Summary

- Core engine: `src/hwpx/document.py`, `src/hwpx/opc/package.py`,
  `src/hwpx/oxml/*`
- Existing high-level tooling before this patch set:
  - schema validator: `src/hwpx/tools/validator.py`
  - text extraction engine: `src/hwpx/tools/text_extractor.py`
  - object finder / exporters: `src/hwpx/tools/object_finder.py`,
    `src/hwpx/tools/exporter.py`
- Workflow-gap code already present at audit start:
  - package validator: `src/hwpx/tools/package_validator.py`
  - page guard: `src/hwpx/tools/page_guard.py`
  - text extraction CLI: `src/hwpx/tools/text_extract_cli.py`
  - script-only unpack/pack/analyze tools under `scripts/`

## Confirmed Gaps vs hwpxskill

These were confirmed by inspecting both repos and the current local checkout.

1. Public unpack/pack workflow was incomplete.
   - `python-hwpx` had script files for unpack/pack, but no package-level CLI
     entry points such as `hwpx-unpack` / `hwpx-pack`.
   - The existing pack/unpack scripts did not record archive entry order or
     compression metadata, so they could not preserve original ZIP layout
     details when repacking.
   - Overwrite behavior was not explicit or safe.

2. Template analysis workflow was incomplete.
   - `python-hwpx` had a script for analyzing reference documents, but it was
     not promoted to a package-level CLI, did not emit a structured JSON
     summary, and had only a smoke test instead of extraction-focused tests.

3. Page-guard coverage was narrower than requested.
   - The existing page guard already acted as a structural drift detector, but
     it did not count shape/control deltas yet.
   - It also needed clearer documentation that it is a proxy/risk heuristic,
     not a rendered page counter.

4. Public docs lagged behind the implemented tooling.
   - `README.md` still documented only `hwpx-validate` in the CLI section.
   - The main usage guide did not document unpack/pack/analyze/page-guard/text
     extraction workflows.

5. Audit documentation itself was missing.
   - There was no repository-local audit note separating verified findings from
     competitor marketing claims.

## Reusable Internals Confirmed

These existing internals made it unnecessary to cargo-cult `hwpxskill`'s raw
XML-first approach.

- `src/hwpx/opc/package.py`
  - `HwpxPackage.open()`
  - `HwpxPackage.part_names()`
  - `HwpxPackage.get_part()`
  - `HwpxPackage.get_xml()`
  - `HwpxPackage.header_paths()`
  - `HwpxPackage.section_paths()`
  - `HwpxPackage.main_content`
- `src/hwpx/tools/validator.py`
  - existing schema validation path
- `src/hwpx/tools/text_extractor.py`
  - existing traversal and text extraction engine
- `src/hwpx/tools/page_guard.py`
  - existing metrics collection shape that could be extended instead of replaced

Conclusion: `python-hwpx` already had enough engine-level primitives to add the
missing workflows without switching to competitor-style "raw XML everywhere".

## Real Reproduced Bugs

### 1. Validation dirty-state mutation (historical, now fixed)

The concrete bug candidate worth treating seriously was whether validation
mutated document state. That bug was real in the earlier implementation:

- `HwpxDocument.validate()` serialized via `_to_bytes_raw()`
- `_to_bytes_raw()` called `self._root.reset_dirty()`
- Result: validating a modified document could clear the dirty state even when
  the user had not saved yet

That behavior is now covered by a regression test:

- `tests/test_gap_closure_tools.py::test_validate_preserves_dirty_state`

At the time of this audit, current `main` already contains the fix, so the bug
does not reproduce anymore on HEAD.

## Bugs I Could Not Reproduce

These claims appeared in or were implied by `hwpxskill`, but I could not
substantiate them from evidence in the current `python-hwpx` checkout.

1. "python-hwpx API has many bugs"
   - Too vague to verify.
   - Current tests and integration flows do not support that broad claim.

2. "High-level API editing necessarily destroys styles/structure"
   - Not reproduced for ordinary paragraph/table editing in the current test
     suite.
   - Existing tests already cover roundtrip and style-preserving behavior.

3. "page_guard detects actual page count changes"
   - Not supported by the competitor implementation itself.
   - Their script measures structural/text drift in `section0.xml`; it does not
     compute rendered page count.

4. Header/footer instability or TypeError complaints
   - No current reproduction from repository tests.
   - Existing `tests/test_section_headers.py` covers the public API surface.

## Competitor Claims That Remain Unverified

1. "XML-direct workflow preserves formatting almost exactly"
   - Plausible for some templates, but not benchmarked here.
   - No controlled comparison was performed in this patch.

2. "Their workflow is more reliable for all existing documents"
   - Not established.
   - The competitor repo does not provide a broad evidence matrix for this.

3. "Template replacement quality is universally better than the object API"
   - Not established.
   - Likely document-dependent.

## Exact Files / Functions Inspected

### Local repository

- `pyproject.toml`
- `README.md`
- `docs/usage.md`
- `src/hwpx/document.py`
  - `HwpxDocument.validate`
  - `HwpxDocument._to_bytes_raw`
- `src/hwpx/opc/package.py`
  - `HwpxPackage.open`
  - `HwpxPackage.part_names`
  - `HwpxPackage.get_part`
  - `HwpxPackage.get_xml`
  - `HwpxPackage.main_content`
  - `HwpxPackage.header_paths`
  - `HwpxPackage.section_paths`
  - `HwpxPackage.save`
- `src/hwpx/tools/validator.py`
  - `validate_document`
- `src/hwpx/tools/package_validator.py`
  - `validate_package`
- `src/hwpx/tools/page_guard.py`
  - `collect_metrics`
  - `compare_metrics`
- `src/hwpx/tools/text_extractor.py`
  - `TextExtractor.iter_sections`
  - `TextExtractor.iter_paragraphs`
  - `TextExtractor.extract_text`
- `src/hwpx/tools/text_extract_cli.py`
- `scripts/office/unpack.py`
- `scripts/office/pack.py`
- `scripts/analyze_template.py`
- `tests/test_gap_closure_tools.py`
- `tests/test_section_headers.py`
- `.github/workflows/release.yml`
- `.github/workflows/tests.yml`

### Competitor repository (`Canine89/hwpxskill`)

- `README.md`
- `scripts/validate.py`
- `scripts/page_guard.py`
- `scripts/text_extract.py`
- `scripts/analyze_template.py`

## Patch Direction Chosen

This first PR-equivalent patch should:

1. promote unpack/pack/analyze into package-level tooling with CLI entry points
2. keep using `python-hwpx` engine abstractions for package inspection and text
   extraction
3. extend page guard as a proxy detector, not as a fake page counter
4. keep backward compatibility with existing `HwpxDocument` APIs
5. strengthen tests and docs around the new tooling
