# SPDX-License-Identifier: Apache-2.0
"""직인 floating placement (M2 P3 slice 2 / FR-003).

Slice 1 (:mod:`hwpx.form_fit.seal`) decided the rule *geometrically* (where the
seal center belongs + pass/fail). Slice 2 actually **places** the seal image at
that point as a **floating** object — ``add_picture`` is inline-only, so the seal
needs a PAPER-relative ``<hp:pos>`` whose offset lands the seal *center* on the
발신명의 last glyph. These tests pin the placement mechanism offline (no Hancom):

* ``seal_pos_offsets`` — pure pt→HWPUNIT center→top-left math, clamped ≥ 0
  (schema: ``vert/horzOffset`` are ``xs:nonNegativeInteger``).
* the oxml floating-pic primitive — ``treatAsChar="0"`` + PAPER relTo + offsets.
* ``place_seal`` — binds the floating pic to the **source** 발신명의 paragraph
  (so it lands on that paragraph's page) and fails closed when absent.
"""
from __future__ import annotations

import base64
import os

import pytest

from hwpx.document import HwpxDocument
from hwpx.form_fit import seal
import hwpx.form_fit.wordbox as wb

HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

# 1x1 PNG (same asset the picture-workflow tests use).
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)

SENDER = "행정안전부장관 홍길동"

# 1 mm = 7200 / 25.4 HWPUNIT (HWPUNIT = 7200 per inch).
_MM_TO_HU = 7200.0 / 25.4


def _seal_pic_elements(document: HwpxDocument):
    return document.oxml.sections[0].element.findall(f".//{HP}pic")


# --------------------------------------------------------------------------- #
# seal_pos_offsets — pure geometry
# --------------------------------------------------------------------------- #


def test_seal_pos_offsets_centers_on_anchor():
    # anchor center at (300pt, 700pt); seal 7200x7200 HWPUNIT (1in square).
    # PAPER/TOP-LEFT offset = center*100 - size/2.
    horz, vert = seal.seal_pos_offsets((300.0, 700.0), 7200, 7200)
    assert horz == round(300.0 * 100 - 7200 / 2)  # 26400
    assert vert == round(700.0 * 100 - 7200 / 2)  # 66400


def test_seal_pos_offsets_clamps_negative_to_zero():
    # a seal larger than its anchor's distance from the paper edge would yield a
    # negative top-left; schema forbids negative offsets -> clamp to 0.
    horz, vert = seal.seal_pos_offsets((1.0, 1.0), 7200, 7200)
    assert horz == 0 and vert == 0


# --------------------------------------------------------------------------- #
# oxml floating-pic primitive
# --------------------------------------------------------------------------- #


def test_add_picture_floating_emits_paper_relative_pos():
    document = HwpxDocument.new()
    paragraph = document.paragraphs[0]
    ref = document.add_image(PNG_1X1, "png")
    paragraph.add_picture(
        ref,
        width=7200,
        height=7200,
        treat_as_char=False,
        pos_overrides={
            "horzRelTo": "PAPER",
            "vertRelTo": "PAPER",
            "horzAlign": "LEFT",
            "vertAlign": "TOP",
            "horzOffset": 26400,
            "vertOffset": 66400,
        },
    )
    pic = _seal_pic_elements(document)[0]
    pos = pic.find(f"{HP}pos")
    assert pos is not None
    assert pos.get("treatAsChar") == "0"
    assert pos.get("horzRelTo") == "PAPER"
    assert pos.get("vertRelTo") == "PAPER"
    assert pos.get("horzOffset") == "26400"
    assert pos.get("vertOffset") == "66400"


def test_add_picture_default_is_inline_treat_as_char():
    document = HwpxDocument.new()
    document.add_picture(PNG_1X1, "png", width=7200, height=7200)
    pos = _seal_pic_elements(document)[0].find(f"{HP}pos")
    assert pos is not None and pos.get("treatAsChar") == "1"


def test_add_picture_pos_overrides_requires_floating():
    # pos_overrides (PAPER relTo/offset) on an INLINE pic is a contradictory
    # inline/floating mix — reject it rather than emit a confusing element.
    document = HwpxDocument.new()
    ref = document.add_image(PNG_1X1, "png")
    with pytest.raises(ValueError):
        document.paragraphs[0].add_picture(
            ref, treat_as_char=True, pos_overrides={"horzRelTo": "PAPER", "horzOffset": 100}
        )


def test_place_seal_records_explicit_page_for_multipage():
    document = _doc_with_sender("제목", SENDER)
    placement = seal.place_seal(
        document,
        image_data=PNG_1X1,
        image_format="png",
        sender_text=SENDER,
        anchor_center_pt=(300.0, 400.0),
        seal_width_mm=25.0,
        page=2,
    )
    assert placement.placed is True
    assert placement.page == 2  # the anchor's render page, recorded for cross-check


# --------------------------------------------------------------------------- #
# place_seal — bind floating pic to the source 발신명의 paragraph
# --------------------------------------------------------------------------- #


def _doc_with_sender(*paragraph_texts: str) -> HwpxDocument:
    document = HwpxDocument.new()
    document.paragraphs[0].text = paragraph_texts[0]
    for extra in paragraph_texts[1:]:
        document.add_paragraph(extra)
    return document


def test_place_seal_attaches_floating_pic_to_sender_paragraph():
    document = _doc_with_sender("제목: 협조 요청", "본문 내용입니다", SENDER)
    placement = seal.place_seal(
        document,
        image_data=PNG_1X1,
        image_format="png",
        sender_text=SENDER,
        anchor_center_pt=(300.0, 700.0),
        seal_width_mm=25.0,
    )
    assert placement.placed is True

    w_hu = round(25.0 * _MM_TO_HU)
    exp_h, exp_v = seal.seal_pos_offsets((300.0, 700.0), w_hu, w_hu)
    assert placement.horz_offset == exp_h
    assert placement.vert_offset == exp_v

    # the floating pic must live in the SENDER paragraph (its anchor page), not a
    # freshly appended trailing paragraph.
    sender_para = document.paragraphs[placement.paragraph_index]
    assert SENDER.replace(" ", "") in sender_para.text.replace(" ", "")
    pic = sender_para.element.find(f".//{HP}pic")
    assert pic is not None
    # a 직인 is stamped OVER the signature line — it must not reflow the text it
    # overlaps, so textWrap is IN_FRONT_OF_TEXT (oracle-confirmed: SQUARE wraps the
    # 발신명의 glyphs and shoves them ~70pt right, breaking the centering).
    assert pic.get("textWrap") == "IN_FRONT_OF_TEXT"
    pos = pic.find(f"{HP}pos")
    assert pos.get("treatAsChar") == "0"
    assert pos.get("horzRelTo") == "PAPER" and pos.get("vertRelTo") == "PAPER"
    assert pos.get("horzOffset") == str(exp_h)
    assert pos.get("vertOffset") == str(exp_v)


def test_place_seal_fails_closed_when_sender_absent():
    document = _doc_with_sender("제목만 있고 발신명의 없음", "본문")
    placement = seal.place_seal(
        document,
        image_data=PNG_1X1,
        image_format="png",
        sender_text=SENDER,
        anchor_center_pt=(300.0, 700.0),
        seal_width_mm=25.0,
    )
    assert placement.placed is False
    assert not _seal_pic_elements(document)  # nothing inserted


def test_place_seal_last_occurrence_wins():
    # the issuer line sits near the foot; a stray earlier mention must not win.
    document = _doc_with_sender("행정안전부장관 (수신)", "중략", SENDER)
    placement = seal.place_seal(
        document,
        image_data=PNG_1X1,
        image_format="png",
        sender_text="행정안전부장관",
        anchor_center_pt=(300.0, 700.0),
        seal_width_mm=25.0,
    )
    assert placement.placed is True
    assert placement.paragraph_index == 2  # the foot line, not paragraph 0


def test_place_seal_finds_sender_in_table_cell():
    # Korean official letters often put the 발신명의 inside a 발신·결재 table box.
    # document.paragraphs (section direct children) does NOT surface cell paragraphs,
    # so place_seal must descend into tables or it silently fails on a whole class.
    document = HwpxDocument.new()
    document.paragraphs[0].text = "제목: 협조 요청"
    table = document.paragraphs[0].add_table(1, 1)
    table.cell(0, 0).add_paragraph(SENDER)

    placement = seal.place_seal(
        document,
        image_data=PNG_1X1,
        image_format="png",
        sender_text=SENDER,
        anchor_center_pt=(300.0, 700.0),
        seal_width_mm=25.0,
    )
    assert placement.placed is True
    # the floating seal exists somewhere in the document (in the cell's paragraph)
    pics = _seal_pic_elements(document)
    assert len(pics) == 1
    assert pics[0].find(f"{HP}pos").get("treatAsChar") == "0"


def test_place_seal_empty_sender_text_fails_closed():
    document = _doc_with_sender("제목", SENDER)
    placement = seal.place_seal(
        document,
        image_data=PNG_1X1,
        image_format="png",
        sender_text="   ",
        anchor_center_pt=(300.0, 700.0),
        seal_width_mm=25.0,
    )
    assert placement.placed is False
    assert "sender" in placement.note.lower()
    assert not _seal_pic_elements(document)


def test_place_seal_records_page_and_clamp():
    document = _doc_with_sender("제목", SENDER)
    placement = seal.place_seal(
        document,
        image_data=PNG_1X1,
        image_format="png",
        sender_text=SENDER,
        anchor_center_pt=(1.0, 1.0),  # within half a seal of the paper corner -> clamps
        seal_width_mm=25.0,
        page=0,
    )
    assert placement.placed is True
    assert placement.page == 0
    assert placement.horz_offset == 0 and placement.vert_offset == 0
    assert placement.clamped is True  # the realized center != requested anchor


def test_add_picture_pos_overrides_clamps_negative_and_float_offsets():
    # the low-level floating primitive must never emit a schema-invalid offset
    # (xs:nonNegativeInteger) even if a caller passes a negative or fractional value.
    document = HwpxDocument.new()
    ref = document.add_image(PNG_1X1, "png")
    document.paragraphs[0].add_picture(
        ref,
        width=7200,
        height=7200,
        treat_as_char=False,
        pos_overrides={"horzOffset": -5, "vertOffset": 3.5},
    )
    pos = _seal_pic_elements(document)[0].find(f"{HP}pos")
    assert pos.get("horzOffset") == "0"   # -5 clamped to 0
    assert pos.get("vertOffset") == "4"   # 3.5 rounded to a non-negative int


def test_place_seal_output_passes_open_safety(tmp_path):
    from hwpx.tools.package_validator import validate_package
    from hwpx.tools.repair import repair_repack

    document = _doc_with_sender("제목", "본문", SENDER)
    placement = seal.place_seal(
        document,
        image_data=PNG_1X1,
        image_format="png",
        sender_text=SENDER,
        anchor_center_pt=(300.0, 700.0),
        seal_width_mm=25.0,
    )
    assert placement.placed is True

    source = tmp_path / "sealed.hwpx"
    repaired = tmp_path / "sealed.repaired.hwpx"
    document.save_to_path(source)
    repair_repack(source, repaired)
    assert validate_package(repaired).ok


# --- live Hancom oracle smoke (FR-003 — seal lands on 발신명의, discriminates) ----


def _mac_seal_oracle_ready() -> bool:
    try:
        from hwpx.visual.oracle import MacHancomOracle

        return MacHancomOracle().available() and wb.fitz_available()
    except Exception:
        return False


def _red_ring_seal_png() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=72, height=72)
    page.draw_circle(fitz.Point(36, 36), 33, color=(0.8, 0, 0), width=4)
    return page.get_pixmap(dpi=200, alpha=False).tobytes("png")


@pytest.mark.skipif(
    not (_mac_seal_oracle_ready() and os.environ.get("HWPX_MAC_ORACLE_SMOKE")),
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the 직인 placement smoke",
)
def test_mac_seal_placement_lands_on_anchor_smoke(tmp_path):
    """A placed 직인 renders centered on the 발신명의 last glyph in real Hancom, and
    the compliance check discriminates a deliberately mis-placed seal (FR-003 /
    acceptance #3). Proves the full library path: ``isEmbeded`` (image renders) +
    ``IN_FRONT_OF_TEXT`` (no reflow) + PAPER offsets (lands on the anchor).
    """
    from hwpx.visual.oracle import MacHancomOracle

    oracle = MacHancomOracle(timeout=120)

    def build():
        doc = HwpxDocument.new()
        doc.paragraphs[0].text = "협조 요청의 건"
        for line in [
            "1. 귀 기관의 무궁한 발전을 기원합니다.",
            "2. 아래와 같이 자료 제출을 요청하오니 협조하여 주시기 바랍니다.",
            "", "붙임  자료 목록 1부.  끝.", "", "", SENDER,
        ]:
            doc.add_paragraph(line)
        return doc

    blank = tmp_path / "seal_blank.hwpx"
    build().save_to_path(str(blank))
    boxes, _, _ = wb.render_glyph_boxes(str(blank), oracle=oracle, out_pdf=str(tmp_path / "b.pdf"))
    anchor = seal.find_seal_anchor(boxes, SENDER)
    assert anchor is not None

    doc = build()
    placement = seal.place_seal(
        doc, image_data=_red_ring_seal_png(), image_format="png",
        sender_text=SENDER, anchor_center_pt=anchor.center, seal_width_mm=22.0,
    )
    assert placement.placed
    filled = tmp_path / "seal_filled.hwpx"
    doc.save_to_path(str(filled))

    boxes2, _, _ = wb.render_glyph_boxes(str(filled), oracle=oracle, out_pdf=str(tmp_path / "f.pdf"))
    seal_rects = wb.extract_image_boxes(str(tmp_path / "f.pdf"))
    assert seal_rects, "seal image did not render (isEmbeded regression?)"
    seal_rect = seal_rects[0]

    # pass: the seal is centered on the 발신명의 last glyph, text undisturbed
    verdict = seal.check_seal_placement(boxes2, seal_rect, SENDER, tol_pt=12.0)
    assert verdict.ok and verdict.centered, verdict.to_dict()
    assert verdict.offset_pt is not None and verdict.offset_pt < 5.0

    # discrimination: a seal shifted far from the anchor must FAIL
    bad = wb.Rect(
        seal_rect.x0 + 160, seal_rect.y0, seal_rect.x1 + 160, seal_rect.y1,
        label="bad", page=seal_rect.page,
    )
    assert seal.check_seal_placement(boxes2, bad, SENDER, tol_pt=12.0).ok is False
