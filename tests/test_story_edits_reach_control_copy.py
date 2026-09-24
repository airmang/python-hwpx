"""Edits to a header or footer made through its object reach the hp:ctrl copy Hancom reads."""

from __future__ import annotations

import io
import re
import zipfile

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP
from hwpx.oxml.paragraph import HwpxOxmlParagraph


def _section_xml(doc: HwpxDocument) -> str:
    return zipfile.ZipFile(io.BytesIO(doc.to_bytes())).read("Contents/section0.xml").decode("utf-8")


def _copies(xml: str, kind: str) -> list[tuple[str, str]]:
    """(where, text) of every copy of *kind*: under secPr or in a body control."""
    out = []
    for match in re.finditer(rf"<hp:{kind}\b[^>]*/>|<hp:{kind}\b.*?</hp:{kind}>", xml, re.S):
        where = "secPr" if xml.rfind("<hp:secPr", 0, match.start()) > xml.rfind("</hp:secPr>", 0, match.start()) else "ctrl"
        out.append((where, "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", match.group(0)))))
    return out


def _doc() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


def test_setting_header_and_footer_text_updates_the_control_copy() -> None:
    doc = _doc()
    header = doc.page.set_header(text="옛 머리말")
    footer = doc.page.set_footer(text="옛 꼬리말")

    header.text = "새 머리말"
    footer.text = "새 꼬리말"
    xml = _section_xml(doc)

    assert _copies(xml, "header") == [("secPr", "새 머리말"), ("ctrl", "새 머리말")]
    assert _copies(xml, "footer") == [("secPr", "새 꼬리말"), ("ctrl", "새 꼬리말")]


def test_runs_paragraphs_and_page_numbers_added_later_reach_the_control_copy() -> None:
    doc = _doc()
    header = doc.page.set_header(text="머리말")
    header.add_run(" 덧붙임")
    paragraph = header.add_paragraph()
    header.add_run("둘째 줄", paragraph=paragraph)
    header.add_page_number_field(paragraph=paragraph)

    xml = _section_xml(doc)
    logical, control = re.findall(r"<hp:header\b.*?</hp:header>", xml, re.S)

    assert control == logical
    assert _copies(xml, "header")[1] == ("ctrl", "머리말 덧붙임둘째 줄")
    assert control.count("<hp:pageNum") == 1


def test_an_edit_through_a_paragraph_of_the_story_reaches_the_control_copy() -> None:
    doc = _doc()
    header = doc.page.set_header(text="머리말")
    story_paragraph = HwpxOxmlParagraph(header.element.find(f".//{HP}p"), doc.sections[0])

    story_paragraph.add_run(" 문단으로 더함")

    assert _copies(_section_xml(doc), "header")[1] == ("ctrl", "머리말 문단으로 더함")


def test_set_content_and_clear_content_reach_the_control_copy() -> None:
    doc = _doc()
    footer = doc.page.set_footer(text="처음")
    footer.set_content([{"text": "내용으로 바꿈"}])
    assert _copies(_section_xml(doc), "footer")[1] == ("ctrl", "내용으로 바꿈")

    footer.clear_content()
    xml = _section_xml(doc)
    assert _copies(xml, "footer") == [("secPr", ""), ("ctrl", "")]
    # an empty paragraph stays: a story without hp:subList stops Hancom opening the document
    stories = re.findall(r"<hp:footer\b.*?</hp:footer>", xml, re.S)
    assert len(stories) == 2 and all("<hp:subList" in story for story in stories)


def test_clearing_a_story_that_exists_only_as_a_control_keeps_a_paragraph() -> None:
    doc = _doc()
    doc.page.set_header(text="한컴 방식")
    sec_pr = doc.sections[0].element.find(f"{HP}p/{HP}run/{HP}secPr")
    for story in sec_pr.findall(f"{HP}header"):
        sec_pr.remove(story)
    [header] = doc.sections[0].properties.headers

    header.clear_content()
    [story] = re.findall(r"<hp:header\b.*?</hp:header>|<hp:header\b[^>]*/>", _section_xml(doc), re.S)

    assert story.count("<hp:p ") == 1 and header.text == ""


def test_set_content_with_nothing_keeps_a_paragraph() -> None:
    doc = _doc()
    footer = doc.page.set_footer(text="처음")

    footer.set_content([])

    stories = re.findall(r"<hp:footer\b.*?</hp:footer>", _section_xml(doc), re.S)
    assert len(stories) == 2 and all("<hp:p " in story for story in stories)


def test_copies_already_alike_are_written_unchanged() -> None:
    doc = _doc()
    doc.page.set_header(text="같음")
    first = doc.to_bytes()
    reopened = HwpxDocument.open(io.BytesIO(first))
    reopened.sections[0].mark_dirty()

    assert _section_xml(reopened) == zipfile.ZipFile(io.BytesIO(first)).read("Contents/section0.xml").decode("utf-8")


def test_a_story_that_exists_only_as_a_control_is_edited_where_it_is() -> None:
    doc = _doc()
    doc.page.set_header(text="한컴 방식")
    sec_pr = doc.sections[0].element.find(f"{HP}p/{HP}run/{HP}secPr")
    for story in sec_pr.findall(f"{HP}header"):
        sec_pr.remove(story)  # as in a document Hancom saved: the control copy alone
    doc.sections[0].mark_dirty()
    [header] = doc.sections[0].properties.headers

    header.text = "고침"

    assert _copies(_section_xml(doc), "header") == [("ctrl", "고침")]


def test_two_control_copies_of_one_story_are_left_alone() -> None:
    doc = _doc()
    header = doc.page.set_header(text="하나")
    run = doc.sections[0].element.find(f"{HP}p/{HP}run")
    control = next(c for c in run.findall(f"{HP}ctrl") if c.find(f"{HP}header") is not None)
    run.append(__import__("copy").deepcopy(control))
    header.text = "둘"

    assert _copies(_section_xml(doc), "header") == [("secPr", "둘"), ("ctrl", "하나"), ("ctrl", "하나")]


def _control_attrs(xml: str, kind: str, name: str) -> list[str | None]:
    """*name* of every control copy of *kind*, in document order."""
    values = []
    for match in re.finditer(rf"<hp:{kind}\b[^>]*>", xml):
        if xml.rfind("<hp:secPr", 0, match.start()) > xml.rfind("</hp:secPr>", 0, match.start()):
            continue
        found = re.search(rf'\b{name}="([^"]*)"', match.group(0))
        values.append(found.group(1) if found else None)
    return values


def test_changing_the_page_type_changes_the_control_copy_too() -> None:
    doc = _doc()
    header = doc.page.set_header(text="홀수 쪽만")

    header.apply_page_type = "ODD"

    assert _control_attrs(_section_xml(doc), "header", "applyPageType") == ["ODD"]


def test_a_story_turned_both_goes_ahead_of_the_page_specific_controls() -> None:
    doc = _doc()
    doc.page.set_header(text="짝수", page_type="EVEN")
    odd = doc.page.set_header(text="홀수", page_type="ODD")

    odd.apply_page_type = "BOTH"

    assert _control_attrs(_section_xml(doc), "header", "applyPageType") == ["BOTH", "EVEN"]


def test_changing_the_id_changes_the_control_copy_too() -> None:
    doc = _doc()
    header = doc.page.set_header(text="아이디")

    header.id = "777"

    assert _control_attrs(_section_xml(doc), "header", "id") == ["777"]
