# SPDX-License-Identifier: Apache-2.0
"""asks10c: footnotes, endnotes, bookmarks, click-here fields and highlights at a character of a paragraph.

Each is checked against what Hangul 2024 saved for the same thing in the same document
(``tests/fixtures/hancom_saved``, see its README): the files ``mid_text_*`` and ``highlight_*`` are one
synthetic document in which Hangul put a note, a bookmark or a highlight, the rest of the document untouched.
Taking any of them, the engine writes the same into an untouched paragraph and the paragraph's runs come out
as Hangul's."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _local(node) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _shape(paragraph) -> list:
    shape = []
    for run in paragraph.element.findall(f"{HP}run"):
        children = []
        for child in run:
            name = _local(child)
            if name == "t":
                text = child.text or ""
                for inner in child:
                    text += f"[{_local(inner)}]" + (inner.tail or "")
                children.append(("t", text))
            elif name == "ctrl":
                children.append(("ctrl", "+".join(_local(inner) for inner in child)))
            else:
                children.append((name, ""))
        shape.append((run.get("charPrIDRef"), children))
    return shape


def _open(name: str) -> HwpxDocument:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return HwpxDocument.open(HANCOM / f"{name}.hwpx")


def _hancom_shape(name: str, index: int) -> list:
    with _open(name) as doc:
        return _shape(doc.paragraphs[index])


def test_a_footnote_in_the_middle_of_text_is_written_as_hangul_writes_it() -> None:
    with _open("highlight_in_one_run") as doc:  # paragraph 1 untouched there
        note = doc.notes.add_footnote("각주", paragraph=doc.paragraphs[1], offset=4)
        assert note.offset == 4
        assert _shape(doc.paragraphs[1]) == _hancom_shape("mid_text_footnote", 1)


def test_an_endnote_in_the_middle_of_text_is_written_as_hangul_writes_it() -> None:
    with _open("mid_text_footnote") as doc:
        hancom = _hancom_shape("mid_text_endnote", 2)
        offset = len(hancom[0][1][0][1])  # the characters before Hangul's endnote
        doc.notes.add_endnote("미주", paragraph=doc.paragraphs[2], offset=offset)
        assert _shape(doc.paragraphs[2]) == hancom


def test_a_bookmark_and_a_footnote_in_one_run_as_hangul_writes_them() -> None:
    with _open("highlight_in_one_run") as doc:
        paragraph = doc.paragraphs[2]
        doc.refs.add_bookmark("앞쪽", paragraph=paragraph, offset=2)
        doc.notes.add_footnote("각주", paragraph=paragraph, offset=6)
        assert _shape(paragraph) == _hancom_shape("mid_text_bookmark_and_footnote", 2)
    with _open("highlight_in_one_run") as doc:
        doc.paragraphs[1].add_bookmark("가운데", offset=5)
        assert _shape(doc.paragraphs[1]) == _hancom_shape("mid_text_bookmark", 1)


@pytest.mark.parametrize(("name", "start", "end"), [
    ("highlight_in_one_run", 1, 4),
    ("highlight_across_runs", 2, 8),
    ("highlight_whole_paragraph", 0, 16),
])
def test_a_highlight_range_is_written_as_hangul_writes_it(name: str, start: int, end: int) -> None:
    with _open("mid_text_footnote") as doc:  # paragraph 3 untouched there
        paragraph = doc.paragraphs[3]
        found = doc.text.highlight(paragraph, start=start, end=end)
        assert found.text == paragraph.text[start:end]
        assert _shape(paragraph) == _hancom_shape(name, 3)
        begin = paragraph.element.find(f".//{HP}markpenBegin")
        assert dict(begin.attrib) == {"color": "#FFFF00"}


def test_a_highlight_across_paragraphs_is_one_pair_a_paragraph() -> None:
    with _open("highlight_in_one_run") as doc:  # paragraphs 1 and 2 untouched there
        first, second = doc.paragraphs[1], doc.paragraphs[2]
        hancom = (_hancom_shape("highlight_two_paragraphs", 1), _hancom_shape("highlight_two_paragraphs", 2))
        start = len(hancom[0][0][1][0][1].split("[")[0])
        end = len(hancom[1][0][1][0][1].split("[markpenEnd]")[0].replace("[markpenBegin]", ""))
        found = doc.text.highlight_span(first, start, second, end)
        assert len(found) == 2
        assert (_shape(first), _shape(second)) == hancom


def test_a_highlight_overlapping_another_is_refused_and_writes_nothing() -> None:
    with _open("highlight_in_one_run") as doc:
        paragraph = doc.paragraphs[3]
        before = _shape(paragraph)
        with pytest.raises(HwpxError) as caught:
            doc.text.highlight(paragraph, start=3, end=6)
        assert caught.value.code == "paragraph-range-splits-mark"
        with pytest.raises(HwpxError) as caught:
            doc.text.highlight_span(doc.paragraphs[2], 0, paragraph, 3)
        assert caught.value.code == "paragraph-range-splits-mark"
        assert _shape(paragraph) == before and "markpen" not in str(_shape(doc.paragraphs[2]))
        with pytest.raises(HwpxError) as caught:
            doc.text.highlight(paragraph, "앞", start=0, end=1)
        assert caught.value.code == "paragraph-range-invalid"


def test_a_click_here_field_wraps_text_across_runs() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("성명: ")
        paragraph.add_run("홍길동", bold=True)
        paragraph.add_run(" 님")
        paragraph.add_form_field("이름", start=4, end=8)
        assert paragraph.text == "성명: 홍길동 님"
        kinds = [(c, k) for _, children in _shape(paragraph) for c, k in children if c != "secPr"]
        assert ("ctrl", "fieldBegin") in kinds and ("ctrl", "fieldEnd") in kinds
        begin = paragraph.element.find(f".//{HP}fieldBegin")
        end = paragraph.element.find(f".//{HP}fieldEnd")
        runs = paragraph.element.findall(f"{HP}run")
        holder = [run for run in runs if begin in list(run.iter())][0]
        closer = [run for run in runs if end in list(run.iter())][0]
        assert holder is not closer  # the value crosses runs: each control in the run it falls in
        reopened = HwpxDocument.open(doc.to_bytes())
        assert [f.name for f in reopened.fields.all] == ["이름"]
        with pytest.raises(HwpxError) as caught:
            paragraph.add_form_field("둘", start=0, end=6)  # holds this field's begin only
        assert caught.value.code == "paragraph-range-splits-field"
        with pytest.raises(HwpxError) as caught:
            paragraph.add_form_field("셋", start=1)
        assert caught.value.code == "paragraph-range-invalid"


def test_a_note_moves_and_copies_to_a_character() -> None:
    with _open("mid_text_footnote") as doc:
        note = doc.paragraphs[1].footnotes[0]
        copy = note.copy_to(doc.paragraphs[2], offset=2)
        assert copy.offset == 2 and copy.inst_id != note.inst_id
        assert [n.element.get("number") for p in doc.paragraphs for n in p.footnotes] == ["1", "2"]
        note.move_to(doc.paragraphs[2], offset=6)
        assert not doc.paragraphs[1].footnotes
        assert [n.offset for n in doc.paragraphs[2].footnotes] == [2, 6]
        with pytest.raises(HwpxError) as caught:
            copy.move_to(copy.body_paragraph)
        assert caught.value.code == "paragraph-move-place-unsupported"
        with HwpxDocument.new() as other:
            with pytest.raises(HwpxError) as caught:
                copy.copy_to(other.add_paragraph("다른 문서"))
            assert caught.value.code == "note-other-document-unsupported"


def test_a_bad_offset_writes_nothing() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나")
        before = _shape(paragraph)
        for call in (lambda: paragraph.add_bookmark("책", offset=5),
                     lambda: doc.notes.add_footnote("각주", paragraph=paragraph, offset=9)):
            with pytest.raises(HwpxError) as caught:
                call()
            assert caught.value.code == "paragraph-range-invalid"
        assert _shape(paragraph) == before


def test_a_highlight_across_runs_reads_whole() -> None:
    # doc.text.highlights read one hp:t at a time and gave only the first run's part of Hangul's highlight
    expected = {"highlight_in_one_run": ["부분글"], "highlight_across_runs": ["분글자굵은부"],
                "highlight_whole_paragraph": ["앞부분글자굵은부분글자뒷부분글자"],
                "highlight_two_paragraphs": ["카타파하", "하나둘"]}
    for name, texts in expected.items():
        with _open(name) as doc:
            assert [found.text for found in doc.text.highlights] == texts


def test_a_note_moved_within_its_paragraph_counts_offset_the_same_before_and_after() -> None:
    # a note takes no character: the offset it is moved to is the same counted before or after the move,
    # as for an object's move_to(offset=)
    with _open("mid_text_footnote") as doc:
        paragraph = doc.paragraphs[1]  # 가나다라 + note(4) + 마바사…
        note = paragraph.footnotes[0]
        note.move_to(paragraph, offset=10)
        assert note.offset == 10 and paragraph.text == "가나다라마바사아자차카타파하"
        note.move_to(paragraph, offset=2)
        assert note.offset == 2
        assert [run_children for _, run_children in _shape(paragraph)] == [
            [("t", "가나"), ("ctrl", "footNote"), ("t", "다라마바사아자차카타파하")]]


def test_a_field_wrapping_text_keeps_its_prompt_memo_and_editable() -> None:
    # Hancom keeps a filled click-here field's 안내문 in its Direction parameter (field_value_shape_filled)
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("성명: 홍길동")
        field = paragraph.add_form_field("이름", start=4, end=7, prompt="이름을 쓰세요", memo="도움말", editable=False)
        begin = field.element
        params = {node.get("name"): node.text for node in begin.iter(f"{HP}stringParam")}
        assert params["Direction"] == "이름을 쓰세요" and params["HelpState"] == "도움말"
        assert begin.get("editable") == "0" and begin.get("type") == "CLICK_HERE"
        assert paragraph.text == "성명: 홍길동"  # no prompt run: the field holds its value
        reopened = HwpxDocument.open(doc.to_bytes())
        found = reopened.fields.all[0]
        assert found.name == "이름"
