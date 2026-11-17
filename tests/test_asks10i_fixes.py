# SPDX-License-Identifier: Apache-2.0
"""asks10i: what the downstream tools found using the asks10 APIs.

- ``note.copy_to`` left a note's lowercase ``instid`` (other writers', python-hwpx 6.6's) on the copy: two notes of
  one document with one instance id. Hancom writes ``instId`` on every note of ``tests/fixtures/hancom_saved``
  (138), as the engine does.
- ``clear_body``'s refusal names the paragraph and what it holds.
- ``FormField.start``/``end``: where a field begins and ends in its paragraph's text."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_COLUMNS = Path(__file__).parent / "fixtures" / "hancom_saved" / "pages_columns_change_text_after_definition.hwpx"


@pytest.mark.parametrize("spelling", ["instId", "instid"])
def test_a_copied_note_gets_a_new_instance_id_in_either_spelling(spelling: str) -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("본문")
        note = paragraph.add_footnote("각주 원문")
        note.element.attrib.pop("instId")
        note.element.set(spelling, "777")
        copy = note.copy_to(doc.add_paragraph("붙일 곳"))
        assert copy.element.get(spelling) not in (None, "777")
        assert note.element.get(spelling) == "777"
        ids = [node.get("instId") or node.get("instid") for section in doc.sections
               for node in section.element.iter(f"{HP}footNote")]
        assert len(ids) == len(set(ids)) == 2


def test_a_new_note_writes_hancoms_spelling() -> None:
    with HwpxDocument.new() as doc:
        note = doc.add_paragraph("본문").add_footnote("각주")
        assert note.element.get("instId") and note.element.get("instid") is None


def test_a_clear_body_refusal_names_the_paragraph_and_what_it_holds() -> None:
    with HwpxDocument.new() as doc:
        doc.add_paragraph("첫")
        doc.page.set_header(text="머리말")
        with pytest.raises(HwpxValueError) as caught:
            doc.sections[0].clear_body()
        assert caught.value.context["paragraph"] == 0
        assert caught.value.context["paragraphs"] == [{"paragraph": 0, "tags": ["hp:t"]}]
    with HwpxDocument.open(_COLUMNS) as doc:
        donor = HwpxDocument.new()
        donor.notes.add_footnote("주", paragraph=donor.add_paragraph("가"))
        note = donor.paragraphs[0].element.find(f".//{HP}footNote")
        doc.sections[0].paragraphs[11].element.find(f".//{HP}colPr").getparent().append(etree.fromstring(
            etree.tostring(note)))
        with pytest.raises(HwpxValueError) as caught:
            doc.sections[0].clear_body(keep_column_changes=True)
        assert caught.value.context["paragraph"] == 11
        assert caught.value.context["paragraphs"][0]["paragraph"] == 11


def test_a_form_field_reads_where_it_begins_and_ends() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("성명: ")
        paragraph.add_run("홍길동", bold=True)
        paragraph.add_run(" 님")
        paragraph.add_form_field("이름", start=4, end=7)
        field = doc.fields.all[0]
        assert (field.start, field.end) == (4, 7) and paragraph.text[field.start:field.end] == "홍길동"
        paragraph.add_form_field("빈 칸")
        empty = doc.fields.all[1]
        assert empty.start == empty.end == len(paragraph.text)
