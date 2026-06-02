# File-Only Operating Plan Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic file-only quality evidence for operating-plan HWPX outputs, including template form-fit outputs, and expose the evidence through python-hwpx, hwpx-mcp-server, and hwpx-skill.

**Architecture:** Keep the canonical quality profile in `python-hwpx/src/hwpx/authoring.py` because the existing document-plan and operating-plan profile APIs already live there. MCP should stay a thin adapter over the python-hwpx API, and hwpx-skill should document the same evidence contract instead of inventing a second quality model.

**Tech Stack:** Python 3.10+, pytest, python-hwpx HWPX package APIs, FastMCP tool wrappers, hwpx-skill Markdown and quickcheck scripts.

---

## Stage Context

Wily Stage: `S-004` / `file-only 운영계획서 품질 프로필 강화`

Current planned phases:

1. `PH-f25bb1bfc0ff` - 품질 프로필 계약 설계
2. `PH-224fbbe93dce` - python-hwpx 구현 및 fixture 테스트
3. `PH-f26710f0e710` - MCP와 skill handoff 노출

Important acceptance points:

- `.hwpx` path alone must produce a stable report with `report_version`, `status`, `score`, `gaps`, `repair_hints`, and `visual_review_required`.
- Complete operating-plan and P7 template form-fit outputs should be close to `ready`, while sparse, ambiguous, or residual-marker-heavy outputs should be `needs_revision`.
- MCP and skill docs must expose the same file-only evidence shape.

## File Structure

- Modify: `python-hwpx/src/hwpx/authoring.py`
  - Owns the public `inspect_operating_plan_quality()` contract.
  - Adds file-only front matter, outline, table, marker, status, and repair-hint evidence without requiring a source `DocumentPlan`.
- Modify: `python-hwpx/tests/test_document_plan.py`
  - Adds path-only ready and needs-revision tests for generated operating plans.
- Modify: `python-hwpx/tests/test_template_formfit.py`
  - Adds a template form-fit output test that runs file-only operating-plan quality after apply.
- Modify: `hwpx-mcp-server/src/hwpx_mcp_server/server.py`
  - Keeps `inspect_operating_plan_quality()` as a thin wrapper but ensures path-only calls return the enriched report.
- Modify: `hwpx-mcp-server/tests/test_quality_generation_pipeline.py`
  - Adds MCP-level file-only quality assertions.
- Modify: `hwpx-skill/SKILL.md`
  - Adds the file-only handoff evidence gate to the operating-plan and template form-fit workflows.
- Modify: `hwpx-skill/README.md`
  - Documents the user-facing command/workflow.
- Modify: `hwpx-skill/scripts/quickcheck.py`
  - Verifies the operating-plan quickcheck observes file-only quality status and visual review gating.

## Task 1: Lock The python-hwpx File-Only Report Contract

**Files:**
- Modify: `python-hwpx/tests/test_document_plan.py`

- [ ] **Step 1: Add a path-only ready-candidate test**

Append this test after `test_operating_plan_profile_passes_complete_submission_candidate`:

```python
def test_operating_plan_file_only_quality_passes_complete_submission_candidate(tmp_path) -> None:
    output = tmp_path / "operating-plan-file-only.hwpx"
    plan = _operating_plan()
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    report = inspect_operating_plan_quality(output)

    assert report["report_version"] == "operating-plan-quality-v1"
    assert report["profile_version"] == "operating-plan-quality-v1"
    assert report["profile_name"] == "operating_plan"
    assert report["status"] == "ready"
    assert report["pass"] is True
    assert report["score"] >= 4.0
    assert report["visual_review_required"] is True
    assert report["dimensions"]["front_matter"]["status"] == "pass"
    assert report["dimensions"]["required_outline"]["status"] == "pass"
    assert report["dimensions"]["schedule_table"]["status"] == "pass"
    assert report["dimensions"]["budget_resource_evidence"]["status"] == "pass"
    assert report["dimensions"]["expected_outcomes"]["status"] == "pass"
    assert report["dimensions"]["closing_material"]["status"] == "pass"
    assert report["dimensions"]["placeholder_residue"]["status"] == "pass"
    assert report["gaps"] == []
    assert report["repair_hints"] == []
    assert report["limitations"]
```

- [ ] **Step 2: Add a path-only needs-revision test**

Append this test after the ready-candidate test:

```python
def test_operating_plan_file_only_quality_reports_actionable_gaps_for_sparse_candidate(tmp_path) -> None:
    output = tmp_path / "sparse-operating-plan-file-only.hwpx"
    plan = {
        "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
        "title": "2026 AI 중점학교 운영계획서",
        "metadata": {"organization": "샘플고등학교"},
        "blocks": [
            {"type": "heading", "level": 1, "text": "Ⅰ. 신청 목적"},
            {"type": "paragraph", "text": "작성 필요: 학교 상황에 맞게 입력하세요."},
            {
                "type": "table",
                "caption": "사업비 사용 계획",
                "columns": [
                    {"key": "item", "label": "항목"},
                    {"key": "amount", "label": "금액"},
                ],
                "rows": [{"item": "TODO", "amount": ""}],
            },
        ],
    }
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    report = inspect_operating_plan_quality(output)

    assert report["report_version"] == "operating-plan-quality-v1"
    assert report["status"] == "needs_revision"
    assert report["pass"] is False
    assert report["score"] < 4.0
    assert any("required_outline" in gap for gap in report["gaps"])
    assert any("schedule_table" in gap for gap in report["gaps"])
    assert any("expected_outcomes" in gap for gap in report["gaps"])
    assert any("closing_material" in gap for gap in report["gaps"])
    assert any("placeholder_residue" in gap for gap in report["gaps"])
    assert any(hint["dimension"] == "schedule_table" for hint in report["repair_hints"])
    assert any(hint["dimension"] == "placeholder_residue" for hint in report["repair_hints"])
    assert report["visual_review_required"] is True
```

- [ ] **Step 3: Run the new tests and verify they fail before implementation**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run pytest tests/test_document_plan.py::test_operating_plan_file_only_quality_passes_complete_submission_candidate tests/test_document_plan.py::test_operating_plan_file_only_quality_reports_actionable_gaps_for_sparse_candidate -q
```

Expected:

```text
FAILED tests/test_document_plan.py::test_operating_plan_file_only_quality_passes_complete_submission_candidate
FAILED tests/test_document_plan.py::test_operating_plan_file_only_quality_reports_actionable_gaps_for_sparse_candidate
```

The failure should be missing `report_version` or incorrect file-only dimension status.

## Task 2: Implement File-Only Quality Evidence In python-hwpx

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py`

- [ ] **Step 1: Add text evidence helpers near `_inspect_operating_plan_quality`**

Add these helpers above `_inspect_operating_plan_quality`:

```python
def _document_text_lines(document: HwpxDocument) -> list[str]:
    full_text = document.export_text()
    table_text = _table_text(document)
    lines: list[str] = []
    for chunk in (full_text, table_text):
        for line in str(chunk or "").splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def _front_matter_from_file_text(lines: list[str], options: Mapping[str, Any]) -> dict[str, Any]:
    joined = "\n".join(lines[:20])
    required_terms = {
        "organization": ["기관", "학교", "신청 기관", "샘플고등학교"],
        "date": ["작성일", "일자", "2026"],
        "document_type": ["문서 유형", "운영계획서", "운영 계획서"],
    }
    metrics = {
        key: _contains_any(joined, values)
        for key, values in required_terms.items()
        if key in set(options["required_metadata"])
    }
    present = bool(metrics) and all(metrics.values())
    return _dimension(
        present=present,
        score=5.0 if present else 2.5,
        metrics={"required_metadata": metrics},
        fail_reason="missing front matter metadata evidence",
        repair_hint="Add visible document metadata near the beginning: 기관, 작성일, and 문서 유형.",
    )
```

- [ ] **Step 2: Update `_inspect_operating_plan_quality` to use file text when no plan is provided**

Inside `_inspect_operating_plan_quality`, replace the current front-matter dimension assignment with this logic:

```python
    file_lines = _document_text_lines(document)
    front_matter = (
        _front_matter_dimension(normalized_plan, options)
        if normalized_plan is not None
        else _front_matter_from_file_text(file_lines, options)
    )
```

Then set `dimensions["front_matter"]` to `front_matter`:

```python
    dimensions = {
        "front_matter": front_matter,
        "required_outline": _dimension(
            present=all(section_results.values()),
            score=5.0 if all(section_results.values()) else max(
                2.0,
                5.0 * sum(section_results.values()) / len(section_results),
            ),
            metrics={"required_sections": section_results},
            fail_reason="missing required operating-plan sections",
            repair_hint=(
                "Add the missing operating-plan headings and body content: "
                + ", ".join(name for name, present in section_results.items() if not present)
                + "."
            ),
        ),
        "content_density": _dimension(
            present=(
                len(all_text) >= int(options["min_text_chars"])
                and len(non_empty_paragraphs) >= int(options["min_non_empty_paragraphs"])
            ),
            score=5.0
            if len(all_text) >= int(options["min_text_chars"])
            and len(non_empty_paragraphs) >= int(options["min_non_empty_paragraphs"])
            else 3.0,
            metrics={
                "text_char_count": len(all_text),
                "non_empty_paragraph_count": len(non_empty_paragraphs),
                "min_text_chars": int(options["min_text_chars"]),
                "min_non_empty_paragraphs": int(options["min_non_empty_paragraphs"]),
            },
            fail_reason="operating-plan content is too sparse",
            repair_hint="Expand section body text with school context, implementation detail, evidence, and review criteria.",
        ),
        "schedule_table": _schedule_table_dimension(all_text, table_blocks, options),
        "budget_resource_evidence": _budget_dimension(
            all_text,
            table_blocks,
            amount_count=amount_count,
            options=options,
        ),
        "expected_outcomes": _dimension(
            present=_contains_any(all_text, options["expected_outcome_terms"]),
            score=5.0 if _contains_any(all_text, options["expected_outcome_terms"]) else 2.0,
            metrics={"terms": options["expected_outcome_terms"]},
            fail_reason="missing expected outcomes or performance-management evidence",
            repair_hint="Add a 기대 효과/성과 관리 section with measurable outcomes and review evidence.",
        ),
        "closing_material": _dimension(
            present=_contains_any(all_text, options["closing_terms"]),
            score=5.0 if _contains_any(all_text, options["closing_terms"]) else 2.0,
            metrics={"terms": options["closing_terms"]},
            fail_reason="missing closing, submission, review, or confirmation material",
            repair_hint="Add a closing/submission block that states review, confirmation, submission, or signature context.",
        ),
        "placeholder_residue": _placeholder_dimension(all_text, options),
    }
```

- [ ] **Step 3: Add stable report fields to the return payload**

In `_inspect_operating_plan_quality`, compute `passed` and `status` before returning:

```python
    passed = average >= 4.0 and not gaps
    status = "ready" if passed else "needs_revision"
```

Return this enriched shape:

```python
    return {
        "report_version": OPERATING_PLAN_QUALITY_VERSION,
        "profile_version": OPERATING_PLAN_QUALITY_VERSION,
        "profile_name": "operating_plan",
        "status": status,
        "pass": passed,
        "score": average,
        "dimensions": dimensions,
        "gaps": gaps,
        "repair_hints": repair_hints,
        "visual_review_required": True,
        "limitations": [
            "This profile checks deterministic text/table/package proxies only.",
            "Submission-quality form fit still requires rendered or human visual review.",
        ],
    }
```

- [ ] **Step 4: Run the python-hwpx focused tests**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run pytest tests/test_document_plan.py::test_operating_plan_file_only_quality_passes_complete_submission_candidate tests/test_document_plan.py::test_operating_plan_file_only_quality_reports_actionable_gaps_for_sparse_candidate tests/test_document_plan.py::test_operating_plan_profile_passes_complete_submission_candidate tests/test_document_plan.py::test_operating_plan_profile_reports_actionable_gaps_for_sparse_candidate -q
```

Expected:

```text
4 passed
```

## Task 3: Cover Template Form-Fit Outputs With The Same File-Only Profile

**Files:**
- Modify: `python-hwpx/tests/test_template_formfit.py`

- [ ] **Step 1: Import the file-only quality API**

Change the import block to include `inspect_operating_plan_quality`:

```python
from hwpx import (
    HwpxDocument,
    analyze_template_formfit,
    apply_template_formfit,
    inspect_operating_plan_quality,
)
```

- [ ] **Step 2: Add an operating-plan template helper**

Append this helper after `_write_template`:

```python
def _write_operating_plan_template(path: Path) -> None:
    doc = HwpxDocument.new()
    try:
        doc.paragraphs[0].text = "2026 AI 중점학교 운영계획서"
        doc.add_paragraph("문서 정보")
        doc.add_paragraph("기관: 샘플고등학교")
        doc.add_paragraph("작성일: 2026-05-30")
        doc.add_paragraph("문서 유형: 운영계획서")
        doc.add_paragraph("Ⅰ. 신청 목적")
        doc.add_paragraph("작성 필요: 신청 목적을 입력하세요.")
        doc.add_paragraph("Ⅱ. 운영 계획")
        doc.add_paragraph("작성 필요: 운영 계획을 입력하세요.")
        doc.add_paragraph("Ⅲ. 추진 일정 및 사업비 사용 계획")
        doc.add_paragraph("TODO")
        doc.add_paragraph("Ⅴ. 기대 효과 및 성과 관리")
        doc.add_paragraph("작성 필요: 기대 효과를 입력하세요.")
        doc.add_paragraph("Ⅵ. 제출 및 확인")
        doc.add_paragraph("본 계획은 검토 후 제출합니다.")
        doc.save_to_path(path)
    finally:
        doc.close()
```

- [ ] **Step 3: Add a form-fit quality test**

Append this test near the existing apply test:

```python
def test_template_formfit_output_has_file_only_operating_plan_quality(tmp_path: Path) -> None:
    source = tmp_path / "operating-plan-template.hwpx"
    destination = tmp_path / "operating-plan-filled.hwpx"
    _write_operating_plan_template(source)
    baseline = {
        "schemaVersion": "hwpx.template-formfit.baseline.v1",
        "baselineId": "operating-plan-template-baseline",
        "sourceSafety": {
            "sourceInPlaceEditsAllowed": False,
            "copyBeforeApplyRequired": True,
            "finalHashCheckRequired": True,
        },
        "locatorPolicy": {
            "residualMarkers": {
                "blockOutsideVisualReview": True,
                "patterns": ["작성 필요", "TODO", "□□□□", "○○"],
            }
        },
        "scalarFields": [],
        "regionMappings": [
            {
                "id": "purpose",
                "anchor": "Ⅰ. 신청 목적",
                "kind": "section-region",
                "sourcePath": "sections.purpose",
                "required": True,
            },
            {
                "id": "operations",
                "anchor": "Ⅱ. 운영 계획",
                "kind": "section-region",
                "sourcePath": "sections.operations",
                "required": True,
            },
            {
                "id": "schedule_budget",
                "anchor": "Ⅲ. 추진 일정 및 사업비 사용 계획",
                "kind": "section-region",
                "sourcePath": "sections.schedule_budget",
                "required": True,
            },
            {
                "id": "outcomes",
                "anchor": "Ⅴ. 기대 효과 및 성과 관리",
                "kind": "section-region",
                "sourcePath": "sections.outcomes",
                "required": True,
            },
        ],
        "visualReviewRegions": [{"id": "layout", "anchor": "Ⅲ. 추진 일정 및 사업비 사용 계획"}],
    }
    content = {
        "sections": {
            "purpose": ["학교 AI 교육 운영 목적과 필요성을 구체화한다."],
            "operations": ["운영 계획은 수업, 연수, 학생 프로젝트를 연결한다."],
            "schedule_budget": [
                "추진 일정은 3월 준비, 4월에서 11월 운영, 12월 평가로 구성한다.",
                "사업비 사용 계획은 교육 운영비 4,000,000원, 교원 연수비 1,000,000원, 자원 구입비 3,000,000원이다.",
            ],
            "outcomes": ["기대 효과와 성과 관리는 학생 AI 소양과 교원 실행 역량을 기준으로 점검한다."],
        }
    }
    analysis = analyze_template_formfit(
        source,
        baseline=baseline,
        content=content,
        destination=destination,
    )

    result = apply_template_formfit(analysis=analysis, confirm=True)
    quality = inspect_operating_plan_quality(destination)

    assert result["handoff_status"] == "ready"
    assert result["visual_review_required"] is True
    assert quality["report_version"] == "operating-plan-quality-v1"
    assert quality["status"] == "ready"
    assert quality["pass"] is True
    assert quality["visual_review_required"] is True
    assert quality["dimensions"]["placeholder_residue"]["status"] == "pass"
```

- [ ] **Step 4: Run template form-fit tests**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run pytest tests/test_template_formfit.py -q
```

Expected:

```text
5 passed
```

## Task 4: Expose The File-Only Contract Through hwpx-mcp-server

**Files:**
- Modify: `hwpx-mcp-server/src/hwpx_mcp_server/server.py`
- Modify: `hwpx-mcp-server/tests/test_quality_generation_pipeline.py`

- [ ] **Step 1: Confirm the MCP wrapper delegates path-only calls**

Review `inspect_operating_plan_quality` in `server.py`. It should keep this shape:

```python
@mcp.tool()
def inspect_operating_plan_quality(
    filename: str,
    document_plan: dict = None,
    profile: dict = None,
) -> dict:
    """운영 계획서 제출 후보의 file-only 품질 프로필을 반환합니다."""
    path = resolve_path(filename)
    if inspect_operating_plan_document_quality is not None:
        return inspect_operating_plan_document_quality(path, plan=document_plan, profile=profile)
    report = _inspect_authoring_quality(
        path,
        document_plan=document_plan,
        quality_profile={"name": "operating_plan", **dict(profile or {})},
    )
    return report.get("profiles", {}).get("operating_plan", report)
```

If the docstring is missing the file-only language, update only the docstring.

- [ ] **Step 2: Add an MCP path-only quality assertion**

Append this test to `tests/test_quality_generation_pipeline.py`:

```python
def test_mcp_inspect_operating_plan_quality_supports_file_only_path(tmp_path) -> None:
    destination = tmp_path / "operating-plan.hwpx"
    result = server.create_document_from_plan(
        filename=str(destination),
        document_plan={
            "schemaVersion": "hwpx.document_plan.v1",
            "title": "2026 AI 중점학교 운영계획서",
            "metadata": {
                "organization": "매원초등학교",
                "date": "2026-05-30",
                "document_type": "운영계획서",
            },
            "blocks": [
                {"type": "heading", "level": 1, "text": "Ⅰ. 신청 목적"},
                {"type": "paragraph", "text": "AI 교육 운영 목적과 필요성을 학교 교육과정 안에서 구체화한다."},
                {"type": "heading", "level": 1, "text": "Ⅱ. 운영 계획"},
                {"type": "paragraph", "text": "수업, 연수, 학생 프로젝트를 연결한 운영 계획을 추진한다."},
                {"type": "heading", "level": 1, "text": "Ⅲ. 추진 일정 및 사업비 사용 계획"},
                {
                    "type": "table",
                    "caption": "추진 일정",
                    "columns": [
                        {"key": "phase", "label": "단계"},
                        {"key": "period", "label": "기간"},
                        {"key": "activity", "label": "세부 추진 내용"},
                    ],
                    "rows": [
                        {"phase": "준비", "period": "3월", "activity": "운영 협의체 구성"},
                        {"phase": "운영", "period": "4월~11월", "activity": "AI 활용 수업 운영"},
                    ],
                },
                {
                    "type": "table",
                    "caption": "사업비 사용 계획",
                    "columns": [
                        {"key": "item", "label": "항목"},
                        {"key": "amount", "label": "금액"},
                        {"key": "basis", "label": "산출근거"},
                    ],
                    "rows": [
                        {"item": "교육 운영비", "amount": "4,000,000원", "basis": "자료 제작"},
                        {"item": "교원 연수비", "amount": "1,000,000원", "basis": "연수 운영"},
                    ],
                },
                {"type": "heading", "level": 1, "text": "Ⅳ. 교육과정 편제표"},
                {"type": "paragraph", "text": "교육과정과 교과 운영 체계를 연계한다."},
                {"type": "heading", "level": 1, "text": "Ⅴ. 기대 효과 및 성과 관리"},
                {"type": "paragraph", "text": "기대 효과와 성과 관리를 지표와 산출물로 확인한다."},
                {"type": "heading", "level": 1, "text": "Ⅵ. 제출 및 확인"},
                {"type": "paragraph", "text": "본 계획은 검토 후 제출하며 운영 과정에서 보완한다."},
            ],
        },
        quality_profile="operating_plan",
    )

    report = server.inspect_operating_plan_quality(filename=str(destination))

    assert result["handoff_status"] == "ready"
    assert report["report_version"] == "operating-plan-quality-v1"
    assert report["status"] == "ready"
    assert report["pass"] is True
    assert report["visual_review_required"] is True
    assert report["gaps"] == []
```

- [ ] **Step 3: Run MCP focused tests**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server
uv run pytest tests/test_quality_generation_pipeline.py -q
```

Expected:

```text
4 passed
```

## Task 5: Update hwpx-skill Handoff Guidance And Quickcheck

**Files:**
- Modify: `hwpx-skill/SKILL.md`
- Modify: `hwpx-skill/README.md`
- Modify: `hwpx-skill/scripts/quickcheck.py`

- [ ] **Step 1: Update operating-plan guidance in `SKILL.md`**

In section `1-2) 운영 계획서 제출 후보 작성`, replace the handoff evidence list with:

```markdown
7. handoff 전 evidence를 확인한다:
   - `plan_validation.ok == true`
   - `quality.validation.reopened == true`
   - `quality.validation.validate_package.ok == true`
   - `quality.validation.validate_document.ok == true`
   - file-only `inspect_operating_plan_quality(path).report_version == "operating-plan-quality-v1"`
   - file-only `inspect_operating_plan_quality(path).status == "ready"`
   - `visual_review_required == true`이면 최종 제출 전 별도 시각 검토가 필요하다고 명시
8. `status="needs_revision"` 또는 `gaps[]`가 있으면 `repair_hints[]`를 반영해 plan을 보강하고 다시 검증한다.
```

- [ ] **Step 2: Update template form-fit guidance in `SKILL.md`**

In section `1-3) P6 기준선 기반 양식 보존 form-fit`, extend the evidence list:

```markdown
5. handoff 전 evidence를 확인한다:
   - `handoff_status == "ready"`
   - `source.preserved == true`
   - `validation.validate_package.ok == true`
   - `validation.validate_document.ok == true`
   - `residual_markers.blocking == []`
   - file-only `inspect_operating_plan_quality(destination).status == "ready"` 또는 남은 gap이 제출 전 수동 보완 가능하다는 근거
6. `visual_review_required=true`이면 렌더링/열람/사람 검토를 최종 제출 전 별도 gate로 남긴다.
```

- [ ] **Step 3: Mirror the same user-facing contract in `README.md`**

In the README operating-plan section, add:

````markdown
생성 또는 form-fit 적용 후에는 파일 경로만으로 다시 검사한다.

```bash
python3 examples/07_create_operating_plan.py
python3 scripts/quickcheck.py --operating-plan
```

MCP가 있으면 `inspect_operating_plan_quality(filename)`를 호출하고,
local Python이면 `inspect_operating_plan_quality(path)`를 호출한다.
핵심 handoff evidence는 `report_version`, `status`, `score`, `gaps`,
`repair_hints`, `visual_review_required`다. `status="ready"`여도
`visual_review_required=true`이면 제출 전 렌더링/열람 검토를 남긴다.
````

- [ ] **Step 4: Add quickcheck assertions for file-only quality**

In `scripts/quickcheck.py`, after the `operating-plan` command succeeds, add an inline Python check:

```python
    if args.operating_plan:
        operating_plan_output = EXAMPLES_DIR / "out" / "07_operating_plan.hwpx"
        check_code = (
            "from hwpx import inspect_operating_plan_quality; "
            f"report = inspect_operating_plan_quality({str(operating_plan_output)!r}); "
            "assert report['report_version'] == 'operating-plan-quality-v1'; "
            "assert report['status'] == 'ready'; "
            "assert report['visual_review_required'] is True"
        )
        commands.append((
            "operating-plan-file-only-quality",
            [sys.executable, "-c", check_code],
        ))
```

Place this block after the `if args.template_formfit:` command append block, so the file-only check runs after the operating-plan example creates its output.

- [ ] **Step 5: Run skill quickcheck**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
python3 scripts/quickcheck.py --operating-plan --template-formfit
```

Expected:

```text
[OK] operating-plan document-plan workflow passed
[OK] template form-fit workflow passed
[OK] basic hwpx skill workflow passed
```

## Task 6: Run Full Verification And Record Stage Evidence

**Files:**
- Modify: Wily Stage `S-004` notes through MCP lifecycle tools

- [ ] **Step 1: Run python-hwpx tests**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run hwpx-mcp-server tests**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server
uv run pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run hwpx-skill quickcheck**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
python3 scripts/quickcheck.py --document-plan --operating-plan --template-formfit
```

Expected:

```text
[OK] document-plan generation workflow passed
[OK] operating-plan document-plan workflow passed
[OK] template form-fit workflow passed
```

- [ ] **Step 4: Record Wily Stage evidence**

Use `mcp__wily_client.add_stage_note` with this body:

```text
S-004 file-only operating-plan quality profile implemented.

Evidence:
- python-hwpx: uv run pytest -q passed
- hwpx-mcp-server: uv run pytest -q passed
- hwpx-skill: python3 scripts/quickcheck.py --document-plan --operating-plan --template-formfit passed

Residual risk:
- visual_review_required remains true for submission-quality layout review because this Stage intentionally uses file-only checks.
```

## Self-Review

Spec coverage:

- File-only `.hwpx` path quality is covered by Task 1 and Task 2.
- Template form-fit output quality is covered by Task 3.
- MCP exposure is covered by Task 4.
- Skill handoff guidance and quickcheck are covered by Task 5.
- Full verification and Wily evidence are covered by Task 6.

Placeholder scan:

- The string `TODO` appears only as test data for residual-marker detection.
- No plan step contains a placeholder instruction.

Type consistency:

- Public report fields are consistent across python-hwpx, MCP, and skill docs: `report_version`, `status`, `score`, `gaps`, `repair_hints`, `visual_review_required`.
- Existing compatibility fields `profile_version`, `profile_name`, and `pass` remain present.
