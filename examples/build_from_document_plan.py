#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Create a formatted HWPX from a declarative agent document plan."""

from __future__ import annotations

from pathlib import Path

from hwpx import (
    create_document_from_plan,
    inspect_document_authoring_quality,
    validate_document_plan,
)


def main() -> None:
    output_path = Path(__file__).resolve().parent / "out" / "operating_plan_document_plan.hwpx"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plan = {
        "schemaVersion": "hwpx.document_plan.v1",
        "title": "2026 AI 중점학교 운영계획서",
        "subtitle": "Declarative HWPX generation smoke sample",
        "metadata": {
            "organization": "Sample High School",
            "author": "AI Education Team",
            "date": "2026-05-13",
            "document_type": "operating_plan",
        },
        "blocks": [
            {"type": "heading", "level": 1, "text": "Ⅰ. 신청 목적"},
            {
                "type": "paragraph",
                "text": "본 계획은 학교의 AI·디지털 기반 수업 역량을 강화하고 학생 맞춤형 학습 경험을 확대하기 위한 운영 방향을 제시한다.",
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
            {
                "type": "paragraph",
                "text": "정규 수업, 교원 연수, 학생 프로젝트를 연계하여 학기별 실행 과제를 운영한다.",
            },
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
                "사업비 사용 계획",
                "기대 효과",
                "제출 및 확인",
            ],
            "visualReviewRequired": True,
        },
    }

    validation = validate_document_plan(plan)
    if not validation.ok:
        payload = validation.to_dict()
        for issue in payload["issues"]:
            print(
                "[ISSUE] "
                f"{issue['severity']} {issue['code']} at {issue['path']}: "
                f"{issue['message']}"
            )
        for hint in payload["repairHints"]:
            print(f"[HINT] {hint['action']} {hint['path']}: {hint['message']}")
        raise SystemExit(1)

    document = create_document_from_plan(plan)
    try:
        document.save_to_path(output_path)
    finally:
        document.close()

    report = inspect_document_authoring_quality(
        output_path,
        plan=plan,
        quality_profile="operating_plan",
    )
    profile = report["profiles"]["operating_plan"]
    print(f"[OK] wrote: {output_path}")
    print(f"[OK] pass={report['pass']} visual_review_required={report['visual_review_required']}")
    print(f"[OK] operating_plan_score={profile['score']} pass={profile['pass']}")


if __name__ == "__main__":
    main()
