# SPDX-License-Identifier: Apache-2.0
"""doc.styles: lookup by name, style edits and removal, numbering as values, tab
definitions, and paragraph shapes and border fills derived from a base."""

from __future__ import annotations

import io

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxLookupError, HwpxValueError
from hwpx.objects import Alignment, LineSpacing, NumberingInfo

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    document.save(buffer)
    reopened = HwpxDocument.open(buffer.getvalue())
    assert reopened.validate().ok
    return reopened


def _definitions(document: HwpxDocument, kind: str) -> dict[str, bytes]:
    header = document.oxml.headers[0].element
    return {element.get("id"): etree.tostring(element) for element in header.iter(f"{HH}{kind}")}


def _item_counts_match(document: HwpxDocument) -> None:
    header = document.oxml.headers[0].element
    for container, kind in (("charProperties", "charPr"), ("paraProperties", "paraPr"),
                            ("tabProperties", "tabPr"), ("borderFills", "borderFill"), ("styles", "style")):
        element = header.find(f".//{HH}{container}")
        if element is not None:
            assert element.get("itemCnt") == str(len(element.findall(f"{HH}{kind}")))




def test_styles_index_by_name_english_name_and_id() -> None:
    document = HwpxDocument.new()
    assert document.styles["바탕글"] is not None
    assert document.styles["Normal"].name == document.styles[0].name == document.styles["0"].name == "바탕글"
    assert "본문" in document.styles and "없는 스타일" not in document.styles
    with pytest.raises(KeyError):
        document.styles["없는 스타일"]


def test_set_style_format_moves_the_style_and_its_paragraphs_only() -> None:
    document = HwpxDocument.new()
    body = document.add_paragraph("본문", style="본문")
    local = document.add_paragraph("따로", style="본문")
    local.runs[-1].bold = True
    plain = document.add_paragraph("바탕", style="바탕글")
    old = document.styles["본문"]

    document.styles.set_style_format("본문", size=13, alignment="CENTER", spacing_after_pt=4)

    new = document.styles["본문"]
    assert (new.para_pr_id_ref, new.char_pr_id_ref) != (old.para_pr_id_ref, old.char_pr_id_ref)
    assert body.runs[-1].size == 13.0 and body.alignment is Alignment.CENTER and body.spacing_after_pt == 4.0
    assert local.alignment is Alignment.CENTER and local.runs[-1].size == 10.0  # a run formatted apart stays
    assert plain.alignment is Alignment.JUSTIFY and plain.runs[-1].size == 10.0
    with pytest.raises(HwpxValueError) as empty:
        document.styles.set_style_format("본문")
    assert empty.value.code == "style-format-empty"
    _reopen(document)


def test_remove_style_renumbers_and_hands_paragraphs_over() -> None:
    document = HwpxDocument.new()
    count = len(document.styles)
    body = document.add_paragraph("본문", style="본문")
    outline = document.add_paragraph("제목", style="개요 1")
    outline_id = int(outline.style_id_ref)

    with pytest.raises(HwpxValueError) as in_use:
        document.styles.remove_style("본문")
    assert in_use.value.code == "style-in-use"
    with pytest.raises(HwpxValueError) as default:
        document.styles.remove_style("바탕글")
    assert default.value.code == "style-remove-default"

    document.styles.remove_style("본문", replacement="바탕글")

    assert len(document.styles) == count - 1 and "본문" not in document.styles
    assert body.style is not None and body.style.name == "바탕글"
    assert int(outline.style_id_ref) == outline_id - 1 and outline.style.name == "개요 1"
    ids = sorted(int(style.raw_id or style.id) for style in document.styles.values())
    assert ids == list(range(len(ids)))
    for style in document.styles.values():
        assert document.styles.get(style.next_style_id_ref) is not None
    _item_counts_match(document)
    reopened = _reopen(document)
    assert reopened.paragraphs[-1].style.name == "개요 1"


def test_numbering_info_reads_levels_as_values() -> None:
    document = HwpxDocument.new()
    info = document.styles.numbering(1)
    assert isinstance(info, NumberingInfo)
    first = info.level(1)
    assert first is not None and (first.number_format, first.text, first.char_pr_id_ref) == ("DIGIT", "^1.", None)
    assert info.level(2).number_format == "HANGUL_SYLLABLE"
    assert document.styles.numbering(999) is None


def test_ensure_tab_definition_and_widened_paragraph_format() -> None:
    document = HwpxDocument.new()
    tab = document.styles.ensure_tab_definition(tab_stops=[{"pos_mm": 30}, {"pos": 20000, "type": "RIGHT"}])
    assert document.styles.ensure_tab_definition(tab_stops=[{"pos": 8504}, {"pos": 20000, "type": "RIGHT"}]) == tab
    stops = document.styles.tab_property(tab).tab_stops
    assert [(stop.pos, stop.type) for stop in stops] == [(8504, "LEFT"), (20000, "RIGHT")]

    shape = document.styles.ensure_paragraph_format(
        base_para_pr_id_ref=0,
        line_spacing=LineSpacing("AT_LEAST", 1200),
        condense=20,
        break_setting={"break_non_latin_word": "KEEP_WORD", "keep_lines": True},
        tab_pr_id_ref=tab,
    )
    read = document.styles.paragraph_property(shape)
    assert read.condense == 20 and read.tab_pr_id_ref == int(tab)
    assert read.break_setting.break_non_latin_word == "KEEP_WORD" and read.break_setting.keep_lines
    paragraph = document.add_paragraph("x", para_pr_id_ref=shape)
    assert paragraph.line_spacing == LineSpacing("AT_LEAST", 1200)
    with pytest.raises(HwpxValueError) as word:
        document.styles.ensure_paragraph_format(break_setting={"break_latin_word": "SOMETIMES"})
    assert word.value.code == "paragraph-format-invalid"
    _item_counts_match(document)
    _reopen(document)


def test_ensure_border_fill_changes_one_side_of_a_base() -> None:
    document = HwpxDocument.new()
    base = document.styles.ensure_border_fill(border_color="#000000")
    before = _definitions(document, "borderFill")
    derived = document.styles.ensure_border_fill(base_border_fill_id_ref=base, sides={"bottom": {"width_mm": 0.4}})
    assert derived != base
    assert document.styles.ensure_border_fill(base_border_fill_id_ref=base, sides={"bottom": {"width_mm": 0.4}}) == derived
    info, original = document.styles.border_fill(derived), document.styles.border_fill(base)
    assert info.bottom.width_mm == 0.4 and info.bottom.color == original.bottom.color
    assert (info.top, info.left, info.right) == (original.top, original.left, original.right)
    assert {key: value for key, value in _definitions(document, "borderFill").items() if key in before} == before
    filled = document.styles.ensure_border_fill(base_border_fill_id_ref=base, fill_color="#FFFF00")
    assert document.styles.border_fill(filled).fill == "#FFFF00"
    with pytest.raises(HwpxValueError) as conflict:
        document.styles.ensure_border_fill(base_border_fill_id_ref=base, border_color="#FF0000")
    assert conflict.value.code == "style-border-base-conflict"
    with pytest.raises(HwpxLookupError) as missing:
        document.styles.ensure_border_fill(base_border_fill_id_ref=999, sides={"top": None})
    assert missing.value.code == "style-definition-not-found"
    _item_counts_match(document)
    _reopen(document)
