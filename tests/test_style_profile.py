from __future__ import annotations

from pathlib import Path

from hwpx import (
    HwpxDocument,
    apply_style_profile_to_plan,
    compare_style_profiles,
    create_document_from_plan,
    describe_template,
    extract_style_profile,
    list_templates,
    register_template,
    validate_document_plan,
)
from hwpx.tools.package_validator import validate_editor_open_safety

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _reference_doc(path: Path, *, placeholders: bool = False) -> None:
    document = HwpxDocument.new()
    document.set_page_size(width=72000, height=36000, orientation="LANDSCAPE")
    document.set_page_margins(
        left=7000,
        right=5000,
        top=3000,
        bottom=3000,
        header=1500,
        footer=1600,
        gutter=1000,
    )
    rich_style = document.ensure_run_style(bold=True, font="함초롬바탕", size=12, color="#224466")
    document.add_paragraph("{{student}} 안내" if placeholders else "참조 서식", char_pr_id_ref=rich_style)
    table = document.add_table(2, 3, width=30000)
    table.set_column_widths([2, 1, 1])
    table.set_cell_text(0, 0, "구분")
    table.set_cell_text(0, 1, "내용")
    table.set_cell_text(0, 2, "비고")
    table.set_cell_text(1, 0, "A")
    table.set_cell_text(1, 1, "${teacher}" if placeholders else "본문")
    table.set_cell_text(1, 2, "확인")
    cell = table.cell(1, 0)
    margin = cell.element.find(f"{HP}cellMargin")
    assert margin is not None
    margin.set("left", "11")
    margin.set("right", "12")
    margin.set("top", "13")
    margin.set("bottom", "14")
    table.mark_dirty()
    document.save_to_path(path)
    document.close()


def test_extract_style_profile_apply_to_plan_and_compare(tmp_path: Path) -> None:
    reference = tmp_path / "reference.hwpx"
    target = tmp_path / "styled.hwpx"
    _reference_doc(reference)

    profile = extract_style_profile(reference)
    assert profile["schemaVersion"] == "hwpx.style-profile.v1"
    assert profile["page"]["orientation"] == "LANDSCAPE"
    assert profile["tables"][0]["columnWeights"] == [0.5, 0.25, 0.25]

    plan = {
        "schemaVersion": "hwpx.document_plan.v2",
        "title": "이식 결과",
        "sections": [
            {
                "blocks": [
                    {"type": "heading", "level": 1, "text": "이식 결과"},
                    {
                        "type": "table",
                        "header": ["구분", "내용", "비고"],
                        "rows": [["A", "본문", "확인"], ["B", "추가", ""]],
                    },
                ]
            }
        ],
    }
    styled_plan = apply_style_profile_to_plan(plan, profile)
    assert styled_plan["sections"][0]["page"]["orientation"] == "LANDSCAPE"
    assert styled_plan["sections"][0]["blocks"][1]["columnWidths"] == [0.5, 0.25, 0.25]
    assert validate_document_plan(styled_plan).ok is True

    document = create_document_from_plan(styled_plan)
    try:
        document.save_to_path(target)
    finally:
        document.close()
    assert validate_editor_open_safety(target).ok is True
    comparison = compare_style_profiles(profile, target)
    assert comparison["pass"] is True


def test_template_registry_lists_describes_and_reports_unfilled_placeholders(tmp_path: Path) -> None:
    template = tmp_path / "notice-template.hwpx"
    registry = tmp_path / "registry.json"
    _reference_doc(template, placeholders=True)

    entry = register_template(
        "notice",
        template,
        registry_path=registry,
        description="student notice",
        tags=["school"],
    )
    listed = list_templates(registry_path=registry)
    described = describe_template("notice", registry_path=registry, values={"student": "김하나"})

    assert entry["placeholderKeys"] == ["student", "teacher"]
    assert listed["templates"][0]["name"] == "notice"
    assert described["placeholderReport"]["missingKeys"] == ["teacher"]
    assert described["styleProfile"]["page"]["orientation"] == "LANDSCAPE"
