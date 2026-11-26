"""A link added to a paragraph object is blue and underlined, like doc.refs.add_hyperlink."""

from __future__ import annotations

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP


def _display_run(paragraph):
    return next(run for run in paragraph.element.findall(f"{HP}run") if run.find(f"{HP}t") is not None
                and (run.find(f"{HP}t").text or "") == "링크")


def _style(document: HwpxDocument, run) -> tuple[str | None, str | None]:
    style = document.styles.char_property(run.get("charPrIDRef")) if hasattr(document.styles, "char_property") else None
    if style is not None:
        return style.color, style.underline_type
    header = document._root.headers[0]
    char_pr = next(el for el in header.element.iter() if el.tag.endswith("}charPr") and el.get("id") == run.get("charPrIDRef"))
    underline = next((el for el in char_pr if el.tag.endswith("}underline")), None)
    return char_pr.get("textColor"), underline.get("type") if underline is not None else None


def test_a_paragraph_link_uses_hancom_link_style_by_default() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    paragraph = document.add_paragraph("앞 글 ")

    paragraph.add_hyperlink("https://example.com", "링크")

    color, underline = _style(document, _display_run(paragraph))
    assert color == "#0000FF"
    assert underline == "BOTTOM"


def test_the_paragraph_link_style_matches_the_document_level_link() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    first = document.add_paragraph("")
    first.add_hyperlink("https://example.com", "링크")
    second = document.add_paragraph("")
    document.refs.add_hyperlink("https://example.com", "링크", paragraph=second)

    assert _display_run(first).get("charPrIDRef") == _display_run(second).get("charPrIDRef")


def test_an_explicit_char_pr_still_wins() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    paragraph = document.add_paragraph("")

    paragraph.add_hyperlink("https://example.com", "링크", char_pr_id_ref=0)

    assert _display_run(paragraph).get("charPrIDRef") == "0"


def test_the_field_runs_keep_the_paragraph_style() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    paragraph = document.add_paragraph("")

    paragraph.add_hyperlink("https://example.com", "링크")

    field_runs = [run for run in paragraph.element.findall(f"{HP}run") if run.find(f"{HP}ctrl") is not None]
    assert [run.get("charPrIDRef") for run in field_runs] == ["0", "0"]


def test_a_footnote_link_gets_the_same_style() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    note = document.add_paragraph("본문").add_footnote("각주 ")

    note.add_hyperlink("https://example.com", "링크")

    color, underline = _style(document, _display_run(note.body_paragraph))
    assert color == "#0000FF"
    assert underline == "BOTTOM"


def _look(document: HwpxDocument, run) -> tuple:
    header = document._root.headers[0]
    char_pr = next(el for el in header._char_properties_element() if el.get("id") == run.get("charPrIDRef"))
    bold = any(el.tag.endswith("}bold") for el in char_pr)
    return char_pr.get("height"), bold, char_pr.get("textColor")


def test_a_link_keeps_the_size_and_weight_of_its_paragraph() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    big = document._root.ensure_run_style(bold=True, size=16)
    paragraph = document.add_paragraph("제목 ", char_pr_id_ref=big)

    paragraph.add_hyperlink("https://example.com", "링크")

    assert _look(document, _display_run(paragraph)) == ("1600", True, "#0000FF")
    assert _style(document, _display_run(paragraph))[1] == "BOTTOM"


def test_a_link_style_made_for_one_paragraph_does_not_leak_into_another() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    big = document._root.ensure_run_style(bold=True, size=16)
    title = document.add_paragraph("제목 ", char_pr_id_ref=big)
    title.add_hyperlink("https://example.com", "링크")
    body = document.add_paragraph("본문 ")

    body.add_hyperlink("https://example.com", "링크")

    assert _look(document, _display_run(body)) == ("1000", False, "#0000FF")
    assert _display_run(body).get("charPrIDRef") != _display_run(title).get("charPrIDRef")


def test_links_in_paragraphs_of_the_same_look_share_one_style() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    big = document._root.ensure_run_style(bold=True, size=16)
    first = document.add_paragraph("제목 ", char_pr_id_ref=big)
    first.add_hyperlink("https://example.com", "링크")
    second = document.add_paragraph("다른 제목 ", char_pr_id_ref=big)
    document.refs.add_hyperlink("https://example.com", "링크", paragraph=second)

    assert _display_run(first).get("charPrIDRef") == _display_run(second).get("charPrIDRef")


# -- the field runs' character shape (hyperlink_field_runs_word_import.hwpx) -------------------------
#
# Hangul puts a link's fieldBegin in the run of the text before it, and its fieldEnd in the link text's run
# (a link alone in its paragraph: both in the link's run). The controls sit in the line: in 8pt text, field
# runs in shape 0 (10pt) make Hangul draw the line taller (desktop check, 2026-11-26).


def _field_shapes(paragraph) -> tuple[str | None, str | None]:
    runs = paragraph.element.findall(f"{HP}run")
    begin = next(run for run in runs if run.find(f"{HP}ctrl/{HP}fieldBegin") is not None)
    end = next(run for run in runs if run.find(f"{HP}ctrl/{HP}fieldEnd") is not None)
    return begin.get("charPrIDRef"), end.get("charPrIDRef")


def _hancom_links() -> list[tuple[str | None, str | None, str | None, str | None]]:
    """(text before, fieldBegin, link text, fieldEnd) shapes of the fixture's four links."""

    import zipfile
    from pathlib import Path

    from lxml import etree

    path = Path(__file__).parent / "fixtures" / "hancom_saved" / "hyperlink_field_runs_word_import.hwpx"
    with zipfile.ZipFile(path) as package:
        root = etree.fromstring(package.read("Contents/section0.xml"))
    found = []
    for paragraph in root.iter(f"{HP}p"):
        runs = paragraph.findall(f"{HP}run")
        begin = next((run for run in runs if run.find(f"{HP}ctrl/{HP}fieldBegin") is not None), None)
        if begin is None:
            continue
        end = next(run for run in runs if run.find(f"{HP}ctrl/{HP}fieldEnd") is not None)
        texts = [run for run in runs if run.find(f"{HP}t") is not None and (run.find(f"{HP}t").text or "")]
        link = next(run for run in texts if "link" in run.find(f"{HP}t").text.lower()
                    and not run.find(f"{HP}t").text.startswith(("Small text", "plain")))
        before = runs[runs.index(begin) - 1] if begin.find(f"{HP}t") is None and runs.index(begin) > 0 else begin
        found.append((before.get("charPrIDRef"), begin.get("charPrIDRef"), link.get("charPrIDRef"),
                      end.get("charPrIDRef")))
    return found


def test_hangul_puts_the_begin_in_the_text_before_the_link() -> None:
    links = _hancom_links()
    assert len(links) == 4
    for before, begin, _link, _end in links[:2] + links[3:]:
        assert begin == before  # the run of the text before it (plain, then 8pt text)
    assert links[2][1] == links[2][2]  # alone in its paragraph: in the link's run


def test_the_field_runs_take_the_text_before_the_link_in_a_paragraph_of_several_shapes() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    small = document.styles.ensure_run(size=8)
    small_bold = document.styles.ensure_run(size=8, bold=True)
    paragraph = document.add_paragraph("")
    paragraph.add_run("Small text ", char_pr_id_ref=small)
    paragraph.add_run("bold ", char_pr_id_ref=small_bold)

    paragraph.add_hyperlink("https://example.com", "링크")

    # they were shape 0 (10pt) and the link text 10pt blue: Hangul drew the 8pt line taller
    assert _field_shapes(paragraph) == (small_bold, small_bold)
    assert _look(document, _display_run(paragraph)) == ("800", True, "#0000FF")


def test_a_link_starting_a_paragraph_can_name_its_field_shape() -> None:
    document = HwpxDocument.new(empty_first_line=True)
    small_link = document.styles.ensure_run(size=8, color="#0563C1", underline=True)
    paragraph = document.add_paragraph("")

    paragraph.add_hyperlink("https://example.com", "링크", char_pr_id_ref=small_link,
                            field_char_pr_id_ref=small_link)

    assert _field_shapes(paragraph) == (small_link, small_link)  # as Hangul writes a link alone
    second = document.add_paragraph("")
    document.refs.add_hyperlink("https://example.com", "링크", paragraph=second, char_pr_id_ref=small_link,
                                field_char_pr_id_ref=small_link)
    assert _field_shapes(second) == (small_link, small_link)


def test_without_a_field_shape_an_empty_paragraph_keeps_shape_0() -> None:
    # DEV-030: the link's own shape stays on its text unless the caller names the field shape
    document = HwpxDocument.new(empty_first_line=True)
    small_link = document.styles.ensure_run(size=8, color="#0563C1")
    paragraph = document.add_paragraph("")

    paragraph.add_hyperlink("https://example.com", "링크", char_pr_id_ref=small_link)

    assert _field_shapes(paragraph) == ("0", "0")


def test_a_field_shape_the_header_lacks_is_refused() -> None:
    import pytest

    from hwpx.errors import HwpxLookupError

    document = HwpxDocument.new(empty_first_line=True)
    paragraph = document.add_paragraph("앞 ")
    before = paragraph.element.findall(f"{HP}run")

    with pytest.raises(HwpxLookupError) as caught:
        paragraph.add_hyperlink("https://example.com", "링크", field_char_pr_id_ref=999)

    assert caught.value.code == "style-definition-not-found"
    assert paragraph.element.findall(f"{HP}run") == before
