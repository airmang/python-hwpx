# SPDX-License-Identifier: Apache-2.0
"""LayoutLint unit + gate tests (plan §2 Phase D).

Seeds the bad cases the lint must catch *without a renderer* — stale lineseg
cache, dirty/lineseg leak, gross cell overflow, malformed table — and asserts a
clean doc passes. Also pins the SavePipeline gating: strict blocks, transparent
ignores (so the rest of the suite is undisturbed).
"""
from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

from lxml import etree

from hwpx import HwpxDocument
from hwpx.layout import lint_layout
from hwpx.layout.lint import (
    FIELD_OVERFLOW,
    OVERFLOW_RISK,
    STALE_LINESEG_DETECTED,
    TABLE_STRUCTURE_INVALID,
)
from hwpx.quality import QualityPolicy, SavePipeline
from hwpx.quality.ledger import DirtyLayoutLedger, DirtyLayoutRange

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _bytes(doc: HwpxDocument) -> bytes:
    return doc.to_bytes()


def _section_name(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return next(n for n in z.namelist() if n.endswith("section0.xml"))


def _ln(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _inject_section0(data: bytes, mutate) -> bytes:
    """Rewrite section0.xml inside *data* after applying *mutate(root)*.

    Seeds a defect directly into the serialized bytes — the only honest way to
    test the lint, since the save path deliberately strips stale lineseg caches.
    """

    with zipfile.ZipFile(io.BytesIO(data)) as zin:
        entries = [(info, zin.read(info.filename)) for info in zin.infolist()]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for info, content in entries:
            if info.filename.endswith("section0.xml"):
                root = etree.fromstring(content)
                mutate(root)
                content = etree.tostring(
                    root, xml_declaration=True, encoding="UTF-8", standalone=True
                )
            zi = zipfile.ZipInfo(info.filename)
            zi.compress_type = (
                zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            )
            zout.writestr(zi, content)
    return out.getvalue()


def _first_paragraph(root) -> object:
    return next(el for el in root.iter() if _ln(el.tag) == "p")


# --------------------------------------------------------------------------- #
# Clean docs pass.
# --------------------------------------------------------------------------- #
def test_clean_document_passes():
    doc = HwpxDocument.new()
    doc.add_paragraph("정상적인 문단입니다.")
    table = doc.add_table(1, 2)
    table.set_cell_text(0, 0, "이름")
    table.set_cell_text(0, 1, "홍길동")
    report = lint_layout(_bytes(doc))
    assert report.ok, [str(f) for f in report.findings]


def test_clean_table_document_has_no_findings():
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    for r in range(2):
        for c in range(2):
            table.set_cell_text(r, c, "값")
    report = lint_layout(_bytes(doc))
    assert report.findings == []


# --------------------------------------------------------------------------- #
# 1: stale lineseg cache (textpos beyond text length).
# --------------------------------------------------------------------------- #
def _text_paragraph(root, text: str):
    """A plain text-only paragraph (so the validator actually measures it)."""

    for para in (el for el in root.iter() if _ln(el.tag) == "p"):
        ts = [t for t in para.iter() if _ln(t.tag) == "t"]
        if ts and "".join(t.text or "" for t in ts) == text:
            # Must contain only runs of plain text for the textpos check to run.
            if all(_ln(c.tag) in ("run", "lineSegArray", "linesegarray") for c in para):
                return para
    raise AssertionError(f"no plain-text paragraph for {text!r}")


def _add_lineseg(root, textpos: str, text: str = "짧은글") -> None:
    para = _text_paragraph(root, text)
    ns = para.tag.rsplit("}", 1)[0].lstrip("{")
    lsa = etree.SubElement(para, f"{{{ns}}}lineSegArray")
    etree.SubElement(lsa, f"{{{ns}}}lineSeg", {"textpos": textpos, "horzsize": "1000"})


def test_seeded_stale_lineseg_is_caught():
    doc = HwpxDocument.new()
    doc.add_paragraph("짧은글")  # 3 chars
    data = _inject_section0(_bytes(doc), lambda root: _add_lineseg(root, "999"))
    report = lint_layout(data)
    assert not report.ok
    assert any(f.code == STALE_LINESEG_DETECTED for f in report.errors)


def _add_measured_lineseg(root, text: str, seg_attrs: list[dict[str, str]]) -> None:
    """Attach a full-attribute cache (textpos/horzsize/textheight) to *text*'s paragraph."""

    para = _text_paragraph(root, text)
    ns = para.tag.rsplit("}", 1)[0].lstrip("{")
    lsa = etree.SubElement(para, f"{{{ns}}}lineSegArray")
    for attrs in seg_attrs:
        etree.SubElement(lsa, f"{{{ns}}}lineSeg", attrs)


_A4_LINE = {"horzsize": "42520", "textheight": "1000"}  # 10pt · 표준 본문 줄 폭


def test_grown_text_with_stale_single_line_cache_is_caught():
    """#85 방향: 텍스트가 캐시 줄 수 너머로 자랐는데 textpos는 전부 유효한 경우.

    범위 검사(textpos > len)는 이 방향을 못 본다 — 꼬리 폭 판정이 잡아야 한다.
    120 한글자 문단에 1줄짜리 캐시: 꼬리 폭 ~120em ≫ 줄 폭 42520×2.
    """

    text = "가" * 120
    doc = HwpxDocument.new()
    doc.add_paragraph(text)
    data = _inject_section0(
        _bytes(doc),
        lambda root: _add_measured_lineseg(root, text, [{"textpos": "0", **_A4_LINE}]),
    )
    report = lint_layout(data)
    assert not report.ok
    assert any(
        f.code == STALE_LINESEG_DETECTED and "lacks lines" in f.message
        for f in report.errors
    )


def test_valid_multiline_cache_tail_passes():
    """정상 다줄 캐시(한컴 저장 형태): 마지막 줄 이후 꼬리가 한 줄 안 → 침묵."""

    text = "가" * 120
    doc = HwpxDocument.new()
    doc.add_paragraph(text)
    segs = [
        {"textpos": "0", **_A4_LINE},
        {"textpos": "42", **_A4_LINE},
        {"textpos": "84", **_A4_LINE},
    ]
    data = _inject_section0(
        _bytes(doc), lambda root: _add_measured_lineseg(root, text, segs)
    )
    assert lint_layout(data).ok


def test_tracked_insert_prefix_artifact_replay():
    """#85 실물 재현 쌍: 수리 전 산출물은 FAIL, 현행(수리 후) 산출물은 PASS.

    현행 코드로 변경추적 삽입을 하면 편집 문단의 캐시가 제거된다(a22342c) —
    그 산출물이 PASS 쪽. FAIL 쪽은 같은 편집에 수리 전처럼 옛 1줄 캐시를
    바이트에 되붙여 재구성한다.
    """

    base = "시행문 본문 첫 문단"
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph(base, char_pr_id_ref="0")
    doc.tracking.insert(paragraph, " 추가로 붙는 안내 문구가 길게 이어진다 " + "안내" * 50, date="2026-08-19")

    fixed = doc.to_bytes()  # 수리 후: 캐시 없음
    assert lint_layout(fixed).ok

    edited_text = paragraph.text

    def reattach(root):  # 수리 전 재구성: 옛 1줄 캐시가 그대로 남았던 상태
        _add_measured_lineseg(root, edited_text, [{"textpos": "0", **_A4_LINE}])

    broken = _inject_section0(fixed, reattach)
    report = lint_layout(broken)
    assert not report.ok
    assert any(
        f.code == STALE_LINESEG_DETECTED and "lacks lines" in f.message
        for f in report.errors
    )


# --------------------------------------------------------------------------- #
# 2: dirty ↔ lineseg leak (ledger-gated).
# --------------------------------------------------------------------------- #
def test_dirty_paragraph_retaining_cache_is_a_leak():
    doc = HwpxDocument.new()
    doc.add_paragraph("내용")
    # A cache that is itself textpos-valid (so check 1 stays quiet) ...
    data = _inject_section0(_bytes(doc), lambda root: _add_lineseg(root, "0", "내용"))

    part = _section_name(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read(part))
    paras = [el for el in root.iter() if el.tag.endswith("}p")]
    index = next(
        i for i, p in enumerate(paras)
        if any((t.text or "") == "내용" for t in p.iter() if t.tag.endswith("}t"))
    )

    ledger = DirtyLayoutLedger()
    ledger.note(DirtyLayoutRange(part=part, start_paragraph=index, reason="text_replaced"))
    report = lint_layout(data, ledger=ledger)
    assert any(f.code == STALE_LINESEG_DETECTED and f.paragraph == index for f in report.errors)

    # Without a ledger the same bytes have nothing to check against → no leak finding.
    assert lint_layout(data).ok


# --------------------------------------------------------------------------- #
# 3: overflow risk (gross unbreakable token).
# --------------------------------------------------------------------------- #
def test_gross_cell_overflow_is_caught():
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    cell = table.cell(0, 0)
    cell.set_size(width=3000)  # ~3 Hangul wide
    # One unbreakable Latin token far wider than the cell.
    table.set_cell_text(0, 0, "WWWWWWWWWWWWWWWWWWWWWWWWWWWW")
    data = _bytes(doc)

    warn = lint_layout(data, overflow_policy="warn")
    assert any(f.code == OVERFLOW_RISK for f in warn.warnings)
    assert warn.ok  # warn-only never blocks

    hard = lint_layout(data, overflow_policy="fail")
    assert any(f.code == FIELD_OVERFLOW for f in hard.errors)
    assert not hard.ok


def test_vertical_balloon_long_hangul_is_warned_not_failed():
    # The headline FormFit defect: breakable Korean that needs far more lines than
    # the cell's height budgets for. Hancom grows the row (no open-unsafe defect),
    # so the lint WARNS (caught) but never hard-fails — never wronger than the oracle.
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    cell = table.cell(0, 0)
    cell.set_size(width=5000, height=3200)  # budgets ~2 lines
    table.set_cell_text(0, 0, "가" * 40)
    report = lint_layout(_bytes(doc), overflow_policy="fail")
    assert report.ok  # vertical balloon is a warning, not a hard error
    assert any(
        f.code == OVERFLOW_RISK and (f.detail or {}).get("kind") == "vertical"
        for f in report.warnings
    )


def test_wrapping_korean_value_is_not_flagged_as_overflow():
    # Long but space/Hangul-breakable content wraps fine — must NOT be flagged
    # (would contradict the oracle, which lets Hancom grow the row).
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    cell = table.cell(0, 0)
    cell.set_size(width=6000)
    table.set_cell_text(0, 0, "서울특별시 강남구 테헤란로 백오십이 번지")
    report = lint_layout(_bytes(doc), overflow_policy="fail")
    assert not any(f.code in (FIELD_OVERFLOW, OVERFLOW_RISK) for f in report.findings)


def test_email_url_path_in_a_cell_do_not_hard_fail():
    # Hancom wraps at in-word punctuation (/ \ - . @ : _), so these are NOT
    # unbreakable tokens. A hard FIELD_OVERFLOW here would contradict the oracle.
    for value in [
        "hong.gildong.teacher2026@school.busan.kr",
        "https://www.busanedu.net/board/notice/2026/ai-classroom/view?id=12345",
        "NVIDIA-RTX-A6000-48GB-GPU-Server-Workstation",
    ]:
        doc = HwpxDocument.new()
        table = doc.add_table(1, 1)
        table.cell(0, 0).set_size(width=10000)
        table.set_cell_text(0, 0, value)
        report = lint_layout(_bytes(doc), overflow_policy="fail")
        assert not any(f.code == FIELD_OVERFLOW for f in report.errors), value


def test_short_token_tiny_sliver_overflow_warns_not_fails():
    # A short ordinary word whose absolute spill is a sliver Hancom absorbs must
    # stay a warning under overflow=fail, not a hard error (measurement honesty).
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).set_size(width=2500)
    table.set_cell_text(0, 0, "Windows")
    report = lint_layout(_bytes(doc), overflow_policy="fail")
    assert report.ok  # not a hard error
    assert any(f.code == OVERFLOW_RISK for f in report.warnings)


def test_genuinely_unbreakable_run_still_hard_fails():
    # The real overflow check must survive the punctuation/floor fixes: a long
    # pure-letter run with a large absolute spill is still a hard error.
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).set_size(width=3000)
    table.set_cell_text(0, 0, "W" * 30)
    report = lint_layout(_bytes(doc), overflow_policy="fail")
    assert any(f.code == FIELD_OVERFLOW for f in report.errors)


def _add_empty_field(doc: HwpxDocument, name: str) -> None:
    paragraph = doc.add_paragraph("", include_run=False)
    p = paragraph.element
    begin = p.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    p.append(begin)
    ctrl = begin.makeelement(f"{HP}ctrl", {"type": "FORM", "id": "c"})
    begin.append(ctrl)
    fb = ctrl.makeelement(
        f"{HP}fieldBegin",
        {"id": "f", "fieldid": "f", "type": "ClickHere", "name": name, "prompt": name},
    )
    ctrl.append(fb)
    end = p.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    p.append(end)
    ec = end.makeelement(f"{HP}ctrl", {})
    end.append(ec)
    ec.append(ec.makeelement(f"{HP}fieldEnd", {"beginIDRef": "f", "fieldid": "f"}))
    paragraph.section.mark_dirty()


def test_required_field_empty_is_flagged_when_declared():
    doc = HwpxDocument.new()
    _add_empty_field(doc, name="주소")  # empty required slot
    data = _bytes(doc)
    # Declared required → error; not declared → silent.
    flagged = lint_layout(data, required_fields={"주소"})
    assert any(f.code == "REQUIRED_FIELD_MISSING" for f in flagged.errors)
    assert lint_layout(data).ok  # no required set → plain templates never trip


def test_dirty_index_convention_handles_body_paragraph_after_table():
    # Pin the flat-document-order convention: a body paragraph AFTER a table is
    # located by its flat index (cell paragraphs included), not its body position.
    doc = HwpxDocument.new()
    doc.add_paragraph("앞")
    doc.add_table(1, 1)
    doc.add_paragraph("뒤")
    data = _inject_section0(_bytes(doc), lambda root: _add_lineseg(root, "0", "뒤"))
    part = _section_name(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read(part))
    paras = [el for el in root.iter() if el.tag.endswith("}p")]
    flat_index = next(
        i for i, p in enumerate(paras)
        if any((t.text or "") == "뒤" for t in p.iter() if t.tag.endswith("}t"))
    )
    assert flat_index >= 3  # after body '앞' + the table's cell subList paragraph(s)

    ledger = DirtyLayoutLedger()
    ledger.note(DirtyLayoutRange(part=part, start_paragraph=flat_index, reason="text_replaced"))
    report = lint_layout(data, ledger=ledger)
    assert any(f.paragraph == flat_index for f in report.errors)


# --------------------------------------------------------------------------- #
# 4: table structural sanity.
# --------------------------------------------------------------------------- #
def _strip_cell_margin(root) -> None:
    cell = next(el for el in root.iter() if _ln(el.tag) == "tc")
    margin = next(c for c in cell if _ln(c.tag) == "cellMargin")
    cell.remove(margin)


def test_malformed_table_missing_required_child_is_caught():
    doc = HwpxDocument.new()
    doc.add_table(1, 1)
    data = _inject_section0(_bytes(doc), _strip_cell_margin)
    report = lint_layout(data)
    assert any(f.code == TABLE_STRUCTURE_INVALID for f in report.errors)


# --------------------------------------------------------------------------- #
# SavePipeline gating.
# --------------------------------------------------------------------------- #
def _stale_doc_bytes() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("짧은글")
    return _inject_section0(_bytes(doc), lambda root: _add_lineseg(root, "999"))


def _layout_only_policy() -> QualityPolicy:
    # Isolate the layout stage so its own code (not reference/open-safety) blocks.
    return QualityPolicy(
        render_check="off", require_visual_complete=False,
        require_reference_integrity=False, require_open_safety=False,
        layout_lint="strict",
    )


def test_pipeline_strict_blocks_seeded_stale(tmp_path):
    data = _stale_doc_bytes()
    out = tmp_path / "blocked.hwpx"
    report = SavePipeline().run(data, output_path=out, quality=_layout_only_policy())
    assert report.ok is False
    assert STALE_LINESEG_DETECTED in report.error_codes
    assert not out.exists()  # output withheld


def test_pipeline_strict_blocks_dirty_leak(tmp_path):
    # A textpos-valid cache on a paragraph the ledger marks dirty → leak (check 2),
    # driven end-to-end through the gate with a ledger.
    doc = HwpxDocument.new()
    doc.add_paragraph("내용")
    data = _inject_section0(_bytes(doc), lambda root: _add_lineseg(root, "0", "내용"))
    part = _section_name(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read(part))
    paras = [el for el in root.iter() if el.tag.endswith("}p")]
    index = next(
        i for i, p in enumerate(paras)
        if any((t.text or "") == "내용" for t in p.iter() if t.tag.endswith("}t"))
    )
    ledger = DirtyLayoutLedger()
    ledger.note(DirtyLayoutRange(part=part, start_paragraph=index, reason="text_replaced"))

    out = tmp_path / "leak.hwpx"
    report = SavePipeline().run(
        data, output_path=out, quality=_layout_only_policy(), ledger=ledger
    )
    assert report.ok is False
    assert STALE_LINESEG_DETECTED in report.error_codes
    assert not out.exists()

    # No ledger → nothing to check against → save proceeds.
    out2 = tmp_path / "noledger.hwpx"
    ok_report = SavePipeline().run(data, output_path=out2, quality=_layout_only_policy())
    assert ok_report.layout.ok is True


def test_pipeline_strict_blocks_malformed_table(tmp_path):
    doc = HwpxDocument.new()
    doc.add_table(1, 1)
    data = _inject_section0(_bytes(doc), _strip_cell_margin)
    out = tmp_path / "badtable.hwpx"
    report = SavePipeline().run(data, output_path=out, quality=_layout_only_policy())
    assert report.ok is False
    assert TABLE_STRUCTURE_INVALID in report.error_codes
    assert not out.exists()


def test_pipeline_strict_blocks_empty_required_field(tmp_path):
    doc = HwpxDocument.new()
    _add_empty_field(doc, name="주소")
    data = _bytes(doc)
    out = tmp_path / "missing.hwpx"
    report = SavePipeline().run(
        data, output_path=out, quality=_layout_only_policy(), required_fields={"주소"}
    )
    assert report.ok is False
    assert "REQUIRED_FIELD_MISSING" in report.error_codes
    assert not out.exists()


def test_pipeline_does_not_double_count_stale_across_stages():
    # Under the full strict default (reference + open-safety on), one stale defect
    # is owned by the reference/open-safety stages; the layout stage must not pile
    # a duplicate STALE_LINESEG_DETECTED onto the flat error list.
    data = _stale_doc_bytes()
    policy = QualityPolicy(render_check="off", require_visual_complete=False, layout_lint="strict")
    report = SavePipeline().run(data, quality=policy)
    assert report.ok is False
    assert report.error_codes.count(STALE_LINESEG_DETECTED) == 0  # owned elsewhere
    assert any("STALE_LINESEG" in e for e in report.layout.errors)  # still fully recorded


def _overflow_doc_bytes() -> bytes:
    """An otherwise open-safe doc whose only defect is a gross cell overflow
    (a lint-only signal — open-safety/reference validators do not measure it)."""

    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).set_size(width=3000)
    table.set_cell_text(0, 0, "WWWWWWWWWWWWWWWWWWWWWWWWWWWW")
    return _bytes(doc)


def test_pipeline_transparent_ignores_layout_lint(tmp_path):
    data = _overflow_doc_bytes()
    out = tmp_path / "written.hwpx"
    report = SavePipeline().run(
        data, output_path=out, quality=QualityPolicy.transparent()
    )
    # transparent => layout_lint off => the gross-overflow cell is not checked.
    assert report.ok is True
    assert report.layout.ok is True
    assert out.exists()


def test_pipeline_strict_blocks_gross_overflow(tmp_path):
    data = _overflow_doc_bytes()
    out = tmp_path / "blocked.hwpx"
    policy = QualityPolicy(
        render_check="off", require_visual_complete=False,
        require_reference_integrity=False, layout_lint="strict", overflow_policy="fail",
    )
    report = SavePipeline().run(data, output_path=out, quality=policy)
    assert report.ok is False
    assert FIELD_OVERFLOW in report.error_codes
    assert not out.exists()


def test_pipeline_warn_mode_surfaces_but_does_not_block(tmp_path):
    data = _stale_doc_bytes()
    out = tmp_path / "warned.hwpx"
    policy = QualityPolicy(
        render_check="off", require_visual_complete=False,
        require_reference_integrity=False, require_open_safety=False,
        layout_lint="warn",
    )
    report = SavePipeline().run(data, output_path=out, quality=policy)
    assert report.layout.ok is True  # warn never blocks
    assert any("STALE_LINESEG" in w for w in report.layout.warnings)
