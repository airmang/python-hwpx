# S-006 Split-Run Form Fill Verified Implementation Plan

> **For agentic workers (Codex):** REQUIRED SUB-SKILL: Use `superpowers:writing-plans` to revise this plan and `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement it task-by-task. Work the checkboxes in order. Do not implement from memory; each design decision must trace to local code, verified reference behavior, or an explicit test.

**Goal:** Add a clean-room, test-first split-run HWPX form-fill path in `python-hwpx` that detects placeholders split across `<hp:t>` and `<hp:run>` boundaries, warns when the placeholder spans multiple `charPrIDRef` values, and fills the placeholder while preserving run structure and first-run character style.

**Wily Stage Context:**
- Project: `hwpx`
- Display key: `S-006`
- Internal stage id: `STG-6be1f34cf574`
- Title: `Phase 1 — 실전 양식 처리 깊이 (split-run 양식 채움 + 서식 쏠림 경고)`
- Current server status at plan time: `draft`
- Claim status: blocked until the Stage is approved/ready
- Dependency: `STG-7df87e5e98c1` / display key `S-005`, already `done`
- Repo scope: `python-hwpx`

**Acceptance From Wily Server:**
- `find_split_placeholders` detects placeholders split across multiple runs and collects `charPrIDRef` values.
- `heterogeneous_warnings` reports placeholders that cross different `charPrIDRef` values.
- `fill_section_bytes` replaces split-run placeholders by injecting the value into the first touched run and clearing only the placeholder fragments from later touched runs.
- The first touched run's `charPrIDRef` is preserved.
- `uv run --extra dev pytest -q` passes.

**Non-Goals:**
- No code copy or line-by-line translation from reference repositories.
- No whole-document form engine in this Stage.
- No MCP or `hwpx-skill` wrapper in this Stage unless a later Stage explicitly requests it.
- No claim that visual layout is submission-ready from XML tests alone.
- No paragraph-crossing placeholder support in the first implementation.
- No table label fill, empty-cell style inference, image handling, or HWP5 write support in this Stage.

**Verified Reference Evidence:**
- `chrisryugj/kordoc`
  - Checked commit: `31ec46a0a55cfa92d37b4a5ad34f4a5de9db4133`
  - License file: `LICENSE` is MIT.
  - Relevant files verified:
    - `src/form/filler-hwpx.ts`
    - `tests/filler-hwpx.test.ts`
    - `README.md`
  - Verified ideas only:
    - HWPX direct XML fill can preserve original formatting by editing text nodes rather than rebuilding document structure.
    - Empty self-closing `<hp:run>` can appear after HWP to HWPX conversion and may need a new `<hp:t>` child when inserting a non-empty value.
    - Paragraph-level `<hp:t>` nodes can be collected with global offsets and a text range can be replaced across multiple text nodes.
    - For cell text replacement, the first run receives the new value and later runs are cleared to avoid duplicate text while preserving structure.
- `sakada3/hwp-ops`
  - Checked commit: `8a5fd2ba82a4b6007d9c4eecf71a0b72e50a7a1e`
  - License file: `LICENSE` is Apache-2.0.
  - Relevant files verified:
    - `scripts/hwpx_scan.py`
    - `scripts/hwpx_fill.py`
    - `reference/hwpx-anatomy.md`
    - `reference/pitfalls.md`
    - `README.md`
  - Verified ideas only:
    - Placeholder scan concatenates paragraph text across runs, maps match ranges back to run/text-node spans, and reports `charPrIDRef` heterogeneity.
    - Split-run fill should not merge or delete runs; it should edit only the relevant text fragments.
    - A placeholder crossing different `charPrIDRef` values is a style-skew risk and should be surfaced as a warning.
    - A layout-preserving fill path should clear stale layout cache such as `hp:linesegarray` for touched paragraphs.

**Clean-Room Boundary:**
- Keep the reference repos as behavior evidence only.
- Write all Python code from local tests and local HWPX model knowledge.
- Use local naming that fits `python-hwpx`; do not mirror TypeScript class/function layout from `kordoc`.
- Do not import, vendor, translate, or mechanically port reference source.
- Add NOTICE attribution only if this Stage ships code based on the verified ideas.
- If a behavior is not covered by the verified files above or a new local test, stop and update this plan before implementing it.

**Local Code Facts To Respect:**
- `tests/template_automation/fixtures/split-run-placeholder/` already contains a split-run fixture.
- `tests/template_automation/fixtures/split-run-placeholder/scenario.json` intentionally proves current exact token replacement does not silently replace split-run placeholders.
- `src/hwpx/oxml/document.py` already has paragraph/run text helpers and a `HwpxOxmlParagraph.text` setter that preserves first-run style, but that setter rewrites paragraph text too broadly for this Stage's fragment-level placeholder fill.
- `src/hwpx/oxml/document.py` has run-level `replace_text` for text inside a run; it does not intentionally fill placeholders split across multiple runs.
- `src/hwpx/tools/__init__.py` exports tool helpers; `form_fill.py` can start as top-level `hwpx.form_fill` because the Wily acceptance names that module.

---

## Task 0: Stage Readiness And Claim

**Files:** none

- [ ] **Step 1: Confirm server identity**

Fetch the Stage from Wily Server:

```bash
# via Wily MCP, not local files
get_stage(project_id="hwpx", stage_id="STG-6be1f34cf574")
```

Expected:
- `display_key == "S-006"`
- `status` is `ready` before claiming
- `plan_status == "needs_plan"` before recording planned phases

- [ ] **Step 2: Claim with fresh observer evidence**

Run observer one-shot first, then claim `STG-6be1f34cf574` with checkout `CO-python-hwpx-main`.

Expected:
- Claim succeeds only after the Stage is ready.
- If the server returns `invalid_state`, stop. Do not implement under an unclaimed draft Stage.

- [ ] **Step 3: Record Wily phases**

After claim, call `plan_stage` with these phases:

1. `Reference verification and RED contract`
2. `Split-run scanner`
3. `charPrIDRef heterogeneity warning`
4. `Fragment-preserving fill`
5. `Fixture integration, NOTICE, and full verification`

---

## Task 1: Reference Verification And RED Contract

**Files:**
- Create: `tests/test_form_fill_split_run.py`
- Optional read-only: `tests/template_automation/fixtures/split-run-placeholder/package/Contents/section0.xml`
- Optional read-only: `tests/template_automation/fixtures/split-run-placeholder/scenario.json`

- [ ] **Step 1: Capture verified reference metadata in the test file header**

Add a short comment block with repository names, commit SHAs, licenses, and "ideas only, no code copied".

Do not paste reference source bodies.

- [ ] **Step 2: Add minimal XML fixtures in tests**

Create small in-test XML snippets for:
- Same-style split placeholder: `{{name}}` split across three runs with `charPrIDRef="3"`.
- Mixed-style split placeholder: `{{name}}` split across two runs with `charPrIDRef="3"` and `charPrIDRef="7"`.
- Prefix/suffix preservation: `이름: {{name}} 님`.
- Single-run placeholder as a control case.
- Paragraph with two placeholders.

- [ ] **Step 3: Add RED scanner test**

Write:

```python
from hwpx.form_fill import find_split_placeholders


def test_finds_placeholder_split_across_runs() -> None:
    found = find_split_placeholders(SAME_STYLE_SECTION)
    target = _only(found)
    assert target.key == "{{name}}"
    assert target.split is True
    assert target.paragraph_index == 0
    assert target.charprid_refs == ("3",)
    assert len(target.fragments) == 3
```

Expected before implementation:

```bash
uv run --extra dev pytest tests/test_form_fill_split_run.py::test_finds_placeholder_split_across_runs -v
```

Fails with `ModuleNotFoundError` or missing symbol.

- [ ] **Step 4: Add RED current-regression guard using existing fixture**

Keep the existing template automation scenario intact. Add a focused assertion only if needed:

```bash
uv run --extra dev pytest tests/template_automation/test_regression_suite.py -k split-run-placeholder -v
```

Expected: current exact token replacement reports zero replacements. This must remain true after the new explicit split-run API lands.

---

## Task 2: Split-Run Scanner

**Files:**
- Create: `src/hwpx/form_fill.py`
- Modify: `tests/test_form_fill_split_run.py`

- [ ] **Step 1: Define result dataclasses**

Use frozen dataclasses:

```python
@dataclass(frozen=True)
class TextFragment:
    paragraph_index: int
    run_index: int
    text_index: int
    char_pr_id_ref: str | None
    local_start: int
    local_end: int


@dataclass(frozen=True)
class Placeholder:
    key: str
    paragraph_index: int
    start: int
    end: int
    split: bool
    charprid_refs: tuple[str, ...]
    fragments: tuple[TextFragment, ...]
```

Keep the public name `charprid_refs` to match Stage wording, but use `char_pr_id_ref` inside fragments for Python readability.

- [ ] **Step 2: Parse section bytes safely**

Implement `find_split_placeholders(section_bytes: bytes) -> list[Placeholder]`.

Rules:
- Use `lxml.etree.fromstring`.
- Match elements by local name so both real OWPML namespaces and compact test namespaces work.
- Traverse each paragraph independently.
- Only collect `<hp:t>` descendants that belong to `<hp:run>` descendants.
- Preserve text-node order.
- Ignore paragraphs with no text nodes.
- Raise a clear `ValueError` for invalid XML bytes.

- [ ] **Step 3: Match placeholder keys**

Use a conservative placeholder regex:

```python
PLACEHOLDER_RE = re.compile(r"\{\{[A-Za-z0-9_.:-]+\}\}")
```

Rationale:
- This Stage is for template keys, not arbitrary brace content.
- Computed fields and broad `{...}` detection belong to other quality/profile stages.

- [ ] **Step 4: Map logical offsets to fragments**

For each paragraph:
- Concatenate all collected `<hp:t>` text.
- Build `(global_start, global_end, run_index, text_index, charPrIDRef, element)` spans.
- For each regex match, collect intersecting spans.
- Record local fragment bounds so later fill can cut only the matched part.

- [ ] **Step 5: Verify scanner tests**

Run:

```bash
uv run --extra dev pytest tests/test_form_fill_split_run.py::test_finds_placeholder_split_across_runs -v
```

Expected: pass.

Add tests for:
- Single-run placeholder has `split is False`.
- Two placeholders in one paragraph are both detected.
- Placeholder with prefix/suffix records correct `start` and `end`.
- Invalid XML raises `ValueError`.

---

## Task 3: charPrIDRef Heterogeneity Warning

**Files:**
- Modify: `src/hwpx/form_fill.py`
- Modify: `tests/test_form_fill_split_run.py`

- [ ] **Step 1: Add RED warning test**

```python
from hwpx.form_fill import find_split_placeholders, heterogeneous_warnings


def test_warns_when_placeholder_crosses_multiple_charprid_refs() -> None:
    placeholders = find_split_placeholders(MIXED_STYLE_SECTION)
    warnings = heterogeneous_warnings(placeholders)
    assert len(warnings) == 1
    assert warnings[0].key == "{{name}}"
    assert warnings[0].charprid_refs == ("3", "7")
```

- [ ] **Step 2: Add warning dataclass**

```python
@dataclass(frozen=True)
class HeterogeneousWarning:
    key: str
    paragraph_index: int
    charprid_refs: tuple[str, ...]
    message: str
```

- [ ] **Step 3: Implement warning function**

Implement:

```python
def heterogeneous_warnings(placeholders: Sequence[Placeholder]) -> list[HeterogeneousWarning]:
    ...
```

Rules:
- Warn only when `len(charprid_refs) > 1`.
- Preserve first-seen `charPrIDRef` order.
- Message should be actionable and Korean-friendly, but tests should assert structured fields first.

- [ ] **Step 4: Verify warning tests**

Run:

```bash
uv run --extra dev pytest tests/test_form_fill_split_run.py -v
```

Expected: pass.

---

## Task 4: Fragment-Preserving Fill

**Files:**
- Modify: `src/hwpx/form_fill.py`
- Modify: `tests/test_form_fill_split_run.py`

- [ ] **Step 1: Add RED fill result tests**

Add tests for:
- Split placeholder is replaced.
- Prefix and suffix around the placeholder remain.
- First touched run still has its original `charPrIDRef`.
- Later touched runs remain present but their placeholder fragments are removed.
- Unmapped placeholder remains unchanged.
- Count reports replacements made.
- Multiple placeholders in one paragraph fill from right to left without offset drift.

Primary test shape:

```python
from hwpx.form_fill import fill_section_bytes


def test_fill_replaces_split_placeholder_preserving_first_run_ref() -> None:
    out, report = fill_section_bytes(
        PREFIX_SUFFIX_SECTION,
        {"{{name}}": "홍길동"},
    )
    assert report.replacements == 1
    assert b"{{name}}" not in out
    assert "이름: 홍길동 님" in _section_text(out)
    assert _first_run_charpr(out) == "3"
```

- [ ] **Step 2: Define fill report**

```python
@dataclass(frozen=True)
class FillReport:
    replacements: int
    placeholders_found: int
    missing_keys: tuple[str, ...]
    warnings: tuple[HeterogeneousWarning, ...]
```

Return:

```python
def fill_section_bytes(
    section_bytes: bytes,
    values: Mapping[str, str],
) -> tuple[bytes, FillReport]:
    ...
```

- [ ] **Step 3: Implement right-to-left replacement**

For each paragraph:
- Detect placeholders from current XML state.
- Process matches in descending `(paragraph_index, start)` order.
- Skip placeholders not present in `values`, recording them in `missing_keys`.
- For a matched placeholder:
  - Insert replacement into the first touched `<hp:t>` at the local start.
  - Remove only matched placeholder fragments from every touched `<hp:t>`.
  - Keep `<hp:run>` elements and their attributes.
  - Do not clear unrelated text or sibling inline objects.

- [ ] **Step 4: Remove touched layout cache**

If a paragraph is modified, remove descendant `hp:linesegarray` elements within that paragraph only.

Rationale:
- `hwp-ops` verified this as a layout-preservation guard.
- `python-hwpx` already has other code paths that clear paragraph layout cache.

- [ ] **Step 5: Preserve XML namespaces and serialization**

Rules:
- Serialize with `encoding="UTF-8"`.
- Do not rename namespaces intentionally.
- Tests should parse XML rather than assert exact byte equality, except for checking absence/presence of key text.

- [ ] **Step 6: Verify focused fill tests**

Run:

```bash
uv run --extra dev pytest tests/test_form_fill_split_run.py -v
```

Expected: pass.

---

## Task 5: Fixture Integration And Public Surface

**Files:**
- Modify: `src/hwpx/__init__.py` if public export is appropriate
- Modify: `src/hwpx/form_fill.py`
- Modify: `tests/test_form_fill_split_run.py`
- Read-only guard: `tests/template_automation/test_regression_suite.py`

- [ ] **Step 1: Add fixture-backed smoke test**

Pack the existing `split-run-placeholder` fixture and read `Contents/section0.xml`.

Test:
- `find_split_placeholders` detects the split placeholder in the fixture section.
- `fill_section_bytes` can replace it in the section bytes.
- The existing automation `token_replace` scenario still reports zero replacements.

- [ ] **Step 2: Decide export boundary**

If users should import this directly:

```python
from hwpx.form_fill import fill_section_bytes
```

No `hwpx.tools` export is required unless a CLI/tool wrapper is added.

If adding top-level exports in `src/hwpx/__init__.py`, keep them minimal:
- `find_split_placeholders`
- `heterogeneous_warnings`
- `fill_section_bytes`

- [ ] **Step 3: Add NOTICE attribution**

If implementation ships, add a short NOTICE entry:

```text
- chrisryugj/kordoc (MIT): HWPX form-fill behavior ideas for preserving text-node/run structure and handling empty/self-closing runs. Clean-room reimplementation; no source code copied.
- sakada3/hwp-ops (Apache-2.0): split-run placeholder scan/fill behavior ideas, charPrIDRef heterogeneity warning, and touched-paragraph layout-cache invalidation. Clean-room reimplementation; no source code copied.
```

- [ ] **Step 4: Run focused regression**

```bash
uv run --extra dev pytest tests/test_form_fill_split_run.py tests/template_automation/test_regression_suite.py -k "split_run or split-run-placeholder" -v
```

Expected: pass.

---

## Task 6: Full Verification And Wily Evidence

**Files:**
- Modify: Wily Stage note only through Wily MCP

- [ ] **Step 1: Run full suite**

```bash
uv run --extra dev pytest -q
```

Expected: pass.

- [ ] **Step 2: Run diff check**

```bash
git diff --check
```

Expected: pass.

- [ ] **Step 3: Record Wily phase completions**

For each Wily phase, record:
- Files changed
- Focused tests
- Full verification result
- Reference evidence used
- Remaining risks

- [ ] **Step 4: Complete Stage only after claim session is valid**

Do not complete from an old or stale checkout snapshot.

Completion evidence must include:
- `tests/test_form_fill_split_run.py` focused result
- `tests/template_automation/test_regression_suite.py -k split-run-placeholder` result
- `uv run --extra dev pytest -q` result
- `git diff --check` result
- Changed files summary
- Clean-room attribution summary

---

## Remaining Design Risks

- The first implementation handles paragraph-local placeholders only. Paragraph-crossing placeholders are intentionally unsupported and should be reported as not found.
- Replacing inside `<hp:t>` with mixed inline children may need a follow-up if local fixtures expose it. This Stage should preserve unrelated inline nodes but does not need to solve all rich inline edit cases unless tests prove the need.
- Namespace serialization may change prefix names. Avoid byte-for-byte assertions for XML prefixes.
- Visual rendering remains unverified. Passing XML/package tests does not prove layout is visually submission-ready.

