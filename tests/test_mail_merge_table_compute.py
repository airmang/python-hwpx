from __future__ import annotations

import csv
from pathlib import Path
from zipfile import ZipFile

from hwpx import (
    HwpxDocument,
    create_document_from_plan,
    inspect_mail_merge_placeholders,
    mail_merge,
    table_compute,
    validate_document_plan,
)
from hwpx.tools.package_validator import validate_editor_open_safety


def _template(path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("{{student}} 보호자님께")
    doc.add_paragraph("학급: {{class_name}} / 담당: ${teacher}")
    doc.save_to_path(path)
    doc.close()


def test_mail_merge_generates_outputs_zip_and_row_reports(tmp_path: Path) -> None:
    template = tmp_path / "notice-template.hwpx"
    _template(template)
    csv_path = tmp_path / "rows.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["student", "class_name", "teacher"])
        writer.writeheader()
        writer.writerow({"student": "김하나", "class_name": "1-1", "teacher": "이교사"})
        writer.writerow({"student": "박두리", "class_name": "1-2", "teacher": ""})

    report = mail_merge(
        template,
        csv_path,
        output_dir=tmp_path / "out",
        filename_pattern="{index:03d}-{student}.hwpx",
        zip_path=tmp_path / "letters.zip",
    )

    assert report["rowCount"] == 2
    assert report["createdCount"] == 2
    assert report["openSafety"]["ok"] is True
    assert report["rowsWithIssues"] == [2]
    assert report["rows"][0]["openSafety"]["ok"] is True
    assert report["rows"][1]["missingKeys"] == ["teacher"]
    assert report["zip"]["entryCount"] == 2
    with ZipFile(tmp_path / "letters.zip") as archive:
        assert sorted(archive.namelist()) == ["001-김하나.hwpx", "002-박두리.hwpx"]

    merged = HwpxDocument.open(report["rows"][0]["filename"])
    try:
        text = merged.export_text()
        assert "김하나 보호자님께" in text
        assert "이교사" in text
    finally:
        merged.close()


def test_mail_merge_hundred_outputs_are_open_safe(tmp_path: Path) -> None:
    template = tmp_path / "certificate-template.hwpx"
    _template(template)
    rows = [
        {"student": f"학생{index:03d}", "class_name": "3-1", "teacher": "담임"}
        for index in range(1, 101)
    ]

    report = mail_merge(template, rows, output_dir=tmp_path / "hundred", filename_pattern="{index:03d}.hwpx")

    assert report["ok"] is True
    assert report["verification"]["openSafety"]["checkedCount"] == 100
    assert report["createdCount"] == 100
    assert all(row["openSafety"]["ok"] for row in report["rows"])
    assert validate_editor_open_safety(report["rows"][-1]["filename"]).ok is True


def test_inspect_mail_merge_placeholders_lists_keys(tmp_path: Path) -> None:
    template = tmp_path / "template.hwpx"
    _template(template)

    report = inspect_mail_merge_placeholders(template)

    assert report["keys"] == ["class_name", "student", "teacher"]


def test_table_compute_appends_sum_average_and_subtotals_to_plan_table() -> None:
    block = {
        "type": "table",
        "columns": [
            {"key": "dept", "label": "부서"},
            {"key": "item", "label": "항목"},
            {"key": "amount", "label": "금액"},
        ],
        "rows": [
            {"dept": "교육", "item": "연수", "amount": "1,000"},
            {"dept": "교육", "item": "교재", "amount": "500"},
            {"dept": "시설", "item": "수선", "amount": "2,000"},
        ],
    }

    report = table_compute(
        block,
        value_columns=["amount"],
        operations=["subtotal", "sum", "average"],
        group_by="dept",
        label_column="item",
    )

    rows = report["computedTable"]["rows"]
    assert rows[2]["item"] == "교육 소계"
    assert rows[2]["amount"] == "1,500"
    assert rows[-2]["item"] == "합계"
    assert rows[-2]["amount"] == "3,500"
    assert rows[-1]["item"] == "평균"
    assert rows[-1]["amount"] == "1,166.666666666666666666666667"
    assert any(item["operation"] == "subtotal" for item in report["evidence"])


def test_table_compute_appends_row_columns_and_generates_valid_plan(tmp_path: Path) -> None:
    block = {
        "type": "table",
        "header": ["이름", "1월", "2월"],
        "rows": [["A", "1,000", "2,000"], ["B", "500", "700"]],
    }

    report = table_compute(block, value_columns=["1월", "2월"], operations=["sum", "average"], append="both")
    computed = report["computedTable"]
    plan = {"schemaVersion": "hwpx.document_plan.v2", "sections": [{"blocks": [computed]}]}

    assert computed["header"] == ["이름", "1월", "2월", "합계", "평균"]
    assert computed["rows"][0][-2:] == ["3,000", "1,500"]
    assert validate_document_plan(plan).ok is True

    target = tmp_path / "computed.hwpx"
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(target)
    finally:
        document.close()
    assert validate_editor_open_safety(target).ok is True
