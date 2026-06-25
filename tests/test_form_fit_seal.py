# SPDX-License-Identifier: Apache-2.0
"""직인/관인 placement compliance geometry (M2 P3 / FR-003).

Pure-geometry tests over synthetic glyph boxes (no Hancom): the 발신명의 anchor is
the last glyph of the matching line, and the compliance check discriminates a
centered seal (pass) from a mis-placed one (fail) — acceptance #3.
"""
from __future__ import annotations

from hwpx.form_fit import seal
from hwpx.form_fit.wordbox import Rect, WordBox


def _line(text, *, x0=100.0, y=400.0, w=12.0, h=14.0, page=0):
    """Glyph boxes for *text* laid out left-to-right; spaces advance without ink."""
    boxes = []
    x = x0
    for ch in text:
        if ch.isspace():
            x += w
            continue
        boxes.append(WordBox(x0=x, y0=y, x1=x + w, y1=y + h, text=ch, page=page))
        x += w
    return boxes


SENDER = "행정안전부장관 홍길동"


def test_find_seal_anchor_returns_last_inked_glyph():
    boxes = _line(SENDER)
    anchor = seal.find_seal_anchor(boxes, SENDER)
    assert anchor is not None
    assert anchor.glyph.text == "동"  # last glyph of the line = seal center target


def test_find_seal_anchor_none_when_line_absent():
    boxes = _line("그냥 본문 텍스트입니다")
    assert seal.find_seal_anchor(boxes, SENDER) is None


def test_find_seal_anchor_matches_substring_line():
    # the sender string appears within a longer issuer line
    boxes = _line("발신 행정안전부장관 홍길동 귀하")
    anchor = seal.find_seal_anchor(boxes, SENDER)
    assert anchor is not None and anchor.glyph.text == "하"  # last glyph of that line


def test_find_seal_anchor_last_occurrence_wins():
    top = _line("행정안전부장관", y=100.0)         # a mention up top
    foot = _line(SENDER, y=720.0)                  # the issuer line near the foot
    anchor = seal.find_seal_anchor(top + foot, "행정안전부장관")
    assert anchor is not None and anchor.glyph.text == "동"  # the foot line wins


def test_check_seal_centered_passes():
    boxes = _line(SENDER)
    anchor = seal.find_seal_anchor(boxes, SENDER)
    cx, cy = anchor.center
    placed = Rect(cx - 18, cy - 18, cx + 18, cy + 18, label="seal", page=0)
    verdict = seal.check_seal_placement(boxes, placed, SENDER, tol_pt=6.0)
    assert verdict.ok and verdict.anchor_found and verdict.centered
    assert verdict.offset_pt is not None and verdict.offset_pt < 1.0
    assert verdict.occluded_glyphs == 0  # only the anchor line is under the seal (exempt)


def test_check_seal_misplaced_fails():
    boxes = _line(SENDER)
    placed = Rect(10.0, 380.0, 50.0, 420.0, label="seal", page=0)  # far left of the anchor
    verdict = seal.check_seal_placement(boxes, placed, SENDER, tol_pt=6.0)
    assert verdict.anchor_found is True
    assert verdict.centered is False and verdict.ok is False
    assert verdict.offset_pt is not None and verdict.offset_pt > 6.0


def test_check_seal_anchor_not_found_fails_closed():
    boxes = _line("본문 내용만 있음")
    placed = Rect(100.0, 100.0, 140.0, 140.0, label="seal", page=0)
    verdict = seal.check_seal_placement(boxes, placed, SENDER, tol_pt=6.0)
    assert verdict.ok is False and verdict.anchor_found is False


def test_check_seal_occlusion_of_other_text_fails():
    boxes = _line(SENDER)
    anchor = seal.find_seal_anchor(boxes, SENDER)
    cx, cy = anchor.center
    # a glyph on a DIFFERENT line, directly under the (centered) seal
    other = WordBox(x0=cx - 5, y0=cy + 40, x1=cx + 5, y1=cy + 54, text="X", page=0)
    placed = Rect(cx - 30, cy - 30, cx + 30, cy + 60, label="seal", page=0)
    verdict = seal.check_seal_placement(
        boxes + [other], placed, SENDER, tol_pt=20.0, max_occluded=0
    )
    assert verdict.anchor_found and verdict.centered  # centered within the loose tol
    assert verdict.occluded_glyphs >= 1 and verdict.ok is False  # ...but occludes other text


def test_check_seal_page_scoped_anchor():
    # the sender line is on page 1; a seal on page 1 must bind to it, not page 0 noise
    boxes = _line("행정안전부장관", y=100.0, page=0) + _line(SENDER, y=700.0, page=1)
    anchor = seal.find_seal_anchor(boxes, SENDER, page=1)
    assert anchor is not None and anchor.glyph.page == 1 and anchor.glyph.text == "동"
