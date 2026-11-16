"""Two different things are called a highlight, and each is written the way Hancom writes it.

* The marker pen (형광펜, ``doc.text.highlight(paragraph, match, color=)``) is a pair of marks *inside*
  the ``hp:t`` holding the text: ``<hp:t>앞 <hp:markpenBegin color="#FFFF00"/>글<hp:markpenEnd/> 뒤</hp:t>``
  -- the shape of ``hancom_saved/line_cache_fields.hwpx`` (and 42 of the 47 marks of the 250 Hancom
  2024 conversions; the other five open a run).
* ``highlight=`` of ``run.set_format``/``paragraph.format_range``/``ensure_run`` is the character
  shape's shade colour (글자 모양 → 음영 색, ``hh:charPr/@shadeColor``): no mark in the text.
"""

from __future__ import annotations

import re
from pathlib import Path

from hwpx import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"
_NS = re.compile(r' xmlns:\w+="[^"]+"')


def _xml(element) -> str:
    from lxml import etree

    return _NS.sub("", etree.tostring(element, encoding="unicode"))


def test_hancom_saves_the_marker_pen_inside_the_text() -> None:
    doc = HwpxDocument.open(SAVED / "line_cache_fields.hwpx")
    highlight = next(h for h in doc.text.highlights if h.text == "시스템")
    text = next(t for t in highlight.paragraph.element.iter(f"{HP}t") if t.find(f"{HP}markpenBegin") is not None)
    assert [child.tag.split("}")[-1] for child in text] == ["markpenBegin", "markpenEnd"]


def test_the_marker_pen_is_written_inside_the_text_as_hancom_does() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("앞 글 뒤")
    highlight = doc.text.highlight(paragraph, "글", color="#FFFF00")
    assert (highlight.text, highlight.color) == ("글", "#FFFF00")
    assert '<hp:t>앞 <hp:markpenBegin color="#FFFF00"/>글<hp:markpenEnd/> 뒤</hp:t>' in _xml(paragraph.element)
    assert paragraph.text == "앞 글 뒤"


def test_a_marker_pen_in_a_table_cell_paragraph() -> None:
    doc = HwpxDocument.new()
    cell_paragraph = doc.add_table(1, 2).cell(0, 0).paragraphs[0]
    cell_paragraph.add_run("① 보기")
    doc.text.highlight(cell_paragraph, "①")
    assert '<hp:markpenBegin color="#FFFF00"/>①<hp:markpenEnd/> 보기</hp:t>' in _xml(cell_paragraph.element)
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok
    assert [(h.text, h.color) for h in reopened.text.highlights] == [("①", "#FFFF00")]


def test_format_range_highlight_is_the_shade_colour_not_a_marker_pen() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("앞 글 뒤")
    (run,) = paragraph.format_range(2, 3, highlight="#FFFF00")
    assert run.text == "글" and run.highlight == "#FFFF00"
    assert paragraph.element.find(f".//{HP}markpenBegin") is None
    style = doc.styles.char_property(run.char_pr_id_ref)
    assert style.attributes["shadeColor"] == "#FFFF00"
    assert doc.text.highlights == ()
