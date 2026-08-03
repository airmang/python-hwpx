# SPDX-License-Identifier: Apache-2.0
"""hwpx.body_patch — ``replace_text``의 표 셀 SQUEEZE 보호 계약 테스트.

배경(야생 양식 채움-겹침 조사): ``body_patch``는 "표-밖 본문" 어휘로
문서화돼 있지만(모듈 docstring), ``<hp:t>`` 텍스트 검색은 구조적으로 표
셀 내부까지 닿는다 — ``table_patch.fill_cells``가 이미 하는
``lineWrap=SQUEEZE``→``BREAK`` 보호(``tests/test_table_patch.py::
test_fill_cell_converts_squeeze_to_break_only_in_touched_cell`` 참조)가
``replace_text``에는 없어서, 셀 안 텍스트를 ``replace_text``로 늘리면
한컴이 압축된 자간으로 겹쳐 그릴 수 있었다(2026-07-07 AI중점학교 신청서
실측 — 같은 세션에서 lineseg 캐시 문제도 함께 발견돼 그건 이미 고쳐져
있었다). 이 파일은 그 보호가 지금은 있음을 증명하고, 문서화된 주 용도인
표-밖 경로가 전혀 영향받지 않았음을 대조로 확인한다.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.body_patch import apply_body_ops
from hwpx.document import HwpxDocument

_SUBLIST_OPEN_RE = re.compile(r"<hp:subList\b[^>]*>")


def _section_name(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return next(n for n in z.namelist() if re.search(r"section\d+\.xml$", n))


def _section_xml(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return z.read(_section_name(data)).decode("utf-8")


def _with_section(data: bytes, section_xml: str) -> bytes:
    """*data*의 section part만 *section_xml*로 바꿔치기한 새 zip 바이트를 만든다."""

    name = _section_name(data)
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            payload = section_xml.encode("utf-8") if item.filename == name else src.read(item.filename)
            dst.writestr(item, payload)
    return buf.getvalue()


@pytest.fixture(scope="module")
def squeeze_doc_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """문단 하나(표 밖) + 1×2 표 하나. 셀 (0,0)만 SQUEEZE, (0,1)은 대조군(BREAK 유지)."""

    path = tmp_path_factory.mktemp("body-patch-squeeze") / "base.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("표 밖 본문입니다.")
    table = doc.add_table(1, 2)
    table.cell(0, 0).text = "짧은값"
    table.cell(0, 1).text = "다른값"
    doc.save_to_path(path)
    doc.close()

    data = path.read_bytes()
    section = _section_xml(data)
    subs = list(_SUBLIST_OPEN_RE.finditer(section))
    assert len(subs) == 2, "1x2 표는 subList(셀)가 정확히 2개여야 함"
    target = subs[0]
    assert 'lineWrap="BREAK"' in target.group(0), "픽스처 가정(기본값 BREAK)이 깨짐"
    patched_tag = target.group(0).replace('lineWrap="BREAK"', 'lineWrap="SQUEEZE"', 1)
    section = section[: target.start()] + patched_tag + section[target.end() :]
    return _with_section(data, section)


def test_replace_text_converts_squeeze_to_break_when_match_is_inside_a_cell(
    squeeze_doc_bytes: bytes,
) -> None:
    result = apply_body_ops(
        squeeze_doc_bytes,
        [
            {
                "op": "replace_text",
                "find": "짧은값",
                "replace": "훨씬 더 길게 채운 실제 값입니다",
                "count": 1,
            }
        ],
    )
    assert result.ok, result.skipped

    section = _section_xml(result.data)
    subs = list(_SUBLIST_OPEN_RE.finditer(section))
    assert len(subs) == 2
    assert 'lineWrap="SQUEEZE"' not in subs[0].group(0)
    assert 'lineWrap="BREAK"' in subs[0].group(0)
    # 대조군 셀(건드리지 않은 셀)은 원래도 BREAK였고 여전히 BREAK — 무관 변경 없음.
    assert 'lineWrap="BREAK"' in subs[1].group(0)
    assert "훨씬 더 길게 채운 실제 값입니다" in section
    assert "짧은값" not in section


def test_replace_text_outside_any_table_never_touches_a_cells_sublist(
    squeeze_doc_bytes: bytes,
) -> None:
    """문서화된 주 용도(표-밖 본문)는 이 안전망 추가로 전혀 영향받지 않는다."""

    before_tag = _SUBLIST_OPEN_RE.search(_section_xml(squeeze_doc_bytes)).group(0)
    assert 'lineWrap="SQUEEZE"' in before_tag

    result = apply_body_ops(
        squeeze_doc_bytes,
        [
            {
                "op": "replace_text",
                "find": "표 밖 본문입니다",
                "replace": "표 밖 본문을 훨씬 더 길게 바꿨습니다",
                "count": 1,
            }
        ],
    )
    assert result.ok, result.skipped

    section = _section_xml(result.data)
    after_tag = _SUBLIST_OPEN_RE.search(section).group(0)
    assert after_tag == before_tag, "표-밖 편집이 셀의 subList를 건드리면 안 된다"
    assert "표 밖 본문을 훨씬 더 길게 바꿨습니다" in section


def test_replace_text_fixes_only_the_touched_cell_when_two_cells_are_squeezed(
    tmp_path: Path,
) -> None:
    """같은 셀에 문단이 여럿이어도 그 셀은 한 번만 편집하고, 안 건드린
    다른 SQUEEZE 셀은 그대로 둔다(선택적 수리 — 무차별 전체 변환 아님)."""

    path = tmp_path / "two_squeeze.hwpx"
    doc = HwpxDocument.new()
    table = doc.add_table(1, 2)
    table.cell(0, 0).text = "첫값"
    table.cell(0, 1).text = "둘값"
    doc.save_to_path(path)
    doc.close()

    data = path.read_bytes()
    section = _section_xml(data)
    for match in list(_SUBLIST_OPEN_RE.finditer(section))[::-1]:
        assert 'lineWrap="BREAK"' in match.group(0)
        patched = match.group(0).replace('lineWrap="BREAK"', 'lineWrap="SQUEEZE"', 1)
        section = section[: match.start()] + patched + section[match.end() :]
    both_squeezed = _with_section(data, section)

    result = apply_body_ops(
        both_squeezed,
        [{"op": "replace_text", "find": "첫값", "replace": "첫 번째 셀의 긴 값", "count": 1}],
    )
    assert result.ok, result.skipped

    changed_section = _section_xml(result.data)
    subs = list(_SUBLIST_OPEN_RE.finditer(changed_section))
    assert 'lineWrap="BREAK"' in subs[0].group(0), "편집된 셀만 BREAK로 바뀌어야 함"
    assert 'lineWrap="SQUEEZE"' in subs[1].group(0), "안 건드린 셀은 SQUEEZE 그대로"
