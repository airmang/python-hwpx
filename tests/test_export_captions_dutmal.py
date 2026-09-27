# SPDX-License-Identifier: Apache-2.0
"""Plain, HTML and Markdown export write captions and 덧말 the way Hancom's text save does.

A table's caption follows the table, in a cell too, a picture's or a shape's caption comes where it
sits, and a 덧말 is its main text followed by ``(덧말:<sub text>)``.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP
from hwpx.tools.exporter import export_html, export_markdown, export_text

EXPORTS = [export_text, export_html, export_markdown]
FIXTURES = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (40, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _table_with_caption() -> HwpxDocument:
    doc = HwpxDocument.new()
    paragraph = doc.sections[0].add_paragraph("표 앞 글")
    table = paragraph.add_table(1, 1)
    table.set_cell_text(0, 0, "칸 글")
    table.set_caption("표 1 요약", side="TOP")
    doc.add_paragraph("표 뒤 글")
    return doc


@pytest.mark.parametrize("export", EXPORTS)
def test_a_table_caption_follows_the_table(export) -> None:
    text = export(_table_with_caption())
    assert text.index("칸 글") < text.index("표 1 요약") < text.index("표 뒤 글")


@pytest.mark.parametrize("export", EXPORTS)
def test_a_picture_caption_is_exported(export) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("그림 앞 글")
    picture = doc.add_picture(_png(), "png")
    picture.set_caption("그림 1 설명")
    assert "그림 1 설명" in export(doc)


@pytest.mark.parametrize("export", EXPORTS)
def test_a_shape_caption_is_exported(export) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("도형 앞 글")
    rect = doc.shapes.add_rectangle(4000, 2000)
    rect.set_caption("도형 설명")
    assert "도형 설명" in export(doc)


@pytest.mark.parametrize("export", EXPORTS)
def test_a_dutmal_is_its_main_text_and_its_sub_text(export) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("덧말 앞 글")
    doc.shapes.add_dutmal("본말", "위 글")
    assert "본말(덧말:위 글)" in export(doc)


def test_a_table_in_a_cell_comes_where_it_sits_with_its_caption_after_it() -> None:
    doc = HwpxDocument.new()
    cell_paragraph = doc.add_table(1, 1).cell(0, 0).paragraphs[0]
    cell_paragraph.add_run("칸 앞")
    inner = cell_paragraph.add_table(1, 2)
    inner.set_cell_text(0, 0, "안 칸1")
    inner.set_cell_text(0, 1, "안 칸2")
    inner.set_caption("안 표 설명", side="TOP")
    cell_paragraph.add_run("칸 뒤")

    assert export_text(doc).split("\n") == ["칸 앞", "안 칸1", "안 칸2", "안 표 설명", "칸 뒤"]


def test_a_caption_keeps_its_auto_number() -> None:
    doc = HwpxDocument.open(FIXTURES / "reader_writer__SimpleRectangle.hwpx")

    assert doc.text.plain().endswith("그림 1 ")


@pytest.mark.parametrize("export", EXPORTS)
def test_a_left_out_table_takes_its_caption_with_it(export) -> None:
    text = export(_table_with_caption(), include_tables=False)

    assert "표 1 요약" not in text and "표 앞 글" in text and "표 뒤 글" in text


def _object_with_caption(run, tag: str):
    holder = run.makeelement(f"{HP}{tag}", {})
    caption = holder.makeelement(f"{HP}caption", {})
    holder.append(caption)
    sub_list = caption.makeelement(f"{HP}subList", {})
    caption.append(sub_list)
    paragraph = sub_list.makeelement(f"{HP}p", {})
    sub_list.append(paragraph)
    caption_run = paragraph.makeelement(f"{HP}run", {})
    paragraph.append(caption_run)
    text = caption_run.makeelement(f"{HP}t", {})
    text.text = "차트 1 매출"
    caption_run.append(text)
    return holder


def test_an_object_written_twice_in_a_switch_is_read_once() -> None:
    # Hancom writes a chart in hp:case and the same chart as OLE in hp:default
    doc = HwpxDocument.new()
    run = doc.add_paragraph("앞").element.find(f"{HP}run")
    switch = run.makeelement(f"{HP}switch", {})
    run.append(switch)
    for branch, tag in (("case", "chart"), ("default", "ole")):
        holder = switch.makeelement(f"{HP}{branch}", {})
        switch.append(holder)
        holder.append(_object_with_caption(run, tag))
    tail = run.makeelement(f"{HP}t", {})
    tail.text = "뒤"
    run.append(tail)

    assert export_text(doc).split("\n") == ["앞", "차트 1 매출", "뒤"]


def test_mail_merge_fills_captions_and_dutmal(tmp_path) -> None:
    from hwpx.tools.mail_merge import merge_template_rows

    doc = HwpxDocument.new()
    doc.add_paragraph("이름: {{name}}")
    paragraph = doc.sections[0].add_paragraph("표 담은 문단")
    table = paragraph.add_table(1, 1)
    table.set_cell_text(0, 0, "칸")
    table.set_caption("캡션: {{title}}")
    doc.shapes.add_dutmal("{{who}}", "덧말", paragraph=doc.add_paragraph(""))
    template = tmp_path / "tpl.hwpx"
    doc.save_to_path(template)

    report = merge_template_rows(template, [{"name": "홍길동", "title": "요약", "who": "김"}], output_dir=tmp_path / "out")

    (row,) = report["rows"]
    assert row["ok"], row
    assert row["replacedCount"] == 3 and row["unresolvedPlaceholders"] == []
    text = export_text(HwpxDocument.open(row["filename"]))
    assert "캡션: 요약" in text and "김(덧말:덧말)" in text and "{{" not in text


def test_a_caption_of_a_table_in_a_cell_is_written_once() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.sections[0].add_paragraph("바깥")
    outer = paragraph.add_table(1, 1)
    cell_paragraph = outer.cell(0, 0).paragraphs[0]
    inner = cell_paragraph.add_table(1, 1)
    inner.set_cell_text(0, 0, "안쪽 칸")
    inner.set_caption("안쪽 표 설명")

    assert export_text(doc).count("안쪽 표 설명") == 1
