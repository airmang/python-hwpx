# SPDX-License-Identifier: Apache-2.0
"""A table's caption is its own place in ``doc.text.paragraphs()`` / ``doc.text.objects()``.

``hp:caption`` sits inside ``hp:tbl`` beside its rows. The walk took it for more of where the table
sat, so a body table's caption paragraph came back as ``"body"`` and a table inside the caption of a
table in a cell came back as ``"cell"`` (found in one of 786 public documents).
"""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _captioned() -> HwpxDocument:
    doc = HwpxDocument.new()
    body_table = doc.add_table(1, 1)
    body_table.set_caption("본문 표 캡션")
    outer = doc.add_table(1, 1)
    inner = outer.cell(0, 0).paragraphs[0].add_table(1, 1)
    inner.set_caption("칸 안 표 캡션")
    caption_paragraph = inner.caption.paragraphs[0]
    caption_table = caption_paragraph.add_table(1, 1)
    caption_table.cell(0, 0).text = "캡션 안 표의 칸"
    return HwpxDocument.open(doc.to_bytes())


def test_caption_paragraphs_are_in_the_caption() -> None:
    doc = _captioned()
    places = {place.paragraph.text: place for place in doc.text.paragraphs() if place.paragraph.text}
    assert places["본문 표 캡션"].where == "caption"
    assert places["칸 안 표 캡션"].where == "caption"
    assert places["캡션 안 표의 칸"].where == "cell"
    body = [place.paragraph.text for place in doc.text.paragraphs(where="body")]
    assert "본문 표 캡션" not in body and body == [paragraph.text for paragraph in doc.paragraphs]


def test_a_table_inside_a_caption_is_in_the_caption() -> None:
    doc = _captioned()
    tables = list(doc.text.objects(kinds="table"))
    assert [place.where for place in tables] == ["body", "body", "cell", "caption"]
    in_cells = list(doc.text.objects(kinds="table", where="cell"))
    assert len(in_cells) == 1 and in_cells[0].object.caption is not None
    # held by the outer table and by the table whose caption it is in
    assert [place.depth for place in doc.text.objects(kinds="table", where="caption")] == [2]


def test_hangul_saved_captions_in_cells() -> None:
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "pages_captioned_tables_in_cells.hwpx")
    captions = [place for place in doc.text.paragraphs(where="caption") if place.paragraph.text]
    assert captions and {place.paragraph.text for place in captions} >= {"캡션 1"}
    assert not any(place.paragraph.text.startswith("캡션") for place in doc.text.paragraphs(where="cell"))
    saved = HwpxDocument.open(FIXTURES / "hancom_saved" / "pages_table_caption_below.hwpx")
    assert [place.paragraph.text for place in saved.text.paragraphs(where="caption")] == ["표 캡션 글"]
    assert "표 캡션 글" not in [place.paragraph.text for place in saved.text.paragraphs(where="body")]
