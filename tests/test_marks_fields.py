# SPDX-License-Identifier: Apache-2.0
"""누름틀 지우기·속성 쓰기, 라디오 단추·콤보 상자·입력 상자 읽기와 값 쓰기."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects import ComboBox, EditBox, RadioButton

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent / "data"
HWPXLIB = FIXTURES / "hwpxlib_corpus"


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not [issue for issue in again.validate().issues if issue.severity == "error"]
    return again


def _doc_with_field(value: str | None = None) -> tuple[HwpxDocument, object]:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("이름: ")
    field = doc.fields.add("성명", prompt="이름을 쓰세요", memo="한글로", paragraph=paragraph)
    if value is not None:
        field.value = value
    paragraph.add_run(" 끝")
    return doc, paragraph


def test_remove_field_keeps_its_text_by_default() -> None:
    doc, paragraph = _doc_with_field("홍길동")
    field = doc.fields.all[0]
    field.remove()
    assert doc.fields.all == ()
    assert paragraph.text == "이름: 홍길동 끝"
    assert paragraph.element.find(f".//{HP}fieldBegin") is None
    assert paragraph.element.find(f".//{HP}fieldEnd") is None
    assert paragraph.element.find(f"{HP}linesegarray") is None
    assert _reopen(doc).paragraphs[-1].text == "이름: 홍길동 끝"


def test_remove_field_with_its_text() -> None:
    doc, paragraph = _doc_with_field("홍길동")
    doc.fields.all[0].remove(keep_text=False)
    assert doc.fields.all == ()
    assert paragraph.text == "이름:  끝"
    _reopen(doc)


def _field_over_two_paragraphs() -> tuple[HwpxDocument, object, object]:
    """A field whose end sits in the next paragraph, as Hancom saves a field holding a
    paragraph break: ``이름: [가`` / ``나] 뒤``."""

    doc, paragraph = _doc_with_field("가")
    end_run = [run for run in paragraph.element.findall(f"{HP}run") if run.find(f"{HP}ctrl/{HP}fieldEnd") is not None][0]
    tail = [run for run in paragraph.element.findall(f"{HP}run")][-1]
    following = doc.add_paragraph("나")
    paragraph.element.remove(end_run)
    paragraph.element.remove(tail)
    following.element.append(end_run)
    following.add_run(" 뒤")
    return doc, paragraph, following


def test_field_running_over_paragraphs_reads_one_line_per_paragraph() -> None:
    doc, _, _ = _field_over_two_paragraphs()
    (field,) = doc.fields.all
    assert field.value == "가\n나" and field.has_end


def test_remove_field_running_over_paragraphs_with_its_text() -> None:
    doc, paragraph, _ = _field_over_two_paragraphs()
    count = len(doc.paragraphs)
    doc.fields.all[0].remove(keep_text=False)
    assert doc.fields.all == ()
    assert len(doc.paragraphs) == count - 1
    assert paragraph.text == "이름:  뒤"
    _reopen(doc)


def test_remove_field_running_over_paragraphs_keeps_both_paragraphs() -> None:
    doc, paragraph, following = _field_over_two_paragraphs()
    doc.fields.all[0].remove()
    assert doc.fields.all == ()
    assert (paragraph.text, following.text) == ("이름: 가", "나 뒤")
    assert following.element.find(f".//{HP}fieldEnd") is None
    _reopen(doc)


def test_field_name_prompt_memo_and_editable_can_be_written() -> None:
    doc, paragraph = _doc_with_field()
    field = doc.fields.all[0]
    assert field.is_placeholder and field.value == "이름을 쓰세요"
    field.name = "대표자"
    field.prompt = "대표자 이름"
    field.memo = "직위 없이"
    field.editable = False
    assert (field.name, field.prompt, field.memo, field.editable) == ("대표자", "대표자 이름", "직위 없이", False)
    again = _reopen(doc).fields.all[0]
    assert (again.name, again.prompt, again.memo, again.editable) == ("대표자", "대표자 이름", "직위 없이", False)
    assert again.value == "대표자 이름" and again.is_placeholder  # 안내문이 보이던 칸은 새 안내문을 보인다
    command = [p.text for p in again.element.iter(f"{HP}stringParam") if p.get("name") == "Command"][0]
    assert command == "Clickhere:set:53:Direction:wstring:6:대표자 이름 HelpState:wstring:5:직위 없이  "


def test_prompt_change_leaves_an_entered_value() -> None:
    doc, _ = _doc_with_field("홍길동")
    field = doc.fields.all[0]
    field.prompt = "새 안내"
    assert doc.fields.all[0].value == "홍길동"


def test_hancom_gold_field_rename_and_remove() -> None:
    doc = HwpxDocument.open((DATA / "clickhere_gold_filled.hwpx").read_bytes())
    field = doc.fields.all[0]
    paragraph_text = field.value
    field.prompt = "DIR"
    again = _reopen(doc).fields.all[0]
    assert again.prompt == "DIR" and again.memo == "MEMOTEXT_TWO" and again.value == paragraph_text
    doc.fields.all[0].remove()
    reopened = _reopen(doc)
    assert reopened.fields.all == ()
    assert any(paragraph_text in p.text for p in reopened.paragraphs)


def test_remove_a_field_from_a_hancom_saved_form_leaves_other_parts() -> None:
    original = (DATA / "clickhere_gold_empty.hwpx").read_bytes()
    doc = HwpxDocument.open(original)
    doc.fields.all[0].remove(keep_text=False)
    data = doc.to_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as a, zipfile.ZipFile(io.BytesIO(data)) as b:
        changed = {n for n in a.namelist() if a.read(n) != b.read(n)}
    assert changed and all(n.startswith("Contents/section") for n in changed)
    again = HwpxDocument.open(data)
    assert again.fields.all == ()
    assert "DIRTEXT_ONE" not in "".join(p.text for p in again.paragraphs)


def test_radio_buttons_read_and_check_from_a_hancom_saved_document() -> None:
    doc = HwpxDocument.open((HWPXLIB / "reader_writer__SimpleButtons.hwpx").read_bytes())
    buttons = doc.fields.radio_buttons
    assert len(buttons) == 1 and isinstance(buttons[0], RadioButton)
    button = buttons[0]
    assert (button.name, button.caption, button.checked, button.group) == ("RadioButton1", "라디오 단추1", False, "")
    button.checked = True
    assert _reopen(doc).fields.radio_buttons[0].checked
    assert len(doc.fields.check_boxes) == 1  # 라디오 단추는 체크박스로 세지 않는다


def test_radio_group_keeps_one_checked() -> None:
    doc = HwpxDocument.open((HWPXLIB / "reader_writer__SimpleButtons.hwpx").read_bytes())
    element = doc.fields.radio_buttons[0].element
    element.set("radioGroupName", "성별")
    twin = element.makeelement(element.tag, dict(element.attrib))
    twin.set("name", "RadioButton2")
    twin.set("value", "CHECKED")
    element.getparent().append(twin)
    first, second = doc.fields.radio_buttons
    first.checked = True
    assert first.checked and not second.checked


def test_combo_box_items_and_value() -> None:
    doc = HwpxDocument.open((HWPXLIB / "reader_writer__SimpleComboBox.hwpx").read_bytes())
    (box,) = doc.fields.combo_boxes
    assert isinstance(box, ComboBox)
    assert box.name == "ComboBox1" and box.items == (("", ""),) and box.value == "" and box.editable_text
    box.value = "직접 쓴 값"
    assert _reopen(doc).fields.combo_boxes[0].value == "직접 쓴 값"
    box.element.set("editEnable", "0")
    with pytest.raises(HwpxValueError) as excinfo:
        box.value = "없는 항목"
    assert excinfo.value.code == "field-choice-unknown"


def test_edit_box_text() -> None:
    doc = HwpxDocument.open((HWPXLIB / "reader_writer__SimpleEdit.hwpx").read_bytes())
    (box,) = doc.fields.edit_boxes
    assert isinstance(box, EditBox)
    assert (box.name, box.text, box.multi_line, box.read_only) == ("Edit1", "1234", False, False)
    box.text = "5678\n9"
    assert _reopen(doc).fields.edit_boxes[0].text == "5678 9"
