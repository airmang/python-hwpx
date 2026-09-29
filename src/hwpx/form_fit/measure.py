# SPDX-License-Identifier: Apache-2.0
"""Conservative text measurement for FormFit (plan §2 C, task 2).

Everything is in **HWPUNIT** (1 pt = 100 HWPUNIT, 1 inch = 7200 HWPUNIT). Crucially
font height *and* cell width share that unit, so a glyph's advance is just a
fraction of the font height (the "em") — no DPI/point conversion is needed.

The advance fractions below are **calibrated against a real Hancom-saved form**
(``work/formfit_calibrate.py`` over 1492 ``lineSegArray`` caches): full-width
Hangul/CJK is reliably 1.0 em; Latin/digit/space/punct are averaged and therefore
*approximate*. That approximation is the whole reason measurement reports a
**confidence** and the engine refuses to hard-fail a borderline case — Hancom (the
render oracle) is the only authority on the close calls (plan §1 "measure-first",
§2 C acceptance "measurement honesty over false precision").

A slot with a :class:`TextStyle` (cell and form-field slots carry one) breaks
lines the way Hancom does, with no font file: the glyphs of common faces take
their design advances rounded to Hancom's layout unit (1/1800 inch), a space
is half an em, 장평 and 자간 scale each advance, the paragraph's break
settings decide where a line may end, spaces at a line end hang past the
margin, 최소 공백 lets inner spaces shrink, indents come off the first or the
following lines, closing punctuation never starts a line, and inline objects
on the line take their width off the first line only (see
:func:`hancom_line_starts`).
"""
from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import lru_cache
from typing import Any, Literal

from ..oxml.table_sizes import cell_margins_of

# Advance width as a fraction of the em (font height in HWPUNIT). Hangul/wide are
# exact (full-width cells); the Latin/digit/punct values are conservative class
# averages — slightly generous so "it fits" stays trustworthy, never tight.
_ADVANCE_EM: dict[str, float] = {
    "hangul": 1.0,
    "wide": 1.0,
    "upper": 0.70,
    "lower": 0.52,
    "digit": 0.55,
    "space": 0.32,
    "punct": 0.42,
    "other": 0.62,
}

# Per-class relative measurement uncertainty. Hangul is rock-solid; Latin/punct
# are crude (no per-glyph metrics yet — deferred to the HarfBuzz pass, plan §2 C
# "Deferred (a)"). A value's overall band is the advance-weighted blend.
_CLASS_UNCERTAINTY: dict[str, float] = {
    "hangul": 0.05,
    "wide": 0.05,
    "space": 0.08,
    "digit": 0.12,
    "upper": 0.20,
    "lower": 0.20,
    "punct": 0.22,
    "other": 0.25,
}

# Width left as a safety inset (cell padding/indent Hancom applies beyond the
# explicit cellMargin; empirically ~284 HWPUNIT on small cells). Applied as a
# multiplicative factor so it scales and also buys headroom on the advance error.
DEFAULT_SAFETY = 0.93

#: Hancom never lays a cell line out narrower than this (HWPUNIT): below it the
#: line keeps this width however narrow the cell.
MIN_LINE_WIDTH = 1440

# --- Vertical (line-height) model ------------------------------------------- #
# Per-line vertical advance as a multiple of the em (font height in HWPUNIT).
# HWP's application default is 160% line spacing, so a line occupies ~1.6 em; this
# is the advance used when a paragraph declares no explicit lineSpacing, and it
# matches ``layout.lint._LINE_SPACING``. Used as the *expected* pitch for the
# authored vertical budget (the point at which the row is warned it will grow).
DEFAULT_LINE_SPACING_RATIO = 1.6

# Tightest per-line advance Hancom is observed to use (a glyph box with no leading).
# Measured on the M9 wild-form corpus: two soft-wrapped lines render inside cells
# only ~2.0 em tall, so the real pitch bottoms out near 1.0 em. Used to compute the
# *optimistic* (most generous) height budget, so a vertical overflow is only treated
# as high confidence when content overflows even at this tightest pitch.
MIN_LINE_SPACING_RATIO = 1.0

# A vertical overflow is a *hard* balloon (shrink-or-refuse) only when content needs
# at least this multiple of the optimistic authored line budget AND this many extra
# lines in absolute terms. Below the gross threshold the row may grow only modestly
# and the render oracle arbitrates. Measure-first calibration on the M9 corpus: a
# hard cap at the optimistic budget mis-refuses 47% of known-good multi-line cells,
# whereas this gross gate mis-refuses 2% — it fires on page-shifting balloons only.
# (Same balloon philosophy as ``layout.lint._BALLOON_FACTOR``.)
GROSS_ROW_GROWTH_FACTOR = 2.0
MIN_ROW_GROWTH_LINES = 2

Confidence = Literal["high", "low"]

# --- Hancom line layout rules (no font file needed) --------------------------- #
#: Spaces that hang past the right margin at a line end; a line never starts
#: with one.
_HANGING_SPACES = " " + chr(0xA0)
#: Closing punctuation that never starts a line; it moves down with the
#: character before it.
_NO_LINE_START = frozenset("!%),.:;?]}¢°’”‰′″℃〉》」』】〕…·、。")
#: Opening punctuation that never ends a line.
_NO_LINE_END = frozenset("([{‘“〈《「『【〔")
#: The scripts whose faces must match for the per-face glyph table to apply to
#: the glyphs that are not Hangul.
_GLYPH_TABLE_SCRIPTS = ("HANGUL", "LATIN", "OTHER", "SYMBOL")

# --- Advances per face ---------------------------------------------------------- #
# Hancom lays glyphs out in 1/1800 inch (``_LAYOUT_UNIT`` HWPUNIT). The em is the
# character height in that unit, rounded down. A glyph takes its design advance
# at that em, rounded half up at 100% 장평 and down at any other 장평, and 자간
# adds its share of that advance, rounded half away from zero. The half-em space
# is half the em, rounded down, at the 장평, rounded half up. Bold text keeps the
# regular advances. A face or glyph not listed below falls back to the class
# averages, unrounded.
_LAYOUT_UNIT = 4

#: The glyphs each face's row below gives, in order: printable ASCII, then
#: punctuation and symbols common in Korean documents, then Roman numerals
#: (Ⅰ–Ⅻ, ⅰ–ⅻ) and circled and parenthesized numbers (①–⑳, ⑴–⒇).
_GLYPHS = '!"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~·…“”‘’「」『』〈〉《》※○●□■△▲◇◆☆★→←↑↓ㆍ×÷±°℃‰—–ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹⅺⅻ①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽⑾⑿⒀⒁⒂⒃⒄⒅⒆⒇'

#: Design advances per face in font units: units per em, a Hangul syllable, the
#: space, and each glyph of ``_GLYPHS`` (0: not in the face).
_DESIGN: dict[str, tuple[int, int, int, tuple[int, ...]]] = {
    "함초롬바탕": (1000, 970, 300, (
        320, 320, 610, 610, 830, 724, 320, 320, 320, 550, 550, 320, 550, 320, 550, 550,
        550, 550, 550, 550, 550, 550, 550, 550, 550, 320, 320, 550, 550, 550, 550, 830,
        706, 605, 685, 719, 627, 617, 683, 734, 305, 315, 660, 605, 839, 734, 732, 603,
        705, 660, 627, 664, 731, 706, 910, 705, 705, 626, 320, 550, 320, 550, 550, 320,
        569, 597, 552, 597, 536, 356, 562, 635, 287, 288, 582, 287, 907, 635, 588, 597,
        579, 478, 496, 356, 635, 563, 720, 542, 543, 486, 320, 320, 320, 550, 320, 960,
        480, 480, 320, 320, 500, 500, 500, 500, 500, 500, 500, 500, 770, 970, 970, 970,
        970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 617, 678, 798, 291,
        970, 988, 875, 625, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970,
        970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970,
        970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970,
        970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970,
        970, 970, 970, 970,
    )),
    "함초롬돋움": (1000, 970, 300, (
        333, 339, 686, 626, 853, 761, 260, 313, 313, 498, 548, 258, 466, 270, 374, 550,
        550, 550, 550, 550, 550, 550, 550, 550, 550, 312, 312, 600, 534, 600, 570, 865,
        654, 664, 633, 701, 625, 609, 645, 694, 317, 515, 664, 584, 826, 728, 676, 660,
        681, 683, 617, 573, 702, 594, 897, 607, 581, 584, 338, 373, 329, 562, 532, 373,
        563, 581, 513, 578, 567, 336, 563, 594, 271, 268, 559, 258, 919, 595, 582, 552,
        552, 427, 513, 349, 595, 469, 760, 483, 466, 479, 372, 342, 372, 546, 294, 702,
        451, 453, 288, 288, 500, 500, 500, 500, 500, 500, 500, 500, 690, 970, 970, 970,
        970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 587, 670, 782, 306,
        970, 892, 522, 348, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970,
        970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970,
        970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970,
        970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970, 970,
        970, 970, 970, 970,
    )),
    "맑은 고딕": (2048, 2048, 720, (
        592, 809, 1242, 1128, 1713, 1675, 475, 624, 624, 870, 1435, 448, 840, 448, 811, 1128,
        1128, 1128, 1128, 1128, 1128, 1128, 1128, 1128, 1128, 448, 448, 1435, 1435, 1435, 942, 2006,
        1348, 1195, 1300, 1469, 1059, 1021, 1437, 1484, 553, 737, 1209, 983, 1878, 1567, 1584, 1169,
        1584, 1249, 1112, 1093, 1439, 1299, 1953, 1231, 1154, 1193, 624, 1564, 624, 1435, 872, 557,
        1065, 1230, 968, 1233, 1096, 648, 1233, 1185, 504, 504, 1036, 504, 1802, 1184, 1227, 1230,
        1233, 724, 887, 706, 1184, 998, 1508, 952, 1009, 946, 624, 490, 624, 1435, 448, 1515,
        776, 776, 473, 473, 1169, 1169, 1059, 1059, 1110, 1110, 1221, 1221, 1638, 2048, 2048, 2048,
        2048, 2048, 2048, 2048, 2048, 2048, 2048, 1946, 1946, 1946, 1946, 2048, 1435, 1435, 1435, 792,
        1946, 2536, 2101, 1051, 1946, 1946, 1946, 1946, 1946, 1946, 1946, 1946, 1946, 1946, 0, 0,
        1946, 1946, 1946, 1946, 1946, 1946, 1946, 1946, 1946, 1946, 0, 0, 2048, 2048, 2048, 2048,
        2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 0, 0, 0, 0, 0,
        2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 2048, 0,
        0, 0, 0, 0,
    )),
    "한컴 고딕": (1000, 932, 264, (
        446, 297, 583, 583, 892, 892, 297, 446, 446, 446, 583, 297, 583, 297, 446, 583,
        583, 583, 583, 583, 583, 583, 583, 583, 583, 297, 297, 446, 583, 446, 669, 1052,
        644, 627, 639, 721, 596, 554, 710, 718, 247, 410, 626, 529, 884, 710, 752, 586,
        752, 610, 592, 621, 696, 635, 961, 617, 611, 594, 446, 961, 446, 434, 446, 297,
        560, 588, 490, 588, 559, 340, 588, 592, 244, 301, 530, 244, 892, 592, 577, 588,
        588, 383, 475, 357, 592, 530, 788, 528, 530, 473, 446, 446, 446, 669, 446, 892,
        446, 446, 303, 303, 486, 486, 486, 486, 486, 486, 486, 486, 932, 932, 932, 932,
        932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 800, 800, 800, 446,
        932, 892, 0, 0, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 0, 0,
        932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 0, 0, 932, 932, 932, 932,
        932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 0, 0, 0, 0, 0,
        932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 932, 0,
        0, 0, 0, 0,
    )),
    "바탕": (1024, 1024, 341, (
        320, 427, 638, 574, 876, 853, 256, 386, 386, 512, 853, 299, 640, 299, 384, 610,
        610, 610, 610, 610, 610, 610, 610, 610, 610, 341, 341, 640, 640, 640, 512, 1024,
        754, 725, 725, 752, 688, 660, 758, 784, 334, 436, 764, 654, 916, 794, 754, 670,
        756, 688, 640, 768, 794, 768, 968, 704, 702, 640, 512, 1024, 512, 512, 512, 597,
        555, 590, 555, 590, 590, 374, 597, 588, 296, 299, 586, 299, 866, 584, 597, 588,
        588, 450, 532, 368, 580, 586, 828, 620, 602, 512, 512, 597, 512, 768, 341, 1024,
        512, 512, 299, 299, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 911,
        911, 1024, 936, 1024, 1024, 1024, 1024, 1024, 1024, 768, 768, 1024, 832, 832, 832, 448,
        1024, 1024, 1024, 512, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 0, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0,
        0, 0, 0, 0,
    )),
    "바탕체": (1024, 1024, 512, (
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024,
        1024, 1024, 512, 512, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 0, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0,
        0, 0, 0, 0,
    )),
    "궁서": (1024, 1024, 341, (
        427, 427, 640, 555, 683, 597, 299, 427, 427, 512, 640, 341, 852, 341, 384, 597,
        597, 597, 597, 597, 597, 597, 597, 597, 597, 341, 341, 725, 640, 725, 597, 753,
        704, 700, 704, 695, 673, 672, 717, 719, 474, 576, 704, 640, 832, 729, 689, 667,
        719, 719, 634, 664, 730, 699, 812, 682, 684, 650, 512, 768, 512, 576, 512, 335,
        628, 653, 630, 653, 625, 512, 653, 666, 481, 483, 657, 512, 896, 662, 673, 671,
        671, 597, 597, 576, 661, 661, 768, 628, 663, 565, 512, 512, 512, 811, 340, 1024,
        512, 512, 341, 341, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 911,
        911, 1024, 936, 1024, 1024, 1024, 1024, 1024, 1024, 768, 768, 1024, 853, 853, 853, 448,
        1024, 1024, 1024, 512, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 0, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0,
        0, 0, 0, 0,
    )),
    "궁서체": (1024, 1024, 512, (
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024,
        1024, 1024, 512, 512, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 0, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0,
        0, 0, 0, 0,
    )),
    "굴림": (1024, 1024, 341, (
        341, 384, 768, 612, 896, 704, 290, 384, 384, 512, 640, 342, 640, 342, 427, 588,
        588, 588, 588, 588, 588, 588, 588, 588, 588, 342, 342, 640, 640, 640, 555, 1024,
        661, 693, 735, 739, 640, 610, 788, 748, 276, 512, 650, 556, 832, 716, 788, 652,
        792, 682, 648, 596, 728, 614, 916, 640, 640, 640, 512, 939, 512, 555, 512, 341,
        576, 620, 586, 620, 581, 350, 620, 585, 247, 247, 512, 237, 882, 594, 620, 620,
        620, 341, 538, 321, 584, 512, 768, 512, 512, 512, 512, 512, 512, 811, 384, 1024,
        512, 512, 341, 341, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 911,
        911, 1024, 936, 1024, 1024, 1024, 1024, 1024, 1024, 768, 768, 1024, 853, 853, 853, 384,
        1024, 1024, 1024, 512, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 0, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0,
        0, 0, 0, 0,
    )),
    "굴림체": (1024, 1024, 512, (
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024,
        1024, 1024, 512, 512, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 0, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0,
        0, 0, 0, 0,
    )),
    "돋움": (1024, 1024, 342, (
        342, 427, 640, 512, 939, 726, 298, 384, 384, 597, 596, 384, 604, 384, 427, 597,
        597, 597, 597, 597, 597, 597, 597, 597, 597, 348, 348, 640, 598, 640, 597, 1024,
        683, 696, 738, 742, 644, 614, 768, 740, 264, 496, 672, 554, 828, 714, 768, 658,
        768, 684, 654, 597, 742, 616, 914, 618, 616, 618, 512, 981, 512, 640, 512, 340,
        597, 614, 572, 618, 572, 352, 612, 574, 234, 234, 522, 236, 939, 582, 614, 616,
        618, 328, 528, 320, 568, 486, 742, 490, 492, 494, 512, 512, 512, 810, 340, 1024,
        469, 469, 299, 299, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 960, 911,
        911, 1024, 936, 1024, 1024, 1024, 1024, 1024, 1024, 768, 768, 1024, 853, 853, 853, 415,
        1024, 1024, 1024, 512, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 0, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0,
        0, 0, 0, 0,
    )),
    "돋움체": (1024, 1024, 512, (
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512,
        512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 512, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024,
        1024, 1024, 512, 512, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 1024, 1024, 1024, 1024,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0, 0, 0, 0, 0,
        1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024, 0,
        0, 0, 0, 0,
    )),
}


def glyph_advance_em(face: str, ch: str) -> float | None:
    """Design advance of *ch* in *face* in em, or ``None`` when not listed."""

    design = _design_units(face, ch)
    return design[0] / design[1] if design is not None else None


def _design_units(face: str, ch: str | None) -> tuple[int, int] | None:
    """``(advance, units per em)`` of *ch* in *face*, a Hangul syllable when *ch*
    is ``None``, or ``None`` when not listed."""

    entry = _DESIGN.get(face)
    if entry is None:
        return None
    upem, hangul, space, glyphs = entry
    if ch is None:
        units = hangul
    elif ch == " ":
        units = space
    else:
        index = _GLYPHS.find(ch) if len(ch) == 1 else -1
        units = glyphs[index] if index >= 0 else 0
    return (units, upem) if units else None


@lru_cache(maxsize=4096)
def _laid_out(units: int, upem: int, height: int, ratio: float, spacing: float) -> float:
    """HWPUNIT a glyph of design advance *units* (of *upem*) takes at a character
    height of *height* HWPUNIT, its 자간 included."""

    scaled = Fraction(units * (height // _LAYOUT_UNIT), upem)
    if ratio == 100:
        advance = math.floor(scaled + Fraction(1, 2))
    else:
        advance = math.floor(scaled * Fraction(ratio) / 100)
    return float((advance + _spacing_units(advance, spacing)) * _LAYOUT_UNIT)


@lru_cache(maxsize=512)
def _laid_out_space(height: int, ratio: float, spacing: float) -> float:
    """HWPUNIT the half-em space takes at a character height of *height* HWPUNIT,
    its 자간 included."""

    half = height // _LAYOUT_UNIT // 2
    advance = math.floor(half * Fraction(ratio) / 100 + Fraction(1, 2))
    return float((advance + _spacing_units(advance, spacing)) * _LAYOUT_UNIT)


def _spacing_units(advance: int, spacing: float) -> int:
    """자간 of *spacing* % on *advance* layout units, rounded half away from zero."""

    share = Fraction(advance) * Fraction(spacing) / 100
    units = math.floor(abs(share) + Fraction(1, 2))
    return units if share >= 0 else -units


@dataclass(frozen=True, slots=True)
class TextStyle:
    """Character and paragraph settings Hancom lays a line out with.

    ``ratio`` (장평, %) and ``spacing`` (자간, % of each glyph's own width)
    scale every advance, except that the glyph ending a line takes no 자간
    after it, and a space is half an em unless ``use_font_space``.
    ``break_non_latin_word`` works the reverse of its name in Hancom:
    ``BREAK_WORD`` (the default) keeps Hangul words whole and ``KEEP_WORD``
    breaks between any two syllables; ``break_latin_word`` works as named.
    ``condense`` (최소 공백, %) lets the spaces inside a line shrink by that
    share. ``indent`` is the first-line indent in HWPUNIT; a negative value is
    a hanging indent taken off every line after the first. ``margin_left`` and
    ``margin_right`` (HWPUNIT) come off every line: Hancom starts a line at the
    paragraph's left margin. ``space_before`` (HWPUNIT) is room above the first
    line; the spacing after the paragraph takes no room in a cell. ``hangul_face``
    and ``glyph_face`` name the faces whose design advances Hangul syllables
    and the other glyphs take, laid out as Hancom rounds them (see
    :func:`char_advance`); an empty or unlisted face, or a glyph it does not
    list, falls back to ``hangul_advance`` (a Hangul syllable in em) and to
    the class averages.
    """

    ratio: float = 100.0
    spacing: float = 0.0
    use_font_space: bool = False
    break_latin_word: str = "KEEP_WORD"
    break_non_latin_word: str = "BREAK_WORD"
    condense: int = 0
    indent: int = 0
    margin_left: int = 0
    margin_right: int = 0
    space_before: int = 0
    hangul_advance: float = 1.0
    glyph_face: str = ""
    hangul_face: str = ""


def classify_char(ch: str) -> str:
    """Bucket *ch* into an advance class (see ``_ADVANCE_EM``)."""

    if ch in " \t ":
        return "space"
    code = ord(ch)
    # Hangul syllables, jamo, compatibility jamo.
    if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
        return "hangul"
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return "wide"
    # Roman numerals and circled and parenthesized numbers: full width in Korean
    # faces (Hancom draws them 0.95 to 1 em, a face without them included).
    if 0x2160 <= code <= 0x217F or 0x2460 <= code <= 0x24FF:
        return "wide"
    # Arrows, geometric shapes (○ □ △ ◇) and other symbols (☆ ☎ ♥): 0.89 to 1 em
    # in the Korean faces the glyph table lists, and full width in one it does not.
    if 0x2190 <= code <= 0x21FF or 0x25A0 <= code <= 0x25FF or 0x2600 <= code <= 0x26FF:
        return "wide"
    if ch.isdigit():
        return "digit"
    if ch.isalpha():
        return "upper" if ch.isupper() else "lower"
    if not ch.isalnum():
        return "punct"
    return "other"


def char_advance(ch: str, font_pt: float, style: TextStyle | None = None) -> float:
    """Advance of *ch* at *font_pt*, in HWPUNIT.

    With *style*, the half-em space and the glyphs of a listed face take the
    advance Hancom lays them out with, their 자간 included (see
    ``_LAYOUT_UNIT``); other glyphs scale their class average.
    """

    if style is None:
        return _ADVANCE_EM[classify_char(ch)] * font_pt * 100.0
    cls = classify_char(ch)
    height = round(font_pt * 100.0)
    if ch == " " and not style.use_font_space:
        return _laid_out_space(height, style.ratio, style.spacing)
    if cls == "hangul":
        design, base = _design_units(style.hangul_face, None), style.hangul_advance
    else:
        design, base = _design_units(style.glyph_face, ch), _ADVANCE_EM[cls]
    if design is not None:
        return _laid_out(design[0], design[1], height, style.ratio, style.spacing)
    return base * font_pt * 100.0 * style.ratio / 100.0 * (1 + style.spacing / 100.0)


def estimate_text_width(text: str, font_pt: float, style: TextStyle | None = None) -> float:
    """Conservative single-line width of *text* at *font_pt*, in HWPUNIT.

    With *style* the advances follow Hancom's rules (see :class:`TextStyle`).
    """

    if style is not None:
        return sum(char_advance(ch, font_pt, style) for ch in text)
    em = font_pt * 100.0
    return sum(_ADVANCE_EM[classify_char(ch)] for ch in text) * em


def _uncertainty_band(text: str) -> float:
    """Advance-weighted relative measurement error for *text* (0 → certain)."""

    stripped = text.strip()
    if not stripped:
        return _CLASS_UNCERTAINTY["space"]
    weighted = 0.0
    total = 0.0
    for ch in stripped:
        cls = classify_char(ch)
        adv = _ADVANCE_EM[cls]
        weighted += adv * _CLASS_UNCERTAINTY[cls]
        total += adv
    return weighted / total if total else _CLASS_UNCERTAINTY["other"]


# In-word punctuation a Latin run may break *after* in the class-average model
# (no TextStyle): an email, URL, file path, or hyphenated model number wraps at
# these. Hancom itself keeps such a word whole unless it is longer than the
# line, which is what the TextStyle path (``hancom_line_starts``) follows.
_LATIN_BREAK_AFTER = frozenset("/\\-.@:_?=&,;")


def _break_opportunities(text: str) -> set[int]:
    """Indices *before which* a soft line break may occur.

    Korean wraps after spaces (word level) and Hancom also allows a break between
    a wide/Hangul glyph and the next character. A pure-Latin run stays whole
    EXCEPT after in-word punctuation (``_LATIN_BREAK_AFTER``), where Hancom wraps.
    """

    opportunities: set[int] = set()
    for index in range(1, len(text)):
        prev, cur = text[index - 1], text[index]
        if prev in " \t ":
            opportunities.add(index)
            continue
        if classify_char(prev) in ("hangul", "wide") or classify_char(cur) in (
            "hangul",
            "wide",
        ):
            opportunities.add(index)
            continue
        if prev in _LATIN_BREAK_AFTER and cur not in (" ", "\t"):
            opportunities.add(index)
    return opportunities


def _hancom_break_opportunities(text: str, style: TextStyle) -> set[int]:
    """Indices before which Hancom may start a new line under *style*."""

    opportunities: set[int] = set()
    for index in range(1, len(text)):
        prev, cur = text[index - 1], text[index]
        if cur in _HANGING_SPACES:
            continue
        if prev in _HANGING_SPACES:
            opportunities.add(index)
            continue
        if classify_char(prev) in ("hangul", "wide") or classify_char(cur) in ("hangul", "wide"):
            if style.break_non_latin_word == "KEEP_WORD":
                opportunities.add(index)
            continue
        if style.break_latin_word == "BREAK_WORD":
            opportunities.add(index)
    return opportunities


def hancom_line_starts(
    text: str,
    widths: list[float],
    font_pt: float,
    style: TextStyle,
    sizes: Sequence[float] | None = None,
    styles: Sequence[TextStyle] | None = None,
    advances: Mapping[int, float] | None = None,
) -> list[int]:
    """Where Hancom starts each line of the one-line *text* (no newlines).

    ``widths[k]`` is the width of line ``k`` in HWPUNIT (the last one repeats).
    A line takes characters while they fit (the last one without its 자간);
    the space right after a word hangs past the margin, and a further space
    that starts at or past it begins the next line. With ``style.condense`` the
    spaces after the line's first text may shrink to make room for a
    character; the spaces before it never do. The line then ends at the last
    break opportunity that fits — never before a closing or after an opening
    punctuation mark — or mid-word when no opportunity is left. *sizes*, when
    given, holds each character's size in pt (runs of several sizes): every
    character, and every space that shrinks, then takes its own size.
    *styles*, when given, holds each character's own style (runs of several
    faces, 장평 or 자간) for its advance; *style* still gives the break rules.
    *advances* gives the width of characters that stand for something else,
    such as an object set as a character, by their index.
    """

    breaks = _hancom_break_opportunities(text, style)
    space = char_advance(" ", font_pt, style)
    unspaced = replace(style, spacing=0.0)
    starts = [0]
    length = len(text)
    start = 0
    while True:
        width = widths[min(len(starts) - 1, len(widths) - 1)]
        end, used, inner, pending, seen, spilled = start, 0.0, 0, 0, False, False
        while end < length:
            ch = text[end]
            size = font_pt if sizes is None else sizes[end]
            look = style if styles is None else styles[end]
            fixed = None if advances is None else advances.get(end)
            advance = char_advance(ch, size, look) if fixed is None else fixed
            if ch in _HANGING_SPACES:
                if used >= width and end > start and text[end - 1] in _HANGING_SPACES:
                    spilled = True
                    break
                used += advance
                if seen:  # the spaces before the line's first text never shrink
                    # a space of another size or style counts as its share of a space at *font_pt*
                    pending += 1 if sizes is None and styles is None else char_advance(" ", size, look) / space
                end += 1
                continue
            shrink = (inner + pending) * space * style.condense / 100.0
            last = fixed if fixed is not None else char_advance(ch, size, unspaced if styles is None else _without_spacing(look))
            if used + last - shrink > width and end > start:
                break
            used += advance
            inner += pending
            pending = 0
            seen = True
            end += 1
        if end >= length:
            return starts
        if spilled:
            start = end
        else:
            options = [
                index for index in breaks
                if start < index <= end
                and text[index] not in _NO_LINE_START
                and text[index - 1] not in _NO_LINE_END
            ]
            start = max(options) if options else end
            while start < length and text[start] in _HANGING_SPACES:
                start += 1
        if start >= length:
            return starts
        starts.append(start)


@lru_cache(maxsize=256)
def _without_spacing(style: TextStyle) -> TextStyle:
    return replace(style, spacing=0.0)


def _hancom_line_count(
    text: str, first_width: float, rest_width: float, font_pt: float, style: TextStyle
) -> int:
    if first_width <= 0 or rest_width <= 0:
        return 1_000_000
    total = 0
    logical = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(logical):
        if not line:
            total += 1
            continue
        widths = [first_width, rest_width] if index == 0 else [rest_width]
        total += len(hancom_line_starts(line, widths, font_pt, style))
    return max(total, 1)


def estimate_lines(
    text: str, available_width: float, font_pt: float, style: TextStyle | None = None
) -> int:
    """Greedy line count for *text* in a slot *available_width* wide (HWPUNIT).

    Greedy packing over-estimates slightly versus a naive width/budget ratio
    (it accounts for wrap waste), which keeps the line count — and therefore an
    overflow verdict — on the conservative side. With *style* the lines follow
    Hancom's rules (see :func:`hancom_line_starts`), and ``style.indent`` comes
    off the first line (or, when negative, off the others).
    """

    if style is not None:
        return _hancom_line_count(
            text,
            available_width - max(style.indent, 0),
            available_width - max(-style.indent, 0),
            font_pt,
            style,
        )
    if available_width <= 0:
        return 1_000_000
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    total = 0
    for line in lines:
        total += _wrap_one_logical_line(line, available_width, font_pt)
    return max(total, 1)


def _wrap_one_logical_line(line: str, available_width: float, font_pt: float) -> int:
    if not line:
        return 1
    breaks = _break_opportunities(line)
    em = font_pt * 100.0
    used = 0.0
    count = 1
    last_break: int | None = None
    used_at_break = 0.0
    for index, ch in enumerate(line):
        adv = _ADVANCE_EM[classify_char(ch)] * em
        if index in breaks:
            last_break = index
            used_at_break = used
        if used + adv > available_width and used > 0:
            count += 1
            if last_break is not None and last_break > 0:
                # Rewrap: characters after the last break opportunity move down.
                used = (used - used_at_break) + adv
                last_break = None
            else:
                used = adv
        else:
            used += adv
    return count


@dataclass(slots=True)
class SlotMetrics:
    """Geometry of the box a value must fit into (HWPUNIT + points)."""

    available_width: float          # usable inner width after margins + safety
    font_pt: float
    max_lines: int = 1
    raw_width: float | None = None  # cellSz.width before margins (diagnostics)
    source: str = "cell"
    # Vertical budget. ``available_height`` is the usable inner height (HWPUNIT)
    # after top/bottom cell margins + the safety inset. ``None`` means the vertical
    # room was not (or could not be) measured, and the fit stays width-only.
    available_height: float | None = None
    # Per-line advance as a multiple of the em, from the cell's declared paragraph
    # line spacing (PERCENT). ``None`` falls back to ``DEFAULT_LINE_SPACING_RATIO``.
    line_spacing_ratio: float | None = None
    # Width already consumed on the line by inline treat-as-char objects
    # (checkboxes, form controls, pictures) that share the target paragraph.
    # Their declared ``hp:sz/@width`` is subtracted from the usable width —
    # ignoring them made the engine call "fits" on a fill that real Hancom
    # wrapped, growing the row and repaginating a 10-page form.
    inline_object_width: float = 0.0
    inline_object_count: int = 0
    # A cell height existed but was unusable (merged row-span fragment, or an
    # auto-grow floor shorter than one line). Records "height budget unavailable"
    # so the fit reports width-only honestly rather than guessing a vertical fit.
    height_unavailable: bool = False
    # Hancom's layout settings for the slot's text. ``None`` keeps the class
    # average model; with a style, lines follow Hancom's rules and the inline
    # objects take their width off the first line only.
    text_style: TextStyle | None = None
    # The cell's own line width (after margins and safety, before the inline
    # objects and the MIN_LINE_WIDTH floor) and that floor after safety. With a
    # text style every line is at least ``min_line_width`` wide after its indent.
    # ``None`` takes the line as ``available_width + inline_object_width``.
    line_width: float | None = None
    min_line_width: float = 0.0
    # The cell's first paragraph line spacing as (type, value): PERCENT in per
    # cent, FIXED / BETWEEN_LINES / AT_LEAST in HWPUNIT. ``None`` falls back to
    # ``line_spacing_ratio``.
    line_spacing: tuple[str, float] | None = None

    @property
    def capacity(self) -> float:
        return self.available_width * self.max_lines

    def _line_ratio(self) -> float:
        ratio = self.line_spacing_ratio
        return ratio if ratio and ratio > 0 else DEFAULT_LINE_SPACING_RATIO

    def line_height(self, font_pt: float | None = None) -> float:
        """Expected per-line vertical advance in HWPUNIT at *font_pt*."""

        pt = self.font_pt if font_pt is None else font_pt
        if self.line_spacing is not None:
            kind, value = self.line_spacing
            return _line_pitch(kind, value, pt * 100.0)
        return pt * 100.0 * self._line_ratio()

    def height_lines(self, font_pt: float | None = None) -> int | None:
        """Expected vertical line budget at *font_pt* (declared/default pitch).

        ``None`` when the vertical room is unmeasured. Never less than 1 — a cell
        always accommodates its first line; the risk we guard is *growth* past it.
        """

        if self.available_height is None:
            return None
        line_h = self.line_height(font_pt)
        if line_h <= 0:
            return None
        return _lines_in_height(self._lines_room(), line_h, (self.font_pt if font_pt is None else font_pt) * 100.0)

    def _lines_room(self) -> float:
        """The available height less the paragraph's spacing before its first line."""

        before = self.text_style.space_before if self.text_style is not None else 0
        return (self.available_height or 0.0) - before

    def height_lines_optimistic(self, font_pt: float | None = None) -> int | None:
        """Most-generous vertical budget (tightest plausible pitch).

        This is the basis for the *confidence* of a vertical overflow: content that
        overflows even this budget is grossly too tall regardless of pitch error.
        """

        if self.available_height is None:
            return None
        pt = self.font_pt if font_pt is None else font_pt
        line_h = min(self.line_height(pt), pt * 100.0 * MIN_LINE_SPACING_RATIO)
        if line_h <= 0:
            return None
        return _lines_in_height(self._lines_room(), line_h, pt * 100.0)


def _line_pitch(kind: str, value: float, size: float) -> float:
    """Hancom's vertical advance of one line of *size* (HWPUNIT) under a spacing
    type: PERCENT a share of the size, FIXED the value, BETWEEN_LINES the size
    plus the value, AT_LEAST the larger of the two.

    Under PERCENT Hancom counts the spacing beyond the size in 1/1800 inch
    (4 HWPUNIT): the em is the size in that unit, rounded down, and its share
    is rounded half away from zero (10.5 pt at 160 %: 262 x 0.6 = 157.2, so 628
    rather than 630)."""

    kind = kind.upper()
    if kind == "FIXED":
        return value
    if kind == "BETWEEN_LINES":
        return size + value
    if kind == "AT_LEAST":
        return max(size, value)
    share = Fraction(round(size) // _LAYOUT_UNIT) * (Fraction(value) - 100) / 100
    units = math.floor(abs(share) + Fraction(1, 2))
    return size + float(_LAYOUT_UNIT) * (units if share >= 0 else -units)


def _laid_out_height(cell_element: Any) -> float | None:
    """The height of the lines Hancom laid out in a cell's own paragraphs (the end
    of their last cached line), or ``None`` when they hold no line cache."""

    if cell_element is None:
        return None
    ends = [
        int(line.get("vertpos", 0)) + int(line.get("vertsize", 0))
        for sub_list in cell_element
        if _local_name(sub_list.tag) == "subList"
        for paragraph in sub_list
        if _local_name(paragraph.tag) == "p"
        for cache in paragraph
        if _local_name(cache.tag) == "linesegarray"
        for line in cache
        if _local_name(line.tag) == "lineseg"
    ]
    return float(max(ends)) if ends else None


def _row_span(cell: object) -> int:
    try:
        return int(getattr(cell, "span", (1, 1))[0])
    except Exception:  # pragma: no cover - defensive
        return 1


def _row_cells(cell: object) -> list[Any]:
    """The cells of the table row (``hp:tr``) holding *cell*, or *cell* alone."""

    element = getattr(cell, "element", None)
    for row in getattr(getattr(cell, "table", None), "rows", None) or ():
        cells = list(getattr(row, "cells", ()))
        if any(getattr(other, "element", None) is element for other in cells):
            return cells
    return [cell]


def _lines_end(cell: object, document: object) -> float:
    """Where the lines of a cell's own paragraphs end: their line cache or, without
    one, the lines its text measures at its own size and full width below the
    paragraph's spacing before (Hancom lays such a cell out when it opens the file)."""

    drawn = _laid_out_height(getattr(cell, "element", None))
    if drawn:
        return drawn
    slot = _cell_slot(cell, document, max_lines=1, font_pt=None, safety=1.0)
    text = str(getattr(cell, "text", "") or "")
    lines = measure(text, slot).lines if text else 1
    before = slot.text_style.space_before if slot.text_style is not None else 0
    return before + (lines - 1) * slot.line_height() + slot.font_pt * 100.0


def _drawn_row_height(cell: object) -> float:
    """The height of the row as its line caches have it: the tallest of its
    cells that span one row, the end of the lines Hancom laid out in it plus
    its top and bottom margins; 0 when no such cell holds a line cache."""

    tallest = 0.0
    for other in _row_cells(cell):
        drawn = _laid_out_height(getattr(other, "element", None)) if _row_span(other) <= 1 else None
        if drawn:
            _left, _right, top, bottom = _effective_cell_margins(other)
            tallest = max(tallest, drawn + top + bottom)
    return tallest


def _auto_grow_row_height(cell: object, document: object) -> float:
    """How tall Hancom draws the row of a cell stored shorter than one line: as
    tall as its tallest cell. Each cell of the row that spans one row is its
    stored height or the end of its lines plus its top and bottom margins,
    whichever is taller; a merged cell is left out."""

    tallest = 0.0
    for other in _row_cells(cell):
        if _row_span(other) > 1:
            continue
        _left, _right, top, bottom = _effective_cell_margins(other)
        stored = float(getattr(other, "height", 0) or 0)
        tallest = max(tallest, stored, _lines_end(other, document) + top + bottom)
    return tallest


def _lines_in_height(height: float, pitch: float, size: float) -> int:
    """How many lines Hancom fits in *height*: n lines take (n - 1) pitches and
    one line's *size*, the last line's spacing left out; never fewer than one."""

    return max(int((height - size) // pitch) + 1, 1)


@dataclass(slots=True)
class Measurement:
    """Verdict of measuring a value against a :class:`SlotMetrics`."""

    width: float                    # predicted single-line width, HWPUNIT
    lines: int                      # predicted wrapped line count
    fits: bool                      # lines <= slot.max_lines
    confidence: Confidence          # trust in fits/overflow given measurement error
    ratio: float                    # width / single-line available_width
    band: float                     # relative measurement uncertainty used
    notes: list[str] = field(default_factory=list)

    @property
    def overflow(self) -> bool:
        return not self.fits

    def to_dict(self) -> dict[str, object]:
        return {
            "width": round(self.width),
            "lines": self.lines,
            "fits": self.fits,
            "confidence": self.confidence,
            "ratio": round(self.ratio, 4),
            "band": round(self.band, 4),
            "notes": list(self.notes),
        }


def _line_count_after_objects(
    value: str, slot: SlotMetrics, style: TextStyle, first: float, rest: float
) -> int:
    """Lines *value* takes after the slot's inline objects. When not even its
    first character fits beside them, the objects fill the first line and
    Hancom starts the text on the next one."""

    if slot.inline_object_width and value and char_advance(value[0], slot.font_pt, style) > first:
        return 1 + _hancom_line_count(value, rest, rest, slot.font_pt, style)
    return _hancom_line_count(value, first, rest, slot.font_pt, style)


def measure(value: str, slot: SlotMetrics) -> Measurement:
    """Measure *value* against *slot* and judge fit + confidence.

    The confidence rule is the honesty contract (plan §2 C): a verdict is *high*
    confidence only when it survives the measurement error band — i.e. the value
    is comfortably inside or comfortably past the slot. Anything within the band
    is *low* confidence, which the engine treats as "defer to the oracle".
    """

    style = slot.text_style
    width = estimate_text_width(value, slot.font_pt, style)
    band = _uncertainty_band(value)
    available_single = slot.available_width or 1.0
    ratio = width / available_single
    if style is None:
        lines = estimate_lines(value, slot.available_width, slot.font_pt)
        capacity = slot.capacity or 1.0
    else:
        # Inline objects share the first line only; indents come off the first
        # line or, when hanging, off the others.
        line = slot.line_width if slot.line_width is not None else slot.available_width + slot.inline_object_width
        line -= style.margin_left + style.margin_right
        # Each line keeps Hancom's minimum width after its indent; the inline
        # objects then take their width off the first line.
        first = max(line - max(style.indent, 0), slot.min_line_width) - slot.inline_object_width
        rest = max(line - max(-style.indent, 0), slot.min_line_width)
        lines = _line_count_after_objects(value, slot, style, first, rest)
        capacity = (max(first, 0.0) + rest * (slot.max_lines - 1)) or 1.0
    fits = lines <= slot.max_lines

    notes: list[str] = []
    if fits:
        # High confidence only if it clears the band — clearly inside the box.
        confidence: Confidence = "high" if width <= capacity * (1 - band) else "low"
        if confidence == "low":
            notes.append(
                "borderline fit: within the measurement error band; "
                "render oracle should confirm"
            )
    else:
        # Need to overflow the band too, else it is a borderline overflow that a
        # crude advance table must not turn into a hard failure.
        if style is None:
            min_lines_high_conf = math.ceil(
                (width * (1 - band)) / available_single - 1e-9
            )
        else:
            optimistic = width * (1 - band)
            min_lines_high_conf = 1 if optimistic <= first else 1 + math.ceil(
                (optimistic - first) / max(rest, 1.0) - 1e-9
            )
        confidence = "high" if min_lines_high_conf > slot.max_lines else "low"
        if confidence == "low":
            notes.append(
                "borderline overflow: within the measurement error band; "
                "defer the hard fail to the render oracle"
            )
    return Measurement(
        width=width,
        lines=lines,
        fits=fits,
        confidence=confidence,
        ratio=ratio,
        band=band,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Bridge to the document model: resolve a cell's slot geometry.
# --------------------------------------------------------------------------- #
def _local_name(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _effective_cell_margins(cell: object) -> tuple[int, int, int, int]:
    """(left, right, top, bottom) the cell is laid out with, as ``cell.margins`` reads them.

    The table's ``hp:inMargin`` unless the cell's ``hasMargin`` is on; see
    :func:`hwpx.oxml.table_sizes.effective_cell_margin_source`.
    """
    element = getattr(cell, "element", None)
    if element is None:
        return (0, 0, 0, 0)
    table_element = getattr(getattr(cell, "table", None), "element", None)
    margins = cell_margins_of(element, table_element)
    if margins is None:
        return (0, 0, 0, 0)
    return margins.left, margins.right, margins.top, margins.bottom


def _document_root(document: object) -> Any:
    """The OXML document root: ``HwpxDocument._root``, or *document* itself.

    Callers pass either; the root's own ``paragraph_property``/``char_property``
    do not raise the 6.0 move warnings that the ``HwpxDocument`` names do.
    """

    return getattr(document, "_root", document)


def _first_para_line_spacing_ratio(cell: object, document: object) -> float | None:
    """Per-line em multiple from the cell's first paragraph line spacing (PERCENT).

    Only PERCENT spacing maps cleanly onto the em-relative line-height model; FIXED
    / ATLEAST / BETWEENLINES are left to the conservative default so we never invent
    a font-independent pitch (the shrink ladder varies the font).
    """

    try:
        paragraphs = cell.paragraphs  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return None
    for paragraph in paragraphs:
        ref = getattr(paragraph, "para_pr_id_ref", None)
        if ref is None or document is None:
            continue
        try:
            prop = _document_root(document).paragraph_property(ref)
        except Exception:  # pragma: no cover - defensive
            prop = None
        spacing = getattr(prop, "line_spacing", None) if prop is not None else None
        if spacing is None or not getattr(spacing, "value", None):
            continue
        if (getattr(spacing, "spacing_type", None) or "PERCENT").upper() != "PERCENT":
            return None
        try:
            return int(spacing.value) / 100.0
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
    return None


def _first_para_line_spacing(cell: object, document: object) -> tuple[str, float] | None:
    """The cell's first paragraph line spacing as (type, value), any type."""

    try:
        paragraphs = cell.paragraphs  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return None
    for paragraph in paragraphs:
        ref = getattr(paragraph, "para_pr_id_ref", None)
        if ref is None or document is None:
            continue
        try:
            prop = _document_root(document).paragraph_property(ref)
        except Exception:  # pragma: no cover - defensive
            prop = None
        spacing = getattr(prop, "line_spacing", None) if prop is not None else None
        if spacing is None or not getattr(spacing, "value", None):
            continue
        try:
            return (getattr(spacing, "spacing_type", None) or "PERCENT").upper(), float(spacing.value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None
    return None


def _style_number(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _face_names(root: Any, char_pr_id_ref: object) -> tuple[str, str]:
    """The Hangul face the character shape names, and that face again as the
    glyph face when the Latin, other and symbol scripts use it too."""

    from ..oxml.header_fonts import font_face

    try:
        faces = {font_face(root.headers[0], char_pr_id_ref, lang) for lang in _GLYPH_TABLE_SCRIPTS}
        face = font_face(root.headers[0], char_pr_id_ref, "HANGUL") or ""
    except Exception:  # pragma: no cover - defensive
        return "", ""
    return face, face if len(faces) == 1 else ""


def text_style_from_refs(
    document: object, para_pr_id_ref: object, char_pr_id_refs: "list[object]"
) -> TextStyle:
    """Hancom layout settings of a paragraph shape and the first resolvable
    character shape among *char_pr_id_refs*."""

    ratio, spacing, use_font_space, hangul_face, glyph_face = 100.0, 0.0, False, "", ""
    root = _document_root(document)
    for ref in char_pr_id_refs:
        try:
            run_style = root.char_property(ref)
        except Exception:  # pragma: no cover - defensive
            run_style = None
        if run_style is None:
            continue
        children = getattr(run_style, "child_attributes", {}) or {}
        ratio = _style_number((children.get("ratio") or {}).get("hangul"), 100.0)
        spacing = _style_number((children.get("spacing") or {}).get("hangul"), 0.0)
        use_font_space = (getattr(run_style, "attributes", {}) or {}).get("useFontSpace") in {"1", "true"}
        hangul_face, glyph_face = _face_names(root, ref)
        break
    try:
        prop = root.paragraph_property(para_pr_id_ref)
    except Exception:  # pragma: no cover - defensive
        prop = None
    if prop is None:
        return TextStyle(
            ratio=ratio,
            spacing=spacing,
            use_font_space=use_font_space,
            glyph_face=glyph_face,
            hangul_face=hangul_face,
        )
    breaks = getattr(prop, "break_setting", None)
    # hp:case carries the HWPUNIT values Hancom lays out with; hp:default doubles them.
    switch = getattr(prop, "version_switch", None)
    case = getattr(switch, "case", None) if switch is not None else None
    margin = getattr(case, "margin", None) if case is not None else None
    if margin is None:
        margin = getattr(prop, "margin", None)
    return TextStyle(
        ratio=ratio,
        spacing=spacing,
        use_font_space=use_font_space,
        break_latin_word=getattr(breaks, "break_latin_word", None) or "KEEP_WORD",
        break_non_latin_word=getattr(breaks, "break_non_latin_word", None) or "BREAK_WORD",
        condense=int(_style_number(getattr(prop, "condense", 0), 0.0)),
        indent=int(_style_number(getattr(margin, "intent", 0), 0.0)),
        margin_left=int(_style_number(getattr(margin, "left", 0), 0.0)),
        margin_right=int(_style_number(getattr(margin, "right", 0), 0.0)),
        space_before=int(_style_number(getattr(margin, "prev", 0), 0.0)),
        glyph_face=glyph_face,
        hangul_face=hangul_face,
    )


def _cell_text_style(cell: object, document: object) -> TextStyle:
    """Hancom layout settings of the cell's first paragraph and first run."""

    try:
        paragraphs = list(cell.paragraphs)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        paragraphs = []
    if not paragraphs or document is None:
        return TextStyle()
    paragraph = paragraphs[0]
    refs = [getattr(run, "char_pr_id_ref", None) for run in getattr(paragraph, "runs", [])]
    return text_style_from_refs(document, getattr(paragraph, "para_pr_id_ref", None), refs)


def _first_run_font_pt(cell: object, document: object) -> float:
    """Resolve the cell's first run font size in points (default 10pt)."""

    try:
        paragraphs = cell.paragraphs  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        paragraphs = []
    for paragraph in paragraphs:
        for run in getattr(paragraph, "runs", []):
            ref = getattr(run, "char_pr_id_ref", None)
            pt = _font_pt_from_ref(ref, document)
            if pt is not None:
                return pt
    return 10.0


def _font_pt_from_ref(ref: object, document: object) -> float | None:
    if ref is None or document is None:
        return None
    try:
        style = _document_root(document).char_property(ref)
    except Exception:  # pragma: no cover - defensive
        return None
    if style is None:
        return None
    height = getattr(style, "attributes", {}).get("height")
    if not height:
        return None
    try:
        return int(height) / 100.0
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def resolve_slot_metrics(
    cell: object,
    document: object,
    *,
    max_lines: int = 1,
    font_pt: float | None = None,
    safety: float = DEFAULT_SAFETY,
) -> SlotMetrics:
    """Build :class:`SlotMetrics` from a live table cell.

    ``available_width = max(cellSz.width - margin.L - margin.R, MIN_LINE_WIDTH) * safety``,
    where the margins are the cell's effective ones (``cell.margins``: the
    table's ``hp:inMargin`` unless ``hasMargin`` is on) —
    verified against Hancom's own ``lineSeg/@horzsize`` (±10 HWPUNIT on 82% of
    cells; the safety factor covers the rest plus paragraph indent, which is left
    to the HarfBuzz pass).

    ``text_style`` carries the Hancom layout settings of the cell's first
    paragraph and run (break settings, 최소 공백, indent, 장평, 자간), so the
    fit follows Hancom's line breaking rules.

    ``available_height`` is the stored inner height, ``cellSz.height - top -
    bottom margin``: Hancom lays lines out up to it without growing the row, and
    the line pitch is Hancom's own, so no safety inset applies (the width's
    covers the error in measuring a line). A merged cell has no usable height (its
    ``cellSz.height`` is a single-row fragment, not the spanned height): it is
    recorded as *unavailable* (``None`` + ``height_unavailable``) and the fit
    stays width-only rather than guess a vertical fit. A cell stored shorter than
    one line grows with its text: Hancom draws its row as tall as the row's
    tallest cell, so that height, less the cell's own margins, is its budget
    (see :func:`_auto_grow_row_height`), and a value needing more lines than the
    row holds grows the row. A row whose laid-out lines already run past its
    stored height is as tall as those lines too (:func:`_drawn_row_height`).
    """

    slot = _cell_slot(cell, document, max_lines=max_lines, font_pt=font_pt, safety=safety)
    _left, _right, top, bottom = _effective_cell_margins(cell)
    if _row_span(cell) > 1:
        # A merged row-span's cellSz.height is only one of the spanned rows.
        return replace(slot, height_unavailable=True)
    raw_height = float(getattr(cell, "height", 0) or 0)
    stored = max(raw_height - top - bottom, 0.0) if raw_height > 0 else 0.0
    if stored * safety >= slot.font_pt * 100.0 * MIN_LINE_SPACING_RATIO:
        # The stored height, unless lines Hancom laid out in the row run past it:
        # Hancom then draws the row as tall as those lines.
        drawn = _drawn_row_height(cell) - top - bottom
        return replace(slot, available_height=max(stored, drawn))
    # Stored shorter than one line at the tightest pitch: the row grows with its
    # text, and holds as many lines as its tallest cell.
    return replace(slot, available_height=_auto_grow_row_height(cell, document) - top - bottom)


def _cell_slot(
    cell: object,
    document: object,
    *,
    max_lines: int,
    font_pt: float | None,
    safety: float,
) -> SlotMetrics:
    """The width, font and text style of a cell's slot, without a height budget."""

    raw_width = float(getattr(cell, "width", 0) or 0)
    element = getattr(cell, "element", None)
    left, right, _top, _bottom = _effective_cell_margins(cell)
    line = max(raw_width - left - right, 0.0) * safety
    inner = (max(raw_width - left - right, MIN_LINE_WIDTH) if raw_width > 0 else 0.0) * safety
    inline_width, inline_count = (
        _inline_object_width(element) if element is not None else (0.0, 0)
    )
    if inline_width:
        inner = max(inner - inline_width, 0.0)
    resolved_pt = font_pt if font_pt is not None else _first_run_font_pt(cell, document)

    return SlotMetrics(
        available_width=inner,
        font_pt=resolved_pt,
        max_lines=max(max_lines, 1),
        raw_width=raw_width,
        source="cell",
        line_spacing_ratio=_first_para_line_spacing_ratio(cell, document),
        inline_object_width=inline_width,
        inline_object_count=inline_count,
        text_style=_cell_text_style(cell, document),
        line_width=line if raw_width > 0 else None,
        min_line_width=MIN_LINE_WIDTH * safety,
        line_spacing=_first_para_line_spacing(cell, document),
    )


def _inline_object_width(cell_element: object) -> tuple[float, int]:
    """Total declared width of inline treat-as-char objects in the cell.

    Checkboxes and similar form controls flow on the text line
    (``hp:pos/@treatAsChar='1'``) and consume their ``hp:sz/@width``; a fill
    value shares whatever width remains. Objects without a declared size are
    counted but contribute 0 width (the count still signals reduced trust).
    """

    total = 0.0
    count = 0
    iter_fn = getattr(cell_element, "iter", None)
    if iter_fn is None:
        return 0.0, 0
    for node in iter_fn():
        tag = getattr(node, "tag", "")
        if not isinstance(tag, str):
            continue
        local = tag.rsplit("}", 1)[-1].lower()
        if local != "pos":
            continue
        if (node.get("treatAsChar") or "").strip() not in {"1", "true", "TRUE"}:
            continue
        holder = node.getparent() if hasattr(node, "getparent") else None
        if holder is None:
            continue
        count += 1
        for sibling in holder:
            sib_local = str(getattr(sibling, "tag", "")).rsplit("}", 1)[-1].lower()
            if sib_local == "sz":
                try:
                    total += float(sibling.get("width") or 0)
                except (TypeError, ValueError):
                    pass
                break
    return total, count


__all__ = [
    "SlotMetrics",
    "TextStyle",
    "Measurement",
    "Confidence",
    "DEFAULT_SAFETY",
    "DEFAULT_LINE_SPACING_RATIO",
    "MIN_LINE_SPACING_RATIO",
    "GROSS_ROW_GROWTH_FACTOR",
    "MIN_ROW_GROWTH_LINES",
    "classify_char",
    "char_advance",
    "estimate_text_width",
    "estimate_lines",
    "hancom_line_starts",
    "measure",
    "resolve_slot_metrics",
]
