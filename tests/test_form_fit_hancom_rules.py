# SPDX-License-Identifier: Apache-2.0
"""FormFit follows Hancom's line layout rules when a slot carries a TextStyle.

A space is half an em, 장평 and 자간 scale every advance (the glyph ending a
line takes no 자간), the paragraph's break settings decide where a line may end
(the Hangul value works the reverse of its name), spaces at a line end hang
past the margin, 최소 공백 lets inner spaces shrink, indents come off the first
or the following lines, closing punctuation never starts a line, and a cell
line is never narrower than 1440 HWPUNIT. All advances here use the class
averages (Hangul 1.0 em, lower-case Latin 0.52 em, punctuation 0.42 em).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from hwpx.document import HwpxDocument
from hwpx.form_fit import (
    FitEngine,
    FitPolicy,
    SlotMetrics,
    TextStyle,
    estimate_lines,
    estimate_text_width,
    hancom_line_starts,
    measure,
)
from hwpx.form_fit.measure import _cell_text_style, glyph_advance_em, resolve_slot_metrics, text_style_from_refs

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_line_rules.hwpx"
FACE_ADVANCES = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_face_advance.hwpx"
INLINE_OBJECTS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_inline_objects.hwpx"
GLYPH_WIDTHS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_glyph_widths.hwpx"

CHARS = TextStyle(break_non_latin_word="KEEP_WORD")  # Hancom 글자 단위


def test_a_space_is_half_an_em_unless_the_font_space_is_used() -> None:
    assert estimate_text_width(" ", 10, TextStyle()) == 500
    assert estimate_text_width(" ", 10, TextStyle(use_font_space=True)) == 320
    assert estimate_text_width(" ", 10) == 320  # no style: class averages as before


def test_ratio_and_spacing_scale_each_advance() -> None:
    assert estimate_text_width("가", 10, TextStyle(ratio=80, spacing=-10)) == 720


def test_the_glyph_ending_a_line_takes_no_spacing() -> None:
    # At 자간 -20 % seven syllables sit 800 apart, but the last one is 1000 wide: 5800 in all.
    assert hancom_line_starts("가나다라마바사", [5600], 10, TextStyle(break_non_latin_word="KEEP_WORD", spacing=-20)) == [0, 6]
    assert hancom_line_starts("가나다라마바사", [8300], 10, TextStyle(break_non_latin_word="KEEP_WORD", spacing=20)) == [0]


def test_a_narrow_cell_still_gets_lines_1440_wide() -> None:
    doc = HwpxDocument.new()
    cell = doc.add_table(1, 1, width=700 + 2 * 510).cell(0, 0)

    assert resolve_slot_metrics(cell, doc, safety=1.0).available_width == 1440


def test_break_word_keeps_hangul_words_whole_and_keep_word_breaks_syllables() -> None:
    assert hancom_line_starts("가나다 라마바사", [5000], 10, TextStyle()) == [0, 4]
    assert hancom_line_starts("가나다 라마바사", [5000], 10, CHARS) == [0, 5]


def test_spaces_at_a_line_end_hang_past_the_margin() -> None:
    assert estimate_lines("가나다라마 ", 5000, 10, TextStyle()) == 1
    assert hancom_line_starts("가나다라마 바", [5000], 10, TextStyle()) == [0, 6]


def test_closing_punctuation_does_not_start_a_line() -> None:
    assert hancom_line_starts("가나다라마.", [5000], 10, CHARS) == [0, 4]


def test_latin_words_do_not_break_after_inner_punctuation() -> None:
    assert hancom_line_starts("aa-bbbb cc", [3000], 10, TextStyle()) == [0, 5]


def test_indents_come_off_the_first_or_the_following_lines() -> None:
    assert estimate_lines("가나다라마", 5000, 10, TextStyle(break_non_latin_word="KEEP_WORD", indent=1000)) == 2
    assert estimate_lines("가나다라마", 5000, 10, TextStyle(break_non_latin_word="KEEP_WORD", indent=-1000)) == 1
    assert estimate_lines("가나다라마바사아", 5000, 10, TextStyle(break_non_latin_word="KEEP_WORD", indent=-1000)) == 2


def test_condense_lets_inner_spaces_shrink() -> None:
    assert estimate_lines("가 나 다라", 4800, 10, TextStyle()) == 2
    assert estimate_lines("가 나 다라", 4800, 10, TextStyle(condense=50)) == 1


def test_inline_objects_take_their_width_off_the_first_line_only() -> None:
    slot = SlotMetrics(
        available_width=2000.0,
        font_pt=10.0,
        max_lines=2,
        inline_object_width=3000.0,
        inline_object_count=1,
        text_style=CHARS,
    )
    assert measure("가나다라마바", slot).lines == 2
    assert measure("가나다라마바", SlotMetrics(available_width=2000.0, font_pt=10.0, max_lines=2)).lines == 3


def test_text_that_cannot_start_beside_the_objects_starts_on_the_next_line() -> None:
    slot = SlotMetrics(
        available_width=500.0,
        font_pt=10.0,
        max_lines=3,
        inline_object_width=4500.0,
        inline_object_count=1,
        text_style=CHARS,
    )
    assert measure("가", slot).lines == 2
    assert measure("가나다라마바", slot).lines == 3
    assert measure("가나다", replace(slot, available_width=0.0)).lines == 2
    assert measure("가나다", replace(slot, available_width=1000.0)).lines == 2


def test_the_lines_after_an_object_wider_than_the_cell_take_the_cell_width() -> None:
    slot = SlotMetrics(
        available_width=0.0,
        font_pt=10.0,
        max_lines=3,
        inline_object_width=6000.0,
        inline_object_count=1,
        text_style=CHARS,
        line_width=5000.0,
    )
    assert measure("가나다라마바", slot).lines == 3


def test_a_hanging_indent_leaves_a_narrow_cell_line_1440_wide() -> None:
    slot = SlotMetrics(
        available_width=1440.0,
        font_pt=10.0,
        max_lines=5,
        text_style=replace(CHARS, indent=-704),
        line_width=1000.0,
        min_line_width=1440.0,
    )
    assert measure("가 12", slot).lines == 2


def test_the_shrink_ladder_keeps_the_text_style() -> None:
    # Fits two lines only because the inline object leaves the second line free.
    slot = SlotMetrics(
        available_width=2000.0,
        font_pt=10.0,
        max_lines=2,
        inline_object_width=3000.0,
        inline_object_count=1,
        text_style=CHARS,
    )
    policy = FitPolicy(mode="wrap_then_shrink", max_lines=2, min_font_pt=8.0)
    result = FitEngine().fit("가나다라마바사아", slot, policy)
    assert result.ok
    assert result.font_pt == 8.0


def test_the_cell_bridge_reads_hancom_settings() -> None:
    document = SimpleNamespace(
        char_property=lambda ref: SimpleNamespace(
            attributes={"useFontSpace": "1"},
            child_attributes={"ratio": {"hangul": "80"}, "spacing": {"hangul": "-5"}},
        ),
        paragraph_property=lambda ref: SimpleNamespace(
            break_setting=SimpleNamespace(break_latin_word="BREAK_WORD", break_non_latin_word="KEEP_WORD"),
            condense=20,
            margin=SimpleNamespace(intent="-1200"),
            version_switch=SimpleNamespace(case=SimpleNamespace(margin=SimpleNamespace(intent="-600"))),
        ),
    )
    cell = SimpleNamespace(
        paragraphs=[SimpleNamespace(para_pr_id_ref="3", runs=[SimpleNamespace(char_pr_id_ref="7")])]
    )

    assert _cell_text_style(cell, document) == TextStyle(
        ratio=80.0,
        spacing=-5.0,
        use_font_space=True,
        break_latin_word="BREAK_WORD",
        break_non_latin_word="KEEP_WORD",
        condense=20,
        indent=-600,
    )


def test_a_real_cell_slot_carries_its_text_style() -> None:
    from hwpx.document import HwpxDocument

    fixture = Path(__file__).parent / "fixtures" / "m2_corpus" / "form_002.hwpx"
    doc = HwpxDocument.open(fixture)
    try:
        cell = next(
            cell
            for paragraph in doc.sections[0].paragraphs
            for table in paragraph.tables
            for row in table.rows
            for cell in row.cells
        )
        slot = resolve_slot_metrics(cell, doc, max_lines=1)
    finally:
        doc.close()
    assert isinstance(slot.text_style, TextStyle)
    assert slot.text_style.break_non_latin_word in {"BREAK_WORD", "KEEP_WORD"}


def _hancom_tables() -> tuple[HwpxDocument, list]:
    doc = HwpxDocument.open(HANCOM_SAVED.read_bytes())
    return doc, [table for paragraph in doc.paragraphs for table in paragraph.tables]


def test_the_indent_hancom_saved_is_read() -> None:
    doc, tables = _hancom_tables()
    indents = [_cell_text_style(table.cell(0, 0), doc).indent for table in tables]

    assert indents.count(1000) == 1 and indents.count(-1000) == 2


def test_the_line_starts_are_the_ones_hancom_saves() -> None:
    """Hancom laid these cells out (a Hangul word or syllable break, spaces, closing and opening
    punctuation, indents, 최소 공백, a Latin hyphen, 자간 and 장평 with and without spaces, a cell
    narrower than a line); each breaks where Hancom broke it."""
    doc, tables = _hancom_tables()

    assert len(tables) == 21
    for table in tables:
        cell = table.cell(0, 0)
        segs = cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")
        style = _cell_text_style(cell, doc)
        slot = resolve_slot_metrics(cell, doc, safety=1.0)
        widths = [slot.available_width - max(style.indent, 0), slot.available_width - max(-style.indent, 0)]

        assert hancom_line_starts(cell.text, widths, slot.font_pt, style) == [int(s.get("textpos")) for s in segs], cell.text


def test_a_hangul_syllable_takes_the_advance_of_its_face() -> None:
    doc = HwpxDocument.new()
    advances = {
        face: text_style_from_refs(doc, None, [doc.oxml.ensure_run_style(font=face, size=10)]).hangul_advance
        for face in ("함초롬바탕", "함초롬돋움", "한컴 고딕", "맑은 고딕")
    }

    assert advances == {"함초롬바탕": 0.972, "함초롬돋움": 0.972, "한컴 고딕": 0.932, "맑은 고딕": 1.0}
    assert round(estimate_text_width("가", 10, TextStyle(hangul_advance=0.972))) == 972


def test_each_face_breaks_where_hancom_breaks() -> None:
    """Fourteen syllables per face, in a cell just wide enough and in one 10 HWPUNIT narrower
    (함초롬바탕, 함초롬돋움, 한컴 고딕, 맑은 고딕), laid out and saved by Hancom."""
    doc = HwpxDocument.open(FACE_ADVANCES.read_bytes())
    tables = [table for paragraph in doc.paragraphs for table in paragraph.tables]

    assert len(tables) == 8
    for table in tables:
        cell = table.cell(0, 0)
        segs = cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")
        style = _cell_text_style(cell, doc)
        slot = resolve_slot_metrics(cell, doc, safety=1.0)

        assert hancom_line_starts(cell.text, [slot.available_width], slot.font_pt, style) == [
            int(s.get("textpos")) for s in segs
        ], (style.hangul_advance, slot.available_width)


def test_text_after_inline_objects_breaks_where_hancom_breaks() -> None:
    """A picture set in the line (its width 1000 to 4700 in a 5000 cell) and then the text: the text
    starts beside it when its first character fits there, else on the next line. Also a picture wider
    than the cell (the lines after it are the cell's width) and a cell narrower than a line with a
    hanging indent (every line stays 1440 wide after the indent)."""
    doc = HwpxDocument.open(INLINE_OBJECTS.read_bytes())
    tables = [table for paragraph in doc.paragraphs for table in paragraph.tables]

    assert len(tables) == 15
    for table in tables:
        cell = table.cell(0, 0)
        segs = cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")
        slot = resolve_slot_metrics(cell, doc, max_lines=10, safety=1.0)

        assert measure(cell.text, slot).lines == len(segs), cell.text


def test_other_glyphs_take_the_measured_widths_of_their_face() -> None:
    assert [glyph_advance_em(face, ".") for face in ("함초롬바탕", "함초롬돋움", "맑은 고딕")] == [0.315, 0.275, 0.215]
    assert glyph_advance_em("맑은 고딕", "0") == 0.555
    assert glyph_advance_em("없는 글꼴", "0") is None
    assert round(estimate_text_width("0.", 10, TextStyle(glyph_face="맑은 고딕"))) == 770
    assert round(estimate_text_width("0.", 10, TextStyle())) == 970  # class averages


def test_the_glyph_table_applies_only_when_every_script_uses_the_face() -> None:
    doc = HwpxDocument.new()
    same = doc.oxml.ensure_run_style(font="맑은 고딕", size=10)
    mixed = doc.oxml.ensure_run_style(font="맑은 고딕", size=10, bold=True)
    char_pr = next(el for el in doc.oxml.headers[0].element.iter() if el.tag.endswith("}charPr") and el.get("id") == str(mixed))
    font_ref = next(child for child in char_pr if child.tag.endswith("}fontRef"))
    font_ref.set("latin", "0")

    assert text_style_from_refs(doc, None, [same]).glyph_face == "맑은 고딕"
    assert text_style_from_refs(doc, None, [mixed]).glyph_face == ""


def test_glyph_widths_break_where_hancom_breaks() -> None:
    """Dates, phone numbers, brackets, per cent and quotes in 함초롬바탕, 함초롬돋움 and 맑은 고딕, each in a
    cell just wider than their measured width and one just narrower, laid out and saved by Hancom."""
    doc = HwpxDocument.open(GLYPH_WIDTHS.read_bytes())
    tables = [table for paragraph in doc.paragraphs for table in paragraph.tables]

    assert len(tables) == 30
    for table in tables:
        cell = table.cell(0, 0)
        segs = cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")
        slot = resolve_slot_metrics(cell, doc, max_lines=10, safety=1.0)

        assert measure(cell.text, slot).lines == len(segs), (cell.text, slot.available_width)
