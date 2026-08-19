# SPDX-License-Identifier: Apache-2.0
"""변경추적 편집 경로의 실한컴 렌더 겹침 회귀 (opt-in 스모크).

#85 실물: 실한컴이 저장한 문서(문단에 진짜 ``hp:linesegarray`` 캐시가 실림)에
변경추적 삽입으로 텍스트를 늘렸는데 옛 캐시가 남으면, 한컴이 캐시 줄배치를
재사용해 글리프가 겹쳐 찍힌다. 수리(a22342c)는 편집 시점에 캐시를 제거한다.

이 스모크는 두 판정을 실한컴 렌더에서 상시 재검한다:

1. **민감도(양성 대조)**: 정본 겹침 픽스처 ``glyph_overlap/slot_overprint.hwpx``
   (자간 −50% 과밀 — 실측 ~23쌍 over-print)를 렌더해 검출기가 겹침을 실제로
   세는지 증명한다. 이게 없으면 2의 "겹침 0"은 공허하다.
2. **회귀**: seoul_sihaengmun gold(실캐시 보유)에 tracking.insert를 적용한
   현행 산출물(편집 문단 캐시 제거됨, a22342c)을 렌더해 글리프 겹침 0을
   단언한다.

정직 기록: 수리 전 바이트 재구성(편집 문단에 원본 캐시를 되붙인 산출물)은
이 세션의 한컴 빌드에서 겹침으로 렌더되지 **않았다** — 한컴이 문서 재배치를
택하는 조건은 세션/빌드 의존적이라 음성 대조로 부적합했다(a22342c 당시의
겹침 렌더는 그 커밋의 render-checked 기록이 증거). 그래서 민감도 증명은
결정적으로 겹치는 정본 양성 픽스처가 맡는다.

기본 스위트에서는 절대 돌지 않는다: ``HWPX_MAC_ORACLE_SMOKE=1`` + macOS +
한컴 + GUI 자동화 권한 + PyMuPDF(companion [oracle] extra) 전제 — TOC
스모크와 같은 관례. 렌더 백엔드·글리프 추출은 companion 계층에서 주입받는다.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hwpx import HwpxDocument

pytestmark = pytest.mark.skipif(
    os.environ.get("HWPX_MAC_ORACLE_SMOKE") != "1",
    reason="set HWPX_MAC_ORACLE_SMOKE=1 on macOS+Hancom to drive the overlap render smoke",
)

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "tests" / "fixtures" / "m3_gongmun_gold" / "seoul_sihaengmun.hwpx"
HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_INSERT_TEXT = (
    " 여기에 변경추적으로 추가된 안내 문구가 길게 이어져 문단이 여러 줄로"
    " 자라나는 상황을 재현한다 " + "안내 문구 " * 12
)


def _local(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _build_tracked_artifact() -> bytes:
    """gold 실캐시 문단에 tracking.insert를 적용한 현행 산출물."""

    document = HwpxDocument.open(GOLD)
    target = None
    for paragraph in document.paragraphs:
        caches = [c for c in paragraph.element if _local(c.tag) == "linesegarray"]
        text = (paragraph.text or "").strip()
        if caches and len(text) >= 8:
            target = paragraph
            break
    assert target is not None, "gold에서 실캐시+본문 문단을 찾지 못했다"

    document.tracking.insert(target, _INSERT_TEXT, date="2026-08-19")
    assert not [c for c in target.element if _local(c.tag) == "linesegarray"], (
        "현행 편집 경로가 캐시를 제거하지 않았다 (a22342c 회귀)"
    )
    return document.to_bytes()


def _overlap_pairs(pdf_path: str) -> int:
    """정본 겹침 검출기(over-print fraction ≥ 0.30)로 센 글리프 겹침 쌍의 수."""

    from hwpx_automation.office.form_fill.fit.wordbox import (
        _overprint_fraction,
        detect_overlaps,
        extract_glyph_boxes,
    )

    boxes = [b for b in extract_glyph_boxes(pdf_path) if b.text.strip()]
    return sum(
        1
        for a, b in detect_overlaps(boxes)
        if _overprint_fraction(a, b) >= 0.30
    )


def test_tracked_insert_render_has_no_glyph_overlap(tmp_path):
    from hwpx_automation.office.rendering.oracle import MacHancomOracle

    oracle = MacHancomOracle()
    assert oracle.available(), "Mac Hancom GUI oracle unreachable"

    # 1) 민감도(양성 대조): 정본 겹침 픽스처가 검출기에서 실제로 겹침으로 센다.
    positive = ROOT / "tests" / "fixtures" / "glyph_overlap" / "slot_overprint.hwpx"
    positive_pdf = oracle.render_pdf(str(positive), str(tmp_path / "overprint.pdf"))
    assert positive_pdf, "양성 대조 픽스처 렌더 실패"
    assert _overlap_pairs(positive_pdf) > 0, (
        "정본 겹침 픽스처에서 겹침이 검출되지 않았다 — 검출기 무효"
    )

    # 2) 회귀: 변경추적 삽입 현행 산출물은 겹침 없이 렌더된다.
    artifact = _build_tracked_artifact()
    src = tmp_path / "tracked.hwpx"
    src.write_bytes(artifact)
    pdf = oracle.render_pdf(str(src), str(tmp_path / "tracked.pdf"))
    assert pdf, "변경추적 산출물 렌더 실패"
    overlaps = _overlap_pairs(pdf)
    assert overlaps == 0, f"변경추적 산출물에서 글리프 겹침 {overlaps}쌍"
