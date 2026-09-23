# SPDX-License-Identifier: Apache-2.0
"""FormFit follows Hancom's line layout rules when a slot carries a TextStyle.

A space is half an em, 장평 and 자간 scale every advance, the paragraph's break
settings decide where a line may end (the Hangul value works the reverse of
its name), spaces at a line end hang past the margin, 최소 공백 lets inner
spaces shrink, indents come off the first or the following lines, and closing
punctuation never starts a line. All advances here use the class averages
(Hangul 1.0 em, lower-case Latin 0.52 em, punctuation 0.42 em).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
from hwpx.form_fit.measure import _cell_text_style, resolve_slot_metrics

CHARS = TextStyle(break_non_latin_word="KEEP_WORD")  # Hancom 글자 단위


def test_a_space_is_half_an_em_unless_the_font_space_is_used() -> None:
    assert estimate_text_width(" ", 10, TextStyle()) == 500
    assert estimate_text_width(" ", 10, TextStyle(use_font_space=True)) == 320
    assert estimate_text_width(" ", 10) == 320  # no style: class averages as before


def test_ratio_and_spacing_scale_each_advance() -> None:
    assert estimate_text_width("가", 10, TextStyle(ratio=80, spacing=-10)) == 720


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
