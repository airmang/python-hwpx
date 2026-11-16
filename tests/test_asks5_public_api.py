# SPDX-License-Identifier: Apache-2.0
"""asks5: what python-hwpx-automation still did through ``.element`` for lack of a public API.

- ``doc.text.iter_paragraphs(where="hidden_comment")``: 숨은 설명 is a place of its own;
- ``doc.fields.buttons``: 명령 단추 with its ``caption``;
- ``section.clear_body(keep_headers=False)``: the body and the headers go, the section settings stay;
- ``paragraph.replace_range(start, end, text)``: characters replaced, runs as they are;
- ``paragraph.copy_to(paragraph, before=)``: a paragraph copied, into another document too.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.tools.package_validator import validate_editor_open_safety

FIXTURES = Path(__file__).parent / "fixtures"
CORPUS = FIXTURES / "hwpxlib_corpus"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _changed(before: bytes, after: bytes) -> set[str]:
    old, new = _parts(before), _parts(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


# -- reads ------------------------------------------------------------------------------------------


def test_hidden_comments_are_a_place_of_their_own() -> None:
    doc = HwpxDocument.open(CORPUS / "error__20230413__test.hwpx")
    hidden = list(doc.text.iter_paragraphs(where="hidden_comment"))
    assert hidden and all(place.where == "hidden_comment" for place in hidden)
    elements = [place.paragraph.element for place in hidden]
    holders = [node for section in doc.sections for node in section.element.iter(f"{_HP}hiddenComment")]
    assert all(any(element in list(holder.iter()) for holder in holders) for element in elements)
    body = [place.paragraph.element for place in doc.text.iter_paragraphs(where="body")]
    assert not any(element is other for element in elements for other in body)


def test_text_art_text_is_read_from_its_object() -> None:
    doc = HwpxDocument.open(CORPUS / "reader_writer__SimpleTextArt.hwpx")
    (place,) = list(doc.text.iter_objects(kinds="textart"))
    assert place.object.attributes["text"].startswith("hwpx 라이브러리 테스트")


def test_command_buttons_and_their_captions() -> None:
    doc = HwpxDocument.open(CORPUS / "reader_writer__SimpleButtons.hwpx")
    (button,) = doc.fields.buttons
    assert (button.name, button.caption) == ("PushButton1", "명령 단추1")
    assert button.paragraph is not None and button.section is doc.sections[0]
    assert all(type(b).__name__ == "Button" for b in doc.fields.buttons)


# -- clear_body(keep_headers=False) --------------------------------------------------------------------


def _with_header() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.page.set_margins(left=11339, top=8504)
    doc.page.set_header(text="머리말 글")
    doc.page.set_footer(text="꼬리말 글")
    doc.page.set_columns(2)
    doc.add_paragraph("둘째")
    return HwpxDocument.open(doc.to_bytes())


def test_clear_body_keeps_headers_by_default() -> None:
    doc = _with_header()
    with pytest.raises(HwpxError) as refused:
        doc.sections[0].clear_body()
    assert refused.value.code == "section-clear-control-content"


def test_clear_body_without_headers_keeps_only_the_section_settings() -> None:
    doc = _with_header()
    original = doc.to_bytes()
    report = doc.sections[0].clear_body(keep_headers=False)
    assert report.removed_paragraphs == 1 and report.stripped_controls == 2
    data = doc.to_bytes()
    assert validate_editor_open_safety(data).ok
    again = HwpxDocument.open(data)
    section = again.sections[0]
    assert len(section.paragraphs) == 1 and section.paragraphs[0].text == ""
    assert section.properties.headers == () and section.properties.footers == ()
    assert section.properties.page_margins.left == 11339
    first = section.element.find(f"{_HP}p")
    assert [c.get("colCount") for c in first.iter(f"{_HP}colPr")] == ["2"]
    assert first.find(f".//{_HP}header") is None and first.find(f".//{_HP}footer") is None
    # nothing else is touched
    assert _changed(original, data) == {"Contents/section0.xml"}


def test_clear_body_keep_headers_takes_a_bool() -> None:
    with pytest.raises(HwpxError) as refused:
        _with_header().sections[0].clear_body(keep_headers="no")  # type: ignore[arg-type]
    assert refused.value.code == "section-clear-mode-invalid"


# -- replace_range ---------------------------------------------------------------------------------


def _two_runs() -> tuple[HwpxDocument, object]:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가나다")
    paragraph.add_run("라마바", bold=True)
    return doc, paragraph


def test_replace_range_keeps_the_runs_as_doc_text_replace_does() -> None:
    doc, paragraph = _two_runs()
    replaced, other = _two_runs()
    paragraph.replace_range(2, 4, "XYZW")  # type: ignore[attr-defined]
    assert replaced.text.replace("다라", "XYZW", everywhere=True) == 1
    assert paragraph.text == "가나XYZW마바"  # type: ignore[attr-defined]
    assert [(r.text, r.char_pr_id_ref) for r in paragraph.runs] == [  # type: ignore[attr-defined]
        (r.text, r.char_pr_id_ref) for r in other.runs]  # type: ignore[attr-defined]
    assert _parts(doc.to_bytes())["Contents/section0.xml"] == _parts(replaced.to_bytes())["Contents/section0.xml"]


def test_replace_range_inserts_and_removes() -> None:
    _doc, paragraph = _two_runs()
    paragraph.replace_range(3, 3, "+")  # type: ignore[attr-defined]  # after 다: in 다's run
    assert [r.text for r in paragraph.runs if r.text] == ["가나다+", "라마바"]  # type: ignore[attr-defined]
    paragraph.replace_range(0, 2, "")  # type: ignore[attr-defined]
    assert paragraph.text == "다+라마바"  # type: ignore[attr-defined]


def test_replace_range_writes_tabs_as_hancom_and_drops_the_cache() -> None:
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "memos_in_fields.hwpx")
    paragraph = next(p for p in doc.paragraphs if len(p.text) > 4 and p.element.find(f"{_HP}linesegarray") is not None
                     and "\t" not in p.text)
    paragraph.replace_range(1, 2, "\t")
    assert paragraph.text[1] == "\t"
    assert paragraph.element.find(f".//{_HP}tab") is not None
    assert paragraph.element.find(f"{_HP}linesegarray") is None


def test_replace_range_refuses_a_range_across_a_tab() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("앞\t뒤")
    before = doc.to_bytes()
    with pytest.raises(HwpxError) as refused:
        paragraph.replace_range(0, 3, "x")
    assert refused.value.code == "paragraph-range-crosses-element"
    with pytest.raises(HwpxError) as refused:
        paragraph.replace_range(0, 9, "x")
    assert refused.value.code == "paragraph-range-invalid"
    assert doc.to_bytes() == before


# -- copy_to ---------------------------------------------------------------------------------------


def _source() -> HwpxDocument:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("원본 ")
    paragraph.add_run("빨간 굵은 글", bold=True, color="#C00000", size=14)
    paragraph.alignment = "CENTER"
    return doc


def test_copy_to_another_document_remaps_the_definitions() -> None:
    source = _source()
    target = HwpxDocument.new()
    anchor = target.add_paragraph("대상")
    before_target = target.to_bytes()
    copied = source.paragraphs[-1].copy_to(anchor)
    assert copied == target.paragraphs[-1] and copied.text == "원본 빨간 굵은 글"
    data = target.to_bytes()
    assert _changed(before_target, data) <= {"Contents/section0.xml", "Contents/header.xml"}
    assert validate_editor_open_safety(data).ok
    again = HwpxDocument.open(data)
    run = again.paragraphs[-1].runs[-1]
    assert run.bold and run.size == 14 and run.color == "#C00000"
    assert again.paragraphs[-1].alignment == "CENTER"
    # the source is as it was
    assert source.paragraphs[-1].text == "원본 빨간 굵은 글"


def test_copy_to_brings_pictures_and_tables_along() -> None:
    import struct
    import zlib

    def png() -> bytes:
        raw = b"".join(b"\x00" + b"\x40\x80\xc8" * 4 for _ in range(4))
        chunk = lambda k, d: struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xFFFFFFFF)  # noqa: E731
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

    source = HwpxDocument.new()
    holder = source.add_paragraph("그림과 표")
    holder.add_picture(source.media.add_image(png(), "png"), width=2000, height=2000)
    holder.add_table(2, 2).cell(0, 0).text = "칸"
    target = HwpxDocument.new()
    anchor = target.add_paragraph("대상")
    copied = source.paragraphs[-1].copy_to(anchor, before=True)
    assert target.paragraphs[0] == copied
    data = target.to_bytes()
    assert validate_editor_open_safety(data).ok
    again = HwpxDocument.open(data)
    assert len(again.media.pictures) == 1
    assert again.paragraphs[0].tables[0].cell(0, 0).text == "칸"
    assert any(name.startswith("BinData/") for name in _parts(data))


def test_paragraphs_copied_one_by_one_keep_one_numbering() -> None:
    """Hancom counts a numbering per definition: three numbered paragraphs copied one by one stay one
    list (1, 2, 3) because the later copies map to the definition the first one brought."""

    source = HwpxDocument.new()
    numbering = source.styles.add_numbering()
    numbered = []
    for i in range(3):
        paragraph = source.add_paragraph(f"번호 {i}")
        paragraph.set_numbering(numbering, level=1)
        numbered.append(paragraph)
    target = HwpxDocument.new()
    last = target.add_paragraph("대상")
    before = set(target.styles.numberings)
    for paragraph in numbered:
        last = paragraph.copy_to(last)
    again = HwpxDocument.open(target.to_bytes())
    refs = {again.styles.paragraph_property(p.para_pr_id_ref).heading.id_ref for p in again.paragraphs[-3:]}
    assert len(refs) == 1
    assert len(set(again.styles.numberings) - before) == 1


def test_copy_to_the_front_of_a_section_takes_its_settings() -> None:
    source = _source()
    target = HwpxDocument.new()
    target.add_paragraph("첫")
    target.page.set_margins(left=11339)
    copied = source.paragraphs[-1].copy_to(target.paragraphs[0], before=True)
    first = target.sections[0].element.find(f"{_HP}p")
    assert first is copied.element and first.find(f"{_HP}run/{_HP}secPr") is not None
    again = HwpxDocument.open(target.to_bytes())
    assert again.sections[0].properties.page_margins.left == 11339


def test_copy_to_in_the_same_document_is_insert_after_s_copy() -> None:
    doc = _source()
    other = doc.add_paragraph("끝")
    copied = doc.paragraphs[-2].copy_to(other)
    assert doc.paragraphs[-1] == copied and copied.text == "원본 빨간 굵은 글"
    assert copied.id != doc.paragraphs[-3].id
    # the section settings of the first paragraph stay behind; the text runs come with their shapes
    assert [(r.text, r.char_pr_id_ref) for r in copied.runs if r.text] == [
        (r.text, r.char_pr_id_ref) for r in doc.paragraphs[-3].runs if r.text]
    assert copied.element.find(f".//{_HP}secPr") is None


def test_copy_to_refuses_what_insert_document_refuses_and_bad_places() -> None:
    doc = _source()
    with pytest.raises(HwpxError) as refused:
        doc.paragraphs[-1].copy_to(3)  # type: ignore[arg-type]
    assert refused.value.code == "paragraph-invalid-type"
    with pytest.raises(HwpxError) as refused:
        doc.paragraphs[-1].copy_to(doc.paragraphs[0], before="yes")  # type: ignore[arg-type]
    assert refused.value.code == "paragraph-invalid-type"
