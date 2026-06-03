# 범정부오피스 흡수 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 범정부오피스의 공무원 보고서 편집 자동화 아이디어를 `python-hwpx` / `hwpx-mcp-server` / `hwpx-skill` 3층 스택에 clean-room 방식으로 흡수한다.

**Architecture:** Windows GUI 실행파일을 따라가지 않는다. 범정부오피스의 버튼 기능을 `document-plan`, `style preset`, `quality profile`, `pure Python utility`, `MCP thin wrapper`, `skill examples`로 재해석한다. 코어는 한컴/Windows/COM 의존 없이 HWPX XML을 직접 다루고, Excel/PDF 계열은 optional helper로 격리한다.

**Tech Stack:** Python 3.10+, lxml, pytest, existing `HwpxDocument`, `authoring.py` document-plan, FastMCP, `uv run --extra dev pytest`.

**Legal boundary:** 범정부오피스 첨부는 공개 Windows 실행파일이고 소스/재사용 라이선스가 없다. 코드는 절대 복사하지 않는다. 기능명/워크플로만 참고하고, 테스트와 구현은 독립 작성한다.

---

## Current Code Anchors

- Core document-plan: `/Users/wilycastle/Code/projects/hwpx/python-hwpx/src/hwpx/authoring.py`
  - currently supports block types: `heading`, `paragraph`, `bullets`, `table`, `page_break`, `memo`.
  - currently supports style tokens: `body`, `title`, `subtitle`, `heading`, `bullet`, `table_header`, `table_cell`.

> **Structural facts the implementer MUST account for (verified against current source):**
>
> - **Two separate preset mechanisms exist; do not confuse them.**
>   - `authoring.DocumentStylePreset` (`authoring.py:124-149`) is what the document-plan path (`create_document_from_plan`) uses. Its token set is `title/subtitle/heading/body/bullet/table_header/table_cell`. It has **no** `callout` or `section_heading`.
>   - `presets/proposal.ProposalStylePreset` (`proposal.py:67-94`) is a *separate* preset used only by `create_proposal_document`; it has `callout`/`section_heading`. Government-report work extends the **authoring** preset, so any `callout`/`gov_*` token must be created there from scratch.
> - **`DocumentStylePreset` is `name`-blind.** `ensure_tokens()` computes a fixed 7-token dict from boolean fields only; `self.name` is never read. So `DocumentStylePreset(name="government_report")` is byte-identical to the default preset until a name-aware mechanism is added (see Task 1.1).
> - **`_SUPPORTED_STYLE_TOKENS` (`authoring.py:28-30`) only drives a validation warning** in `_validate_paragraph_block` (`:621`). Adding a token there does NOT make it render.
> - **Rendering ignores unknown tokens and heading level.** `_render_block` (`:936-976`): paragraph branch uses `tokens.get(style, tokens["body"])` (silent fallback to body); heading branch always uses `tokens["heading"]` regardless of level; bullets branch always emits `f"• {item}"`.
> - **`_normalize_block` drops unmodeled fields.** bullets → `{"items": items}` only (no `style`); table → `{"caption", "columns", "rows"}` only (no `unit`/`tableProfile`); `_normalize_rows` does no whitespace normalization. New fields require normalize + validate changes, not just render changes.
> - **Quality-profile dispatch is hardcoded to `operating_plan`.** Real resolver is `_requested_profile_name()` (`:1165-1189`); `_profile_reports()` (`:1142-1162`) early-returns `{}` for any non-`operating_plan` name; the top-level gaps append (`:458-462`) also hardcodes `operating_plan`. There is no `_resolve_quality_profile()` function.

- Existing **authoring** preset to extend: `authoring.DocumentStylePreset` in `python-hwpx/src/hwpx/authoring.py`
- Separate proposal preset (reference only, do not extend for gov work): `python-hwpx/src/hwpx/presets/proposal.py`
- Existing tests: `/Users/wilycastle/Code/projects/hwpx/python-hwpx/tests/test_document_plan.py`, `test_proposal_preset.py`, `test_document_formatting.py`
- MCP document-plan tools: `/Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server/src/hwpx_mcp_server/server.py:765-938`
  - shared private helpers tools already delegate to: `_inspect_authoring_quality`, `_quality_profile_argument`, `_handoff_status`, `_next_action` (`server.py:715-762`). New gov tools must delegate to these, not call decorated `@mcp.tool()` functions directly.
- Existing visual-review loop (Phase 7 must reconcile with, not duplicate): `hwpx-skill/examples/09_visual_review_loop.md`, `hwpx-skill/scripts/visual_review.py`, prior plan `docs/superpowers/plans/2026-05-30-computeruse-visual-review-loop.md`.
- Skill examples: `/Users/wilycastle/Code/projects/hwpx/hwpx-skill/examples/`

## Non-goals

- No Windows executable execution or decompilation.
- No `.hwp` binary direct editing.
- No Excel dependency in `python-hwpx` core.
- No attempt to reproduce `1,000+` micro-buttons. Absorb high-value capability families.

---

## Phase 1 — Government Report Style Core

### Task 1.1: Add `government_report` style preset tokens

**Objective:** Add a public-sector report style preset that can produce government-report-like headings, body, bullets, callouts, and table headers.

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py`
- Test: `python-hwpx/tests/test_government_report_preset.py`

**Step 1: Write failing tests**

Create tests for:
- `create_document_from_plan(..., preset="government_report")` succeeds.
- generated document contains title, subtitle, metadata, heading, bullets, table.
- `inspect_document_authoring_quality(..., quality_profile="government_report")` returns `profiles.government_report.profile_name == "government_report"`.
- **differentiation guard:** a `government_report` document and a `standard_korean_business` document built from the same plan produce *different* run-style usage (e.g. heading run carries underline under gov, not under default) — this proves the preset is no longer name-blind.
- **default-preset regression guard:** `DocumentStylePreset(name=DEFAULT_STYLE_PRESET).ensure_tokens(doc)` returns the same token→style mapping as before (assert against `test_document_plan.py` expectations).

**Step 2: Run failure**

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run --extra dev pytest tests/test_government_report_preset.py -v
```

Expected: FAIL because profile/preset is not implemented.

**Step 3: Implement name-aware preset + token wiring (NOT a one-line alias)**

> ⚠️ `DocumentStylePreset` is currently `name`-blind (see Code Anchors). Adding a token to `_SUPPORTED_STYLE_TOKENS` only changes a validation warning — it does NOT render. This step is the load-bearing change for the whole feature; budget for it accordingly.

In `authoring.py`, do ALL of the following (each is required for the token to actually appear in output):

1. **Make the preset name-aware.** Introduce a small registry mapping preset name → `DocumentStylePreset` field overrides (or branch inside `ensure_tokens` on `self.name`). `government_report` should use stronger emphasis (e.g. `heading_bold=True, heading_underline=True`, bolder title). Default `standard_korean_business` behavior must stay byte-identical (regression-guard with `test_document_plan.py`).
2. **Extend the token dict returned by `ensure_tokens()`** to include the new semantic tokens, created from existing `ensure_run_style()` primitives only (no font metrics yet):
   - `gov_title`, `gov_subtitle`, `gov_heading_1`, `gov_heading_2`, `callout`
   - (bullet glyph variants are handled in Task 1.2 via a prefix, not a token — do not add `gov_*_bullet` tokens here unless they carry distinct run styling.)
3. **Wire `_render_block` to consume them:**
   - heading branch (`authoring.py:941-947`) currently always uses `tokens["heading"]` regardless of level — change it to select `gov_heading_1`/`gov_heading_2` by `level` when those tokens exist, with a safe fallback to `tokens["heading"]`.
   - paragraph branch already does `tokens.get(style, tokens["body"])`, so `callout`/`gov_*` styled paragraphs render once the tokens exist in the dict.
4. **Extend `_SUPPORTED_STYLE_TOKENS`** (`authoring.py:28-30`) with the new tokens so `_validate_paragraph_block` stops warning on them. (This is the validation-only step — keep it, but know it is not what makes them render.)

Keep the default-preset regression green: `DocumentStylePreset(name=DEFAULT_STYLE_PRESET)` must return the same token IDs/run styles as before this change.

**Step 4: Run tests**

```bash
uv run --extra dev pytest tests/test_government_report_preset.py tests/test_document_plan.py -v
```

**Step 5: Commit**

```bash
git add src/hwpx/authoring.py tests/test_government_report_preset.py
git commit -m "feat: add government report document preset"
```

### Task 1.2: Add semantic bullet block variants

**Objective:** Replace generic `•` bullets with Korean public-report bullet styles: `□`, `○`, `-`, `※`, `*`.

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py`
- Test: `python-hwpx/tests/test_government_report_preset.py`

**Input schema addition:**

```json
{
  "type": "bullets",
  "style": "square",
  "items": ["주요 추진 내용"]
}
```

Supported styles:
- `default` -> `• `
- `square` -> `□ `
- `circle` -> `○ `
- `dash` -> `- `
- `note` -> `※ `
- `star` -> `* `

> ⚠️ `_normalize_block` bullets branch (`authoring.py:866-870`) currently returns `{"items": items}` and **drops `style`**; `_validate_block` bullets branch (`:569-579`) never reads it. Updating only `_render_block` will read a `style` key that isn't there. The normalize/validate plumbing below is mandatory, not optional.

**Steps:**
1. Add parametrized test for all bullet styles (assert exact rendered prefix), plus a test that an unknown style falls back to `default` (or raises a validation warning — pick one and test it).
2. Verify current implementation always emits `•` and fails.
3. **Preserve `style` in `_normalize_block` bullets branch** (default `"default"`); normalize to lowercase.
4. **Accept/validate `style` in `_validate_block` bullets branch** — warn (not error) on unknown style, mirroring `_validate_paragraph_block`'s unknown-token warning.
5. Implement `_bullet_prefix(style: str) -> str` with a dict lookup and `default` fallback.
6. Update `_render_block()` bullet branch to use `_bullet_prefix(block.data.get("style", "default"))`.
7. Verify `export_text()` contains exact prefixes and that `normalize_document_plan` round-trips `style`.

**Command:**

```bash
uv run --extra dev pytest tests/test_government_report_preset.py::test_government_bullet_styles -v
```

### Task 1.3: Add government-report quality profile

**Objective:** Deterministically score whether a generated document resembles a usable public-sector report.

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py`
- Test: `python-hwpx/tests/test_government_report_quality.py`

**Profile checks:**
- front matter: organization/date/document_type or equivalent metadata present.
- outline: at least one numbered/roman/Korean heading pattern (`Ⅰ.`, `1.`, `가.`).
- report bullets: any of `□`, `○`, `-`, `※` present.
- table evidence: at least one table with non-empty header row.
- caption evidence: text containing `표`, `단위`, `붙임`, or explicit table caption.
- placeholder residue: fail on **unresolved templates** `\{\{.*?\}\}` and the explicit markers `TODO`, `TBD`, `[입력]`, `입력내용`, `작성 필요`. Do **not** use a bare `{...}` regex — it false-positives on legitimate content and would also flag the `{{ }}` computed-field syntax mid-render (see Task 2.2). Mirror the explicit-pattern approach in `_placeholder_dimension`/`_operating_plan_profile` (`authoring.py:1384-1394, 1483-1499`).

**Implementation route (edit these three real call sites — there is no `_resolve_quality_profile`):**
- `_requested_profile_name()` (`authoring.py:1165-1189`): add aliases `government_report`, `gov_report`, `공문보고서`, and (for plan-driven auto-detection) match `document_type`/title containing `공문`/`보고서`/`government_report`.
- `_profile_reports()` (`authoring.py:1142-1162`): it currently early-returns `{}` unless `profile_name == "operating_plan"`. Add a `government_report` branch that calls the new `_inspect_government_report_quality(document, normalized_plan=..., profile=...)`, modeled on `_inspect_operating_plan_quality` (`:1192-1317`) and returning `profile_name/status/score/dimensions/gaps/repair_hints/visual_review_required`.
- top-level gaps append in `inspect_document_authoring_quality` (`authoring.py:458-462`): it hardcodes `operating_plan`. Add a parallel branch so a failing `government_report` profile appends to `gaps` and flips top-level `pass`.
- Add `_inspect_government_report_quality(document, normalized_plan, profile)` plus a `_government_report_profile(profile)` options builder (mirror `_operating_plan_profile`).

**Verification:**

```bash
uv run --extra dev pytest tests/test_government_report_quality.py tests/test_document_plan.py -v
```

---

## Phase 2 — Report Utility Functions

### Task 2.1: Create Korean report calculator module

**Objective:** Implement 범정부오피스-style pure functions without HWPX coupling.

**Files:**
- Create: `python-hwpx/src/hwpx/tools/report_utils.py`
- Test: `python-hwpx/tests/test_report_utils.py`
- Modify: `python-hwpx/src/hwpx/tools/__init__.py` only if needed.

**Functions:**

```python
def format_krw_hangul(amount: int | str) -> str: ...
def format_number_commas(value: int | float | str) -> str: ...
def calculate_age(birth_date: str, base_date: str | None = None) -> int: ...
def format_delta(before: float, after: float, *, unit: str = "", precision: int = 1) -> str: ...
def format_delta_percent(before: float, after: float, *, precision: int = 1, percentage_point: bool = False) -> str: ...
def calculate_ratios(values: list[float], *, precision: int = 1) -> list[str]: ...
def normalize_korean_date(value: str, style: str = "iso") -> str: ...
```

**Edge cases:**
- zero amount.
- negative delta uses `△` by default.
- division by zero returns explicit error or `N/A`, not crash.
- date parsing supports `2026. 6. 2.`, `2026-06-02`, `2026/06/02`.

**Commands:**

```bash
uv run --extra dev pytest tests/test_report_utils.py -v
```

### Task 2.2: Add document-plan computed fields

**Objective:** Let agents request computed text inside document plans.

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py`
- Modify: `python-hwpx/src/hwpx/tools/report_utils.py`
- Test: `python-hwpx/tests/test_document_plan_computed_fields.py`

**Schema:**

```json
{
  "type": "paragraph",
  "text": "총 사업비: {{ krw_hangul(1200000) }}"
}
```

MVP computed operations (intentionally a subset of the Task 2.1 / Task 5.2 surface — `age`, `delta_percent`, `ratios` are reachable as utility/MCP calls but are not yet wired into inline `{{ }}` templates):
- `krw_hangul(value)`
- `commas(value)`
- `delta(before, after, unit)`
- `ratio(value, total)`
- `date(value, style)`

**YAGNI constraint:** implement a small safe parser, not `eval`. The placeholder-residue check (Task 1.3) targets `\{\{.*?\}\}`, so any `{{ }}` that survives rendering must surface as a validation error and will also be caught as residue — these two must agree on the same `{{ }}` delimiter.

**Verification:**
- Computed placeholders render into final paragraph/table cells.
- Unknown function leaves validation error, not silent text.

---

## Phase 3 — Table Normalization

### Task 3.1: Add table profile metadata to document-plan table blocks

**Objective:** Enable `tableProfile="government"` and captions/units without manual per-cell styling.

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py`
- Test: `python-hwpx/tests/test_government_table_profile.py`

**Schema:**

```json
{
  "type": "table",
  "caption": "추진 일정",
  "unit": "단위: 명",
  "tableProfile": "government",
  "columns": [...],
  "rows": [...]
}
```

> ⚠️ `_normalize_block` table branch (`authoring.py:872-879`) keeps only `caption/columns/rows` and **drops `unit`/`tableProfile`**; `_normalize_rows` (`:919-933`) does no whitespace normalization. The plumbing below is required before any render change has effect.

**Implementation:**
- **Preserve `unit`, `tableProfile`, and per-cell `preserveWhitespace` in `_normalize_block` table branch**; validate `tableProfile` against a known set in `_validate_block` (warn on unknown).
- Preserve `caption` as visible paragraph before table for now (unchanged from current `_add_plan_table`).
- **Add `unit` as a visible paragraph.** Default placement is *after* the caption but *before* the table. ⚠️ See the reopen-path caveat below — placing `unit` directly above the table changes which paragraph the file-only profile treats as caption.
- Normalize cell text in `_normalize_rows`: strip surrounding whitespace and collapse internal newlines unless `preserveWhitespace=true`.
- Apply header token to first row; table cell token elsewhere (already handled by `_add_plan_table`).

**Reopen-path interaction (must be tested, not just the plan path):**
`_document_table_blocks` (`authoring.py:1566-1612`) attributes the *immediately preceding paragraph* as a table's caption. If `unit` is the paragraph directly above the table, the file-only / reopened-document profile will read the unit text as the caption and the real caption gets lost. Options: (a) place `unit` paragraph *after* the table, or (b) teach `_document_table_blocks` to skip a `단위:`-prefixed line when resolving caption. Pick one and cover it with a reopen-based test (open the saved file, run `inspect_document_authoring_quality` with no plan, assert caption/unit evidence).

**Verification:**

```bash
uv run --extra dev pytest tests/test_government_table_profile.py -v
```

### Task 3.2: Add table cleanup utility

**Objective:** Provide Excel/PDF paste cleanup equivalent at text/table level.

**Files:**
- Create: `python-hwpx/src/hwpx/tools/table_cleanup.py`
- Test: `python-hwpx/tests/test_table_cleanup.py`

**Functions:**

```python
def normalize_cell_text(text: str) -> str: ...
def normalize_table_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]: ...
def add_sequence_column(rows: list[dict[str, str]], key: str = "no") -> list[dict[str, str]]: ...
def add_reverse_sum(rows: list[dict[str, str]], source_key: str, target_key: str = "sum") -> list[dict[str, str]]: ...
```

**Scope:** pure data transform first. Do not mutate HWPX tables in MVP.

---

## Phase 4 — Paste-to-Document-Plan

### Task 4.1: Add plain text report parser

**Objective:** Absorb `G서식변신` idea by converting ChatGPT/PDF pasted text into structured document-plan blocks.

**Files:**
- Create: `python-hwpx/src/hwpx/tools/report_parser.py`
- Test: `python-hwpx/tests/test_report_parser.py`

**Input patterns:**
- Markdown headings: `#`, `##`
- Korean report headings: `Ⅰ.`, `Ⅱ.`, `1.`, `가.`, `□`, `○`, `-`, `※`
- Table-like lines separated by tabs or `|`

**Output:**

```python
def parse_government_report_text(text: str, *, title: str = "") -> dict:
    """Return hwpx.document_plan.v1 dict."""
```

**Validation:** returned plan must pass `validate_document_plan()`.

### Task 4.2: Add MCP tool for parser

**Objective:** Expose paste cleanup to AI clients.

**Files:**
- Modify: `hwpx-mcp-server/src/hwpx_mcp_server/server.py`
- Test: `hwpx-mcp-server/tests/test_government_report_tools.py`

**Tool:**

```python
@mcp.tool()
def parse_government_report_text(text: str, title: str = None, style_preset: str = "government_report") -> dict:
    """붙여넣은 보고서 초안/PDF 텍스트를 hwpx.document_plan.v1로 변환합니다."""
```

**Return:**
- `document_plan`
- `plan_validation`
- `next_tool`: `create_document_from_plan`

---

## Phase 5 — MCP Thin Wrappers

### Task 5.1: Add `create_government_report_document` MCP tool

**Objective:** Make the best path obvious for agents: no need to remember style/profile arguments.

**Files:**
- Modify: `hwpx-mcp-server/src/hwpx_mcp_server/server.py`
- Test: `hwpx-mcp-server/tests/test_government_report_tools.py`

> ⚠️ Do **not** call the `@mcp.tool()`-decorated `create_document_from_plan` from inside another tool — under FastMCP the bound name may be a Tool wrapper, not the plain function, so a direct call is fragile. Follow the existing codebase pattern (`server.py:715-762`): extract the tool body into a private helper and have both tools delegate to it.

**Refactor + tool:**

```python
def _create_document_from_plan_impl(
    filename: str,
    document_plan: dict,
    style_preset: str = "standard_korean_business",
    quality_profile: str | None = None,
    profile: dict | None = None,
) -> dict:
    """Shared implementation; the existing create_document_from_plan tool also calls this."""
    ...  # move current create_document_from_plan(...) body here verbatim


@mcp.tool()
def create_document_from_plan(filename: str, document_plan: dict, style_preset: str = "standard_korean_business", quality_profile: str = None, profile: dict = None) -> dict:
    """선언형 document_plan으로 HWPX를 생성하고 즉시 저장/검증합니다."""
    return _create_document_from_plan_impl(filename, document_plan, style_preset, quality_profile, profile)


@mcp.tool()
def create_government_report_document(filename: str, document_plan: dict, profile: dict = None) -> dict:
    """정부보고서 스타일로 HWPX를 생성합니다(style/profile 인자 자동 적용)."""
    return _create_document_from_plan_impl(
        filename=filename,
        document_plan={**document_plan, "stylePreset": "government_report"},
        style_preset="government_report",
        quality_profile="government_report",
        profile=profile,
    )
```

**Verification:**

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server
uv run --with-editable ../python-hwpx --extra test pytest tests/test_government_report_tools.py -v
```

Test that the wrapper's output matches calling `create_document_from_plan` with the gov arguments explicitly (Gate E "wrapper behavior matches direct behavior").

### Task 5.2: Add report utility MCP tool

**Objective:** Let agents compute Korean report values before writing them into documents.

**Tool:**

```python
@mcp.tool()
def compute_report_value(operation: str, values: dict) -> dict: ...
```

Supported `operation`:
- `krw_hangul`
- `commas`
- `age`
- `delta`
- `delta_percent`
- `ratios`
- `date`

Return includes `value`, `operation`, `warnings`.

---

## Phase 6 — Skill Examples and Quickcheck

### Task 6.1: Add government report example

**Files:**
- Create: `hwpx-skill/examples/10_mcp_government_report.md`
- Create: `hwpx-skill/examples/10_create_government_report.py`
- Modify generated plugin copies by running build script later.

**Content:**
- sample `document_plan` with `□`, `○`, `※` bullets.
- table with `tableProfile="government"`, caption, unit.
- `create_government_report_document` MCP workflow.
- final `inspect_document_authoring_quality` workflow.

### Task 6.2: Extend quickcheck

**Files:**
- Modify: `hwpx-skill/scripts/quickcheck.py`

**Flag:**

```bash
python3 scripts/quickcheck.py --government-report
```

**Checks:**
- imports `python-hwpx` with government profile.
- generates sample HWPX.
- validates package.
- runs government quality inspection.

### Task 6.3: Rebuild multi-host plugin bundles

**Command:**

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
python3 scripts/build_hwpx_plugins.py
python3 scripts/validate_hwpx_plugin.py
git diff -- plugins .claude-plugin .codex-plugin openclaw.plugin.json
```

---

## Phase 7 — ComputerUse Visual Review Loop

> ⚠️ **Reconcile with existing work before adding anything.** A visual-review loop already ships: `hwpx-skill/examples/09_visual_review_loop.md`, `hwpx-skill/scripts/visual_review.py`, and prior plan `docs/superpowers/plans/2026-05-30-computeruse-visual-review-loop.md`. Phase 7 must **extend** that loop, not build a parallel one. Before Task 7.1, read `visual_review.py` and `09_visual_review_loop.md` and decide per task: extend the existing script/example, or add a genuinely new artifact. The new `11_*` example and the viewer-detection helper are net-new only if 09 does not already cover them; otherwise fold the government-report specifics into 09.

### Task 7.1: Add viewer detection helper

**Objective:** Decide which local app can visually open generated HWPX files before using ComputerUse.

**Files:**
- Create: `hwpx-skill/scripts/detect_hwpx_viewer.py`
- Test: `hwpx-skill/tests/test_detect_hwpx_viewer.py` if test layout exists; otherwise cover through quickcheck smoke.

**Detection order on macOS:**
1. Hancom/Hangul app bundle if installed.
2. LibreOffice if installed.
3. Finder Quick Look as weak fallback.
4. `blocked` if no viewer exists.

**Output schema:**

```json
{
  "status": "available|weak|blocked",
  "viewer": "Hancom|LibreOffice|QuickLook|none",
  "app": "Application name for ComputerUse",
  "reason": "human-readable explanation"
}
```

### Task 7.2: Add visual review evidence workflow to quickcheck

**Objective:** Make visual review reproducible and evidence-backed instead of manual handwaving.

**Files:**
- Modify: `hwpx-skill/scripts/quickcheck.py`
- Modify: `hwpx-skill/scripts/visual_review.py` if it lacks fields for viewer/screenshot metadata.
- Create: `hwpx-skill/examples/11_computeruse_visual_review.md`

**Flag:**

```bash
python3 scripts/quickcheck.py --government-report --visual-review
```

**Expected behavior:**
- If viewer available: generate HWPX, open viewer, use ComputerUse externally to capture screenshot, record `observed_pass` or `observed_fail`.
- If ComputerUse/viewer unavailable: record `status=blocked`, not pass.
- Never downgrade a blocked visual review into ready/submission-ready.

### Task 7.3: Add ComputerUse review checklist prompt

**Objective:** Standardize what the visual reviewer checks from screenshots.

**Files:**
- Create: `hwpx-skill/references/government-report-visual-review.md`
- Rebuild plugin bundles after adding reference.

**Checklist:**
- file opened without conversion/error dialog,
- first page is readable,
- title/subtitle/front matter not overlapped,
- heading hierarchy visually distinguishable,
- report bullets visible and aligned,
- tables fit page width,
- table header/body text visible,
- caption/unit near table,
- no obvious text clipping,
- screenshot path recorded.

---

## Phase 8 — Optional Advanced Generators

Do only after Phase 1-7 are green.

### Task 8.1: Photo table generator

**Core schema:**

```json
{
  "type": "image_grid",
  "columns": 2,
  "images": [{"path": "...", "caption": "현장 사진"}]
}
```

Start as document-plan validation + placeholder paragraph if image embedding is not stable. Then wire to existing image embed APIs.

### Task 8.2: Meeting nameplate generator

**Pure function first:**

```python
def build_meeting_nameplates(names: list[str], *, size: str = "150x70") -> dict:
    """Return document-plan table blocks."""
```

### Task 8.3: Organization chart generator

Use table-based org chart first. Avoid shape-heavy layout until visual review tooling improves.

---

## Execution Strategy

Recommended order:

1. `python-hwpx` Phase 1 tests + implementation.
2. `python-hwpx` Phase 2 utility tests + implementation.
3. `python-hwpx` Phase 3 table cleanup.
4. `python-hwpx` Phase 4 parser.
5. `hwpx-mcp-server` wrappers.
6. `hwpx-skill` examples/quickcheck/bundle rebuild.
7. ComputerUse visual review loop and evidence capture.
8. Optional advanced templates.

Use a separate branch:

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
git checkout -b feat/govoffice-absorption
```

If implementing across repos, use matching branches:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server
git checkout -b feat/govoffice-absorption
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
git checkout -b feat/govoffice-absorption
```

## Quality Assurance Gates

Quality is guaranteed by layered gates. A feature is not accepted because it "looks okay"; it must leave machine-readable evidence.

### Gate A — TDD evidence per behavior

Every production behavior starts with a failing test:

1. Write one narrow test.
2. Run the specific test and capture RED failure.
3. Implement the minimum code.
4. Run the same test and capture GREEN pass.
5. Run the local affected test file.

Required evidence per task:
- failing test command and expected failure reason,
- passing test command,
- affected regression test command.

### Gate B — Deterministic document validity

Every generated HWPX path must pass:
- `validate_package` zip/package integrity,
- `document.validate()` schema/document check,
- reopen check from saved bytes/path,
- text/table evidence extraction,
- no placeholder residue unless explicitly allowed.

No file is marked usable unless package/schema/reopen are all green.

### Gate C — Profile-specific scoring

`government_report` profile must return:
- `profile_name: government_report`,
- `status: ready | needs_revision`,
- numeric `score`,
- `dimensions`,
- `gaps`,
- `repair_hints`,
- `visual_review_required: true`.

The profile must check at minimum:
- front matter evidence,
- outline/heading evidence,
- public-report bullet evidence,
- table/header/caption/unit evidence,
- placeholder residue.

A score can approve structure only. It cannot waive visual review.

### Gate D — Golden fixture and snapshot coverage

Add fixtures generated only from code, not external binaries:
- minimal government report,
- report with tables/captions/units,
- report with bad placeholders,
- paste-cleanup text sample,
- calculator edge cases.

For each fixture, assert exported text and quality profile dimensions. Avoid brittle XML full snapshots except for targeted tags/attributes.

### Gate E — MCP integration evidence

MCP wrappers must prove:
- invalid plan returns `created: false` and repair hints,
- valid plan creates file,
- returned quality has `handoff_status`, `next_action`, and profile report,
- wrapper behavior matches direct `python-hwpx` behavior.

### Gate F — Skill/quickcheck smoke

`hwpx-skill` must include a quickcheck:

```bash
python3 scripts/quickcheck.py --government-report
```

It must:
- create a sample government report,
- validate package/schema/reopen,
- inspect `government_report` profile,
- print stable `[OK]` output.

### Gate G — Independent review before commit

Before commit/push:
- run `git diff --stat` and inspect changed files,
- scan diff for secrets/shell/eval/pickle/path traversal risks,
- run targeted tests and relevant full tests,
- dispatch independent reviewer for diff review when implementation touches 2+ files,
- fix any reviewer security/logic blockers before commit.

### Gate H — ComputerUse visual review boundary

XML checks do not guarantee rendered layout. Any user-facing final document remains `visual_review_required=true` until ComputerUse or a human viewer review confirms:
- Hangul/Hancom viewer or LibreOffice opens the file cleanly,
- first page title/subtitle/front matter are visible and not overlapped,
- tables are not clipped horizontally,
- captions/units are placed near the intended table,
- page breaks do not split headings from their first body block,
- Korean bullets render as intended (`□`, `○`, `-`, `※`, `*`),
- exported screenshot evidence is stored with the quality report.

Preferred automated visual loop:

1. Generate `.hwpx` into a temp/output path.
2. Open with the best available local viewer:
   - preferred: Hancom Office/Hangul if installed,
   - fallback: LibreOffice if it can render the file,
   - fallback: system Quick Look/Finder preview only as weak evidence.
3. Use ComputerUse scoped to the viewer app to capture page screenshots.
4. Save screenshot(s) under `outputs/visual-review/<case-id>/`.
5. Run `scripts/visual_review.py --screenshot <path> --status observed_pass|observed_fail`.
6. Attach visual evidence path into the quality report.

Do not claim "submission-ready" from automated XML checks alone. Only `observed_pass` visual evidence can clear the final layout gate.

## Final Verification Matrix

Run after all phases:

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run --extra dev pytest tests/test_government_report_preset.py tests/test_government_report_quality.py tests/test_report_utils.py tests/test_government_table_profile.py tests/test_report_parser.py tests/test_document_plan.py -v

cd /Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server
uv run --with-editable ../python-hwpx --extra test pytest tests/test_government_report_tools.py tests/test_document_plan_mcp_e2e.py -v

cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
uv run --with lxml --with ../python-hwpx python scripts/quickcheck.py --government-report
python3 scripts/build_hwpx_plugins.py
python3 scripts/validate_hwpx_plugin.py
```

## Acceptance Criteria

- Agents can generate a government-report styled HWPX using one MCP tool call. ("styled" is only met once Task 1.1's *differentiation guard* passes — i.e. the gov output is provably distinct from `standard_korean_business`. Until then the deliverable is "structured", not "styled".)
- Generated report passes package/schema/reopen checks.
- Government quality profile reports score/status/gaps/repair_hints.
- Korean report calculators are unit-tested and independent of HWPX.
- Text pasted from ChatGPT/PDF can become a valid document-plan.
- Skill docs teach the workflow without relying on this chat context.

## Risk Controls

- Keep utility functions pure and heavily tested.
- Keep MCP wrappers thin; business logic stays in `python-hwpx`.
- Keep Excel helpers optional; no pandas/openpyxl dependency in core unless explicitly approved.
- Visual fidelity still requires visual review; do not claim final submission quality from XML-only checks.
