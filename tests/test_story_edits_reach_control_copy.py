"""Edits to a header or footer made through its object reach the hp:ctrl copy Hancom reads.

Since 7.0 python-hwpx writes a header or footer once, as the ``hp:ctrl`` story Hancom reads and saves.
Up to 6.x it also kept a copy under ``hp:secPr`` (with an ``hp:headerApply``); documents written that
way still open, and their two copies are kept in step (``_as_written_by_6x`` builds one).
"""

from __future__ import annotations

import copy
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


def _as_written_by_6x(doc: HwpxDocument) -> HwpxDocument:
    """*doc* reopened with each header and footer also kept under hp:secPr, as python-hwpx up to 6.x wrote it."""

    first = doc.sections[0].element.find(f"{HP}p")
    sec_pr = first.find(f"{HP}run/{HP}secPr")
    for ctrl in first.findall(f"{HP}run/{HP}ctrl"):
        for story in list(ctrl):
            name = story.tag.rsplit("}", 1)[-1]
            if name in ("header", "footer"):
                sec_pr.append(copy.deepcopy(story))
                apply = {"idRef": story.get("id"), "applyPageType": story.get("applyPageType", "BOTH")}
                sec_pr.append(sec_pr.makeelement(f"{HP}{name}Apply", apply))
    doc.sections[0].mark_dirty()
    return HwpxDocument.open(io.BytesIO(doc.to_bytes()))


def test_a_header_and_footer_are_written_once_in_the_control_hancom_reads() -> None:
    doc = _doc()
    header = doc.page.set_header(text="옛 머리말")
    footer = doc.page.set_footer(text="옛 꼬리말")

    header.text = "새 머리말"
    footer.text = "새 꼬리말"
    xml = _section_xml(doc)

    assert _copies(xml, "header") == [("ctrl", "새 머리말")]
    assert _copies(xml, "footer") == [("ctrl", "새 꼬리말")]
    assert "headerApply" not in xml and "footerApply" not in xml


def test_setting_the_text_of_a_6x_story_updates_its_control_copy() -> None:
    doc = _doc()
    doc.page.set_header(text="옛 머리말")
    doc.page.set_footer(text="옛 꼬리말")
    doc = _as_written_by_6x(doc)
    header = doc.sections[0].properties.get_header()
    footer = doc.sections[0].properties.get_footer()

    header.text = "새 머리말"
    footer.text = "새 꼬리말"
    xml = _section_xml(doc)

    assert _copies(xml, "header") == [("secPr", "새 머리말"), ("ctrl", "새 머리말")]
    assert _copies(xml, "footer") == [("secPr", "새 꼬리말"), ("ctrl", "새 꼬리말")]


def test_set_header_on_a_6x_document_leaves_the_one_control_copy() -> None:
    doc = _doc()
    first = doc.page.set_header(text="옛 머리말")
    doc.page.set_footer(text="꼬리말")
    doc = _as_written_by_6x(doc)

    header = doc.page.set_header(text="새 머리말")
    xml = _section_xml(doc)

    assert _copies(xml, "header") == [("ctrl", "새 머리말")]
    assert header.id == first.id and "headerApply" not in xml
    # the footer was not set again: its two copies stay as they were
    assert _copies(xml, "footer") == [("secPr", "꼬리말"), ("ctrl", "꼬리말")]
    assert HwpxDocument.open(io.BytesIO(doc.to_bytes())).validate().ok


def test_runs_paragraphs_and_page_numbers_added_later_go_into_the_one_copy() -> None:
    doc = _doc()
    header = doc.page.set_header(text="머리말")
    header.add_run(" 덧붙임")
    paragraph = header.add_paragraph()
    header.add_run("둘째 줄", paragraph=paragraph)
    header.add_page_number_field(paragraph=paragraph)

    xml = _section_xml(doc)
    (control,) = re.findall(r"<hp:header\b.*?</hp:header>", xml, re.S)

    assert _copies(xml, "header") == [("ctrl", "머리말 덧붙임둘째 줄")]
    assert control.count("<hp:pageNum") == 1


def test_runs_added_later_to_a_6x_story_reach_the_control_copy() -> None:
    doc = _doc()
    doc.page.set_header(text="머리말")
    doc = _as_written_by_6x(doc)
    header = doc.sections[0].properties.get_header()
    header.add_run(" 덧붙임")

    xml = _section_xml(doc)
    logical, control = re.findall(r"<hp:header\b.*?</hp:header>", xml, re.S)

    assert control == logical
    assert _copies(xml, "header")[1] == ("ctrl", "머리말 덧붙임")


def test_an_edit_through_a_paragraph_of_the_story_is_saved() -> None:
    doc = _doc()
    header = doc.page.set_header(text="머리말")
    story_paragraph = HwpxOxmlParagraph(header.element.find(f".//{HP}p"), doc.sections[0])

    story_paragraph.add_run(" 문단으로 더함")

    assert _copies(_section_xml(doc), "header") == [("ctrl", "머리말 문단으로 더함")]


def test_set_content_and_clear_content_keep_one_copy() -> None:
    doc = _doc()
    footer = doc.page.set_footer(text="처음")
    footer.set_content([{"text": "내용으로 바꿈"}])
    assert _copies(_section_xml(doc), "footer") == [("ctrl", "내용으로 바꿈")]

    footer.clear_content()
    xml = _section_xml(doc)
    assert _copies(xml, "footer") == [("ctrl", "")]
    # an empty paragraph stays: a story without hp:subList stops Hancom opening the document
    stories = re.findall(r"<hp:footer\b.*?</hp:footer>", xml, re.S)
    assert len(stories) == 1 and all("<hp:subList" in story for story in stories)


def test_clearing_a_story_that_exists_only_as_a_control_keeps_a_paragraph() -> None:
    doc = _doc()
    doc.page.set_header(text="한컴 방식")
    [header] = doc.sections[0].properties.headers

    header.clear_content()
    [story] = re.findall(r"<hp:header\b.*?</hp:header>|<hp:header\b[^>]*/>", _section_xml(doc), re.S)

    assert story.count("<hp:p ") == 1 and header.text == ""


def test_set_content_with_nothing_keeps_a_paragraph() -> None:
    doc = _doc()
    footer = doc.page.set_footer(text="처음")

    footer.set_content([])

    stories = re.findall(r"<hp:footer\b.*?</hp:footer>", _section_xml(doc), re.S)
    assert len(stories) == 1 and all("<hp:p " in story for story in stories)


def test_copies_already_alike_are_written_unchanged() -> None:
    doc = _doc()
    doc.page.set_header(text="같음")
    first = _as_written_by_6x(doc).to_bytes()
    reopened = HwpxDocument.open(io.BytesIO(first))
    reopened.sections[0].mark_dirty()

    assert _section_xml(reopened) == zipfile.ZipFile(io.BytesIO(first)).read("Contents/section0.xml").decode("utf-8")


def test_a_story_that_exists_only_as_a_control_is_edited_where_it_is() -> None:
    doc = _doc()
    doc.page.set_header(text="한컴 방식")
    doc.sections[0].mark_dirty()
    [header] = doc.sections[0].properties.headers

    header.text = "고침"

    assert _copies(_section_xml(doc), "header") == [("ctrl", "고침")]


def test_two_control_copies_of_one_6x_story_are_left_alone() -> None:
    doc = _doc()
    doc.page.set_header(text="하나")
    doc = _as_written_by_6x(doc)
    header = doc.sections[0].properties.get_header()
    run = doc.sections[0].element.find(f"{HP}p/{HP}run")
    control = next(c for c in run.findall(f"{HP}ctrl") if c.find(f"{HP}header") is not None)
    run.append(copy.deepcopy(control))
    header.text = "둘"

    assert _copies(_section_xml(doc), "header") == [("secPr", "둘"), ("ctrl", "하나"), ("ctrl", "하나")]


def test_set_header_keeps_one_control_of_its_page_type_in_the_first_paragraph() -> None:
    doc = _doc()
    doc.page.set_header(text="하나")
    run = doc.sections[0].element.find(f"{HP}p/{HP}run")
    control = next(c for c in run.findall(f"{HP}ctrl") if c.find(f"{HP}header") is not None)
    run.append(copy.deepcopy(control))  # two controls of one page type, as an old python-hwpx could leave

    doc.page.set_header(text="둘")

    assert _copies(_section_xml(doc), "header") == [("ctrl", "둘")]


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


def test_a_6x_story_turned_both_goes_ahead_of_the_page_specific_controls() -> None:
    doc = _doc()
    doc.page.set_header(text="짝수", page_type="EVEN")
    doc.page.set_header(text="홀수", page_type="ODD")
    doc = _as_written_by_6x(doc)

    doc.sections[0].properties.get_header("ODD").apply_page_type = "BOTH"

    assert _control_attrs(_section_xml(doc), "header", "applyPageType") == ["BOTH", "EVEN"]


def _reopened_with_a_header_field(*, written_by_6x: bool = False) -> HwpxDocument:
    doc = _doc()
    header = doc.page.set_header(text="Name: ")
    paragraph = HwpxOxmlParagraph(header.element.find(f".//{HP}p"), doc.sections[0])
    doc.fields.add("who", prompt="type here", paragraph=paragraph)
    if written_by_6x:
        return _as_written_by_6x(doc)
    return HwpxDocument.open(io.BytesIO(doc.to_bytes()))


def _control_header(doc: HwpxDocument):
    return next(
        story for control in doc.oxml.sections[0].element.iter(f"{HP}ctrl")
        for story in control if story.tag == f"{HP}header"
    )


def test_a_header_lists_its_form_field_once() -> None:
    assert [field.name for field in _reopened_with_a_header_field().fields.all] == ["who"]
    assert [field.name for field in _reopened_with_a_header_field(written_by_6x=True).fields.all] == ["who"]


def test_filling_a_header_field_by_name_fills_the_one_copy() -> None:
    doc = _reopened_with_a_header_field()

    doc.fields.fill("Alice", name="who")

    assert [where for where, text in _copies(_section_xml(doc), "header") if "Alice" in text] == ["ctrl"]


def test_filling_a_6x_header_field_by_name_reaches_both_copies() -> None:
    doc = _reopened_with_a_header_field(written_by_6x=True)

    doc.fields.fill("Alice", name="who")
    xml = _section_xml(doc)

    assert [where for where, text in _copies(xml, "header") if "Alice" in text] == ["secPr", "ctrl"]


def test_an_edit_to_the_control_copy_of_a_6x_story_is_kept_and_reaches_the_other_copy() -> None:
    doc = _doc()
    doc.page.set_header(text="머리말")
    doc = _as_written_by_6x(doc)
    next(_control_header(doc).iter(f"{HP}t")).text = "한/글 쪽에서 고침"
    doc.oxml.sections[0].mark_dirty()

    xml = _section_xml(doc)

    assert _copies(xml, "header") == [("secPr", "한/글 쪽에서 고침"), ("ctrl", "한/글 쪽에서 고침")]


def test_a_control_edit_made_right_after_setting_the_story_is_kept() -> None:
    doc = _doc()
    doc.page.set_header(text="머리말")
    next(_control_header(doc).iter(f"{HP}t")).text = "바로 고침"

    assert _copies(_section_xml(doc), "header") == [("ctrl", "바로 고침")]


def test_a_6x_story_object_keeps_working_after_a_save_that_updated_it() -> None:
    doc = _doc()
    doc.page.set_header(text="머리말")
    doc = _as_written_by_6x(doc)
    header = doc.sections[0].properties.get_header()
    next(_control_header(doc).iter(f"{HP}t")).text = "한/글 쪽에서 고침"
    doc.oxml.sections[0].mark_dirty()
    doc.to_bytes()

    header.text = "나중에 고침"

    assert _copies(_section_xml(doc), "header") == [("secPr", "나중에 고침"), ("ctrl", "나중에 고침")]


def test_a_control_only_story_turned_both_goes_ahead_too() -> None:
    doc = _doc()
    doc.page.set_header(text="짝수", page_type="EVEN")
    doc.page.set_header(text="홀수", page_type="ODD")

    doc.oxml.sections[0].properties.get_header("ODD").apply_page_type = "BOTH"

    assert _control_attrs(_section_xml(doc), "header", "applyPageType") == ["BOTH", "EVEN"]


def test_changing_the_id_changes_the_control_copy_too() -> None:
    doc = _doc()
    header = doc.page.set_header(text="아이디")

    header.id = "777"

    assert _control_attrs(_section_xml(doc), "header", "id") == ["777"]
