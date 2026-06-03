from hwpx import validate_document_plan
from hwpx.tools.report_parser import parse_government_report_text


def test_parse_government_report_text_returns_valid_document_plan_v2() -> None:
    plan = parse_government_report_text(
        """
# 추진 계획
## 세부 일정
본문입니다.
""",
        title="상반기 보고",
    )

    assert plan["schemaVersion"] == "hwpx.document_plan.v2"
    assert plan["metadata"]["title"] == "상반기 보고"
    assert validate_document_plan(plan).ok is True


def test_parse_government_report_text_recognizes_markdown_and_korean_headings() -> None:
    plan = parse_government_report_text(
        """
# 총괄
Ⅰ. 사업 개요
1. 추진 방향
가. 세부 내용
""",
    )

    headings = [
        (block["level"], block["text"])
        for block in plan["sections"][0]["blocks"]
        if block["type"] == "heading"
    ]
    assert headings == [
        (1, "총괄"),
        (1, "Ⅰ. 사업 개요"),
        (2, "1. 추진 방향"),
        (3, "가. 세부 내용"),
    ]


def test_parse_government_report_text_recognizes_bullets() -> None:
    plan = parse_government_report_text(
        """
□ 주요 과제
○ 세부 과제
- 실행 항목
※ 참고 사항
""",
    )

    bullet_items = [
        item
        for block in plan["sections"][0]["blocks"]
        if block["type"] == "bullets"
        for item in block["items"]
    ]
    assert bullet_items == ["주요 과제", "세부 과제", "실행 항목", "참고 사항"]


def test_parse_government_report_text_recognizes_tab_and_pipe_tables() -> None:
    plan = parse_government_report_text(
        """
항목\t금액\t비고
장비\t1,000\t구입
| 단계 | 기간 | 내용 |
| 준비 | 3월 | 협의 |
""",
    )

    tables = [
        block for block in plan["sections"][0]["blocks"] if block["type"] == "table"
    ]
    assert tables == [
        {"type": "table", "header": ["항목", "금액", "비고"], "rows": [["장비", "1,000", "구입"]]},
        {"type": "table", "header": ["단계", "기간", "내용"], "rows": [["준비", "3월", "협의"]]},
    ]
    assert validate_document_plan(plan).ok is True
