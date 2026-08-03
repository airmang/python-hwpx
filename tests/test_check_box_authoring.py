# SPDX-License-Identifier: Apache-2.0
"""체크박스 양식개체 저작 계약 테스트 (specs/060 P0 실측 계약).

실한컴 실측으로 확정된 불변식을 고정한다:
- ``value`` 어휘는 ``CHECKED``/``UNCHECKED``(각각 ☑/□로 렌더)
- **``<hp:formCharPr>``는 필수 자식** — 없으면 한컴이 문서를 거부한다
  (단일 변인 프로브로 확정). 구조 검증(open-safety/ID 무결성)은 이 결함을
  잡지 못하므로 방출 형상 자체를 테스트로 고정한다.
- ``<hp:checkBtn>``은 ``<hp:ctrl>`` 래핑 없이 run 직속 자식(누름틀과 다름)
"""

from __future__ import annotations

import zipfile

import pytest

from hwpx.document import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _section_xml(path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "".join(
            archive.read(name).decode("utf-8")
            for name in sorted(archive.namelist())
            if name.endswith("section0.xml")
        )


def test_add_check_box_emits_the_measured_hancom_shape(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_check_box("동의합니다", checked=True, name="Agree")
    path = tmp_path / "checkbox.hwpx"
    doc.save_to_path(path)
    doc.close()

    xml = _section_xml(path)
    assert '<hp:checkBtn' in xml
    assert 'value="CHECKED"' in xml
    assert 'caption="동의합니다"' in xml
    assert 'name="Agree"' in xml
    # 필수 자식 3종 — formCharPr 누락은 실한컴 거부 사유다.
    for child in ("formCharPr", "sz", "pos"):
        assert f"<hp:{child}" in xml, f"missing mandatory child: {child}"
    # 누름틀과 달리 ctrl 래핑을 쓰지 않는다.
    assert "<hp:ctrl><hp:checkBtn" not in xml


def test_check_box_children_are_inside_the_element(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_check_box("자식 위치", checked=False)
    path = tmp_path / "children.hwpx"
    doc.save_to_path(path)
    doc.close()

    reopened = HwpxDocument.open(path)
    checks = [
        element
        for section in reopened.sections
        for element in section.element.iter(f"{HP}checkBtn")
    ]
    assert len(checks) == 1
    names = [child.tag.split("}")[-1] for child in checks[0]]
    assert "formCharPr" in names and "sz" in names and "pos" in names
    reopened.close()


def test_unchecked_is_the_default_and_round_trips(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_check_box("기본 상태")
    path = tmp_path / "default.hwpx"
    doc.save_to_path(path)
    doc.close()

    assert 'value="UNCHECKED"' in _section_xml(path)
    reopened = HwpxDocument.open(path)
    boxes = reopened.list_check_boxes()
    assert [b["caption"] for b in boxes] == ["기본 상태"]
    assert boxes[0]["checked"] is False
    reopened.close()


def test_list_and_set_by_index_and_name(tmp_path) -> None:
    doc = HwpxDocument.new()
    doc.add_check_box("첫째", name="First")
    doc.add_check_box("둘째", checked=True, name="Second")

    listed = doc.list_check_boxes()
    assert [(b["index"], b["name"], b["checked"]) for b in listed] == [
        (0, "First", False),
        (1, "Second", True),
    ]

    assert doc.set_check_box(True, index=0)["checked"] is True
    assert doc.set_check_box(False, name="Second")["value"] == "UNCHECKED"
    assert [b["checked"] for b in doc.list_check_boxes()] == [True, False]

    path = tmp_path / "toggled.hwpx"
    doc.save_to_path(path)
    doc.close()
    reopened = HwpxDocument.open(path)
    assert [b["checked"] for b in reopened.list_check_boxes()] == [True, False]
    reopened.close()


def test_selector_and_caption_refusals_are_typed() -> None:
    doc = HwpxDocument.new()
    doc.add_check_box("하나", name="Dup")
    doc.add_check_box("둘", name="Dup")

    with pytest.raises(ValueError, match="exactly one of index or name"):
        doc.set_check_box(True)
    with pytest.raises(ValueError, match="exactly one of index or name"):
        doc.set_check_box(True, index=0, name="Dup")
    with pytest.raises(ValueError, match="ambiguous"):
        doc.set_check_box(True, name="Dup")
    with pytest.raises(ValueError, match="not found"):
        doc.set_check_box(True, name="없는이름")
    with pytest.raises(ValueError, match="index not found"):
        doc.set_check_box(True, index=99)
    with pytest.raises(ValueError, match="non-empty"):
        doc.add_check_box("   ")
    doc.close()


def test_check_box_inside_a_table_cell(tmp_path) -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    cell_paragraph = table.rows[0].cells[1].paragraphs[0]
    cell_paragraph.add_check_box("셀 안", checked=True)

    path = tmp_path / "cell.hwpx"
    doc.save_to_path(path)
    doc.close()

    reopened = HwpxDocument.open(path)
    boxes = reopened.list_check_boxes()
    assert [(b["caption"], b["checked"]) for b in boxes] == [("셀 안", True)]
    reopened.close()


def test_authored_document_passes_open_safety(tmp_path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    doc.add_check_box("열림 안전", checked=True)
    path = tmp_path / "safe.hwpx"
    doc.save_to_path(path)
    doc.close()

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True
