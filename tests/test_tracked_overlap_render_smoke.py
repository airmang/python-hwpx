# SPDX-License-Identifier: Apache-2.0
"""변경추적 편집 경로의 실한컴 렌더 겹침 회귀 (opt-in 스모크).

#85 실물: 변경추적 삽입으로 문단이 자랐는데 옛 ``hp:linesegarray``가 남으면
한컴이 캐시 줄배치를 재사용해 글리프가 겹쳐 찍힌다. 이 스모크는 그 결함
쌍을 실한컴 렌더에서 상시 재검한다:

1. 현행 편집 경로 산출물(캐시 제거됨) → 렌더 → 글리프 겹침 0 근사.
2. 수리 전 재구성 산출물(옛 1줄 캐시 되붙임) → 렌더 → 겹침이 실측으로
   검출되어야 한다(검출기 자체의 민감도 증명 — 이게 없으면 1은 공허).

기본 스위트에서는 절대 돌지 않는다: ``HWPX_MAC_ORACLE_SMOKE=1`` + macOS +
한컴 설치 + GUI 자동화 권한이 전제(TOC 스모크와 동일 관례). 렌더 백엔드는
companion 계층에서 주입받는다 — core는 renderer-neutral이다.
"""
from __future__ import annotations

import io
import os
import zipfile

import pytest
from lxml import etree

from hwpx import HwpxDocument

pytestmark = pytest.mark.skipif(
    os.environ.get("HWPX_MAC_ORACLE_SMOKE") != "1",
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the overlap render smoke",
)

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_A4_LINE = {"textpos": "0", "vertpos": "0", "vertsize": "1000",
            "textheight": "1000", "baseline": "850", "spacing": "600",
            "horzpos": "0", "horzsize": "42520", "flags": "393216"}


def _build_pair() -> tuple[bytes, bytes]:
    """(수리 후 산출물, 수리 전 재구성 산출물) — 같은 변경추적 삽입."""

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("시행문 본문 첫 문단의 원래 내용이다", char_pr_id_ref="0")
    doc.tracking.insert(
        paragraph,
        " 여기에 변경추적으로 추가된 안내 문구가 길게 이어져 문단이 두 줄"
        " 세 줄로 자라나는 상황을 재현한다 " + "안내 문구 " * 12,
        date="2026-08-19",
    )
    fixed = doc.to_bytes()

    # 수리 전 재구성: 편집 문단에 옛 1줄 캐시를 바이트에 되붙인다.
    with zipfile.ZipFile(io.BytesIO(fixed)) as zin:
        entries = [(info, zin.read(info.filename)) for info in zin.infolist()]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        for info, content in entries:
            if info.filename.endswith("section0.xml"):
                root = etree.fromstring(content)
                para = next(
                    el for el in root.iter(f"{{{HP_NS}}}p")
                    if "시행문 본문" in "".join(el.itertext())
                )
                lsa = etree.SubElement(para, f"{{{HP_NS}}}linesegarray")
                etree.SubElement(lsa, f"{{{HP_NS}}}lineseg", _A4_LINE)
                content = etree.tostring(
                    root, xml_declaration=True, encoding="UTF-8", standalone=True
                )
            zi = zipfile.ZipInfo(info.filename)
            zi.compress_type = (
                zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            )
            zout.writestr(zi, content)
    return fixed, out.getvalue()


def _overlap_pairs(pdf_path: str) -> int:
    """서로 다른 줄의 글리프 박스가 실질 면적으로 겹치는 쌍의 수."""

    from hwpx_automation.office.form_fill.fit.wordbox import extract_glyph_boxes

    boxes = [b for b in extract_glyph_boxes(pdf_path) if b.text.strip()]
    count = 0
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a.line == b.line and a.block == b.block:
                continue  # 같은 줄 이웃 글리프의 미세 접촉은 겹침이 아니다
            ix = min(a.x1, b.x1) - max(a.x0, b.x0)
            iy = min(a.y1, b.y1) - max(a.y0, b.y0)
            if ix <= 0 or iy <= 0:
                continue
            inter = ix * iy
            smaller = min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0))
            if smaller > 0 and inter / smaller > 0.30:
                count += 1
    return count


def test_tracked_insert_render_has_no_glyph_overlap(tmp_path):
    from hwpx_automation.office.rendering.oracle import MacHancomOracle

    oracle = MacHancomOracle()
    assert oracle.available(), "Mac Hancom GUI oracle unreachable"
    fixed, broken = _build_pair()

    fixed_src = tmp_path / "fixed.hwpx"
    fixed_src.write_bytes(fixed)
    fixed_pdf = oracle.render_pdf(str(fixed_src), str(tmp_path / "fixed.pdf"))
    assert fixed_pdf, "수리 후 산출물 렌더 실패"
    fixed_overlaps = _overlap_pairs(fixed_pdf)

    broken_src = tmp_path / "broken.hwpx"
    broken_src.write_bytes(broken)
    broken_pdf = oracle.render_pdf(str(broken_src), str(tmp_path / "broken.pdf"))
    assert broken_pdf, "수리 전 재구성 산출물 렌더 실패"
    broken_overlaps = _overlap_pairs(broken_pdf)

    assert fixed_overlaps == 0, f"현행 산출물에서 글리프 겹침 {fixed_overlaps}쌍"
    assert broken_overlaps > 0, (
        "수리 전 재구성 산출물에서 겹침이 검출되지 않았다 — "
        "검출기 민감도 또는 재구성이 무효"
    )
