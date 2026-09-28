"""``notes=True`` writes foot and end notes where they sit, as Hancom's text save does.

Each case builds a small document; the expected text is what Hancom's text save (Unicode text)
wrote for the same document, with CRLF written as LF and the blank lines at its ends left out
(the empty first paragraph of a new document is a blank line there).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from hwpx.document import HwpxDocument
from hwpx.tools.exporter import export_html, export_markdown, export_text

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _new() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")
    return document


def _note_format(document: HwpxDocument, section: int, tag: str, *, numbering: dict[str, str] | None = None,
                 **number_format: str) -> None:
    properties = next(document.sections[section].element.iter(f"{HP}{tag}Pr"))
    for key, value in number_format.items():
        properties.find(f"{HP}autoNumFormat").set(key, value)
    for key, value in (numbering or {}).items():
        properties.find(f"{HP}numbering").set(key, value)
    document.sections[section].mark_dirty()


def _noted(document: HwpxDocument, before: str, note: str, after: str, *, end: bool = False, section=None):
    paragraph = document.add_paragraph(before, section=section) if section is not None else document.add_paragraph(before)
    (document.notes.add_endnote if end else document.notes.add_footnote)(note, paragraph=paragraph)
    if after:
        paragraph.add_run(after)
    return paragraph


def body_footnote() -> HwpxDocument:
    document = _new()
    _noted(document, "본문 앞", "각주 글", "본문 뒤")
    document.add_paragraph("끝 문단")
    return document


def note_at_end() -> HwpxDocument:
    document = _new()
    _noted(document, "본문 끝", "끝 각주", "")
    document.add_paragraph("다음 문단")
    return document


def stale_numbers() -> HwpxDocument:
    document = _new()
    first, second = document.add_paragraph("가 앞"), document.add_paragraph("나 앞")
    document.notes.add_footnote("나중 각주", paragraph=second)  # stored as number 1
    document.notes.add_footnote("먼저 각주", paragraph=first)  # stored as number 2
    first.add_run("가 뒤")
    second.add_run("나 뒤")
    return document


def two_paragraph_note() -> HwpxDocument:
    document = _new()
    paragraph = document.add_paragraph("본문 앞")
    note = document.notes.add_footnote("각주 첫 문단", paragraph=paragraph)
    sub_list = note.element.find(f"{HP}subList")
    second = sub_list.makeelement(f"{HP}p", dict(sub_list.find(f"{HP}p").attrib))
    run = second.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    text = run.makeelement(f"{HP}t", {})
    text.text = "각주 둘째 문단"
    run.append(text)
    second.append(run)
    sub_list.append(second)
    paragraph.add_run("본문 뒤")
    document.add_paragraph("끝 문단")
    return document


def roman_brackets() -> HwpxDocument:
    document = _new()
    _note_format(document, 0, "footNote", type="ROMAN_SMALL", prefixChar="(", suffixChar=")")
    for word in ("하나", "둘", "셋"):
        _noted(document, f"{word} 앞", f"{word} 각주", f"{word} 뒤")
    return document


def user_char() -> HwpxDocument:
    document = _new()
    _note_format(document, 0, "footNote", type="USER_CHAR", userChar="*", suffixChar="")
    for word in ("하나", "둘"):
        _noted(document, f"{word} 앞", f"{word} 각주", f"{word} 뒤")
    return document


def continuous_start_number() -> HwpxDocument:
    document = _new()
    _note_format(document, 0, "footNote", numbering={"newNum": "5"})
    for word in ("하나", "둘"):
        _noted(document, f"{word} 앞", f"{word} 각주", f"{word} 뒤")
    return document


def _two_sections(*, numbering: dict[str, str] | None = None, end: bool = False) -> HwpxDocument:
    document = _new()
    tag, word = ("endNote", "미주") if end else ("footNote", "각주")
    _noted(document, "앞 구역", f"앞 구역 {word}", "" if end else "앞 구역 뒤", end=end)
    section = document.add_section()
    _noted(document, "뒤 구역", f"뒤 구역 {word}", "" if end else "뒤 구역 뒤", end=end, section=section)
    if numbering:
        for index in (0, 1):
            _note_format(document, index, tag, numbering=numbering)
    return document


def new_number_control() -> HwpxDocument:
    document = _new()
    for index, word in enumerate(("하나", "둘", "셋")):
        paragraph = document.add_paragraph(f"{word} 앞")
        if index == 1:
            run = paragraph.element.find(f"{HP}run")
            control = run.makeelement(f"{HP}ctrl", {})
            control.append(control.makeelement(f"{HP}newNum", {"num": "7", "numType": "FOOTNOTE"}))
            run.insert(0, control)
        document.notes.add_footnote(f"{word} 각주", paragraph=paragraph)
        paragraph.add_run(f"{word} 뒤")
    return document


def foot_and_end() -> HwpxDocument:
    document = _new()
    paragraph = document.add_paragraph("앞")
    document.notes.add_footnote("각주", paragraph=paragraph)
    paragraph.add_run("가운데")
    document.notes.add_endnote("미주", paragraph=paragraph)
    paragraph.add_run("뒤")
    _noted(document, "다음 앞", "둘째 미주", "다음 뒤", end=True)
    return document


HANCOM_TEXT_SAVE: list[tuple[Callable[[], HwpxDocument], str]] = [
    (body_footnote, "첫 문단\n본문 앞1)1)각주 글\n본문 뒤\n끝 문단"),
    (note_at_end, "첫 문단\n본문 끝1)1)끝 각주\n\n다음 문단"),
    (stale_numbers, "첫 문단\n가 앞1)1)먼저 각주\n가 뒤\n나 앞2)2)나중 각주\n나 뒤"),
    (two_paragraph_note, "첫 문단\n본문 앞1)1)각주 첫 문단\n각주 둘째 문단\n본문 뒤\n끝 문단"),
    (roman_brackets, "첫 문단\n하나 앞(i)(i)하나 각주\n하나 뒤\n둘 앞(ii)(ii)둘 각주\n둘 뒤\n셋 앞(iii)(iii)셋 각주\n셋 뒤"),
    (user_char, "첫 문단\n하나 앞**하나 각주\n하나 뒤\n둘 앞****둘 각주\n둘 뒤"),
    (continuous_start_number, "첫 문단\n하나 앞1)1)하나 각주\n하나 뒤\n둘 앞2)2)둘 각주\n둘 뒤"),
    (lambda: _two_sections(), "첫 문단\n앞 구역1)1)앞 구역 각주\n앞 구역 뒤\n\n뒤 구역2)2)뒤 구역 각주\n뒤 구역 뒤"),
    (lambda: _two_sections(numbering={"type": "ON_SECTION"}),
     "첫 문단\n앞 구역1)1)앞 구역 각주\n앞 구역 뒤\n\n뒤 구역1)1)뒤 구역 각주\n뒤 구역 뒤"),
    (lambda: _two_sections(numbering={"type": "ON_SECTION", "newNum": "5"}),
     "첫 문단\n앞 구역5)5)앞 구역 각주\n앞 구역 뒤\n\n뒤 구역5)5)뒤 구역 각주\n뒤 구역 뒤"),
    (lambda: _two_sections(numbering={"type": "ON_SECTION"}, end=True),
     "첫 문단\n앞 구역1)1)앞 구역 미주\n\n\n뒤 구역1)1)뒤 구역 미주"),
    (new_number_control, "첫 문단\n하나 앞1)1)하나 각주\n하나 뒤\n둘 앞7)7)둘 각주\n둘 뒤\n셋 앞8)8)셋 각주\n셋 뒤"),
    (foot_and_end, "첫 문단\n앞1)1)각주\n가운데1)1)미주\n뒤\n다음 앞2)2)둘째 미주\n다음 뒤"),
]


@pytest.mark.parametrize(("build", "hancom"), HANCOM_TEXT_SAVE, ids=[
    "body", "at_end", "stale_numbers", "two_paragraphs", "roman", "user_char", "continuous_start",
    "sections", "on_section", "on_section_start", "endnote_on_section", "new_number", "foot_and_end",
])
def test_notes_are_written_as_hancoms_text_save_writes_them(build, hancom: str) -> None:
    assert export_text(build(), notes=True).strip("\n") == hancom


def test_notes_are_left_out_by_default() -> None:
    assert export_text(body_footnote()) == "첫 문단\n본문 앞본문 뒤\n끝 문단"


def test_notes_numbered_per_page_are_numbered_straight_on() -> None:
    # Pages are not laid out here; Hancom numbers these per page.
    document = _new()
    _note_format(document, 0, "footNote", numbering={"type": "ON_PAGE"})
    for word in ("하나", "둘"):
        _noted(document, f"{word} 앞", f"{word} 각주", f"{word} 뒤")

    assert export_text(document, notes=True) == "첫 문단\n하나 앞1)1)하나 각주\n하나 뒤\n둘 앞2)2)둘 각주\n둘 뒤"


def test_a_note_in_a_cell_is_written_in_the_cell() -> None:
    document = _new()
    cell = document.add_table(1, 1).cell(0, 0)
    cell.text = "칸 앞"
    document.notes.add_footnote("칸 각주", paragraph=cell.paragraphs[0])
    cell.paragraphs[0].add_run("칸 뒤")

    assert "칸 앞1)1)칸 각주\n칸 뒤" in export_text(document, notes=True)
    assert "칸 각주" not in export_text(document)


def test_html_and_markdown_write_notes_too() -> None:
    assert "본문 앞1)1)각주 글\n본문 뒤" in export_html(body_footnote(), notes=True)
    assert "본문 앞1)1)각주 글\n본문 뒤" in export_markdown(body_footnote(), notes=True)
    assert "각주 글" not in export_markdown(body_footnote())
