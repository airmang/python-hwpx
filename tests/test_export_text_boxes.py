"""Text in text boxes reaches plain, HTML and Markdown export and the page preview.

A text box's paragraphs come where the box sits in the paragraph that holds it, in document
order with the paragraph's tables; text on both sides of the box is written around it. The
preview writes the text next to the shape marker.
"""

from __future__ import annotations

from hwpx.document import HwpxDocument
from hwpx.oxml import HwpxOxmlParagraph
from hwpx.oxml.namespaces import HP
from hwpx.tools.exporter import export_html, export_markdown, export_text
from hwpx.tools.layout_preview import render_layout_preview


def _document() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("앞 문단")
    holder = document.add_paragraph("상자 담은 문단")
    document.shapes.add_rectangle(paragraph=holder).set_draw_text("상자 글")
    holder.add_table(1, 1).cell(0, 0).text = "같은 문단의 칸"
    document.add_paragraph("뒤 문단")
    return document


def test_a_text_box_in_a_table_cell_shows_once_in_the_preview() -> None:
    document = HwpxDocument.new()
    cell = document.add_table(1, 1).cell(0, 0)
    cell.text = "칸 글"
    document.shapes.add_rectangle(paragraph=cell.paragraphs[0]).set_draw_text("칸상자글")

    html = render_layout_preview(document.to_bytes()).html

    assert html.count("칸상자글") == 1
    assert html.count("칸 글") == 1


def test_mail_merge_fills_placeholders_in_text_boxes(tmp_path) -> None:
    from hwpx.tools.mail_merge import merge_template_rows

    document = HwpxDocument.new()
    document.add_paragraph("이름: {{name}}")
    holder = document.add_paragraph("상자 담은 문단")
    document.shapes.add_rectangle(paragraph=holder).set_draw_text("상자: {{name}}")
    cell = document.add_table(1, 1).cell(0, 0)
    cell.text = "칸"
    document.shapes.add_rectangle(paragraph=cell.paragraphs[0]).set_draw_text("칸 상자: {{name}}")
    template = tmp_path / "tpl.hwpx"
    document.save_to_path(template)

    report = merge_template_rows(template, [{"name": "홍길동"}], output_dir=tmp_path / "out")

    (row,) = report["rows"]
    assert row["ok"], row
    assert row["replacedCount"] == 3
    text = export_text(HwpxDocument.open(row["filename"]))
    assert "상자: 홍길동" in text and "칸 상자: 홍길동" in text and "{{name}}" not in text


def test_plain_text_puts_the_box_after_its_paragraph_in_document_order() -> None:
    text = export_text(_document())

    assert text.split("\n") == ["앞 문단", "상자 담은 문단", "상자 글", "같은 문단의 칸", "뒤 문단"]


def _box_between_text() -> HwpxDocument:
    document = HwpxDocument.new()
    holder = document.add_paragraph("상자 앞 글")
    document.shapes.add_rectangle(paragraph=holder).set_draw_text("상자 글")
    holder.add_run("상자 뒤 글")
    return document


def test_the_box_text_comes_where_the_box_sits_in_its_paragraph() -> None:
    document = _box_between_text()

    assert export_text(document).split("\n") == ["상자 앞 글", "상자 글", "상자 뒤 글"]
    assert export_markdown(document).split("\n\n") == ["상자 앞 글", "상자 글", "상자 뒤 글"]
    assert "<p>상자 앞 글</p>\n<p>상자 글</p>\n<p>상자 뒤 글</p>" in export_html(document, full_document=False)


def test_a_numbered_paragraph_keeps_its_label_on_the_text_before_the_box() -> None:
    document = _box_between_text()
    document.styles.apply_list_format(paragraph_index=1, kind="number")

    assert export_text(document, list_labels=True).split("\n") == ["1. 상자 앞 글", "상자 글", "상자 뒤 글"]


def test_markdown_and_html_carry_the_box_text() -> None:
    document = _document()

    markdown = export_markdown(document)
    html = export_html(document, full_document=False)

    assert markdown.index("상자 담은 문단") < markdown.index("상자 글") < markdown.index("| 같은 문단의 칸 |")
    assert "<p>상자 글</p>" in html
    assert html.index("<p>상자 글</p>") < html.index("<td>같은 문단의 칸</td>")


def test_without_tables_the_box_text_stays() -> None:
    text = export_text(_document(), include_tables=False)

    assert text.split("\n") == ["앞 문단", "상자 담은 문단", "상자 글", "뒤 문단"]


def test_a_box_in_a_cell_comes_where_it_sits_in_the_cell() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_table(1, 1).cell(0, 0).paragraphs[0]
    paragraph.add_run("칸 앞")
    document.shapes.add_rectangle(paragraph=paragraph).set_draw_text("칸 상자")
    paragraph.add_run("칸 뒤")

    assert export_text(document).split("\n") == ["칸 앞", "칸 상자", "칸 뒤"]


def test_a_box_in_a_cell_is_read_once_with_the_cell() -> None:
    document = HwpxDocument.new()
    cell = document.add_table(1, 1).cell(0, 0)
    document.shapes.add_rectangle(paragraph=cell.paragraphs[0]).set_draw_text("칸 속 상자")

    text = export_text(document)

    assert text.count("칸 속 상자") == 1


def test_a_box_in_a_header_is_not_body_text() -> None:
    document = HwpxDocument.new()
    document.page.set_header(text="머리말")
    section = document.oxml.sections[0]
    for header in section.element.iter(f"{HP}header"):
        paragraph = HwpxOxmlParagraph(header.find(f"{HP}subList/{HP}p"), section)
        document.shapes.add_rectangle(paragraph=paragraph).set_draw_text("머리말 상자")
    document.add_paragraph("본문")

    assert "머리말 상자" not in export_text(document)


def test_the_masking_policy_covers_box_text() -> None:
    text = export_text(_document(), masking_policy=lambda value: value.replace("상자", "**"))

    assert "** 글" in text and "상자" not in text


def test_the_document_namespace_exports_the_box_text() -> None:
    document = _document()

    assert "상자 글" in document.text.plain()
    assert "상자 글" in document.text.markdown()
    assert "상자 글" in document.text.html()


def test_the_preview_writes_the_box_text_next_to_the_shape_marker() -> None:
    html = render_layout_preview(_document().to_bytes()).html

    marker = html.index("⟦도형⟧")
    assert html.index('<span class="hwpx-shape-text">상자 글</span>') > marker
