from __future__ import annotations

from pathlib import Path
from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety


HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _append(parent, tag: str, attrs: dict[str, str] | None = None):
    child = parent.makeelement(tag, attrs or {})
    parent.append(child)
    return child


def _add_click_here_field(
    doc: HwpxDocument,
    *,
    name: str = "일시",
    prompt: str = "회의 일시",
    value: str = "입력하세요",
) -> None:
    paragraph = doc.add_paragraph("", include_run=False)
    p = paragraph.element
    begin_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    ctrl = _append(begin_run, f"{HP}ctrl", {"type": "FORM", "id": "ctrl-date"})
    field_begin = _append(
        ctrl,
        f"{HP}fieldBegin",
        {
            "id": "field-date",
            "fieldid": "field-date",
            "type": "ClickHere",
            "name": name,
            "prompt": prompt,
        },
    )
    parameters = _append(field_begin, f"{HP}parameters", {"count": "2"})
    _append(parameters, f"{HP}stringParam", {"name": "FieldName"}).text = name
    _append(parameters, f"{HP}stringParam", {"name": "Instruction"}).text = prompt

    text_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    _append(text_run, f"{HP}t").text = value
    end_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    end_ctrl = _append(end_run, f"{HP}ctrl")
    _append(end_ctrl, f"{HP}fieldEnd", {"beginIDRef": "field-date", "fieldid": "field-date"})
    _append(p, f"{HP}lineSegArray")
    paragraph.section.mark_dirty()


def test_list_form_fields_reports_name_prompt_and_current_value() -> None:
    doc = HwpxDocument.new()
    _add_click_here_field(doc)

    fields = doc.list_form_fields()

    assert len(fields) == 1
    assert fields[0]["field_id"] == "field-date"
    assert fields[0]["name"] == "일시"
    assert fields[0]["prompt"] == "회의 일시"
    assert fields[0]["instruction"] == "회의 일시"
    assert fields[0]["current_value"] == "입력하세요"
    assert fields[0]["control_type"] == "FORM"
    assert fields[0]["field_type"] == "ClickHere"
    assert fields[0]["has_end"] is True


def test_fill_form_field_preserves_run_formatting_and_open_safety(tmp_path: Path) -> None:
    path = tmp_path / "form-field.hwpx"
    doc = HwpxDocument.new()
    _add_click_here_field(doc)

    result = doc.fill_form_field("2026-06-11 10:00", name="일시")
    doc.save_to_path(path)

    assert result["ok"] is True
    assert result["before_value"] == "입력하세요"
    assert result["after_value"] == "2026-06-11 10:00"
    assert result["style_preserved"] is True
    assert validate_editor_open_safety(path.read_bytes()).ok is True

    reopened = HwpxDocument.open(path)
    fields = reopened.list_form_fields()
    assert fields[0]["current_value"] == "2026-06-11 10:00"
    paragraph = reopened.paragraphs[fields[0]["paragraph_index"]]
    assert paragraph.element.find(f"{HP}lineSegArray") is None


def test_fill_form_field_rejects_memo_and_hyperlink_fields() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("", include_run=False)
    p = paragraph.element
    for field_type in ("MEMO", "HYPERLINK"):
        run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
        ctrl = _append(run, f"{HP}ctrl", {"type": field_type})
        _append(ctrl, f"{HP}fieldBegin", {"id": field_type.lower(), "type": field_type})
    paragraph.section.mark_dirty()

    assert doc.list_form_fields() == []
