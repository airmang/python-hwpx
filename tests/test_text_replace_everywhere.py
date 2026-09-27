"""``doc.text.replace(..., everywhere=True)`` reaches what Hancom's "모두 바꾸기" reaches.

Without the option only body paragraphs change, one run at a time (unchanged). With it, table
cells (nested too), text boxes, captions, headers, footers, footnotes, endnotes, master pages and
field values change as well, and a word split over runs with different formats is replaced as a whole, each
new character in the run of the character it replaces. Memo bodies are left alone.
"""

from __future__ import annotations

import io
import re
import zipfile

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP


def _section_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def _master_page_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/masterpage0.xml").decode("utf-8")


def _document_with_every_place() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("본문사과")
    document.add_table(2, 2).cell(0, 0).text = "칸사과"
    outer = document.add_table(2, 2)
    outer.cell(1, 1).paragraphs[0].add_table(1, 1).cell(0, 0).text = "안칸사과"
    document.shapes.add_rectangle(paragraph=document.add_paragraph("글상자 앞")).set_draw_text("글상자사과")
    document.page.set_header(text="머리말사과")
    document.page.set_footer(text="꼬리말사과")
    document.notes.add_footnote("각주사과", document.add_paragraph("각주 붙은 문단"))
    document.notes.add_endnote("미주사과", document.add_paragraph("미주 붙은 문단"))
    document.fields.add("f1", prompt="안내", paragraph=document.add_paragraph("누름틀: "))
    document.fields.fill("누름틀값사과", name="f1")
    document.add_table(1, 1).set_caption("캡션사과")
    document.parts.add_master_page(text="바탕쪽사과")
    return document


PLACES = ["본문", "칸", "안칸", "글상자", "머리말", "꼬리말", "각주", "미주", "누름틀값", "캡션"]


def test_everywhere_replaces_in_every_place_hancom_does() -> None:
    document = _document_with_every_place()

    count = document.text.replace("사과", "배", everywhere=True)

    xml = _section_xml(document)
    assert count == len(PLACES) + 1
    assert "사과" not in xml
    for place in PLACES:
        assert f"{place}배" in xml, place
    assert "바탕쪽배" in _master_page_xml(document)


def test_the_default_still_changes_body_runs_only() -> None:
    document = _document_with_every_place()

    count = document.text.replace("사과", "배")

    xml = _section_xml(document)
    assert count == 2  # the body paragraph and the field value, which sits in body runs
    assert "칸사과" in xml and "머리말사과" in xml
    assert "바탕쪽사과" in _master_page_xml(document)


def test_a_header_written_twice_counts_once_and_both_copies_change() -> None:
    document = HwpxDocument.new()
    document.page.set_header(text="머리말사과 사과")

    count = document.text.replace("사과", "배", everywhere=True)

    xml = _section_xml(document)
    assert count == 2
    assert xml.count("머리말배 배") == 2
    assert "사과" not in xml
    assert document.oxml.sections[0].properties.get_header().text == "머리말배 배"


def test_a_word_over_two_runs_takes_the_format_of_its_first_run() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    first = paragraph.add_run("나뉜사", bold=True)
    second = paragraph.add_run("과")

    count = document.text.replace("사과", "배", everywhere=True)

    assert count == 1
    assert first.text == "나뉜배"
    assert second.text == ""
    assert paragraph.text == "나뉜배"


def _run_texts(paragraph) -> list[tuple[str, bool]]:
    return [(run.text, bool(run.bold)) for run in paragraph.runs]


def test_each_new_character_takes_the_run_of_the_character_it_replaces() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    paragraph.add_run("가나")
    paragraph.add_run("다라", bold=True)

    document.text.replace("나다", "XY", everywhere=True)

    assert _run_texts(paragraph)[-2:] == [("가X", False), ("Y라", True)]


def test_extra_new_characters_follow_the_last_replaced_one() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    paragraph.add_run("가나")
    paragraph.add_run("다라", bold=True)

    document.text.replace("나다", "XYZ", everywhere=True)

    assert _run_texts(paragraph)[-2:] == [("가X", False), ("YZ라", True)]


def test_a_word_over_three_runs_keeps_each_runs_format() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    paragraph.add_run("가")
    paragraph.add_run("나", bold=True)
    paragraph.add_run("다라", italic=True)

    document.text.replace("가나다", "XYZ", everywhere=True)

    assert [run.text for run in paragraph.runs][-3:] == ["X", "Y", "Z라"]
    assert [bool(run.bold) for run in paragraph.runs][-3:] == [False, True, False]
    assert bool(paragraph.runs[-1].italic)


def test_text_on_both_sides_of_a_tab_is_not_one_word() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("사\t과")

    count = document.text.replace("사과", "배", everywhere=True)

    assert count == 0
    assert paragraph.text == "사\t과"


def test_memo_bodies_are_left_alone() -> None:
    document = HwpxDocument.new()
    document.notes.add_memo("메모사과", anchor=document.add_paragraph("본문사과"))

    count = document.text.replace("사과", "배", everywhere=True)

    xml = _section_xml(document)
    assert count == 1
    assert "본문배" in xml
    assert "메모배" not in xml


def test_limit_counts_across_places_in_document_order() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("하나사과")
    document.add_table(1, 1).cell(0, 0).text = "둘사과"
    document.add_paragraph("셋사과")

    count = document.text.replace("사과", "배", everywhere=True, limit=2)

    xml = _section_xml(document)
    assert count == 2
    assert "하나배" in xml and "둘배" in xml and "셋사과" in xml


def test_a_format_condition_only_looks_at_matching_runs() -> None:
    document = HwpxDocument.new()
    cell = document.add_table(1, 1).cell(0, 0)
    paragraph = cell.paragraphs[0]
    paragraph.add_run("굵은사과", bold=True)
    bold_ref = paragraph.runs[-1].char_pr_id_ref
    paragraph.add_run(" 보통사과")

    count = document.text.replace("사과", "배", everywhere=True, char_pr_id_ref=bold_ref)

    assert count == 1
    assert cell.text.endswith("굵은배 보통사과")


def test_changed_paragraphs_drop_their_line_layout_cache() -> None:
    document = HwpxDocument.new()
    cell = document.add_table(1, 1).cell(0, 0)
    cell.text = "칸사과"
    paragraph = cell.element.find(f"{HP}subList").find(f"{HP}p")
    cache = paragraph.makeelement(f"{HP}linesegarray", {})
    cache.append(cache.makeelement(f"{HP}lineseg", {"horzsize": "1"}))
    paragraph.append(cache)

    document.text.replace("사과", "배", everywhere=True)

    assert paragraph.find(f"{HP}linesegarray") is None


def test_replacements_survive_save_and_reopen() -> None:
    document = _document_with_every_place()
    document.text.replace("사과", "배", everywhere=True)

    reopened = HwpxDocument.open(document.to_bytes())

    assert reopened.text.replace("사과", "배", everywhere=True) == 0
    assert re.search(r"칸배", _section_xml(reopened))
