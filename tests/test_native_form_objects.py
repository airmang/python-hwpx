# SPDX-License-Identifier: Apache-2.0
"""라디오 단추·콤보 상자·입력 상자 만들기 (``doc.fields.add_radio_button`` / ``add_combo_box`` /
``add_edit_box``), the way ``add_check_box`` makes a check box.

Each is written as Hancom writes a new one: the element order and attributes of the
Hancom-saved ``reader_writer__SimpleButtons`` / ``SimpleComboBox`` / ``SimpleEdit`` samples. The
created object reads back through the readers (``doc.fields.radio_buttons`` …) as the same live
view type, the document saves, reopens and validates, and only the section part changes.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.objects import ComboBox, EditBox, RadioButton

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HWPXLIB = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
BUTTONS = HWPXLIB / "reader_writer__SimpleButtons.hwpx"
COMBO = HWPXLIB / "reader_writer__SimpleComboBox.hwpx"
EDIT = HWPXLIB / "reader_writer__SimpleEdit.hwpx"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(document.to_bytes())
    assert not reopened.validate().issues
    return reopened


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _changed_parts(before: bytes, after: bytes) -> set[str]:
    old, new = _parts(before), _parts(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


def _shape(element) -> tuple[list[str], list[str]]:
    """Attribute names in order and child element names in order."""
    return list(element.attrib), [etree.QName(child).localname for child in element]


def _hancom(path: Path, local: str):
    return next(HwpxDocument.open(path).sections[0].element.iter(f"{HP}{local}"))


@pytest.mark.parametrize(
    ("make", "local", "sample"),
    [
        (lambda d: d.fields.add_radio_button("예"), "radioBtn", BUTTONS),
        (lambda d: d.fields.add_combo_box("가"), "comboBox", COMBO),
        (lambda d: d.fields.add_edit_box("1234"), "edit", EDIT),
    ],
)
def test_a_new_form_object_has_the_shape_hancom_saves(make, local, sample) -> None:
    created = make(HwpxDocument.new()).element
    assert etree.QName(created).localname == local
    assert _shape(created) == _shape(_hancom(sample, local))
    assert etree.QName(created.getparent()).localname == "run"  # a run's child, set as a character
    assert created.find(f"{HP}pos").get("treatAsChar") == "1"


def test_new_objects_take_the_values_hancom_gives_a_new_one() -> None:
    # The values of Hancom's own new objects (SimpleButtons/SimpleComboBox and the Hancom-made public
    # samples form-01.hwp/form-02.hwp as Hancom opens them): an edit box masks nothing.
    document = HwpxDocument.new()
    radio = document.fields.add_radio_button("예").element
    combo = document.fields.add_combo_box().element
    edit = document.fields.add_edit_box().element
    assert (radio.get("backColor"), radio.get("borderTypeIDRef"), radio.find(f"{HP}sz").get("width")) == (
        "#FFFFFF", "0", "8504")
    assert (combo.get("backColor"), combo.get("borderTypeIDRef"), combo.get("listBoxRows"), combo.get("editEnable")) == (
        "#F0F0F0", "5", "10", "1")
    assert (edit.get("passwordChar"), edit.get("backColor"), edit.get("borderTypeIDRef"), edit.get("maxLength")) == (
        "", "#F0F0F0", "5", "2147483647")
    assert [e.get("tabOrder") for e in (radio, combo, edit)] == ["1", "2", "3"]
    assert [e.get("name") for e in (radio, combo, edit)] == ["RadioButton1", "ComboBox1", "Edit1"]


def test_add_radio_button_reads_back_and_checks_within_its_group() -> None:
    document = HwpxDocument.open(BUTTONS)
    before = document.to_bytes()
    first = document.fields.add_radio_button("예", group="동의", checked=True)
    second = document.fields.add_radio_button("아니오", group="동의", paragraph=first.paragraph)
    assert isinstance(first, RadioButton) and isinstance(second, RadioButton)
    assert (first.caption, first.group, first.checked, second.checked) == ("예", "동의", True, False)
    assert first.name == "RadioButton2" and second.name == "RadioButton3"  # the sample has RadioButton1
    assert first.element.get("tabOrder") == "4"  # after the sample's three objects
    second.checked = True
    assert not first.checked
    reopened = _reopen(document)
    assert [(b.caption, b.group, b.checked) for b in reopened.fields.radio_buttons] == [
        ("라디오 단추1", "", False), ("예", "동의", False), ("아니오", "동의", True),
    ]
    assert _changed_parts(before, document.to_bytes()) == {"Contents/section0.xml"}


def test_add_combo_box_keeps_its_text_as_hancom_does() -> None:
    document = HwpxDocument.open(COMBO)
    box = document.fields.add_combo_box("서울", editable_text=False, name="도시")
    assert isinstance(box, ComboBox)
    assert (box.name, box.text, box.items, box.value, box.editable_text) == ("도시", "서울", (("", "서울"),), "", False)
    hancom = HwpxDocument.open(COMBO).fields.combo_boxes[0]
    assert (hancom.text, hancom.items) == ("", (("", ""),))
    box.text = "부산"
    reopened = _reopen(document)
    assert [b.text for b in reopened.fields.combo_boxes] == ["", "부산"]


def test_add_edit_box_text_lines_and_read_only() -> None:
    document = HwpxDocument.open(EDIT)
    one_line = document.fields.add_edit_box("가\n나")
    many = document.fields.add_edit_box("가\n나", multi_line=True, read_only=True, name="메모")
    assert isinstance(one_line, EditBox) and isinstance(many, EditBox)
    assert (one_line.text, one_line.multi_line, one_line.read_only, one_line.name) == ("가 나", False, False, "Edit2")
    assert (many.text, many.multi_line, many.read_only, many.name) == ("가\n나", True, True, "메모")
    reopened = _reopen(document)
    assert [b.text for b in reopened.fields.edit_boxes] == ["1234", "가 나", "가\n나"]


def test_form_objects_go_into_a_given_paragraph_or_a_table_cell() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 2)
    holder = table.paragraph.element
    cell_paragraph = table.cell(0, 1).paragraphs[0]
    box = document.fields.add_edit_box("칸", paragraph=cell_paragraph)
    assert box.paragraph is not None and box.paragraph.element is cell_paragraph.element
    assert holder.find(f"{HP}linesegarray") is None
    count = len(document.paragraphs)
    document.fields.add_combo_box(paragraph=0)
    assert len(document.paragraphs) == count  # into paragraph 0, no new paragraph
    _reopen(document)


@pytest.mark.parametrize(
    ("call", "code"),
    [
        (lambda d: d.fields.add_radio_button(""), "field-radio-caption-empty"),
        (lambda d: d.fields.add_radio_button("예", group=3), "field-radio-group-value"),
        (lambda d: d.fields.add_combo_box(5), "field-form-text-value"),
        (lambda d: d.fields.add_edit_box(None), "field-form-text-value"),
    ],
)
def test_bad_arguments_are_refused_before_anything_is_added(call, code) -> None:
    document = HwpxDocument.new()
    before = document.to_bytes()
    with pytest.raises(HwpxError) as excinfo:
        call(document)
    assert excinfo.value.code == code and excinfo.value.suggestion
    assert document.to_bytes() == before
