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
        return style.text_color(), style.underline_type()
    header = document._root.headers[0]
    char_pr = next(el for el in header.element.iter() if el.tag.endswith("}charPr") and el.get("id") == run.get("charPrIDRef"))
    underline = next((el for el in char_pr if el.tag.endswith("}underline")), None)
    return char_pr.get("textColor"), underline.get("type") if underline is not None else None


def test_a_paragraph_link_uses_hancom_link_style_by_default() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("앞 글 ")

    paragraph.add_hyperlink("https://example.com", "링크")

    color, underline = _style(document, _display_run(paragraph))
    assert color == "#0000FF"
    assert underline == "BOTTOM"


def test_the_paragraph_link_style_matches_the_document_level_link() -> None:
    document = HwpxDocument.new()
    first = document.add_paragraph("")
    first.add_hyperlink("https://example.com", "링크")
    second = document.add_paragraph("")
    document.refs.add_hyperlink("https://example.com", "링크", paragraph=second)

    assert _display_run(first).get("charPrIDRef") == _display_run(second).get("charPrIDRef")


def test_an_explicit_char_pr_still_wins() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")

    paragraph.add_hyperlink("https://example.com", "링크", char_pr_id_ref=0)

    assert _display_run(paragraph).get("charPrIDRef") == "0"


def test_the_field_runs_keep_the_paragraph_style() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")

    paragraph.add_hyperlink("https://example.com", "링크")

    field_runs = [run for run in paragraph.element.findall(f"{HP}run") if run.find(f"{HP}ctrl") is not None]
    assert [run.get("charPrIDRef") for run in field_runs] == ["0", "0"]


def test_a_footnote_link_gets_the_same_style() -> None:
    document = HwpxDocument.new()
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
    document = HwpxDocument.new()
    big = document._root.ensure_run_style(bold=True, size=16)
    paragraph = document.add_paragraph("제목 ", char_pr_id_ref=big)

    paragraph.add_hyperlink("https://example.com", "링크")

    assert _look(document, _display_run(paragraph)) == ("1600", True, "#0000FF")
    assert _style(document, _display_run(paragraph))[1] == "BOTTOM"


def test_a_link_style_made_for_one_paragraph_does_not_leak_into_another() -> None:
    document = HwpxDocument.new()
    big = document._root.ensure_run_style(bold=True, size=16)
    title = document.add_paragraph("제목 ", char_pr_id_ref=big)
    title.add_hyperlink("https://example.com", "링크")
    body = document.add_paragraph("본문 ")

    body.add_hyperlink("https://example.com", "링크")

    assert _look(document, _display_run(body)) == ("1000", False, "#0000FF")
    assert _display_run(body).get("charPrIDRef") != _display_run(title).get("charPrIDRef")


def test_links_in_paragraphs_of_the_same_look_share_one_style() -> None:
    document = HwpxDocument.new()
    big = document._root.ensure_run_style(bold=True, size=16)
    first = document.add_paragraph("제목 ", char_pr_id_ref=big)
    first.add_hyperlink("https://example.com", "링크")
    second = document.add_paragraph("다른 제목 ", char_pr_id_ref=big)
    document.refs.add_hyperlink("https://example.com", "링크", paragraph=second)

    assert _display_run(first).get("charPrIDRef") == _display_run(second).get("charPrIDRef")


def test_markdown_writes_link_text_without_the_link_style() -> None:
    from hwpx.tools.markdown_export import export_markdown

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    document.refs.add_hyperlink("https://example.com", "링크", paragraph=paragraph)

    markdown = export_markdown(document)

    assert "[링크](https://example.com)" in markdown
    assert "<u>" not in markdown and "#0000FF" not in markdown
