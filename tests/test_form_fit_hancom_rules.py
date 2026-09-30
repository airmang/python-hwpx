# SPDX-License-Identifier: Apache-2.0
"""FormFit follows Hancom's line layout rules when a slot carries a TextStyle.

A space is half an em, 장평 and 자간 scale every advance (the glyph ending a
line takes no 자간), the paragraph's break settings decide where a line may end
(the Hangul value works the reverse of its name), spaces at a line end hang
past the margin, 최소 공백 lets inner spaces shrink (less their 자간, for the word
that crosses the margin only), each glyph takes its script's 장평 and 자간, indents come off the first
or the following lines, closing punctuation never starts a line, and a cell
line is never narrower than 1440 HWPUNIT. Unless a test names a face, the
advances use the class averages (Hangul 1.0 em, lower-case Latin 0.52 em,
punctuation 0.42 em).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

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
from hwpx.form_fit.measure import (
    _cell_text_style,
    char_advance,
    classify_char,
    glyph_advance_em,
    glyph_script,
    resolve_slot_metrics,
    text_style_from_refs,
)

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_line_rules.hwpx"
FACE_ADVANCES = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_face_advance.hwpx"
INLINE_OBJECTS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_inline_objects.hwpx"
GLYPH_WIDTHS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_glyph_widths.hwpx"
NUMERAL_WIDTHS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_numeral_widths.hwpx"
UNLISTED_SYMBOLS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_unlisted_face_symbols.hwpx"
LINE_HEIGHTS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_line_heights.hwpx"
ROUNDED_ADVANCES = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_rounded_advances.hwpx"
LINE_PITCHES = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_line_pitches.hwpx"
PARAGRAPH_MARGINS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_paragraph_margins.hwpx"
PARAGRAPH_SPACING = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_paragraph_spacing.hwpx"

CHARS = TextStyle(break_non_latin_word="KEEP_WORD")  # Hancom 글자 단위
SPACE_RUNS = Path(__file__).parent / "fixtures" / "hancom_saved" / "formfit_space_runs.hwpx"
CONDENSE_ROWS = [
    Path(__file__).parent / "fixtures" / "hancom_saved" / f"formfit_condense_{name}.hwpx"
    for name in ("margin_word", "space_without_spacing", "text_reaching_margin")
]
SCRIPT_ROWS = [
    Path(__file__).parent / "fixtures" / "hancom_saved" / f"formfit_script_{name}.hwpx"
    for name in ("latin_ratio", "latin_spacing", "symbols")
]


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


def test_each_character_can_take_its_own_size() -> None:
    style = TextStyle(break_non_latin_word="KEEP_WORD")

    assert hancom_line_starts("가나다라마", [5000], 10, style) == [0]
    assert hancom_line_starts("가나다라마", [5000], 10, style, sizes=[10, 10, 20, 10, 10]) == [0, 4]


def test_each_character_can_take_its_own_style() -> None:
    wide = TextStyle(break_non_latin_word="KEEP_WORD")
    narrow = TextStyle(break_non_latin_word="KEEP_WORD", ratio=50)

    assert hancom_line_starts("가나다라마바", [4800], 10, wide) == [0, 4]
    assert hancom_line_starts("가나다라마바", [4800], 10, wide, styles=[wide] * 3 + [narrow] * 3) == [0]


def test_a_character_can_stand_for_an_object_of_its_own_width() -> None:
    style = TextStyle(break_non_latin_word="KEEP_WORD")

    assert hancom_line_starts("가￼나", [5000], 10, style) == [0]
    assert hancom_line_starts("가￼나", [5000], 10, style, advances={1: 3500}) == [0, 2]


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


def test_condense_shrinks_a_space_less_its_spacing() -> None:
    # At 자간 -10 % a space is 448 wide, but 최소 공백 40 takes 40 % of 500 off it: five spaces give 1000,
    # room for the first syllable of the word crossing 6790 (it needs 950).
    style = TextStyle(break_non_latin_word="KEEP_WORD", spacing=-10, condense=40)

    assert hancom_line_starts("가 " * 5 + "가나", [6790], 10, style) == [0, 11]


def test_a_line_whose_text_reached_the_margin_takes_no_further_word() -> None:
    # The eleventh syllable crosses 14100 and fits as its spaces shrink; the space after it starts past the
    # margin, so the next word starts the next line though the spaces could shrink enough for it. At 15100
    # the text stops short of the margin and the next word shrinks the spaces too.
    assert hancom_line_starts("가 " * 10 + "가", [14100], 10, TextStyle(condense=50)) == [0, 20]
    assert hancom_line_starts("가 " * 10 + "가", [15100], 10, TextStyle(condense=50)) == [0]
    # Its spaces hang, however many: none starts a line.
    assert hancom_line_starts("가 " * 9 + "가  ", [14100], 10, TextStyle(condense=50)) == [0]


def test_each_glyph_takes_the_spacing_of_its_script() -> None:
    latin = TextStyle(scripts=(("latin", 80.0, -20.0),))

    assert char_advance("1", 10, TextStyle(scripts=(("latin", 80.0, 0.0),))) == 440
    assert char_advance("가", 10, latin) == char_advance("가", 10, TextStyle())
    assert char_advance(" ", 10, latin) == 400  # the Hangul 장평 and the Latin 자간
    assert char_advance("\u2026", 10, TextStyle(scripts=(("symbol", 50.0, 0.0),))) == 210
    assert [glyph_script(ch) for ch in "a1,\u00b7\u2018\u201d\u2026\u203b\u25cb\u300c\u4e00가"] == (
        ["latin"] * 6 + ["symbol"] * 4 + ["hanja", "hangul"]
    )


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
    faces = ("함초롬바탕", "함초롬돋움", "한컴 고딕", "맑은 고딕", "바탕", "궁서체")
    widths = {
        face: estimate_text_width("가", 10, text_style_from_refs(doc, None, [doc.oxml.ensure_run_style(font=face, size=10)]))
        for face in faces
    }

    assert widths == {"함초롬바탕": 972, "함초롬돋움": 972, "한컴 고딕": 932, "맑은 고딕": 1000, "바탕": 1000, "궁서체": 1000}
    assert round(estimate_text_width("가", 10, TextStyle(hangul_advance=0.972))) == 972  # a face not listed


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
        ], (style.hangul_face, slot.available_width)


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


def test_other_glyphs_take_the_design_widths_of_their_face() -> None:
    assert [glyph_advance_em(face, ".") for face in ("함초롬바탕", "함초롬돋움", "맑은 고딕")] == [0.32, 0.27, 448 / 2048]
    assert glyph_advance_em("맑은 고딕", "0") == 1128 / 2048
    assert glyph_advance_em("없는 글꼴", "0") is None
    assert estimate_text_width("0.", 10, TextStyle(glyph_face="맑은 고딕")) == 552 + 220
    assert round(estimate_text_width("0.", 10, TextStyle())) == 970  # class averages


def test_advances_are_rounded_to_hancom_layout_units() -> None:
    """1/1800 inch (4 HWPUNIT): the design advance at the size, rounded half up at 100 % 장평 and down at any
    other 장평; 자간 adds its share of that, rounded half away from zero."""
    batang = TextStyle(hangul_face="함초롬바탕")

    assert [estimate_text_width("가", pt, batang) for pt in (9, 9.5, 10, 10.5, 11, 12)] == [872, 920, 972, 1016, 1068, 1164]
    assert [estimate_text_width("가", 10, replace(batang, ratio=r)) for r in (50, 90, 95, 110, 150)] == [
        484, 872, 920, 1064, 1452,
    ]
    assert estimate_text_width("가", 10, replace(batang, ratio=90, spacing=-5)) == 872 - 44
    assert estimate_text_width("가", 10, TextStyle(hangul_face="맑은 고딕", spacing=-5)) == 1000 - 52
    assert estimate_text_width("A", 10, TextStyle(glyph_face="맑은 고딕", ratio=95)) == 624


def test_the_half_em_space_is_rounded_on_its_own() -> None:
    """Half the em, rounded down, at the 장평, rounded half up; the font's own space as any glyph."""
    assert [estimate_text_width(" ", pt, TextStyle()) for pt in (9, 10, 11, 12)] == [448, 500, 548, 600]
    assert [estimate_text_width(" ", 10, TextStyle(ratio=r)) for r in (90, 95, 110)] == [452, 476, 552]
    assert [estimate_text_width(" ", 11, TextStyle(ratio=r)) for r in (90, 95, 110)] == [492, 520, 604]
    assert estimate_text_width(" ", 10, TextStyle(use_font_space=True, glyph_face="함초롬바탕")) == 300
    assert estimate_text_width(" ", 11, TextStyle(use_font_space=True, glyph_face="맑은 고딕")) == 388


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


def test_roman_numerals_and_circled_numbers_break_where_hancom_breaks_them() -> None:
    # Hancom laid out each of Ⅰ ⅳ ① ⑩ ⑴ ⑳ and five syllables in 함초롬바탕, 함초롬돋움 and
    # 맑은 고딕 at 10 pt, in the widest cell that took two lines and the narrowest that took one.
    doc = HwpxDocument.open(NUMERAL_WIDTHS.read_bytes())
    tables = [table for paragraph in doc.paragraphs for table in paragraph.tables]

    assert len(tables) == 36
    for table in tables:
        cell = table.cell(0, 0)
        segs = cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")
        slot = resolve_slot_metrics(cell, doc, max_lines=10, safety=1.0)

        assert measure(cell.text, slot).lines == len(segs), (cell.text, slot.available_width)


def test_a_numeral_a_face_does_not_list_is_full_width() -> None:
    assert classify_char("⑳") == "wide" and classify_char("Ⅻ") == "wide"


def test_a_symbol_in_a_face_the_table_does_not_list_breaks_where_hancom_breaks_it() -> None:
    # Five ○ in 휴먼명조 10 pt, which the glyph table does not list, in cells 4400 and 5400 wide inside:
    # Hancom laid them out in two lines and in one.
    doc = HwpxDocument.open(UNLISTED_SYMBOLS.read_bytes())
    tables = [table for paragraph in doc.paragraphs for table in paragraph.tables]

    lines = []
    for table in tables:
        cell = table.cell(0, 0)
        segs = cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")
        slot = resolve_slot_metrics(cell, doc, max_lines=10, safety=1.0)
        assert glyph_advance_em(slot.text_style.hangul_face, "○") is None
        assert measure(cell.text, slot).lines == len(segs), (cell.width, len(segs))
        lines.append(len(segs))
    assert lines == [2, 1]
    assert {classify_char(ch) for ch in "→○□☆"} == {"wide"}


def test_a_cell_holds_lines_up_to_its_stored_height() -> None:
    # Hancom laid the spacing before and two lines out in the second cell (3482 of its stored 3532 with the
    # margins) and kept the row: lines fit up to the stored height, with no inset below it.
    doc, tables = _one_cell_tables(PARAGRAPH_SPACING)
    assert [int(table.element.find(f"{HP}sz").get("height")) for table in tables][1] == 3532
    for table in tables:
        for paragraph in table.element.iter(f"{HP}p"):
            for cache in paragraph.findall(f"{HP}linesegarray"):
                paragraph.remove(cache)

    budgets = [resolve_slot_metrics(table.cell(0, 0), doc).height_lines() for table in tables]

    assert budgets == [1, 2, 2]


def test_each_line_spacing_type_advances_a_line_as_hancom_does() -> None:
    def pitch(kind: str, value: float) -> float:
        return SlotMetrics(available_width=5000.0, font_pt=10.0, line_spacing=(kind, value)).line_height()

    assert [pitch("PERCENT", 130), pitch("FIXED", 1200), pitch("BETWEEN_LINES", 300)] == [1300, 1200, 1300]
    assert [pitch("AT_LEAST", 800), pitch("AT_LEAST", 1500)] == [1000, 1500]


def test_percent_spacing_is_counted_in_hancom_layout_units() -> None:
    """The spacing beyond the size: the em in 1/1800 inch (size // 4) times the share, rounded half away
    from zero, in units of 4 HWPUNIT; the size itself and the other spacing types are not rounded."""
    def pitch(pt: float, kind: str, value: float) -> float:
        return SlotMetrics(available_width=5000.0, font_pt=pt, line_spacing=(kind, value)).line_height()

    assert [pitch(10.5, "PERCENT", p) for p in (90, 115, 130, 160, 175)] == [946, 1206, 1366, 1678, 1838]
    assert [pitch(9.5, "PERCENT", p) for p in (90, 160)] == [854, 1518]
    assert [pitch(10, "PERCENT", p) for p in (115, 175)] == [1152, 1752]
    assert [pitch(10, "FIXED", 1333), pitch(10, "BETWEEN_LINES", 333), pitch(10, "AT_LEAST", 1333)] == [1333, 1333, 1333]


def test_the_last_line_of_a_cell_takes_no_spacing() -> None:
    slot = SlotMetrics(available_width=5000.0, font_pt=10.0, available_height=4200.0, line_spacing=("PERCENT", 160))

    assert slot.height_lines() == 3  # 2 x 1600 + 1000
    assert replace(slot, available_height=4199.0).height_lines() == 2


@pytest.mark.parametrize("fixture, count", [(LINE_HEIGHTS, 46), (LINE_PITCHES, 26)])
def test_the_line_budget_matches_the_heights_hancom_gives_cells(fixture: Path, count: int) -> None:
    """Cells grown by Hancom to their text: 1 to 5 lines under every line spacing type at 10 and 12 pt,
    and three lines at 9.5, 10.5 and 11.5 pt under 90 to 175 % and spacing values that are not multiples
    of 4. The table height Hancom saved, less the cell margins, holds exactly those lines."""
    doc = HwpxDocument.open(fixture.read_bytes())
    tables = [table for paragraph in doc.paragraphs for table in paragraph.tables]

    assert len(tables) == count
    for table in tables:
        cell = table.cell(0, 0)
        lines = len(cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg"))
        height = int(table.element.find(f"{HP}sz").get("height"))
        margin = cell.element.find(f"{HP}cellMargin")
        content = height - int(margin.get("top")) - int(margin.get("bottom"))
        slot = resolve_slot_metrics(cell, doc, safety=1.0)

        assert replace(slot, available_height=float(content)).height_lines() == lines, (slot.line_spacing, content)
        if lines > 1:
            assert replace(slot, available_height=float(content - 1)).height_lines() == lines - 1
def test_rounded_advances_break_where_hancom_breaks() -> None:
    """Addresses, dates, phone numbers, amounts and Latin in twelve faces at 9 to 12 pt, 장평 90 to 110 % and
    자간 -20 to 5 %, each in a cell exactly as wide as its line and in one 2 HWPUNIT narrower, laid out and
    saved by Hancom."""
    doc = HwpxDocument.open(ROUNDED_ADVANCES.read_bytes())
    tables = [table for paragraph in doc.paragraphs for table in paragraph.tables]
    hancom = [
        len(table.cell(0, 0).paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")) for table in tables
    ]

    assert hancom == [1, 2] * 26
    for table, lines in zip(tables, hancom):
        cell = table.cell(0, 0)
        slot = resolve_slot_metrics(cell, doc, max_lines=10, safety=1.0)

        assert measure(cell.text, slot).lines == lines, (cell.text, slot.font_pt, slot.available_width)


def _one_cell_tables(path: Path) -> tuple[HwpxDocument, list]:
    doc = HwpxDocument.open(path.read_bytes())
    return doc, [table for paragraph in doc.paragraphs for table in paragraph.tables]


def test_paragraph_margins_come_off_every_line_as_hancom_lays_them_out() -> None:
    # Ten syllables in paragraphs whose margins (left, right, indent) are (1000, 0, 0), (500, 500, 0),
    # (0, 800, 0) and (600, 200, 400), each in a cell 150 wider than the text and the margins and one 150
    # narrower. Hancom laid them out and saved them.
    doc, tables = _one_cell_tables(PARAGRAPH_MARGINS)

    lines = []
    for table in tables:
        cell = table.cell(0, 0)
        segs = cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")
        slot = resolve_slot_metrics(cell, doc, max_lines=10, safety=1.0)
        assert measure(cell.text, slot).lines == len(segs), (cell.width, len(segs))
        lines.append(len(segs))
    assert lines == [1, 2] * 4


def test_spacing_before_takes_room_in_a_cell_and_spacing_after_does_not() -> None:
    # Two lines in a paragraph with 600 before and 400 after, in cells stored 50 taller than the two lines,
    # than the spacing before and the two lines, and than all three. Hancom started each first line at 600
    # and grew only the first row, to the spacing before, the two lines and the cell margins.
    doc, tables = _one_cell_tables(PARAGRAPH_SPACING)
    heights = [int(table.element.find(f"{HP}sz").get("height")) for table in tables]
    first_lines = [
        int(table.cell(0, 0).paragraphs[0].element.find(f"{HP}linesegarray/{HP}lineseg").get("vertpos"))
        for table in tables
    ]

    assert heights == [3482, 3532, 3932]
    assert first_lines == [600, 600, 600]
    # Hancom drew the first row as tall as its lines, so those lines are its room.
    budgets = [resolve_slot_metrics(table.cell(0, 0), doc, safety=1.0).height_lines() for table in tables]
    assert budgets == [2, 2, 2]
    # By the stored heights alone the spacing before leaves the first cell one line.
    for table in tables:
        for paragraph in table.element.iter(f"{HP}p"):
            for cache in paragraph.findall(f"{HP}linesegarray"):
                paragraph.remove(cache)
    budgets = [resolve_slot_metrics(table.cell(0, 0), doc, safety=1.0).height_lines() for table in tables]
    assert budgets == [1, 2, 2]


def test_space_runs_and_condense_break_where_hancom_breaks_them() -> None:
    # 최소 공백 75: "가나다 라마바 사아자 차카타" in cells 12400, 12900 and 11900 wide inside, "가" + 20 spaces
    # + "나" and 20 spaces + "가나" in cells 8000 and 10500 wide; the first two again with 최소 공백 0 in the
    # widest cell. Hancom shrank the spaces between words by 75%, never the spaces before a line's first
    # text, and began the next line with a space that started past the line.
    doc = HwpxDocument.open(SPACE_RUNS.read_bytes())
    tables = [table for paragraph in doc.paragraphs for table in paragraph.tables]

    assert len(tables) == 9
    for table in tables:
        cell = table.cell(0, 0)
        segs = cell.paragraphs[0].element.findall(f"{HP}linesegarray/{HP}lineseg")
        slot = resolve_slot_metrics(cell, doc, max_lines=10, safety=1.0)
        starts = hancom_line_starts(cell.text, [slot.line_width], slot.font_pt, slot.text_style)

        assert starts == [int(seg.get("textpos")) for seg in segs], (cell.width, slot.text_style.condense)
        assert measure(cell.text, slot).lines == len(segs)


def _row_line_starts(path: Path) -> list[tuple[list[int], list[int]]]:
    """(FormFit's line starts, Hancom's) of each row of a Hancom-saved fixture: every paragraph of 100 or more
    characters, each line as wide as Hancom laid it out."""
    doc = HwpxDocument.open(path.read_bytes())
    rows = []
    for paragraph in doc.paragraphs:
        text = paragraph.text
        if len(text) < 100:
            continue
        segs = paragraph.element.findall(f"{HP}linesegarray/{HP}lineseg")
        refs = [run.char_pr_id_ref for run in paragraph.runs if run.text]
        style = text_style_from_refs(doc, paragraph.para_pr_id_ref, refs)
        points = int(doc.oxml.char_property(refs[0]).attributes["height"]) / 100
        starts = hancom_line_starts(text, [int(seg.get("horzsize")) for seg in segs], points, style)
        rows.append((starts, [int(seg.get("textpos")) for seg in segs]))
    return rows


@pytest.mark.parametrize("fixture", CONDENSE_ROWS, ids=lambda path: path.stem)
def test_condense_breaks_where_hancom_breaks(fixture: Path) -> None:
    # Rows of "가나 " and of "가나다라마 ", 25 each, 0.15 mm narrower one after another, at 9 pt with 최소 공백
    # 40 (장평 100, and 90 with 자간 -5) and 20 (장평 98, 자간 -10). Hancom shrank the spaces by that share of a
    # space without 자간, only for the word crossing the margin: once the text reached it, the next word started
    # the next line.
    rows = _row_line_starts(fixture)

    assert len(rows) == 50
    assert [starts for starts, _ in rows] == [hancom for _, hancom in rows]


@pytest.mark.parametrize("fixture", SCRIPT_ROWS, ids=lambda path: path.stem)
def test_each_script_takes_its_own_spacing_where_hancom_breaks(fixture: Path) -> None:
    # Rows of digits, "가 ", Latin letters and "가," whose character shape gives the Latin script 장평 80, or
    # the Hangul script 자간 -20 and the Latin one 0; and rows of "가" and a middle dot, a quote, an ellipsis,
    # a reference mark, a circle and a corner bracket when every script has its own 장평. The rows of the
    # ideographic comma, a glyph the face table does not list, are left out.
    doc = HwpxDocument.open(fixture.read_bytes())
    texts = [paragraph.text for paragraph in doc.paragraphs if len(paragraph.text) >= 100]
    rows = [row for row, text in zip(_row_line_starts(fixture), texts) if "、" not in text]

    assert len(rows) >= 100
    assert [starts for starts, _ in rows] == [hancom for _, hancom in rows]
