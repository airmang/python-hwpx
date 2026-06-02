from __future__ import annotations

import hashlib
from pathlib import Path

from hwpx import (
    HwpxDocument,
    analyze_template_formfit,
    apply_template_formfit,
    inspect_operating_plan_quality,
)
from hwpx.tools.package_validator import validate_package
from hwpx.tools.validator import validate_document


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _baseline() -> dict:
    return {
        "schemaVersion": "hwpx.template-formfit.baseline.v1",
        "baselineId": "unit-template-baseline",
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
        "scalarFields": [
            {
                "id": "school.name",
                "kind": "scalar-line",
                "locator": {"kind": "scalar-line", "anchor": "학 교 명 :"},
                "sourcePath": "school.name",
                "required": False,
            }
        ],
        "regionMappings": [
            {
                "id": "overview.background_purpose",
                "anchor": "1. 추진 배경 및 목적",
                "kind": "section-region",
                "sourcePath": "sections.background_purpose",
                "required": True,
            },
            {
                "id": "schedule.timeline",
                "anchor": "Ⅶ 추진 일정",
                "kind": "table-region",
                "sourcePath": "sections.timeline.rows[]",
                "required": True,
                "columns": ["월", "추진 내용"],
            },
        ],
        "visualReviewRegions": [{"id": "photos", "anchor": "대상 공간 사진"}],
    }


def _content() -> dict:
    return {
        "school": {"name": "광교고등학교"},
        "sections": {
            "background_purpose": [
                "AI 융합형 교육실 구축으로 학생 맞춤형 탐구 수업을 확대한다.",
                "교원 공동 설계와 지역 연계를 통해 지속 가능한 운영 체계를 만든다.",
            ],
            "timeline": {
                "rows": [
                    {"월": "3월", "추진 내용": "운영 협의체 구성"},
                    {"월": "4월", "추진 내용": "공간 설계 및 기자재 선정"},
                ]
            },
        },
    }


def _write_template(path: Path) -> None:
    doc = HwpxDocument.new()
    try:
        doc.paragraphs[0].text = "AI 융합형 교육실 구축·운영 계획서"
        doc.add_paragraph("학 교 명 :")
        doc.add_paragraph("1. 추진 배경 및 목적")
        doc.add_paragraph("작성 필요: 추진 배경을 입력하세요.")
        doc.add_paragraph("Ⅶ 추진 일정")
        doc.add_paragraph("TODO")
        doc.add_paragraph("대상 공간 사진")
        doc.save_to_path(path)
    finally:
        doc.close()


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
        doc.add_paragraph("추진 일정")
        schedule = doc.add_table(4, 4)
        schedule.set_cell_text(0, 0, "단계")
        schedule.set_cell_text(0, 1, "기간")
        schedule.set_cell_text(0, 2, "세부 추진 내용")
        schedule.set_cell_text(0, 3, "담당")
        schedule.set_cell_text(1, 0, "준비")
        schedule.set_cell_text(1, 1, "3월")
        schedule.set_cell_text(1, 2, "운영 계획 공유 및 교과별 교육과정 협의")
        schedule.set_cell_text(1, 3, "운영팀")
        schedule.set_cell_text(2, 0, "운영")
        schedule.set_cell_text(2, 1, "4월~11월")
        schedule.set_cell_text(2, 2, "AI 활용 수업, 학생 프로젝트, 교원 연수 운영")
        schedule.set_cell_text(2, 3, "교과협의회")
        schedule.set_cell_text(3, 0, "평가")
        schedule.set_cell_text(3, 1, "12월")
        schedule.set_cell_text(3, 2, "성과 분석, 우수 사례 공유, 차년도 개선안 수립")
        schedule.set_cell_text(3, 3, "평가팀")
        doc.add_paragraph("사업비 사용 계획")
        budget = doc.add_table(3, 4)
        budget.set_cell_text(0, 0, "항목")
        budget.set_cell_text(0, 1, "금액")
        budget.set_cell_text(0, 2, "비율(%)")
        budget.set_cell_text(0, 3, "산출근거")
        budget.set_cell_text(1, 0, "교육 운영비")
        budget.set_cell_text(1, 1, "4,000,000원")
        budget.set_cell_text(1, 2, "50")
        budget.set_cell_text(1, 3, "수업 자료 제작과 학생 프로젝트 재료비")
        budget.set_cell_text(2, 0, "자원 구입비")
        budget.set_cell_text(2, 1, "3,000,000원")
        budget.set_cell_text(2, 2, "37.5")
        budget.set_cell_text(2, 3, "AI 교육 기자재와 공용 학습 자원 구입")
        doc.save_to_path(path)
    finally:
        doc.close()


def test_analyze_template_formfit_is_non_mutating_and_reports_required_targets(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    destination = tmp_path / "filled.hwpx"
    _write_template(source)
    before_hash = _sha256(source)

    analysis = analyze_template_formfit(
        source,
        baseline=_baseline(),
        content=_content(),
        destination=destination,
    )

    assert analysis["mutated"] is False
    assert analysis["source"]["unchanged_after_analysis"] is True
    assert analysis["resolved_count"] == 3
    assert analysis["unresolved_count"] == 0
    assert analysis["next_tool"] == "apply_template_formfit"
    assert analysis["visual_review_required"] is True
    assert not destination.exists()
    assert _sha256(source) == before_hash


def test_apply_template_formfit_copies_source_and_returns_validation_evidence(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    destination = tmp_path / "filled.hwpx"
    _write_template(source)
    before_hash = _sha256(source)
    before_mtime = source.stat().st_mtime_ns
    analysis = analyze_template_formfit(
        source,
        baseline=_baseline(),
        content=_content(),
        destination=destination,
    )

    result = apply_template_formfit(analysis=analysis, confirm=True)

    assert result["handoff_status"] == "ready"
    assert result["source"]["preserved"] is True
    assert result["source"]["sha256_before"] == before_hash
    assert result["source"]["mtime_ns_before"] == before_mtime
    assert result["destination"]["changed"] is True
    assert result["validation"]["validate_package"]["ok"] is True
    assert result["validation"]["validate_document"]["ok"] is True
    assert result["residual_markers"]["blocking"] == []
    assert validate_package(destination).ok
    assert validate_document(destination).ok
    assert _sha256(source) == before_hash
    assert source.stat().st_mtime_ns == before_mtime

    reopened = HwpxDocument.open(destination)
    try:
        text = reopened.export_text()
        assert "학 교 명 : 광교고등학교" in text
        assert "AI 융합형 교육실 구축으로 학생 맞춤형 탐구 수업" in text
        assert "운영 협의체 구성" in text
        assert "작성 필요" not in text
        assert "TODO" not in text
    finally:
        reopened.close()


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
            "operations": [
                "운영 계획은 수업, 연수, 학생 프로젝트를 연결한다.",
                "교육과정은 정보, 과학, 국어 교과의 탐구 활동을 중심으로 편성하고 학기별 산출물과 평가 기록을 연계한다.",
                "교원 협의회는 공동 수업안을 개발하고 학생 계정 관리, 윤리 기준, 데이터 보호 절차를 월별로 점검한다.",
                "학생 프로젝트는 문제 발견, AI 도구 실습, 결과 공유 단계로 운영하여 학교 현장의 실제 개선 과제를 다룬다.",
            ],
            "schedule_budget": [
                "추진 일정은 3월 준비, 4월에서 11월 운영, 12월 평가로 구성한다.",
                "사업비 사용 계획은 교육 운영비 4,000,000원, 교원 연수비 1,000,000원, 자원 구입비 3,000,000원이다.",
                "예산 집행 증빙은 품의, 검수, 결과 보고를 연결하여 산출근거와 사용 목적이 확인되도록 관리한다.",
            ],
            "outcomes": [
                "기대 효과와 성과 관리는 학생 AI 소양과 교원 실행 역량을 기준으로 점검한다.",
                "성과 지표는 학생 참여율, 프로젝트 완성도, 교원 연수 이수율, 수업 공개 결과를 포함한다.",
                "학기 말 검토 회의에서 운영 자료와 만족도 결과를 확인하고 다음 연도 개선 과제를 제출 자료에 반영한다.",
            ],
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


def test_template_formfit_blocks_missing_required_anchor_before_apply(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    destination = tmp_path / "filled.hwpx"
    _write_template(source)
    baseline = _baseline()
    baseline["regionMappings"][0]["anchor"] = "없는 필수 앵커"

    analysis = analyze_template_formfit(
        source,
        baseline=baseline,
        content=_content(),
        destination=destination,
    )
    result = apply_template_formfit(analysis=analysis, confirm=True)

    assert analysis["resolved_count"] == 2
    assert analysis["unresolved_count"] == 1
    assert analysis["unresolved"][0]["reason"] == "anchor not found"
    assert result["handoff_status"] == "blocked"
    assert result["reason"] == "unresolved template targets remain"
    assert not destination.exists()


def test_template_formfit_refuses_source_in_place_apply(tmp_path: Path) -> None:
    source = tmp_path / "template.hwpx"
    _write_template(source)
    analysis = analyze_template_formfit(
        source,
        baseline=_baseline(),
        content=_content(),
        destination=source,
    )

    result = apply_template_formfit(analysis=analysis, confirm=True)

    assert result["handoff_status"] == "blocked"
    assert result["reason"] == "source-in-place edit refused"
