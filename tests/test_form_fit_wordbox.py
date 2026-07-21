# SPDX-License-Identifier: Apache-2.0
"""Word/glyph-box geometry oracle (M2 P1 / rhwp ⑨).

Covers geometry (glyph-granular overlap, overflow, cross-page isolation), the
fail-closed provenance/binding contract, freeze-load + degrade-not-crash, and
real ``fitz`` extraction against synthetic PDFs (no Hancom needed for these). The
real-Hancom ground truth rides in ``fixtures/form_fit_wordbox/notice_clean.json``.
"""
from __future__ import annotations

import json
import os

import pytest

from hwpx.form_fit import wordbox as wb


def _box(x0, y0, x1, y1, text="x", page=0):
    return wb.WordBox(x0=x0, y0=y0, x1=x1, y1=y1, text=text, page=page)


# --- geometry: overlap (glyph-granular) -------------------------------------

def test_collide_true_for_stacked_glyphs():
    a = _box(10, 10, 30, 22)
    b = _box(12, 11, 32, 23)  # heavy area overlap -> 글자 겹침
    assert a.collides(b) and b.collides(a)


def test_no_collision_for_adjacent_glyph_seam():
    a = _box(10, 10, 20, 22)
    b = _box(20, 10, 30, 22)  # share only the kerning seam (area 0)
    assert not a.collides(b)


def test_collision_is_area_gated_not_axis_gated():
    # A diagonal nudge: 0.7pt on each axis = 0.49pt² overlap -> a real collision.
    a = _box(10, 10, 21, 21)
    b = _box(20.3, 20.3, 31.3, 31.3)
    assert a.overlap_area(b) == pytest.approx(0.49, abs=1e-6)
    assert a.collides(b)  # the old AND-of-axes gate wrongly let this pass
    # A corner touch: 0.3pt each axis = 0.09pt² -> a seam, not a collision.
    c = _box(20.7, 20.7, 31, 31)
    assert not a.collides(c)


def test_no_collision_across_pages():
    a = _box(10, 10, 30, 22, page=0)
    b = _box(10, 10, 30, 22, page=1)
    assert not a.collides(b)
    assert a.overlap_area(b) == 0.0


def test_detect_overlaps_returns_each_pair_once():
    boxes = [_box(0, 0, 10, 10), _box(2, 2, 12, 12), _box(100, 100, 110, 110)]
    assert len(wb.detect_overlaps(boxes)) == 1


def test_intra_token_stacking_is_caught_at_glyph_granularity():
    # The headline 방송신청서 defect: chars of ONE whitespace-free token cramped so
    # the glyphs overlap. At glyph granularity this is visible.
    glyphs = [_box(10, 10, 24, 22, "겹"), _box(12, 10, 26, 22, "침")]
    assert wb.detect_overlaps(glyphs)  # not blind anymore


def test_nan_box_is_not_a_silent_collision():
    good = _box(10, 10, 20, 20)
    nan = _box(float("nan"), 10, 20, 20)
    assert not nan.finite
    assert not good.collides(nan)  # NaN must not fabricate a collision


# --- geometry: overflow + clip ownership ------------------------------------

def test_overflow_of_rect():
    clip = wb.Rect(0, 0, 100, 20, label="cell")
    assert clip.overflow_of(_box(5, 5, 95, 15)) <= 0
    assert clip.overflow_of(_box(5, 5, 130, 15)) == pytest.approx(30.0)


def test_detect_overflow_only_flags_owning_clip():
    clip = wb.Rect(0, 0, 100, 20, label="cell")
    inside = _box(5, 5, 95, 15)
    escaping = _box(5, 5, 130, 15)
    far = _box(500, 500, 540, 515)  # belongs to no clip -> page chrome
    flagged = wb.detect_overflow([inside, escaping, far], [clip])
    assert [r.label for _, r in flagged] == ["cell"]
    assert flagged[0][0] is escaping


def test_overflow_does_not_alias_across_pages():
    # A page-0 clip must NOT judge a page-1 box, even one that geometrically
    # ESCAPES it — only the same-page guard prevents the cross-page false-fail.
    clip = wb.Rect(0, 0, 100, 20, label="p0", page=0)
    escaping_p1 = _box(5, 5, 130, 15, page=1)  # would overflow by 30 if page-blind
    assert wb.detect_overflow([escaping_p1], [clip]) == []  # no cross-page false-fail
    # positive control: the SAME geometry on page 0 IS flagged (proves the test bites)
    escaping_p0 = _box(5, 5, 130, 15, page=0)
    assert wb.detect_overflow([escaping_p0], [clip])


def test_owning_clip_picks_tightest_area():
    outer = wb.Rect(0, 0, 200, 100, label="outer")
    inner = wb.Rect(40, 40, 60, 60, label="inner")
    box = _box(45, 45, 55, 55)  # center inside both -> innermost wins
    assert wb._owning_clip(box, [outer, inner]).label == "inner"
    assert wb._owning_clip(box, [inner, outer]).label == "inner"  # order-independent


# --- verdict + honesty contract --------------------------------------------

def test_clean_verdict_with_explicit_render_checked():
    v = wb.verdict_from_boxes([_box(0, 0, 10, 10), _box(40, 0, 50, 10)], render_checked=True)
    assert v.render_checked and v.ok
    assert not v.overflow_detected and not v.overlap_detected


def test_render_checked_defaults_false_fail_closed():
    # Honesty-critical default: a verdict is NOT a pass unless faithfulness is asserted.
    v = wb.verdict_from_boxes([_box(0, 0, 10, 10)])
    assert v.render_checked is False
    assert v.ok is False
    assert v.note == "unverified"


def test_overflow_checked_distinguishes_unevaluated_from_clean():
    no_clips = wb.verdict_from_boxes([_box(0, 0, 10, 10)], render_checked=True)
    assert no_clips.overflow_checked is False  # not evaluated, not "clean"
    with_clips = wb.verdict_from_boxes(
        [_box(0, 0, 10, 10)], [wb.Rect(0, 0, 100, 20)], render_checked=True
    )
    assert with_clips.overflow_checked is True


def test_overlap_makes_verdict_not_ok():
    v = wb.verdict_from_boxes([_box(0, 0, 10, 10), _box(2, 2, 12, 12)], render_checked=True)
    assert v.overlap_detected and not v.ok


def test_unverified_is_never_a_silent_pass():
    v = wb.unverified_verdict("no Hancom and no frozen fixture")
    assert v.render_checked is False
    assert v.ok is False
    assert v.note.startswith("unverified")
    assert v.to_dict()["ok"] is False


# --- fixture: freeze / load / fail-closed provenance ------------------------

def test_freeze_load_roundtrip_with_provenance(tmp_path):
    boxes = [_box(1, 2, 3, 4, text="가"), _box(5, 6, 7, 8, text="나", page=1)]
    fx = wb.WordBoxFixture(
        boxes=boxes, page_sizes=[(595.0, 842.0)], source="unit",
        checked=True, source_sha256="abc123", backend="MacHancomOracle",
    )
    path = tmp_path / "frozen.json"
    fx.freeze(str(path))
    back = wb.WordBoxFixture.load(str(path))
    assert back.checked is True and back.source_sha256 == "abc123"
    assert back.backend == "MacHancomOracle"
    assert [b.text for b in back.boxes] == ["가", "나"]
    assert back.boxes[1].page == 1


def test_missing_checked_key_loads_fail_closed(tmp_path):
    # A fixture (or schema-drifted/forged file) without `checked` must NOT load
    # as a faithful capture.
    path = tmp_path / "no_checked.json"
    path.write_text(json.dumps({"version": 1, "boxes": [[1, 2, 3, 4, "x", 0, 0, 0, 0]]}))
    fx = wb.WordBoxFixture.load(str(path))
    assert fx.checked is False
    assert fx.source_sha256 is None


def test_future_version_fixture_is_rejected(tmp_path):
    path = tmp_path / "future.json"
    path.write_text(json.dumps({"version": 999, "checked": True, "boxes": []}))
    with pytest.raises(ValueError):
        wb.WordBoxFixture.load(str(path))


# --- end-to-end verify_form_fill (no Hancom needed) ------------------------

_NOTICE = os.path.join(  # the document the checked-in fixture certifies
    os.path.dirname(__file__), "..", "src", "hwpx", "conformance", "corpus", "notice.hwpx"
)
_NOTICE_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "form_fit_wordbox", "notice_clean.json"
)


def test_real_hancom_fixture_is_glyph_granular_and_clean():
    # Checked-in ground truth: notice.hwpx rendered by real Hancom, glyph boxes
    # frozen. Regresses offline forever, bound to its source by sha256.
    assert os.path.exists(_NOTICE_FIXTURE), "real-Hancom fixture must be checked in"
    fx = wb.WordBoxFixture.load(_NOTICE_FIXTURE)
    assert fx.checked and fx.source_sha256 and fx.backend == "MacHancomOracle"
    assert len(fx.boxes) > 30  # glyph-granular, not 15 word boxes
    # Pin granularity: every box is a SINGLE glyph (this is what makes intra-token
    # 글자겹침 visible). A word-granular fixture must NOT satisfy this test.
    assert all(len(b.text) == 1 for b in fx.boxes)
    assert all(b.word_no == -1 for b in fx.boxes)  # glyph extractor, not word
    assert wb.detect_overlaps(fx.boxes) == []  # a clean render has no 겹침


def test_verify_from_bound_fixture_is_render_checked():
    v = wb.verify_form_fill(_NOTICE, frozen_path=_NOTICE_FIXTURE)
    assert v.render_checked is True and v.ok is True
    assert not v.overlap_detected


def test_verify_rejects_stale_or_mismatched_source():
    wrong = os.path.join(os.path.dirname(_NOTICE), "report_table.hwpx")
    v = wb.verify_form_fill(wrong, frozen_path=_NOTICE_FIXTURE)
    assert v.render_checked is False
    assert "match" in v.note or "stale" in v.note


def test_verify_rejects_fixture_without_provenance(tmp_path):
    path = tmp_path / "no_prov.json"
    wb.WordBoxFixture(boxes=[_box(1, 1, 2, 2)], checked=True).freeze(str(path))  # no sha
    v = wb.verify_form_fill(_NOTICE, frozen_path=str(path))
    assert v.render_checked is False
    assert "provenance" in v.note


def test_verify_rejects_unfaithful_fixture(tmp_path):
    path = tmp_path / "unfaithful.json"
    wb.WordBoxFixture(
        boxes=[_box(1, 1, 2, 2)], checked=False, source_sha256="x"
    ).freeze(str(path))
    v = wb.verify_form_fill(_NOTICE, frozen_path=str(path))
    assert v.render_checked is False
    assert "faithful" in v.note


def test_verify_degrades_on_corrupt_fixture_not_crash(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json")
    v = wb.verify_form_fill(_NOTICE, frozen_path=str(path))  # must not raise
    assert v.render_checked is False
    assert "unreadable" in v.note


class _UnavailableOracle:
    def available(self):
        return False

    def render_pdf(self, hwpx_path, out_pdf=None):  # pragma: no cover
        return None


def test_verify_degrades_without_oracle_or_fixture():
    v = wb.verify_form_fill("anything.hwpx", oracle=_UnavailableOracle())
    assert v.render_checked is False and v.ok is False
    assert "unverified" in v.note


def test_string_checked_field_loads_fail_closed(tmp_path):
    # bool("false") is True in Python; a STRING checked must not pass as faithful.
    path = tmp_path / "strbool.json"
    path.write_text(json.dumps({"version": 1, "checked": "false", "sourceSha256": "x" * 64, "boxes": []}))
    assert wb.WordBoxFixture.load(str(path)).checked is False


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_unparseable_render_degrades_not_crash(tmp_path):
    # A Hancom export that exists + is non-empty but is not parseable (truncated /
    # interrupted / non-PDF) must degrade to unverified, never crash the fill path.
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7 this is not actually a valid pdf body")
    src = tmp_path / "a.hwpx"
    src.write_bytes(b"hwpx bytes")

    class _TruncOracle:
        def available(self):
            return True

        def render_pdf(self, hwpx_path, out_pdf=None):
            return str(bad)

    v = wb.verify_form_fill(str(src), oracle=_TruncOracle())  # must not raise
    assert v.render_checked is False and v.ok is False
    assert "unverified" in v.note


def test_directory_hwpx_path_degrades_not_crash(tmp_path):
    # HWPX is a ZIP often unpacked to a like-named DIRECTORY; sha256_file must not
    # crash the fill path on it (os.path.exists is True for a dir).
    as_dir = tmp_path / "doc.hwpx"
    as_dir.mkdir()
    v = wb.verify_form_fill(str(as_dir), frozen_path=_NOTICE_FIXTURE)  # must not raise
    assert v.render_checked is False
    assert "unreadable" in v.note or "match" in v.note


def test_oracle_invocation_failure_degrades_not_crash():
    class _RaisingOracle:
        def available(self):
            return True

        def render_pdf(self, hwpx_path, out_pdf=None):
            raise RuntimeError("AppleScript/COM blew up")

    v = wb.verify_form_fill("anything.hwpx", oracle=_RaisingOracle())  # must not raise
    assert v.render_checked is False and v.ok is False
    assert "render backend failed" in v.note


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_freeze_to_bad_dir_does_not_sink_faithful_verdict(tmp_path):
    import fitz

    rendered = tmp_path / "r.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=200).insert_text((40, 80), "OK", fontsize=12)
    doc.save(str(rendered))
    doc.close()
    src = tmp_path / "s.hwpx"
    src.write_bytes(b"x")

    class _StubOracle:
        def available(self):
            return True

        def render_pdf(self, hwpx_path, out_pdf=None):
            return str(rendered)

    bad_freeze = tmp_path / "missing_dir" / "frozen.json"  # parent does not exist
    v = wb.verify_form_fill(str(src), oracle=_StubOracle(), freeze_to=str(bad_freeze))
    assert v.render_checked is True  # persistence failure must not sink the verdict
    assert not bad_freeze.exists()


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_freeze_to_with_nul_byte_does_not_sink_verdict(tmp_path):
    import fitz

    rendered = tmp_path / "r.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=200).insert_text((40, 80), "OK", fontsize=12)
    doc.save(str(rendered))
    doc.close()
    src = tmp_path / "s.hwpx"
    src.write_bytes(b"x")

    class _StubOracle:
        def available(self):
            return True

        def render_pdf(self, hwpx_path, out_pdf=None):
            return str(rendered)

    # NUL in the path raises ValueError (not OSError) deep in mkstemp/os.replace.
    v = wb.verify_form_fill(str(src), oracle=_StubOracle(), freeze_to="fo\x00o.json")
    assert v.render_checked is True  # best-effort persistence must not sink it


def test_non_rect_clip_is_tolerated_not_crash():
    # clips is typed Sequence[Rect]; a caller passing a bare tuple/None must not
    # crash the verdict (fail-closed, never raise on the fill path).
    boxes = [_box(5, 5, 95, 15)]
    v = wb.verdict_from_boxes(boxes, [(0, 0, 100, 20), None], render_checked=True)
    assert isinstance(v, wb.FormFillVerdict)  # no AttributeError


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_zero_page_render_degrades_not_silent_pass(tmp_path):
    # A 0-page render is a failed render, not a clean pass. Hand-crafted because
    # fitz refuses to *save* a 0-page doc. Whether fitz opens it (-> empty-page
    # guard) or rejects it (-> catch-all), the verdict must not be render_checked.
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    src = tmp_path / "z.hwpx"
    src.write_bytes(b"x")

    class _EmptyOracle:
        def available(self):
            return True

        def render_pdf(self, hwpx_path, out_pdf=None):
            return str(empty)

    v = wb.verify_form_fill(str(src), oracle=_EmptyOracle())  # must not raise
    assert v.render_checked is False  # a 0-page render is not a clean pass
    assert v.ok is False


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_encrypted_render_degrades_not_crash(tmp_path):
    import fitz

    enc = tmp_path / "enc.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=200).insert_text((50, 80), "secret", fontsize=12)
    doc.save(str(enc), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()
    src = tmp_path / "b.hwpx"
    src.write_bytes(b"hwpx")

    class _EncOracle:
        def available(self):
            return True

        def render_pdf(self, hwpx_path, out_pdf=None):
            return str(enc)

    v = wb.verify_form_fill(str(src), oracle=_EncOracle())  # must not raise
    assert v.render_checked is False and v.ok is False


# --- real fitz extraction (no Hancom) --------------------------------------

@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_extract_word_boxes_from_synthetic_pdf(tmp_path):
    import fitz

    pdf = tmp_path / "synthetic.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((50, 100), "Hello world", fontsize=12)
    doc.save(str(pdf))
    doc.close()
    boxes = wb.extract_word_boxes(str(pdf))
    texts = [b.text for b in boxes]
    assert "Hello" in texts and "world" in texts


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_extract_glyph_boxes_and_detect_real_overlap(tmp_path):
    import fitz

    pdf = tmp_path / "stacked.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    # Two distinct wide glyphs whose boxes overlap -> a real visual collision.
    page.insert_text((50, 100), "M", fontsize=40)  # wide, spans well past 70
    page.insert_text((70, 100), "W", fontsize=40)  # starts inside M's box
    doc.save(str(pdf))
    doc.close()
    glyphs = wb.extract_glyph_boxes(str(pdf))
    assert len(glyphs) >= 2  # per-glyph, not per-word
    assert wb.detect_overlaps(glyphs)  # the overlap is detected


def test_extract_degrades_when_fitz_absent(monkeypatch):
    monkeypatch.setattr(wb, "fitz_available", lambda: False)
    with pytest.raises(wb.OracleUnavailable):
        wb.extract_glyph_boxes("/nonexistent.pdf")


def test_extract_image_boxes_degrades_when_fitz_absent(monkeypatch):
    monkeypatch.setattr(wb, "fitz_available", lambda: False)
    with pytest.raises(wb.OracleUnavailable):
        wb.extract_image_boxes("/nonexistent.pdf")


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_extract_image_boxes_unreadable_pdf_degrades(tmp_path):
    bad = tmp_path / "not.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(wb.OracleUnavailable):
        wb.extract_image_boxes(str(bad))


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_extract_image_boxes_page_analysis_failure_skips_not_crashes(tmp_path, monkeypatch):
    # a page whose image analysis raises contributes no boxes rather than crashing
    import fitz

    rendered = tmp_path / "img.pdf"
    doc = fitz.open()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8))
    pix.clear_with(128)
    doc.new_page(width=200, height=200).insert_image(fitz.Rect(10, 10, 50, 50), pixmap=pix)
    doc.save(str(rendered))
    doc.close()

    def _boom(self, *a, **k):
        raise RuntimeError("layout analysis failed")

    monkeypatch.setattr(fitz.Page, "get_image_info", _boom)
    assert wb.extract_image_boxes(str(rendered)) == []  # degraded, no crash


# --- P2: cell-clip extraction + overflow verify ----------------------------

def _grid_pdf(path, *, overflow_text=False):
    """A bordered 2x2 table; optionally a cell value that escapes its border."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    # draw a 2x2 grid: verticals at x=50,200,350 ; horizontals at y=50,150,250
    for x in (50, 200, 350):
        page.draw_line((x, 50), (x, 250), color=(0, 0, 0), width=1)
    for y in (50, 150, 250):
        page.draw_line((50, y), (350, y), color=(0, 0, 0), width=1)
    page.insert_text((60, 100), "ok", fontsize=11)  # well inside top-left cell
    if overflow_text:
        # a long value in the top-right cell (x 200..350); at fontsize 16 it runs
        # well past the x=350 border so a glyph straddles it (center in, edge out)
        page.insert_text((210, 100), "OVERFLOWINGVALUE!!!", fontsize=16)
    doc.save(str(path))
    doc.close()


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_extract_cell_clips_finds_drawn_table(tmp_path):
    pdf = tmp_path / "grid.pdf"
    _grid_pdf(pdf)
    clips = wb.extract_cell_clips(str(pdf))
    assert clips, "find_tables should detect the bordered grid"
    assert all(isinstance(c, wb.Rect) for c in clips)


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_extract_cell_clips_graceful_on_no_table(tmp_path):
    import fitz

    pdf = tmp_path / "plain.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=200).insert_text((50, 80), "no table here", fontsize=12)
    doc.save(str(pdf))
    doc.close()
    assert wb.extract_cell_clips(str(pdf)) == []  # no crash, no phantom cells


def test_verify_form_overflow_degrades_without_oracle():
    v = wb.verify_form_overflow("x.hwpx", oracle=_UnavailableOracle())
    assert v.render_checked is False and v.ok is False


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_verify_form_overflow_no_table_is_honest(tmp_path):
    import fitz

    pdf = tmp_path / "plain.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=200).insert_text((50, 80), "free text", fontsize=12)
    doc.save(str(pdf))
    doc.close()

    class _O:
        def available(self):
            return True

        def render_pdf(self, h, out_pdf=None):
            return str(pdf)

    v = wb.verify_form_overflow("x.hwpx", oracle=_O())
    assert v.render_checked is True
    assert v.overflow_checked is False  # no cells -> overflow not evaluated, not "clean"
    assert "not evaluated" in v.note


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_verify_form_overflow_clean_vs_escape(tmp_path):
    clean = tmp_path / "clean.pdf"
    escape = tmp_path / "escape.pdf"
    _grid_pdf(clean, overflow_text=False)
    _grid_pdf(escape, overflow_text=True)

    def _oracle_for(p):
        class _O:
            def available(self):
                return True

            def render_pdf(self, h, out_pdf=None):
                return str(p)

        return _O()

    vc = wb.verify_form_overflow("x.hwpx", oracle=_oracle_for(clean))
    ve = wb.verify_form_overflow("x.hwpx", oracle=_oracle_for(escape))
    # clean grid: text stays inside cells
    assert vc.render_checked and vc.overflow_checked and not vc.overflow_detected
    # escaped value: at least one glyph runs past its cell border
    assert ve.overflow_detected and not ve.ok


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_extract_out_of_range_page_degrades_not_crash(tmp_path):
    import fitz

    pdf = tmp_path / "one.pdf"
    doc = fitz.open()
    doc.new_page(width=200, height=200)
    doc.save(str(pdf))
    doc.close()
    with pytest.raises(wb.OracleUnavailable):  # not a raw IndexError
        wb.extract_glyph_boxes(str(pdf), page=5)


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_verify_renders_and_freezes_via_stub_oracle(tmp_path):
    import fitz

    rendered = tmp_path / "rendered.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((40, 80), "FILLED OK", fontsize=12)
    doc.save(str(rendered))
    doc.close()
    src = tmp_path / "src.hwpx"
    src.write_bytes(b"fake hwpx bytes for hashing")

    class _StubOracle:
        def available(self):
            return True

        def render_pdf(self, hwpx_path, out_pdf=None):
            return str(rendered)

    frozen = tmp_path / "frozen.json"
    v = wb.verify_form_fill(str(src), oracle=_StubOracle(), freeze_to=str(frozen))
    assert v.render_checked is True
    reloaded = wb.WordBoxFixture.load(str(frozen))
    assert reloaded.checked is True
    assert reloaded.source_sha256 == wb.sha256_file(str(src))  # provenance bound
    assert reloaded.backend == "_StubOracle"
    assert reloaded.boxes  # per-glyph capture produced boxes


# --- P2: layout stability (differential blank-render vs filled-render) -------

def _layout_pdf(path, *, pages=1, rows=2, cols=2):
    """N-page PDF; each page draws one bordered rows×cols grid with text per cell.

    ``find_tables`` needs cell text to detect the table (measured), so every cell
    carries a token.
    """
    import fitz

    cw, ch = 110.0, 36.0
    x0, y0 = 40.0, 40.0
    width = x0 * 2 + cols * cw
    height = y0 * 2 + rows * ch
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=width, height=height)
        xs = [x0 + i * cw for i in range(cols + 1)]
        ys = [y0 + j * ch for j in range(rows + 1)]
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[-1]), color=(0, 0, 0), width=1)
        for y in ys:
            page.draw_line((xs[0], y), (xs[-1], y), color=(0, 0, 0), width=1)
        for r in range(rows):
            for c in range(cols):
                page.insert_text((xs[c] + 6, ys[r] + 24), f"r{r}c{c}", fontsize=9)
    doc.save(str(path))
    doc.close()


def _stub_oracle(*, mapping=None, fixed=None):
    """Oracle stub whose ``render_pdf`` returns a pre-rendered PDF path.

    ``mapping``: hwpx_path -> pdf path (distinct blank/filled renders).
    ``fixed``: one pdf returned for any input.
    """

    class _O:
        def available(self):
            return True

        def render_pdf(self, hwpx_path, out_pdf=None):
            if mapping is not None:
                return str(mapping[hwpx_path])
            return str(fixed)

    return _O()


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_layout_signature_captures_pages_and_tables(tmp_path):
    pdf = tmp_path / "two.pdf"
    _layout_pdf(pdf, pages=2, rows=3, cols=2)
    sig = wb.extract_layout_signature(str(pdf))
    assert sig.page_count == 2
    assert sig.table_shapes  # at least one table detected
    assert all(r > 0 and c > 0 for r, c in sig.table_shapes)


def test_diff_layout_identical_is_stable():
    sig = wb.LayoutSignature(page_count=2, table_shapes=((3, 2), (3, 2)))
    diff = wb.diff_layout(sig, sig)
    assert diff.stable and diff.page_count_stable and diff.table_shapes_stable
    assert diff.reasons == ()


def test_diff_layout_page_growth_is_unstable():
    blank = wb.LayoutSignature(page_count=1, table_shapes=((3, 2),))
    filled = wb.LayoutSignature(page_count=2, table_shapes=((3, 2),))
    diff = wb.diff_layout(blank, filled)
    assert not diff.stable and not diff.page_count_stable
    assert any("page count" in r for r in diff.reasons)


def test_diff_layout_row_growth_is_unstable():
    blank = wb.LayoutSignature(page_count=1, table_shapes=((3, 2),))
    filled = wb.LayoutSignature(page_count=1, table_shapes=((4, 2),))  # a row split/grew
    diff = wb.diff_layout(blank, filled)
    assert diff.page_count_stable and not diff.table_shapes_stable and not diff.stable
    assert any("table shapes" in r for r in diff.reasons)


def test_diff_layout_table_order_independent():
    blank = wb.LayoutSignature(page_count=1, table_shapes=((3, 2), (5, 4)))
    filled = wb.LayoutSignature(page_count=1, table_shapes=((5, 4), (3, 2)))
    assert wb.diff_layout(blank, filled).stable  # multiset, not sequence


def test_diff_layout_table_shapes_advisory_when_not_required():
    blank = wb.LayoutSignature(page_count=1, table_shapes=((3, 2),))
    filled = wb.LayoutSignature(page_count=1, table_shapes=((4, 2),))
    diff = wb.diff_layout(blank, filled, require_table_shapes=False)
    assert diff.stable  # page count is the only gate when table shapes are advisory
    assert not diff.table_shapes_stable  # still computed + reported honestly
    assert any("table shapes" in r for r in diff.reasons)


def test_extract_layout_signature_degrades_when_fitz_absent(monkeypatch):
    monkeypatch.setattr(wb, "fitz_available", lambda: False)
    with pytest.raises(wb.OracleUnavailable):
        wb.extract_layout_signature("/nonexistent.pdf")


def test_extract_layout_signature_uses_borders_only_strategy(monkeypatch):
    """The structural fingerprint must detect tables from drawn borders only.

    S-094 P3: the ``find_tables`` default (``"lines"``) snaps table edges to text
    positions, so injecting a fill value into an empty cell invents phantom tables
    and flips the "table-shape" signal even when the drawn grid is unchanged. The
    fingerprint pins ``strategy="lines_strict"`` so it stays text-independent —
    this test fails closed if a future edit drops back to the content-sensitive
    default.
    """

    import sys
    import types

    seen: list[str] = []

    class _Tables:
        tables = ()  # no tables; we only care which strategy was requested

    class _Page:
        rect = types.SimpleNamespace(width=100.0, height=100.0)

        def find_tables(self, *, strategy="lines"):
            seen.append(strategy)
            return _Tables()

    class _Doc:
        def __iter__(self):
            return iter([_Page()])

        def __len__(self):
            return 1

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    stub = types.ModuleType("fitz")
    stub.open = lambda _path: _Doc()
    monkeypatch.setitem(sys.modules, "fitz", stub)
    monkeypatch.setattr(wb, "fitz_available", lambda: True)

    wb.extract_layout_signature("/whatever.pdf")
    assert seen == ["lines_strict"]


def test_verify_layout_stability_degrades_without_baseline():
    # neither blank_hwpx nor blank_signature -> honest unverified before any render
    v = wb.verify_form_layout_stability("filled.hwpx")
    assert v.render_checked is False and v.ok is False
    assert "no blank baseline" in v.note


def test_verify_layout_stability_degrades_when_render_fails():
    v = wb.verify_form_layout_stability(
        "filled.hwpx",
        blank_signature=wb.LayoutSignature(page_count=1),
        oracle=_UnavailableOracle(),
    )
    assert v.render_checked is False and "unverified" in v.note


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_render_form_layout_returns_signature(tmp_path):
    pdf = tmp_path / "f.pdf"
    _layout_pdf(pdf, pages=1, rows=2, cols=2)
    glyphs, clips, sig, backend = wb.render_form_layout(
        "x.hwpx", oracle=_stub_oracle(fixed=pdf)
    )
    assert sig.page_count == 1 and sig.table_shapes
    assert clips  # the grid is detected as overflow clips too
    assert backend == "_O"


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_verify_layout_stability_stable_via_stub_oracle(tmp_path):
    blank_pdf = tmp_path / "blank.pdf"
    filled_pdf = tmp_path / "filled.pdf"
    _layout_pdf(blank_pdf, pages=1, rows=3, cols=2)
    _layout_pdf(filled_pdf, pages=1, rows=3, cols=2)  # same structure, fill stayed put
    oracle = _stub_oracle(mapping={"blank.hwpx": blank_pdf, "filled.hwpx": filled_pdf})
    v = wb.verify_form_layout_stability("filled.hwpx", blank_hwpx="blank.hwpx", oracle=oracle)
    assert v.render_checked and v.layout_stable is True
    assert not v.overflow_detected and v.ok


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_verify_layout_stability_detects_page_growth(tmp_path):
    blank_pdf = tmp_path / "blank.pdf"
    filled_pdf = tmp_path / "filled.pdf"
    _layout_pdf(blank_pdf, pages=1, rows=3, cols=2)
    _layout_pdf(filled_pdf, pages=2, rows=3, cols=2)  # the fill spilled onto a 2nd page
    oracle = _stub_oracle(mapping={"b.hwpx": blank_pdf, "f.hwpx": filled_pdf})
    v = wb.verify_form_layout_stability("f.hwpx", blank_hwpx="b.hwpx", oracle=oracle)
    assert v.render_checked and v.layout_stable is False and not v.ok
    assert "layout unstable" in v.note and "page count" in v.note


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_verify_layout_stability_with_precomputed_blank_signature(tmp_path):
    # template-once: the blank baseline is a frozen signature; only the filled renders
    filled_pdf = tmp_path / "filled.pdf"
    _layout_pdf(filled_pdf, pages=1, rows=3, cols=2)
    baseline = wb.extract_layout_signature(str(filled_pdf))  # the template's shape
    v = wb.verify_form_layout_stability(
        "f.hwpx", blank_signature=baseline, oracle=_stub_oracle(fixed=filled_pdf)
    )
    assert v.render_checked and v.layout_stable is True


# --- P2: differential overflow (filled escapes minus blank baseline) ---------

def _clip():
    return wb.Rect(50.0, 5.0, 110.0, 30.0, label="c0", page=0)


def _esc(text, page=0):
    # center 107.5 inside the clip, but x1=115 escapes the 110 right edge by 5pt
    return wb.WordBox(x0=100.0, y0=10.0, x1=115.0, y1=20.0, text=text, page=page)


def _inside(text, page=0):
    return wb.WordBox(x0=60.0, y0=10.0, x1=75.0, y1=20.0, text=text, page=page)


def test_diff_overflow_cancels_baseline_escape():
    # the same marginal find_tables-noise escape in BOTH renders cancels (the 171 lesson)
    clips = [_clip()]
    blank = [_esc("가")]
    filled = [_esc("가")]
    assert wb.detect_overflow(blank, clips, tol=1.0)             # absolute would flag it
    assert wb.diff_overflow(blank, clips, filled, clips, tol=1.0) == []


def test_diff_overflow_flags_new_escape():
    clips = [_clip()]
    blank = [_inside("가")]   # fits in blank
    filled = [_esc("가")]     # the fill pushed it out of the cell
    assert len(wb.diff_overflow(blank, clips, filled, clips, tol=1.0)) == 1


def test_diff_overflow_count_aware():
    clips = [_clip()]
    blank = [_esc("가")]                 # one baseline escape
    filled = [_esc("가"), _esc("가")]    # two -> exactly one is new
    assert len(wb.diff_overflow(blank, clips, filled, clips, tol=1.0)) == 1


def test_diff_overflow_clean_has_none():
    clips = [_clip()]
    assert wb.diff_overflow([_inside("가")], clips, [_inside("가")], clips, tol=1.0) == []


# --- P2: differential overlap (filled-render collisions minus blank baseline) -

def _ov(x, y, text="x", page=0, size=5.0):
    """A small square glyph box centered near (x, y)."""
    return wb.WordBox(x0=x, y0=y, x1=x + size, y1=y + size, text=text, page=page)


def test_diff_overlaps_cancels_identical_baseline():
    # one collision at the same spot in BOTH renders -> nothing new
    blank = [_ov(10, 10, "글"), _ov(12, 10, "겹")]
    filled = [_ov(10, 10, "글"), _ov(12, 10, "겹")]
    assert wb.detect_overlaps(blank)  # the baseline collision is real
    assert wb.diff_overlaps(blank, filled) == []


def test_diff_overlaps_flags_new_collision():
    blank = [_ov(10, 10, "글"), _ov(12, 10, "겹")]              # baseline only
    filled = [
        _ov(10, 10, "글"), _ov(12, 10, "겹"),                   # same baseline
        _ov(50, 50, "新"), _ov(52, 50, "規"),                   # NEW collision
    ]
    new = wb.diff_overlaps(blank, filled)
    assert len(new) == 1
    assert {new[0][0].text, new[0][1].text} == {"新", "規"}


def test_diff_overlaps_tolerates_subpixel_jitter():
    # the whole baseline collision shifts < tol between renders -> still cancels
    blank = [_ov(10.0, 10.0, "글"), _ov(12.0, 10.0, "겹")]
    filled = [_ov(10.4, 10.3, "글"), _ov(12.4, 10.3, "겹")]
    assert wb.diff_overlaps(blank, filled) == []


def test_diff_overlaps_cancels_moved_baseline_by_identity():
    # adversarial finding #4/#5: a benign baseline over-print that merely TRANSLATES
    # (an in-page reflow diff_layout cannot see) must still cancel by identity, not
    # resurface as a false "new" overlap. Position-keyed cancellation flooded here.
    blank = [_ov(10, 10, "글"), _ov(12, 10, "겹")]
    filled = [_ov(40, 40, "글"), _ov(42, 40, "겹")]  # same identity, shifted far
    assert wb.diff_overlaps(blank, filled) == []


def test_diff_overlaps_count_aware_flags_extra_occurrence():
    # one (글,겹) over-print in blank, TWO in filled -> exactly one is new
    blank = [_ov(10, 10, "글"), _ov(12, 10, "겹")]
    filled = [_ov(10, 10, "글"), _ov(12, 10, "겹"), _ov(60, 60, "글"), _ov(62, 60, "겹")]
    assert len(wb.diff_overlaps(blank, filled)) == 1


def test_diff_overlaps_catches_tiny_glyph_over_wide_glyph():
    # adversarial finding #2: a narrow glyph fully inside a wide one (period crammed
    # onto a CJK label) is the textbook 글자겹침; the area-fraction gate scores it
    # 1.0 where the old min(width) center gate missed it.
    wide = wb.WordBox(x0=100, y0=100, x1=120, y1=120, text="한")        # 20x20
    period = wb.WordBox(x0=114, y0=108, x1=117, y1=112, text=".")        # fully inside, off-center
    assert wb._overprint_fraction(wide, period) >= 0.9
    assert len(wb.diff_overlaps([wide], [wide, period])) == 1


def test_diff_overlaps_excludes_vertical_flow_edge_touch():
    # adversarial finding #6: vertically-adjacent CJK glyphs touch edge-to-edge
    # (same column, one glyph-height apart) — normal vertical flow, NOT an over-print.
    top = wb.WordBox(x0=100, y0=100, x1=114, y1=114, text="국")
    bottom = wb.WordBox(x0=100, y0=113, x1=114, y1=127, text="주")  # ~1pt y-overlap
    assert wb._overprint_fraction(top, bottom) < wb._OVERLAP_AREA_FRAC
    assert wb.diff_overlaps([], [top, bottom]) == []


def test_diff_overlaps_empty_blank_flags_all():
    filled = [_ov(10, 10, "글"), _ov(12, 10, "겹")]
    assert len(wb.diff_overlaps([], filled)) == 1


def test_diff_overlaps_ignores_jittering_adjacent_flow():
    # The calibration lesson (522 false positives): normal adjacent CJK flow —
    # centers ~one glyph-width apart — collides rawly but is NOT 겹침, and it shifts
    # position between renders. The stack gate must drop it so the differential does
    # not drown. A whole row shifted past `tol` must still yield zero new overlaps.
    def row(x0):
        return [
            wb.WordBox(x0=x0 + i * 6, y0=10, x1=x0 + i * 6 + 8, y1=18, text=t, page=0)
            for i, t in enumerate("가나다라")
        ]

    blank = row(10)
    filled = row(25)  # whole row shifted +15pt, still pure adjacent flow
    assert wb.detect_overlaps(blank)              # adjacent boxes DO collide rawly
    assert wb.diff_overlaps(blank, filled) == []  # ...but the over-print area gate drops them


def test_diff_overlaps_is_page_isolated():
    blank = [_ov(10, 10, "글", page=0), _ov(12, 10, "겹", page=0)]
    filled = [_ov(10, 10, "글", page=1), _ov(12, 10, "겹", page=1)]  # same coords, page 1
    # a collision on page 1 is NOT cancelled by an identical one on page 0
    assert len(wb.diff_overlaps(blank, filled)) == 1


def _overlap_pdf(path, *, extra=False):
    """PDF with a baseline glyph collision; optionally a second 'new' one.

    Uses wide Latin glyphs (fitz's built-in font has no CJK, so 한글 would render
    as a single substitute glyph and never collide).
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    # baseline collision (present in BOTH renders): two glyphs OVER-PRINTED (centers
    # nearly coincident) so it reads as a stack, not normal adjacent flow.
    page.insert_text((50, 100), "M", fontsize=40)
    page.insert_text((53, 100), "W", fontsize=40)  # ~on top of M -> stacked
    if extra:
        # a second, NEW stacked collision far enough away to be a distinct location
        page.insert_text((50, 300), "M", fontsize=40)
        page.insert_text((53, 300), "W", fontsize=40)
    doc.save(str(path))
    doc.close()


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_verify_differential_flags_only_new_overlap(tmp_path):
    blank_pdf = tmp_path / "b.pdf"
    filled_pdf = tmp_path / "f.pdf"
    _overlap_pdf(blank_pdf, extra=False)
    _overlap_pdf(filled_pdf, extra=True)
    oracle = _stub_oracle(mapping={"b.hwpx": blank_pdf, "f.hwpx": filled_pdf})
    v = wb.verify_form_fill_differential("b.hwpx", "f.hwpx", oracle=oracle)
    assert v.render_checked is True
    assert v.overlap_detected is True and not v.ok
    assert len(v.overlap) >= 1
    assert "new glyph overlap" in v.note


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_verify_differential_clean_has_no_new_overlap(tmp_path):
    blank_pdf = tmp_path / "b.pdf"
    filled_pdf = tmp_path / "f.pdf"
    _overlap_pdf(blank_pdf, extra=False)
    _overlap_pdf(filled_pdf, extra=False)  # identical baseline, no new collision
    oracle = _stub_oracle(mapping={"b.hwpx": blank_pdf, "f.hwpx": filled_pdf})
    v = wb.verify_form_fill_differential("b.hwpx", "f.hwpx", oracle=oracle)
    assert v.render_checked is True
    assert v.overlap_detected is False  # the baseline collision cancels


def test_verify_differential_degrades_on_render_fail():
    v = wb.verify_form_fill_differential("b.hwpx", "f.hwpx", oracle=_UnavailableOracle())
    assert v.render_checked is False and "unverified" in v.note


@pytest.mark.skipif(not wb.fitz_available(), reason="PyMuPDF (fitz) not installed")
def test_extract_image_boxes_returns_image_rects(tmp_path):
    """An embedded image (e.g. a placed 직인) is found by its rendered rect — the
    seal is a picture, not a glyph, so ``get_text`` would never surface it."""
    import fitz

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8))
    pix.clear_with(128)
    rendered = tmp_path / "img.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=400)
    page.insert_image(fitz.Rect(50, 100, 130, 180), pixmap=pix)  # an 80x80 box
    doc.save(str(rendered))
    doc.close()

    boxes = wb.extract_image_boxes(str(rendered))
    assert len(boxes) == 1
    box = boxes[0]
    assert box.page == 0
    assert abs(box.x0 - 50) < 1.0 and abs(box.y0 - 100) < 1.0
    assert abs(box.x1 - 130) < 1.0 and abs(box.y1 - 180) < 1.0


# --- P2: live Hancom oracle smoke (FR-002 — overflow-0 + layout-stable) ------

def _mac_form_oracle_ready() -> bool:
    try:
        from hwpx.visual.oracle import MacHancomOracle

        return MacHancomOracle().available() and wb.fitz_available()
    except Exception:
        return False


@pytest.mark.skipif(
    not (_mac_form_oracle_ready() and os.environ.get("HWPX_MAC_ORACLE_SMOKE")),
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the form-fill render smoke",
)
def test_mac_form_fill_overflow0_layout_stable_smoke(tmp_path):
    """A real Korean gov form, filled via ``form_fit``, opens Hancom-clean (FR-002).

    Layout-neutral same-length substitutions into the 담당 부서 contact block must
    leave the document intact: overflow 0, layout stable (page + table-shape count),
    oracle-verified. Calibrated 2026-06-25 on ``public_official_table`` — ``find_
    tables`` table-shapes are deterministic across the fill, so ``require_table_
    shapes=True`` does not false-trigger on a clean fill (blank/filled both render
    5 pages, shapes ((1,2),(3,4),(1,2)), 2904 glyphs).
    """

    from hwpx.document import HwpxDocument
    from hwpx.form_fit.policy import FitPolicy
    from hwpx.visual.oracle import MacHancomOracle

    blank = "tests/fixtures/m2_corpus/public_official_table.hwpx"
    doc = HwpxDocument.open(blank)
    tables = []
    for paragraph in doc.paragraphs:
        tables.extend(getattr(paragraph, "tables", []))
    contact = tables[4]  # the 담당 부서 / 책임자 block
    for row, col, value in [(0, 1, "행정안전부"), (0, 4, "홍길동"), (1, 4, "김영수"), (3, 4, "이지은")]:
        result = contact.set_cell_text(row, col, value, fit=FitPolicy.keep())
        assert result is not None and result.ok and not result.overflow_detected
    filled = tmp_path / "public_official_filled.hwpx"
    doc.save_to_path(str(filled))

    # one comprehensive verdict: overflow + layout-stability + differential overlap
    oracle = MacHancomOracle(timeout=120)
    verdict = wb.verify_form_fill_differential(blank, str(filled), oracle=oracle)

    assert verdict.render_checked is True
    assert verdict.layout_stable is True       # page + table-shape structure preserved
    assert verdict.overflow_checked is True    # table cells were detected
    assert verdict.overflow_detected is False  # overflow 0
    assert verdict.overlap_detected is False   # no NEW 글자겹침 (baseline cancelled)
    assert verdict.ok is True


@pytest.mark.skipif(
    not (_mac_form_oracle_ready() and os.environ.get("HWPX_MAC_ORACLE_SMOKE")),
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the 글자겹침 render smoke",
)
def test_mac_glyph_overprint_caught_smoke():
    """The positive case: a real Hancom-rendered 글자겹침 is caught (FR-002).

    ``slot_overprint.hwpx`` is the same 발신명의 line as ``slot_clean.hwpx`` with 자간
    compressed to −50 % — the canonical 방송신청서 failure where a value is crammed
    into a slot until consecutive glyphs over-print. The differential-overlap signal
    MUST flag it, and it is caught by NO other signal: the compressed text takes less
    width (no cell escape → overflow 0) and the page count is unchanged (layout
    stable). Complements ``…_overflow0_layout_stable_smoke`` (the clean negative).
    """

    from hwpx.visual.oracle import MacHancomOracle

    base = "tests/fixtures/glyph_overlap"
    oracle = MacHancomOracle(timeout=120)
    verdict = wb.verify_form_fill_differential(
        f"{base}/slot_clean.hwpx", f"{base}/slot_overprint.hwpx", oracle=oracle
    )

    assert verdict.render_checked is True
    assert verdict.overlap_detected is True    # the real 글자겹침 is detected
    assert verdict.overflow_detected is False  # compressed text never escapes a cell
    assert verdict.layout_stable is True       # same page/structure
    assert verdict.ok is False                 # ...so overlap is the sole failing signal
    assert verdict.overlap                     # colliding glyph pairs are reported
