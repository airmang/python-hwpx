# SPDX-License-Identifier: Apache-2.0
"""asks10b: text put in at a position, a range taken out, and a range moved or copied
(``insert_text``, ``delete_range``, ``move_range``, ``copy_range``) and ``set_text_preserving_runs`` with
tabs already in the text.

Positions count as ``paragraph.text`` does. What Hangul 2024 writes for the same things is in
``tests/fixtures/hancom_saved`` (see its README): a note or a bookmark in the middle of a run's text stays in
that run between two ``hp:t`` (``mid_text_*``); a highlight's start and end sit once each inside the ``hp:t``
of the runs they fall in (``highlight_*``)."""

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
    """The paragraph as Hancom writes it: per run its charPrIDRef and children, an ``hp:t`` as its text with
    ``[name]`` for each element inside, a control as its control's name."""

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


# -- insert_text ---------------------------------------------------------------------------------


def test_text_goes_in_at_its_place_in_the_run_of_the_character_before() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나다라")
        paragraph.add_run("굵게", bold=True)
        bold = paragraph.runs[-1].char_pr_id_ref
        runs = paragraph.insert_text(2, "XY")
        assert paragraph.text == "가나XY다라굵게"
        assert [run.text for run in runs] == ["가나XY다라"]
        paragraph.insert_text(6, "Z")  # at a run boundary: the run of the character before
        assert paragraph.text == "가나XY다라Z굵게"
        assert paragraph.runs[-2].text == "가나XY다라Z" and paragraph.runs[-1].char_pr_id_ref == bold


def test_tabs_and_line_breaks_go_in_as_hancom_writes_them() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나")
        paragraph.insert_text(1, "\t다\n")
        assert paragraph.text == "가\t다\n나"
        assert _shape(paragraph)[-1] == ("0", [("t", "가[tab]다[lineBreak]나")])


def test_text_with_a_shape_of_its_own_is_a_run_of_its_own() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나다라")
        runs = paragraph.insert_text(2, "굵", bold=True)
        assert paragraph.text == "가나굵다라"
        assert [run.text for run in runs] == ["굵"] and runs[0].bold
        shapes = _shape(paragraph)[-3:]
        assert [children for _, children in shapes] == [[("t", "가나")], [("t", "굵")], [("t", "다라")]]
        assert shapes[0][0] == shapes[2][0] != shapes[1][0]
        same = paragraph.insert_text(5, "마", char_pr_id_ref=shapes[2][0])
        assert [run.text for run in same] == ["다라마"]  # one run for one character shape
        with pytest.raises(HwpxError) as caught:
            paragraph.insert_text(0, "가", char_pr_id_ref="9999")
        assert caught.value.code == "style-char-pr-missing"
        with pytest.raises(HwpxError) as caught:
            paragraph.insert_text(0, "가", weight=3)
        assert caught.value.code == "style-run-format-invalid"
        assert paragraph.text == "가나굵다라마"


def test_text_goes_after_a_note_at_its_place() -> None:
    doc = _open("mid_text_footnote")
    with doc:
        paragraph = doc.paragraphs[1]  # 가나다라 + footnote + 마바사..., Hangul's form
        assert paragraph.footnotes[0].offset == 4
        paragraph.insert_text(4, "끼움")
        assert paragraph.text == "가나다라끼움마바사아자차카타파하"
        assert paragraph.footnotes[0].offset == 4
        assert _shape(paragraph) == [("0", [("t", "가나다라"), ("ctrl", "footNote"), ("t", "끼움마바사아자차카타파하")])]


def test_a_bad_offset_or_text_is_refused() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나")
        for offset in (-1, 3, "1", True):
            with pytest.raises(HwpxError) as caught:
                paragraph.insert_text(offset, "x")  # type: ignore[arg-type]
            assert caught.value.code == "paragraph-range-invalid"
        with pytest.raises(HwpxError):
            paragraph.insert_text(0, 3)  # type: ignore[arg-type]
        assert paragraph.insert_text(1, "") == ()
        assert paragraph.text == "가나"


# -- delete_range --------------------------------------------------------------------------------


def test_a_range_across_runs_goes_and_runs_of_one_shape_become_one() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("앞부분")
        paragraph.add_run("굵은", bold=True)
        paragraph.add_run("뒷부분")
        paragraph.delete_range(1, 7)
        assert paragraph.text == "앞부분"[:1] + "뒷부분"[2:]
        assert [children for _, children in _shape(paragraph)][-1:] == [[("t", "앞분")]]
        paragraph.delete_range(0, 2)
        assert paragraph.text == ""
        assert _shape(paragraph)[-1][1] == [("t", "")]  # Hancom's empty paragraph: <hp:run><hp:t/></hp:run>


def test_a_section_s_settings_stay_and_nothing_changes_for_an_empty_range() -> None:
    with HwpxDocument.new() as doc:
        first = doc.paragraphs[0]
        first.insert_text(0, "첫 문단")
        before = _shape(first)
        first.delete_range(2, 2)
        assert _shape(first) == before
        first.delete_range(0, 4)
        assert first.text == "" and first.element.find(f".//{HP}secPr") is not None


def test_a_control_inside_is_refused_unless_removed() -> None:
    doc = _open("mid_text_bookmark_and_footnote")
    with doc:
        paragraph = doc.paragraphs[2]  # 하나 + bookmark + 둘셋넷다 + footnote + 섯여섯일곱여덟
        with pytest.raises(HwpxError) as caught:
            paragraph.delete_range(1, 8)
        assert caught.value.code == "paragraph-range-holds-objects"
        assert caught.value.context["kinds"] == ["bookmark", "footNote"]
        assert paragraph.text == "하나둘셋넷다섯여섯일곱여덟"
        paragraph.delete_range(2, 6)  # both at the range's ends: they stay
        assert paragraph.text == "하나섯여섯일곱여덟"
        assert _shape(paragraph) == [("0", [("t", "하나"), ("ctrl", "bookmark"), ("ctrl", "footNote"),
                                            ("t", "섯여섯일곱여덟")])]
        paragraph.delete_range(1, 3, objects="remove")
        assert paragraph.text == "하여섯일곱여덟"
        assert _shape(paragraph) == [("0", [("t", "하여섯일곱여덟")])]
        assert not doc.paragraphs[2].footnotes


def test_removing_a_note_numbers_the_notes_after_it_again() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나")
        doc.notes.add_footnote("첫", paragraph=paragraph)  # at 2
        paragraph.add_run("다라마바")
        doc.notes.add_footnote("둘", paragraph=paragraph)  # at 6
        assert [note.element.get("number") for note in paragraph.footnotes] == ["1", "2"]
        paragraph.delete_range(1, 3, objects="remove")
        notes = paragraph.footnotes
        assert len(notes) == 1 and notes[0].element.get("number") == "1"
        assert paragraph.text == "가라마바"


def test_a_field_with_one_end_in_the_range_is_refused() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("앞")
        paragraph.add_hyperlink("https://example.com", "링크")
        paragraph.add_run("뒤")
        text = paragraph.text
        assert text == "앞링크뒤"
        with pytest.raises(HwpxError) as caught:
            paragraph.delete_range(0, 2, objects="remove")
        assert caught.value.code == "paragraph-range-splits-field"
        paragraph.delete_range(0, len(text), objects="remove")
        assert paragraph.text == "" and paragraph.element.find(f".//{HP}fieldBegin") is None


def test_a_tracked_change_s_mark_is_refused() -> None:
    with HwpxDocument.new() as doc:
        doc.add_paragraph("가나다")
        doc.tracking.insert(len(doc.paragraphs) - 1, "끼운 글")
        paragraph = next(p for p in doc.paragraphs if p.element.find(f".//{HP}insertBegin") is not None)
        with pytest.raises(HwpxError) as caught:
            paragraph.delete_range(0, len(paragraph.text))
        assert caught.value.code in ("paragraph-range-splits-mark", "paragraph-range-holds-objects")


def test_a_highlight_reaching_out_of_the_range_keeps_the_rest() -> None:
    doc = _open("highlight_across_runs")
    with doc:
        paragraph = doc.paragraphs[3]  # 앞부[B]분글자 | 굵은부[E]분글자 | 뒷부분글자
        paragraph.delete_range(4, 9)  # its end inside: it now ends where the range was
        assert paragraph.text == "앞부분글글자뒷부분글자"
        assert _shape(paragraph)[0] == ("0", [("t", "앞부[markpenBegin]분글[markpenEnd]")])
    doc = _open("highlight_across_runs")
    with doc:
        paragraph = doc.paragraphs[3]
        paragraph.delete_range(1, 3)  # its start inside: it now starts where the range was
        assert _shape(paragraph)[0] == ("0", [("t", "앞[markpenBegin]글자")])
        assert _shape(paragraph)[1] == ("7", [("t", "굵은부[markpenEnd]분글자")])
        paragraph.delete_range(1, 6)  # the whole highlight, its marks at the range's ends: both go
        assert "markpen" not in str(_shape(paragraph))


# -- copy_range and move_range -------------------------------------------------------------------


def test_a_range_with_a_note_copies_into_the_middle_of_text_as_hancom_writes_it() -> None:
    doc = _open("mid_text_footnote")
    with doc:
        source, target = doc.paragraphs[1], doc.paragraphs[2]
        where = source.copy_range(3, 5, to=target, offset=2)
        assert where == (2, 4)
        assert target.text == "하나라마둘셋넷다섯여섯일곱여덟"
        # Hangul's own form for a note in the middle of a run (mid_text_bookmark_and_footnote, mid_text_footnote)
        assert _shape(target) == [("0", [("t", "하나라"), ("ctrl", "footNote"), ("t", "마둘셋넷다섯여섯일곱여덟")])]
        copied, original = target.footnotes[0], source.footnotes[0]
        assert copied.element.get("instId") != original.element.get("instId")
        assert copied.offset == 3 and source.text == "가나다라마바사아자차카타파하"


def test_a_copied_highlight_is_opened_and_closed_at_the_copy_s_edges() -> None:
    doc = _open("highlight_across_runs")
    with doc:
        source, target = doc.paragraphs[3], doc.paragraphs[4]
        source.copy_range(0, 7, to=target, offset=0)  # its start inside, its end (8) outside
        assert _shape(target)[:2] == [("0", [("t", "앞부[markpenBegin]분글자")]), ("7", [("t", "굵은[markpenEnd]")])]
    doc = _open("highlight_in_one_run")
    with doc:
        source, target = doc.paragraphs[3], doc.paragraphs[4]
        source.copy_range(2, 7, to=target, offset=0)  # its end inside, its start (1) outside
        assert _shape(target)[0] == ("0", [("t", "[markpenBegin]분글[markpenEnd]자")])


def test_moving_a_range_keeps_its_objects() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나다라마바")
        shape = paragraph.add_rectangle(width=1000, height=1000)
        shape.move_to(paragraph, offset=3)
        shape_id = shape.element.get("id")
        target = doc.add_paragraph("하나둘")
        where = paragraph.move_range(2, 5, to=target, offset=1)
        assert where == (1, 4)
        assert paragraph.text == "가나바" and target.text == "하다라마나둘"
        moved = target.element.find(f".//{HP}rect")
        assert moved is shape.element and moved.get("id") == shape_id
        assert paragraph.element.find(f".//{HP}rect") is None


def test_moving_a_range_within_its_paragraph() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나다라마바")
        assert paragraph.move_range(0, 2, to=paragraph, offset=6) == (4, 6)
        assert paragraph.text == "다라마바가나"
        assert paragraph.move_range(4, 6, to=paragraph, offset=0) == (0, 2)
        assert paragraph.text == "가나다라마바"
        with pytest.raises(HwpxError) as caught:
            paragraph.move_range(0, 4, to=paragraph, offset=2)
        assert caught.value.code == "paragraph-range-into-itself"


def test_a_range_goes_to_another_document_with_its_shapes() -> None:
    with HwpxDocument.new() as source, HwpxDocument.new() as target:
        paragraph = source.add_paragraph("보통")
        paragraph.add_run("굵게", bold=True, color="#FF0000")
        into = target.add_paragraph("받는 문단")
        assert paragraph.copy_range(1, 4, to=into, offset=2) == (2, 5)
        assert into.text == "받는통굵게 문단"
        bold = [run for run in into.runs if run.text == "굵게"][0]
        assert bold.bold and bold.color.upper() == "#FF0000"
        assert paragraph.move_range(0, 2, to=into) == (8, 10)
        assert paragraph.text == "굵게" and into.text == "받는통굵게 문단보통"


def test_a_table_does_not_go_to_another_document_in_a_range() -> None:
    with HwpxDocument.new() as source, HwpxDocument.new() as target:
        paragraph = source.add_paragraph("가나다")
        table = paragraph.add_table(1, 1)
        table.move_to(paragraph, offset=1)
        with pytest.raises(HwpxError) as caught:
            paragraph.copy_range(0, 3, to=target.add_paragraph("x"))
        assert caught.value.code == "shape-copy-document-unsupported"


def test_a_note_does_not_go_into_a_note() -> None:
    doc = _open("mid_text_footnote")
    with doc:
        source = doc.paragraphs[1]
        other = doc.notes.add_footnote("다른 각주", paragraph=doc.paragraphs[2])
        with pytest.raises(HwpxError) as caught:
            source.copy_range(3, 5, to=other.body_paragraph)
        assert caught.value.code == "paragraph-move-place-unsupported"


def test_a_range_cannot_go_into_its_own_table() -> None:
    with HwpxDocument.new() as doc:
        paragraph = doc.add_paragraph("가나다")
        table = paragraph.add_table(1, 1)
        table.move_to(paragraph, offset=1)
        cell_paragraph = table.rows[0].cells[0].paragraphs[0]
        with pytest.raises(HwpxError) as caught:
            paragraph.move_range(0, 3, to=cell_paragraph)
        assert caught.value.code == "paragraph-range-into-itself"


# -- set_text_preserving_runs with tabs (N11) ----------------------------------------------------


def test_set_text_preserving_runs_edits_text_beside_hancom_s_tabs() -> None:
    doc = _open("line_cache_tabs")
    with doc:
        paragraph = next(p for p in doc.paragraphs if "\t" in p.text)
        old = paragraph.text
        tabs_before = [dict(tab.attrib) for tab in paragraph.element.iter(f"{HP}tab")]
        cut = old.index("\t") + 1
        value = old[:cut] + "새" + old[cut:]
        paragraph.set_text_preserving_runs(value)
        assert paragraph.text == value
        assert [dict(tab.attrib) for tab in paragraph.element.iter(f"{HP}tab")] == tabs_before
        paragraph.set_text_preserving_runs(value.replace("새", "\t둘"))
        assert paragraph.text == value.replace("새", "\t둘")
