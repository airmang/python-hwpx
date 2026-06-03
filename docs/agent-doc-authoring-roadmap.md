# Agent Document Authoring Roadmap

Status: planning note based on `python-hwpx`, `hwpx-mcp-server`, and
`hwpx-skill` as inspected on 2026-05-09.

## Objective

Make HWPX a first-class AI-agent document generation target by promoting the
current proposal/form-specific workflows into one explicit vertical slice:

1. Agent normalizes a request into a declarative document plan.
2. `python-hwpx` generates a valid `.hwpx` from that plan.
3. `hwpx-mcp-server` exposes the plan workflow through MCP.
4. `hwpx-skill` teaches agents when and how to use it.
5. Tests prove the generated file reopens, validates, and can be exercised
   through both local library and MCP paths.

This note is intentionally implementation-facing. It does not propose code
changes outside the agreed roadmap.

## Current State

### `python-hwpx`

Evidence:

- `src/hwpx/document.py` already has the needed public document primitives:
  `HwpxDocument.new()`, paragraph/table/style helpers, `save_to_path()`,
  `to_bytes()`, `validate()`, and package-level validation tooling.
- `src/hwpx/presets/proposal.py` provides the first agent-oriented generation
  surface: `ProposalSpec`, `create_proposal_document()`, and
  `inspect_proposal_quality()`.
- `tests/test_proposal_preset.py` proves the proposal preset can generate an
  HWPX, save it, reopen/inspect it, pass quality gates, and use multiple style
  tokens.
- `docs/usage.md` documents the proposal preset and its proxy quality gates.
- `shared/hwpx/benchmarks/*.md` already captures lessons from `python-docx`,
  Open XML SDK, docx4j, MCP reference servers, VS Code Agent Skills, and pyhwp.

Gap:

- There is no generic, reusable declarative document-plan contract. The current
  high-level generation API is proposal-specific.
- Quality inspection is useful but domain-specific. It should become a generic
  authoring report with optional rubric-specific extensions.

### `hwpx-mcp-server`

Evidence:

- `src/hwpx_mcp_server/server.py` exposes `create_proposal_document`,
  `inspect_document_quality`, `analyze_quality_generation`, and
  `apply_quality_generation`.
- Current default FastMCP surface exposes 39 tools; advanced mode exposes 49.
- `src/hwpx_mcp_server/quality_generation.py` already implements a useful
  non-mutating analyze step, an apply step with confirmation, validation, and
  revision history.
- `tests/test_quality_generation_pipeline.py` verifies:
  non-mutating analysis, no per-run quality sample requirement, generated
  output creation, package/document validation, and revision history.
- Existing MCP tests cover default vs advanced tool exposure, JSON-RPC contract
  shape, and basic end-to-end tool calls.

Gap:

- The generation pipeline is currently tied to a built-in AI school application
  profile and proposal preset strategy.
- The plan lives as an internal quality-generation analysis object, not as a
  stable public `hwpx.document_plan.v1` schema that agents can author directly.
- Release-facing docs still contain stale tool-count/version language in places.

### `hwpx-skill`

Evidence:

- `SKILL.md` already routes proposal/planning requests to the proposal preset.
- `SKILL.md` also documents the MCP quality-generation workflow for
  form-plus-idea inputs.
- `examples/04_create_proposal.py`, `examples/05_mcp_quality_pipeline.md`, and
  `scripts/quickcheck.py --proposal` give agents executable entry points.
- `references/api.md` documents the proposal preset and quality criteria.

Gap:

- The skill does not yet teach a generic declarative document-plan workflow.
- Version references are inconsistent with current repo state: the skill still
  mentions older local measurements while `python-hwpx` is at `2.9.1` and
  `hwpx-mcp-server` depends on `python-hwpx>=2.9.1`.
- `quickcheck.py` only verifies the basic and proposal paths, not an MCP-backed
  or generic document-plan slice.

## Mature Pattern Benchmarks

| Pattern source | Mature behavior | HWPX stack mapping |
| --- | --- | --- |
| `python-docx` | Very short happy path: create/open, add content, save. | Keep `create_document_from_plan(plan).save_to_path(path)` as the simplest local path. Do not require XML knowledge for v1. |
| Open XML SDK | Validation is a product surface, not a side utility. | Make plan validation, package validation, document schema validation, and reopen checks part of the default generation report. |
| docx4j | Beginner path and deep package/XML path are separated. | Keep `hwpx.document_plan.v1` limited to headings, paragraphs, tables, page breaks, metadata, and basic style tokens; leave direct OWPML/XML editing in advanced APIs. |
| MCP reference servers | Public tool surface is small, explicit, stateless, and security-conscious. | MCP calls should take explicit `filename`/`destination_filename`, never hidden sessions for the basic path, and should clearly mark mutating calls. |
| filesystem/git-style MCP workflows | Risky state changes benefit from analyze/preview/apply gates. | Keep `analyze_document_plan` non-mutating and `apply_document_plan(confirm=True)` mutating; return next-action hints and validation evidence. |
| VS Code Agent Skills | Skills are executable workflow assets with frontmatter, direct links, examples, and quick verification. | Keep `SKILL.md` focused on routing and decisions; move signatures to `references/api.md`; add a runnable document-plan example and quickcheck mode. |
| Codex DOCX document skill | Shipping requires render/inspect/iterate when a renderer exists; structural XML checks alone miss layout defects. | HWPX v1 cannot honestly claim visual parity without a renderer. Reports should expose `visual_review_required=True` and reserve render/pixel gates for a future HWPX renderer integration. |

## Target Contract: `hwpx.document_plan.v1`

Add a generic plan format that an agent can produce without knowing OWPML.
Keep v1 intentionally small enough to validate and support well.

```json
{
  "schemaVersion": "hwpx.document_plan.v1",
  "title": "2026 AI Education Operating Plan",
  "subtitle": "Draft for internal review",
  "metadata": {
    "organization": "Sample School",
    "author": "AI Education Team",
    "date": "2026-05-09",
    "document_type": "plan"
  },
  "stylePreset": "standard_korean_business",
  "blocks": [
    {"type": "heading", "level": 1, "text": "Executive Summary"},
    {"type": "paragraph", "text": "Summarize the goal and scope."},
    {
      "type": "table",
      "caption": "Budget",
      "columns": [
        {"key": "item", "label": "Item", "widthWeight": 2},
        {"key": "amount", "label": "Amount", "widthWeight": 1},
        {"key": "note", "label": "Note", "widthWeight": 2}
      ],
      "rows": [
        {"item": "AI devices", "amount": "5,000,000 KRW", "note": "Laptop and classroom equipment"}
      ]
    }
  ],
  "qualityGates": {
    "validatePackage": true,
    "validateDocument": true,
    "reopen": true,
    "minNonEmptyParagraphs": 3,
    "visualReviewRequired": true
  }
}
```

V1 supported blocks:

- `heading`: `level` 1-3 and `text`
- `paragraph`: `text`, optional semantic style token
- `bullets`: list of strings, rendered through the safest current paragraph
  path first; true list semantics can be a v2 goal
- `table`: caption, columns, rows, optional width weights
- `page_break`
- `memo`: optional, only when current public memo APIs are stable enough for
  generated documents

V1 explicit non-goals:

- Binary `.hwp` generation or conversion
- Pixel-perfect recreation of an existing document
- Arbitrary OWPML injection
- Complex images, shapes, form controls, fields, change tracking, headers, and
  master-page authoring
- Claiming visual quality without renderer-backed review

## Implementation Plan

### Phase 1: Core Plan Builder in `python-hwpx`

Deliverables:

- New module: `src/hwpx/authoring.py` or `src/hwpx/plans.py`
- Public API:
  - `normalize_document_plan(plan: Mapping[str, Any]) -> DocumentPlan`
  - `validate_document_plan(plan: Mapping[str, Any]) -> PlanValidationReport`
  - `create_document_from_plan(plan: Mapping[str, Any] | DocumentPlan, *, preset: str | DocumentStylePreset | None = None) -> HwpxDocument`
  - `inspect_document_authoring_quality(source: str | Path | HwpxDocument, *, plan: Mapping[str, Any] | None = None) -> dict[str, Any]`
- Public exports from `hwpx.__init__` once the API is stable.
- Documentation:
  - `docs/usage.md` section for document plans.
  - `docs/examples.md` entry for a minimal plan.
- Example:
  - `examples/build_from_document_plan.py`

Implementation notes:

- Use standard-library dataclasses or typed dictionaries in core. Avoid adding
  Pydantic to `python-hwpx` unless the project accepts that dependency.
- Build only through public `HwpxDocument` methods. Direct XML should be
  reserved for missing core capabilities and called out explicitly.
- Reuse proposal-preset style-token ideas, but rename the generic preset to
  something domain-neutral such as `standard_korean_business`.
- Keep proposal support by translating `ProposalSpec` to `DocumentPlan` rather
  than maintaining two separate generation engines.
- Authoring quality report should include:
  - `report_version`
  - plan schema version
  - block counts by type
  - required gate results
  - package/document validation result
  - reopen result
  - style-token usage
  - `visual_review_required`
  - actionable gaps

Tests:

- `tests/test_document_plan.py`
  - rejects missing/unsupported `schemaVersion`
  - rejects invalid block types and malformed table rows
  - generates a document with heading, paragraph, bullets, table, and page break
  - saves, reopens, validates with `validate_document()` and `validate_package()`
  - verifies extracted text and table content
  - verifies deterministic report shape and `visual_review_required=True`
- Add a fixture manifest for the generated sample only after the format proves
  stable. Do not treat generated output as an editor-authored canonical fixture.

Acceptance gate:

```bash
cd /Users/wilycastle/Code/projects/python-hwpx
uv run pytest -q tests/test_document_plan.py tests/test_proposal_preset.py
```

### Phase 2: MCP Exposure in `hwpx-mcp-server`

Deliverables:

- New public tools on the active FastMCP surface:
  - `validate_document_plan(document_plan: dict) -> dict`
  - `create_document_from_plan(filename: str, document_plan: dict, style_preset: str = "standard_korean_business") -> dict`
  - `inspect_document_authoring_quality(filename: str, document_plan: dict | None = None) -> dict`
- Optional two-step workflow if direct create proves too risky:
  - `analyze_document_plan(document_plan, destination_filename=None)` is
    non-mutating and returns `plan_id`, normalized plan, predicted operations,
    unsupported features, and quality gates.
  - `apply_document_plan(plan_id=None, analysis=None, destination_filename=None, confirm=True)` writes the file and returns validation evidence.

Implementation notes:

- Keep the basic path filename-based and stateless.
- Mark mutating tools clearly in docstrings and README.
- Prefer one generic plan tool family over extending the proposal-specific API
  with more special cases.
- Keep existing `create_proposal_document` as a compatibility convenience, but
  implement it through the generic plan builder once available.
- Replace internal quality-generation fallback logic with generic plan building
  where possible, while preserving the current form-plus-idea workflow.
- Update release-facing docs to the actual tool counts after implementation.

Tests:

- `tests/test_document_plan_mcp_e2e.py`
  - tool exposure in default mode
  - `validate_document_plan` rejects bad input without writing a file
  - `create_document_from_plan` writes a valid HWPX
  - generated output passes `validate_package()` and `validate_document()`
  - generated output can be read by `get_document_text` and table tools
  - JSON-RPC call path works through the test MCP client, not only direct
    Python function calls
- Extend contract tests to assert sanitized schemas for the new tools.

Acceptance gate:

```bash
cd /Users/wilycastle/Code/projects/hwpx-mcp-server
uv run pytest -q tests/test_document_plan_mcp_e2e.py tests/test_mcp_end_to_end.py tests/test_contract.py tests/test_quality_generation_pipeline.py
```

### Phase 3: Skill Instructions in `hwpx-skill`

Deliverables:

- `SKILL.md`
  - Add "new HWPX generation from a natural-language request" routing.
  - Tell agents to normalize into `hwpx.document_plan.v1` first.
  - Prefer MCP document-plan tools when an HWPX MCP server is connected.
  - Fall back to local `python-hwpx` plan builder when MCP is unavailable.
  - Require validation/reopen evidence before handoff.
  - Keep `visual_review_required=True` limitation explicit.
- `references/api.md`
  - Document the generic plan schema, builder functions, and report fields.
  - Update version table to current stack baselines.
- New examples:
  - `examples/06_create_from_document_plan.py`
  - `examples/06_mcp_document_plan.md`
- `scripts/quickcheck.py`
  - Add `--document-plan`.
  - Keep `--proposal` as a compatibility/vertical specialization check.

Tests:

- Run local quickcheck:

```bash
cd /Users/wilycastle/Code/projects/hwpx-skill
uv run python scripts/quickcheck.py --document-plan --proposal
```

- If MCP quickcheck is added, keep it opt-in because user environments may not
  have a running MCP server.

### Phase 4: Stack Smoke and Release Discipline

Deliverables:

- Extend `shared/hwpx/scripts/run_stack_smoke_test.sh` with the new document
  plan path:
  - core generation
  - MCP generation
  - skill quickcheck
- Add or update shared manifest:
  - `shared/hwpx/fixtures/manifests/90-agent-document-plan.yml`
- Update stack docs:
  - compatibility matrix for `python-hwpx>=2.9.1` or the actual release that
    introduces the plan API
  - MCP README tool counts
  - skill README version baselines

Release order:

1. Release `python-hwpx` with the plan API.
2. Bump `hwpx-mcp-server` dependency to that version and expose plan tools.
3. Update `hwpx-skill` examples/docs after both upstream surfaces are available.

## Prioritized Vertical Slice

The first slice should be deliberately narrow:

Input:

- A JSON `hwpx.document_plan.v1` with title, metadata, two headings, two
  paragraphs, one bullet list, one budget table, and quality gates.

Core output:

- `create_document_from_plan()` produces `agent-plan-smoke.hwpx`.
- File reopens through `HwpxDocument.open()`.
- `validate_package()` and `validate_document()` pass.
- Text extraction contains all expected heading/paragraph/table values.

MCP output:

- `validate_document_plan()` returns normalized plan and no write.
- `create_document_from_plan()` writes the same shape to the requested filename.
- `get_document_text()` and `get_table_text()` confirm contents.
- Tool schema is sanitized and JSON-RPC smoke passes.

Skill output:

- `SKILL.md` tells agents the exact routing.
- `quickcheck.py --document-plan` creates and inspects the sample document.
- The example explains that visual review is still required for final layout
  confidence unless a renderer is integrated.

Done means:

- The same plan can be used from Python, MCP, and the skill example.
- All validation gates are part of the returned report, not left as manual
  tribal knowledge.
- Proposal-specific workflows still work, ideally as adapters over the generic
  plan builder.

## Risk Register

| Risk | Mitigation |
| --- | --- |
| Generic plan grows into an under-specified layout language. | Keep v1 small and reject unsupported blocks early. |
| Generated documents pass XML validation but look poor. | Return `visual_review_required=True`; defer visual pass/fail until renderer support exists. |
| MCP tool surface becomes crowded. | Add one generic plan family and keep proposal/form tools as compatibility wrappers. |
| Core library takes on too much domain-specific quality logic. | Separate generic authoring gates from optional rubric/profile-specific checks. |
| Skill examples drift from actual APIs. | Add `quickcheck.py --document-plan` and include it in release checks. |
| Version docs drift again. | Update compatibility matrix, MCP README, and skill README in the same release sequence. |

## Definition of Done

The vertical slice is complete when all of the following are true:

- A stable `hwpx.document_plan.v1` schema is documented.
- `python-hwpx` can create and inspect a valid HWPX from the plan.
- The generated HWPX passes package validation, document validation, and reopen
  checks in automated tests.
- `hwpx-mcp-server` exposes the plan workflow with sanitized input schemas and
  JSON-RPC coverage.
- `hwpx-skill` routes new-document requests to the plan workflow and has a
  quickcheck/example path.
- Stack smoke exercises the same plan through core, MCP, and skill surfaces.
- Existing proposal and quality-generation tests remain green.
