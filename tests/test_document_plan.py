from __future__ import annotations

import pytest

from hwpx import (
    DOCUMENT_PLAN_SCHEMA_VERSION,
    HwpxDocument,
    create_document_from_plan,
    inspect_document_authoring_quality,
    inspect_operating_plan_quality,
    normalize_document_plan,
    validate_document_plan,
)
from hwpx.tools.package_validator import validate_package
from hwpx.tools.validator import validate_document


def _plan() -> dict:
    return {
        "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
        "title": "2026 AI Education Operating Plan",
        "subtitle": "Draft for internal review",
        "metadata": {
            "organization": "Sample School",
            "author": "AI Education Team",
            "date": "2026-05-09",
        },
        "stylePreset": "standard_korean_business",
        "blocks": [
            {"type": "heading", "level": 1, "text": "Executive Summary"},
            {
                "type": "paragraph",
                "text": "The program connects classroom practice, teacher training, and evidence review.",
            },
            {
                "type": "bullets",
                "items": [
                    "Provide AI literacy lessons for each grade band.",
                    "Run teacher workshops before classroom rollout.",
                ],
            },
            {"type": "page_break"},
            {"type": "heading", "level": 2, "text": "Budget"},
            {
                "type": "table",
                "caption": "Budget Plan",
                "columns": [
                    {"key": "item", "label": "Item", "widthWeight": 2},
                    {"key": "amount", "label": "Amount", "widthWeight": 1},
                    {"key": "note", "label": "Note", "widthWeight": 2},
                ],
                "rows": [
                    {
                        "item": "AI devices",
                        "amount": "5,000,000 KRW",
                        "note": "Laptop and classroom equipment",
                    },
                    {
                        "item": "Teacher training",
                        "amount": "1,000,000 KRW",
                        "note": "Workshops and coaching",
                    },
                ],
            },
        ],
        "qualityGates": {
            "validatePackage": True,
            "validateDocument": True,
            "reopen": True,
            "minNonEmptyParagraphs": 5,
            "visualReviewRequired": True,
        },
    }


def _operating_plan() -> dict:
    return {
        "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
        "title": "2026 AI 중점학교 운영계획서",
        "subtitle": "익명화된 제출 후보",
        "metadata": {
            "organization": "샘플고등학교",
            "author": "AI교육기획팀",
            "date": "2026-05-13",
            "document_type": "운영계획서",
        },
        "stylePreset": "standard_korean_business",
        "blocks": [
            {"type": "heading", "level": 1, "text": "Ⅰ. 신청 목적"},
            {
                "type": "paragraph",
                "text": "본 계획은 학교의 AI·디지털 기반 수업 역량을 강화하고 학생 맞춤형 학습 경험을 확대하기 위한 운영 방향을 제시한다.",
            },
            {"type": "heading", "level": 2, "text": "실태 및 필요성"},
            {
                "type": "paragraph",
                "text": "교사별 생성형 AI 활용 경험의 편차와 학생 계정 관리 부담을 줄이기 위해 학교 단위의 공통 운영 모델이 필요하다.",
            },
            {"type": "heading", "level": 2, "text": "AI 중점학교 운영 목표"},
            {
                "type": "bullets",
                "items": [
                    "책임 있는 AI 활용 체계를 마련한다.",
                    "학생의 AI 리터러시와 비판적 사고 역량을 강화한다.",
                    "수업, 평가, 기록을 연계한 맞춤형 피드백 구조를 정착시킨다.",
                ],
            },
            {"type": "heading", "level": 1, "text": "Ⅱ. 운영 계획"},
            {"type": "heading", "level": 2, "text": "1. 운영과제 세부내용 및 추진 전략"},
            {
                "type": "paragraph",
                "text": "정규 수업, 교원 연수, 학생 프로젝트를 연계하여 학기별 실행 과제를 운영한다.",
            },
            {"type": "heading", "level": 2, "text": "2. AI 중점학교 운영 추진 체계"},
            {
                "type": "table",
                "caption": "추진 일정",
                "columns": [
                    {"key": "phase", "label": "단계", "widthWeight": 1},
                    {"key": "period", "label": "기간", "widthWeight": 1},
                    {"key": "activity", "label": "세부 추진 내용", "widthWeight": 3},
                    {"key": "owner", "label": "담당", "widthWeight": 1},
                ],
                "rows": [
                    {
                        "phase": "준비",
                        "period": "3월",
                        "activity": "운영 계획 공유 및 교과별 협의회 구성",
                        "owner": "운영팀",
                    },
                    {
                        "phase": "운영",
                        "period": "4월~11월",
                        "activity": "AI 활용 수업, 학생 프로젝트, 교원 연수 운영",
                        "owner": "교과협의회",
                    },
                    {
                        "phase": "평가",
                        "period": "12월~2월",
                        "activity": "성과 분석, 우수 사례 공유, 차년도 개선안 수립",
                        "owner": "평가팀",
                    },
                ],
            },
            {"type": "heading", "level": 1, "text": "Ⅲ. 추진 일정 및 사업비 사용 계획"},
            {
                "type": "table",
                "caption": "사업비 사용 계획",
                "columns": [
                    {"key": "item", "label": "항목", "widthWeight": 2},
                    {"key": "amount", "label": "금액", "widthWeight": 1},
                    {"key": "ratio", "label": "비율(%)", "widthWeight": 1},
                    {"key": "basis", "label": "산출근거", "widthWeight": 3},
                ],
                "rows": [
                    {
                        "item": "교육 운영비",
                        "amount": "4,000,000원",
                        "ratio": "50",
                        "basis": "수업 자료 제작, 학생 프로젝트 재료비",
                    },
                    {
                        "item": "교원 연수비",
                        "amount": "1,000,000원",
                        "ratio": "12.5",
                        "basis": "AI 활용 수업 설계 연수 운영",
                    },
                    {
                        "item": "자산 취득비",
                        "amount": "3,000,000원",
                        "ratio": "37.5",
                        "basis": "AI 교육 전용 교구 및 실습 장비",
                    },
                ],
            },
            {"type": "heading", "level": 1, "text": "Ⅳ. 교육과정 편제표"},
            {
                "type": "paragraph",
                "text": "세부 교육과정 편제표는 학교 자율 양식으로 별도 첨부하고, 본문에는 운영 방향과 연계 과목을 요약한다.",
            },
            {"type": "heading", "level": 1, "text": "Ⅴ. 기대 효과 및 성과 관리"},
            {
                "type": "bullets",
                "items": [
                    "AI 활용 수업 공개와 수업 나눔을 통해 교원 실행 역량을 높인다.",
                    "학생 산출물, 참여도, 만족도 자료를 종합하여 성과를 관리한다.",
                    "차년도 교육과정 편성과 예산 계획에 운영 결과를 반영한다.",
                ],
            },
            {"type": "heading", "level": 1, "text": "Ⅵ. 제출 및 확인"},
            {
                "type": "paragraph",
                "text": "본 운영계획서는 학교 구성원의 검토를 거쳐 제출하며, 선정 이후 세부 실행 계획과 증빙 자료를 보완한다.",
            },
        ],
        "qualityGates": {
            "validatePackage": True,
            "validateDocument": True,
            "reopen": True,
            "minNonEmptyParagraphs": 12,
            "minTableCount": 2,
            "requiredText": [
                "Ⅰ. 신청 목적",
                "Ⅱ. 운영 계획",
                "Ⅲ. 추진 일정 및 사업비 사용 계획",
                "추진 일정",
                "사업비 사용 계획",
            ],
            "visualReviewRequired": True,
        },
    }


def _table_texts(document: HwpxDocument) -> list[list[list[str]]]:
    tables = []
    for paragraph in document.paragraphs:
        for table in paragraph.tables:
            tables.append([[cell.text for cell in row.cells] for row in table.rows])
    return tables


def test_validate_document_plan_reports_schema_and_block_errors() -> None:
    report = validate_document_plan(
        {
            "schemaVersion": "bad",
            "blocks": [{"type": "table", "columns": [{"key": "a"}], "rows": ["bad"]}],
        }
    )

    assert report.ok is False
    payload = report.to_dict()
    issue_codes = {issue["code"] for issue in payload["issues"]}
    assert "invalid_schema_version" in issue_codes
    assert "invalid_table_row" in issue_codes
    assert any(issue["path"] == "schemaVersion" for issue in payload["issues"])
    assert any(issue["path"] == "blocks[0].rows[0]" for issue in payload["issues"])
    assert any(hint["path"] == "schemaVersion" for hint in payload["repairHints"])


def test_normalize_document_plan_rejects_invalid_blocks() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        normalize_document_plan(
            {
                "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
                "title": "Invalid",
                "blocks": [{"type": "unknown"}],
            }
        )


def test_validate_document_plan_reports_recoverable_table_and_style_warnings(tmp_path) -> None:
    plan = {
        "schemaVersion": DOCUMENT_PLAN_SCHEMA_VERSION,
        "title": "Recoverable Warnings",
        "blocks": [
            {"type": "paragraph", "style": "hero", "text": "Unknown styles fall back to body."},
            {
                "type": "table",
                "columns": [
                    {"key": "item", "label": "Item", "widthWeight": "wide"},
                    {"key": "amount", "label": "Amount", "widthWeight": 0},
                ],
                "rows": [
                    {"item": "AI devices", "note": "ignored extra key"},
                    {"item": "Teacher training", "amount": "1,000,000 KRW"},
                ],
            },
        ],
    }

    report = validate_document_plan(plan)

    assert report.ok is True
    payload = report.to_dict()
    warning_codes = {
        issue["code"]
        for issue in payload["issues"]
        if issue["severity"] == "warning"
    }
    assert {
        "unknown_style_token",
        "invalid_width_weight",
        "table_row_missing_cells",
        "table_row_extra_cells",
    }.issubset(warning_codes)
    assert any(hint["action"] == "review" for hint in payload["repairHints"])

    output = tmp_path / "recoverable-warnings.hwpx"
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    assert validate_package(output).ok
    assert validate_document(output).ok


def test_validate_document_plan_reports_invalid_quality_gate_values() -> None:
    plan = _plan()
    plan["qualityGates"] = {
        "validatePackage": "yes",
        "minNonEmptyParagraphs": 0,
        "minTableCount": "two",
        "requiredText": ["Executive Summary", ""],
    }

    report = validate_document_plan(plan)

    assert report.ok is False
    payload = report.to_dict()
    issue_codes = {issue["code"] for issue in payload["issues"]}
    assert "invalid_quality_gate_type" in issue_codes
    assert "invalid_quality_gate_minimum" in issue_codes
    assert "invalid_required_text" in issue_codes
    assert any(issue["path"] == "qualityGates.minTableCount" for issue in payload["issues"])


def test_create_document_from_plan_generates_valid_formatted_hwpx(tmp_path) -> None:
    output = tmp_path / "agent-plan-smoke.hwpx"
    document = create_document_from_plan(_plan())
    try:
        document.save_to_path(output)
    finally:
        document.close()

    assert output.exists()
    assert validate_package(output).ok
    assert validate_document(output).ok

    reopened = HwpxDocument.open(output)
    try:
        full_text = reopened.export_text()
        assert "2026 AI Education Operating Plan" in full_text
        assert "Executive Summary" in full_text
        assert "Provide AI literacy lessons" in full_text
        assert any(paragraph.element.get("pageBreak") == "1" for paragraph in reopened.paragraphs)

        tables = _table_texts(reopened)
        assert len(tables) >= 2
        assert any(row == ["Item", "Amount", "Note"] for table in tables for row in table)
        assert any("AI devices" in cell for table in tables for row in table for cell in row)
    finally:
        reopened.close()


def test_operating_plan_vertical_slice_reports_required_content_and_tables(tmp_path) -> None:
    output = tmp_path / "operating-plan.hwpx"
    plan = _operating_plan()
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    report = inspect_document_authoring_quality(output, plan=plan)

    assert output.exists()
    assert report["pass"] is True
    assert report["validation"]["reopened"] is True
    assert report["validation"]["validate_package"]["ok"] is True
    assert report["validation"]["validate_document"]["ok"] is True
    assert report["document"]["table_count"] >= 2
    assert report["quality_gates"]["minTableCount"] is True
    assert report["quality_gates"]["requiredText"] is True
    assert report["content_evidence"]["required_text"]
    assert all(item["present"] for item in report["content_evidence"]["required_text"])
    assert report["visual_review_required"] is True

    reopened = HwpxDocument.open(output)
    try:
        full_text = reopened.export_text()
        assert "AI 중점학교 운영 목표" in full_text
        assert "사업비 사용 계획" in full_text
        assert "# Ⅰ. 신청 목적" not in full_text
        assert "- 책임 있는 AI 활용 체계" not in full_text
        assert "• 책임 있는 AI 활용 체계" in full_text
        assert "문서 정보" in full_text
        assert "기관" in full_text
        assert "작성자" in full_text
        assert "작성일" in full_text
        assert "organization" not in full_text
        assert "author" not in full_text
        assert "date" not in full_text
        assert "Field" not in full_text
        assert "Value" not in full_text

        tables = _table_texts(reopened)
        cell_widths = [
            cell.width
            for paragraph in reopened.paragraphs
            for table in paragraph.tables
            for row in table.rows
            for cell in row.cells
        ]
        assert all(width <= 48_000 for width in cell_widths)
        assert any(
            row == ["단계", "기간", "세부 추진 내용", "담당"]
            for table in tables
            for row in table
        )
        assert any(
            row == ["항목", "금액", "비율(%)", "산출근거"]
            for table in tables
            for row in table
        )
    finally:
        reopened.close()


def test_operating_plan_profile_passes_complete_submission_candidate(tmp_path) -> None:
    output = tmp_path / "operating-plan-profile.hwpx"
    plan = _operating_plan()
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    report = inspect_document_authoring_quality(
        output,
        plan=plan,
        quality_profile="operating_plan",
    )
    profile = report["profiles"]["operating_plan"]
    direct = inspect_operating_plan_quality(output, plan=plan)

    assert report["pass"] is True
    assert profile["profile_version"] == "operating-plan-quality-v1"
    assert profile["pass"] is True
    assert direct["pass"] is True
    assert profile["score"] >= 4.0
    assert profile["dimensions"]["required_outline"]["status"] == "pass"
    assert profile["dimensions"]["front_matter"]["status"] == "pass"
    assert profile["dimensions"]["schedule_table"]["status"] == "pass"
    assert profile["dimensions"]["budget_resource_evidence"]["status"] == "pass"
    assert profile["dimensions"]["expected_outcomes"]["status"] == "pass"
    assert profile["dimensions"]["closing_material"]["status"] == "pass"
    assert profile["dimensions"]["placeholder_residue"]["status"] == "pass"
    assert profile["gaps"] == []
    assert profile["visual_review_required"] is True


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
    assert any("budget_resource_evidence" in gap for gap in report["gaps"])
    assert any("expected_outcomes" in gap for gap in report["gaps"])
    assert any("closing_material" in gap for gap in report["gaps"])
    assert any("placeholder_residue" in gap for gap in report["gaps"])
    assert any(hint["dimension"] == "schedule_table" for hint in report["repair_hints"])
    assert any(
        hint["dimension"] == "budget_resource_evidence"
        for hint in report["repair_hints"]
    )
    assert any(hint["dimension"] == "placeholder_residue" for hint in report["repair_hints"])
    assert report["visual_review_required"] is True


def test_operating_plan_file_only_quality_requires_explicit_front_matter(tmp_path) -> None:
    output = tmp_path / "operating-plan-without-front-matter.hwpx"
    plan = _operating_plan()
    plan["metadata"] = {}
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    report = inspect_operating_plan_quality(output)

    assert report["status"] == "needs_revision"
    assert report["dimensions"]["front_matter"]["status"] == "fail"
    assert any("front_matter" in gap for gap in report["gaps"])
    assert any(hint["dimension"] == "front_matter" for hint in report["repair_hints"])


def test_operating_plan_file_only_quality_counts_schedule_data_rows_only(tmp_path) -> None:
    output = tmp_path / "operating-plan-short-schedule.hwpx"
    plan = _operating_plan()
    for block in plan["blocks"]:
        if block.get("type") == "table" and block.get("caption") == "추진 일정":
            block["rows"] = block["rows"][:2]
            break
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    report = inspect_operating_plan_quality(output)
    schedule = report["dimensions"]["schedule_table"]

    assert report["status"] == "needs_revision"
    assert schedule["status"] == "fail"
    assert schedule["metrics"]["table_row_count"] == 2
    assert any("schedule_table" in gap for gap in report["gaps"])


def test_operating_plan_profile_reports_actionable_gaps_for_sparse_candidate(tmp_path) -> None:
    output = tmp_path / "sparse-operating-plan.hwpx"
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
        "qualityGates": {
            "validatePackage": True,
            "validateDocument": True,
            "reopen": True,
            "minNonEmptyParagraphs": 3,
            "visualReviewRequired": True,
        },
    }
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    report = inspect_document_authoring_quality(
        output,
        plan=plan,
        quality_profile="operating_plan",
    )
    profile = report["profiles"]["operating_plan"]

    assert report["pass"] is False
    assert profile["pass"] is False
    assert profile["score"] < 4.0
    assert "operating plan quality failed" in report["gaps"]
    assert any("required_outline" in gap for gap in profile["gaps"])
    assert any("schedule_table" in gap for gap in profile["gaps"])
    assert any("budget_resource_evidence" in gap for gap in profile["gaps"])
    assert any("expected_outcomes" in gap for gap in profile["gaps"])
    assert any("closing_material" in gap for gap in profile["gaps"])
    assert any("placeholder_residue" in gap for gap in profile["gaps"])
    assert any(hint["dimension"] == "schedule_table" for hint in profile["repair_hints"])
    assert any(hint["dimension"] == "placeholder_residue" for hint in profile["repair_hints"])


def test_inspect_document_authoring_quality_reports_gates_and_styles(tmp_path) -> None:
    output = tmp_path / "quality.hwpx"
    plan = _plan()
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output)
    finally:
        document.close()

    report = inspect_document_authoring_quality(output, plan=plan)

    assert report["report_version"] == "hwpx-authoring-quality-v1"
    assert report["pass"] is True
    assert report["plan_validation"]["ok"] is True
    assert report["block_counts"]["heading"] == 2
    assert report["block_counts"]["table"] == 1
    assert report["validation"]["reopened"] is True
    assert report["validation"]["validate_package"]["ok"] is True
    assert isinstance(report["validation"]["validate_package"]["issues"], list)
    assert report["validation"]["validate_document"]["ok"] is True
    assert isinstance(report["validation"]["validate_document"]["issues"], list)
    assert report["quality_gates"]["visualReviewRequired"] is True
    assert report["visual_review_required"] is True
    assert report["style_token_usage"]["used_run_style_count"] >= 3
    assert report["recovery"]["next_actions"]
