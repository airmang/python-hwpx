# Exam Typesetting — Implementation Plan 3: MCP exposure (조판기/keep-together/split-verify를 설치 surface로)

Stage `STG-a47dede4fa57` (S-056) · Wily phase `PH-7adb7e648d06` · spans **two repos**:
`python-hwpx` (1 small touch) + `hwpx-mcp-server` (the surface). Branch
`feat/s056-exam-typesetting` in both. **Push 금지** (owner pushes).

## Goal

Expose Plan 2's `hwpx.exam` composer over the installed MCP surface so an LLM driving
the plugin by prompt alone can re-typeset an authored exam into a school form, verify
문항-split honestly, and toggle keep-together — the foundation Plan 4's skill routes to.

**Owner decision (2026-06-26): full, spec-complete surface (all three):**
1. `compose_exam` — the leap tool; wraps `compose_exam_into_form`. **NEW** `@mcp.tool()`.
2. `verify_question_splits` — spec item 3(b); render + `measure_question_splits`. **NEW**.
3. keep-together params on `set_paragraph_format` — spec item 3(a); `keep_with_next` /
   `keep_lines` / `page_break_before`. Extends the existing tool **+** the high-level
   `HwpxDocument.set_paragraph_format` (engine `ensure_paragraph_format(break_setting=)`
   already exists from Plan 1).

## Constitution Check (`.specify/memory/constitution.md` v1.x)

- **I Spec Kit is product truth**: spec `specs/003-exam-typesetting/spec.md` §"Engine / MCP
  work items" item 3 is the authority; this plan is its task graph. ✅
- **III Evidence before completion**: every task ends with a run + commit; phase completes
  only with full-suite green in both repos + a final review. ✅
- **IV/V Oracle truth, no-silent-true**: the MCP tools **inherit the composer's honest
  degradation** — no oracle → `renderChecked=false`; curve-export (`n_blocks==0`) →
  `splits=null` + `needsReview=true`. The MCP layer MUST NOT manufacture a green. ✅
- **VI Fail-closed**: parse/profile errors and bad inputs (md XOR path) return an honest
  error dict, never a silently-wrong document; writes go through `_save_doc_verification`
  (openSafety). ✅
- **VII Lossless-first**: keep-together appends a new paraPr (Plan 1 behaviour); compose
  preserves 관리박스 + footer (Plan 2 behaviour). No new mutation paths. ✅
- **Scope note (II / scope discipline)**: spec 3(a) "param on `set_paragraph_format`" lives
  in `src/hwpx/document.py:1809`, which is **not** in the Wily stage's declared `scope[]`
  (that lists `_document_impl.py`/`authoring.py`). The touch is small, directly serves the
  stage's defining "keep-together" requirement, and was **owner-approved 2026-06-26** with
  the surface decision. Recorded here + in the stage note.

## Global constraints

- TDD per task: **failing test → run (red) → minimal impl → run (green) → full suite → commit.**
- `python-hwpx` suite baseline: **1047 passed / 36 skipped** (HEAD `8fd10d4`).
- `hwpx-mcp-server` is on `main` (`f1af6a3`, v2.6.0). **Create `feat/s056-exam-typesetting`**
  there before Task 2; commit locally only.
- MCP↔engine wiring: `hwpx-mcp-server/pyproject.toml` resolves `python-hwpx` as an
  **editable sibling path** (`[tool.uv.sources] python-hwpx = {path="../python-hwpx",
  editable=true}`), so `hwpx.exam` (feature-branch only, unreleased) imports automatically
  in local dev. The published wheel pins `python-hwpx>=2.14.0`; **`hwpx.exam` is not in any
  released wheel yet** → a python-hwpx release carrying `hwpx.exam` + an MCP pin bump is a
  **Plan 4 / release** concern, flagged not done here.
- New tools follow the **M2 `place_seal` template** (`server.py:3674`): plain `@mcp.tool()`
  returning an honest `dict`; `resolve_path` → `_revision_guard` → work →
  `_save_doc_verification` / `_with_save_verification`; oracle-absent degrades to
  `renderChecked=false` with a `note`.

## Verified consumed signatures (file:line, read 2026-06-26)

```python
# python-hwpx — composer (Plan 2, feat/s056-exam-typesetting)
exam/compose.py:155  compose_exam_into_form(form_path, exam_md, out_path, *,
                         oracle=None, max_rounds=2, role_style_names=None) -> ComposeResult
exam/compose.py:137  ComposeResult(out_path, render_checked, splits|None, overflow|None,
                         placeholders_ok, rounds, needs_review, notes: tuple[str,...])
exam/measure.py:117  measure_question_splits(pdf_path, *, marker_re=DEFAULT_QUESTION_MARKER,
                         valid_ids: set[str]|None=None) -> SplitReport
exam/measure.py:106  SplitReport(n_splits, n_blocks, n_glyphs, kinds: dict, split_ids: tuple)
exam/parser.py:60    parse_exam_markdown(md, *, title="") -> ExamDoc        # raises ExamParseError
exam/parser.py:23    ExamParseError(line_no, text, reason)                 # fail-loud
exam/profile.py:58   profile_form(doc, *, role_style_names=None) -> FormProfile  # raises FormProfileError
exam/profile.py:27   FormProfileError(ValueError)
visual/oracle.py:326 resolve_oracle(*, powershell=None, timeout=300.0, dpi=150,
                         osascript="osascript") -> RenderBackend  # COM→Mac→Null
visual/oracle.py:312 NullOracle()  # available()->False (deterministic verify=off)

# python-hwpx — keep-together extension point (3a)
document.py:1809        HwpxDocument.set_paragraph_format(*, paragraph_index=None,
                          paragraph_indexes=None, alignment=None, line_spacing_percent=None,
                          indent_*_mm=..., spacing_*_pt=..., outline_level=None,
                          bottom_border=False, ...) -> dict        # EXTEND: + keep_* params
document.py:1893        header.ensure_paragraph_format(base_para_pr_id=..., ...)  # call site to forward break_setting
_document_impl.py:5282  ensure_paragraph_format(..., break_setting: Mapping[str,bool]|None=None) -> str  # Plan 1, ready
_document_impl.py:5332  if break_setting is not None: self._apply_paragraph_break_setting(...)

# hwpx-mcp-server — surface + helpers (main, v2.6.0)
server.py:3306   @mcp.tool() set_paragraph_format(filename, paragraph_index=None,
                    paragraph_indexes=None, alignment=None, ..., outline_level=None,
                    dry_run=False, expected_revision=None) -> dict   # EXTEND: + keep_* params
server.py:3327   doc.set_paragraph_format(...)                       # forward keep_* here
server.py:3674   @mcp.tool() place_seal(...) -> dict                 # honest-report template
tools.py:364     SetParagraphFormatInput(DocumentLocatorInput)       # EXTEND: + keepWithNext/keepLines/pageBreakBefore
helpers (server.py): resolve_path, open_doc, _revision_guard, _save_doc_verification,
                     _with_save_verification, _with_dry_run_verification
```

## File structure

```
python-hwpx/
  src/hwpx/document.py                       # T1: + keep_with_next/keep_lines/page_break_before
  tests/test_set_paragraph_format_keep.py    # T1 (new)
hwpx-mcp-server/
  src/hwpx_mcp_server/server.py              # T2 set_paragraph_format keep params; T3 verify_question_splits; T4 compose_exam
  src/hwpx_mcp_server/tools.py               # T2 SetParagraphFormatInput keep params (+ any guide text)
  tests/test_exam_mcp.py                     # T2/T3/T4 (new)
  tests/fixtures/exam/                        # T4: form fixture + sample md (copy from python-hwpx if absent)
  CHANGELOG.md                               # T5
  pyproject.toml                             # T5 version 2.6.0 -> 2.7.0
```

## Scope decisions (read before executing)

- **`compose_exam` md input**: accept `exam_md` (inline string) **XOR** `exam_md_filename`
  (path read server-side); exactly one required → else honest error. Primary path is the
  inline string (the skill authors md in context); the filename path is for large bodies.
- **`verify` toggle on `compose_exam`**: `verify=True` (default) → `oracle=None` →
  `resolve_oracle()` (degrades honestly if absent). `verify=False` → pass `NullOracle()`
  → deterministic `renderChecked=false` + `needsReview=true` (compose-only, no Hancom).
- **`verify_question_splits` scoping**: optional `valid_question_numbers: list[str]`
  → `valid_ids=set(...)` so the form's chrome (e.g. a "2026." year) never opens a spurious
  block; `n_blocks==0` → curve-export → `splits=null` + `needsReview` (no silent 0).
- **No oracle in CI**: oracle-touching test paths are gated `HWPX_MAC_ORACLE_SMOKE=1`
  (M2 convention); the default suite exercises the **honest-degrade** paths only.
- **Output shape**: camelCase keys to match the server (`renderChecked`, `needsReview`,
  `placeholdersOk`, `outputPath`, `splits`, `overflow`, `rounds`, `notes`).

---

## Task 1 — engine: keep-together on `HwpxDocument.set_paragraph_format` (spec 3a, python-hwpx)

Forward keep-together to the Plan-1 `ensure_paragraph_format(break_setting=)`.

- [ ] **Step 1 — failing test** `tests/test_set_paragraph_format_keep.py`: open a doc with ≥1
  paragraph, call `doc.set_paragraph_format(paragraph_index=0, keep_with_next=True,
  keep_lines=True)`; assert the paragraph's new `paraPr` carries `<hh:breakSetting>` with
  `keepWithNext="1"`/`keepLines="1"`, that a **new** paraPr id was minted (existing untouched
  = lossless), and that `set_paragraph_format()` with **no** options still raises
  `ValueError` (guard still fires).
- [ ] **Step 2 — run red.**
- [ ] **Step 3 — minimal impl** in `document.py:1809`: add keyword params `keep_with_next:
  bool|None=None`, `keep_lines: bool|None=None`, `page_break_before: bool|None=None`; build
  `break_setting = {k:v for ... if not None}`; include it in the "at least one option
  required" guard (`:1861`); pass `break_setting=break_setting or None` to the
  `header.ensure_paragraph_format(...)` call (`:1893`).
- [ ] **Step 4 — run green** (new test + targeted existing paraPr tests).
- [ ] **Step 5 — full suite** (`.venv/bin/python -m pytest -q`, expect 1048+ passed), commit
  on `feat/s056-exam-typesetting`.

## Task 2 — MCP: keep-together params on `set_paragraph_format` (spec 3a, hwpx-mcp-server)

**First**: `git -C hwpx-mcp-server switch -c feat/s056-exam-typesetting`.

- [ ] **Step 1 — failing test** `tests/test_exam_mcp.py::test_set_paragraph_format_keep`: in a
  tmp workspace, write a small `.hwpx`, call the `set_paragraph_format` tool fn with
  `keep_with_next=True`; reopen via python-hwpx and assert `breakSetting/@keepWithNext == "1"`.
- [ ] **Step 2 — run red.**
- [ ] **Step 3 — minimal impl**: add `keep_with_next/keep_lines/page_break_before` params to
  `server.py:3306` and forward to `doc.set_paragraph_format(...)`; add
  `keepWithNext/keepLines/pageBreakBefore` aliased fields to `SetParagraphFormatInput`
  (`tools.py:364`). Keep the docstring's Korean register.
- [ ] **Step 4 — run green.**
- [ ] **Step 5 — full suite** (`hwpx-mcp-server/.venv/bin/python -m pytest -q`), commit.

## Task 3 — MCP: `verify_question_splits` tool (spec 3b, hwpx-mcp-server)

New `@mcp.tool()` after `check_seal_compliance` (`server.py:~3792`).

- [ ] **Step 1 — failing test**: `test_verify_question_splits_no_oracle` — with the oracle
  absent (monkeypatch `resolve_oracle()` → `NullOracle()`), the tool returns
  `{"ok": True/False, "renderChecked": False, "needsReview": True, "note": ...}` and **no**
  `splits` number (honest, no silent 0). Plus `test_verify_question_splits_curve_export`:
  monkeypatch a fake oracle returning a PDF whose `measure_question_splits` yields
  `n_blocks==0` → `renderChecked=True, splits=None, needsReview=True`.
- [ ] **Step 2 — run red.**
- [ ] **Step 3 — minimal impl**: `verify_question_splits(filename, valid_question_numbers:
  list[str]|None=None, marker_regex: str|None=None) -> dict`. Resolve path; `oracle =
  resolve_oracle()`; if `not oracle.available()` → honest `renderChecked=False` degrade.
  Else `pdf = oracle.render_pdf(path)`; `None` → honest degrade. Else `report =
  measure_question_splits(pdf, valid_ids=set(valid_question_numbers) if given else None,
  marker_re=re.compile(marker_regex) if given else DEFAULT)`. `report.n_blocks==0` →
  `splits=None`+`needsReview`+curve-export note. Else return `n_splits/kinds/split_ids/
  n_blocks` with `renderChecked=True`, `needsReview = n_splits>0`.
- [ ] **Step 4 — run green.** (Oracle render path gated `HWPX_MAC_ORACLE_SMOKE`.)
- [ ] **Step 5 — full suite**, commit.

## Task 4 — MCP: `compose_exam` tool (the leap, hwpx-mcp-server)

New `@mcp.tool()`; the primary surface Plan 4 routes to.

- [ ] **Step 1 — fixtures**: ensure `tests/fixtures/exam/` has a form `.hwpx` that profiles
  (styles 바탕글/문항자동번호넣기/1행답항/5행답항 + ≥1 anchor para) + a `sample_exam.md`.
  Copy from `python-hwpx/tests/fixtures/exam/` if not already present; add provenance note.
- [ ] **Step 2 — failing test** `test_compose_exam_verify_off`: call `compose_exam(form,
  exam_md=<sample>, output=<tmp>, verify=False)`; assert the output `.hwpx` exists,
  `renderChecked is False`, `needsReview is True`, `splits is None`, `notes` non-empty,
  and the output reopens cleanly (openSafety ok). Plus `test_compose_exam_parse_error`
  (malformed md → honest error dict, no file written) and `test_compose_exam_input_xor`
  (both/neither of `exam_md`/`exam_md_filename` → error).
- [ ] **Step 3 — run red.**
- [ ] **Step 4 — minimal impl**: `compose_exam(form_filename, output, exam_md: str|None=None,
  exam_md_filename: str|None=None, max_rounds=2, verify=True, role_style_names: dict|None=None,
  expected_revision=None) -> dict`. Validate md XOR path (read the file via `resolve_path`).
  `oracle = None if verify else NullOracle()`. Wrap `compose_exam_into_form(...)` in
  try/except for `ExamParseError`/`FormProfileError` → honest error dict. Map `ComposeResult`
  → camelCase dict + append `_save_doc_verification` evidence on the output path.
- [ ] **Step 5 — run green** (compose path is oracle-free with `verify=False`; an
  `HWPX_MAC_ORACLE_SMOKE` end-to-end on the real A_form is honest-unverified per the
  curve-export finding — assert `renderChecked=True`+`needsReview=True`, not a green).
- [ ] **Step 6 — full suite**, commit.

## Task 5 — wiring, CHANGELOG, version (hwpx-mcp-server)

- [ ] **Step 1**: register the new tools wherever the server enumerates its surface (tool
  guide / catalog / any tool-count test in `tests/`) so `compose_exam` +
  `verify_question_splits` appear; update `tools.py` guide text if it lists tools.
- [ ] **Step 2**: CHANGELOG entry (honest: composer leap tool + split-verify + keep-together;
  note the curve-export honest-unverified caveat and the unreleased python-hwpx dep).
- [ ] **Step 3**: bump `pyproject.toml` 2.6.0 → **2.7.0**.
- [ ] **Step 4**: full suite green in **both** repos; `git diff --check` both. Commit.

## Definition of done (phase `PH-7adb7e648d06`)

- Three tools live on `feat/s056-exam-typesetting` (hwpx-mcp-server) + the engine keep-param
  on the same branch (python-hwpx); both suites green; honest-degrade paths tested without an
  oracle; no silent-true anywhere.
- Final whole-branch adversarial review (code-reviewer) across both diffs → clean or
  fixed-and-re-reviewed.
- Wily phase completed by **root** with evidence (commits, suite counts, review verdict).
  Branches **unpushed**. Plan 4 (skill + leap demo) is the next phase.
