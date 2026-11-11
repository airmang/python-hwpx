# SPDX-License-Identifier: Apache-2.0
"""``hwpx.body_patch``의 색 기준 일괄 연산(`strip_runs_by_color`, `recolor_runs_by_color`).

`strip_runs_by_color`는 대상 색 run이 **직접** 가진 글만 비워야 한다. 표·글상자·
각주를 품은 run은 그 안에 다른 run을 담고 있고, 안쪽 run의 글은 안쪽 run의
색을 따른다(2026-11 점검 ENG-03: 여는 태그를 첫 `</hp:run>`과 짝지어 첫 칸의
검은 글이 지워졌다).
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from hwpx.body_patch import strip_runs_by_color
from hwpx.document import HwpxDocument

SECTION = "Contents/section0.xml"
_SEG = (
    '<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
    'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/></hp:linesegarray>'
)


def _base() -> tuple[bytes, str]:
    """빈 문서와 빨강 글자 모양 id."""

    doc = HwpxDocument.new()
    red = str(doc.styles.ensure_run(color="#FF0000"))
    data = doc.to_bytes()
    doc.close()
    return data, red


def _with_body(data: bytes, body: str) -> bytes:
    """구역 정의 문단은 그대로 두고 그 뒤에 *body* 문단들을 붙인다."""

    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            payload = src.read(item.filename)
            if item.filename == SECTION:
                xml = payload.decode("utf-8")
                end = xml.rindex("</hs:sec>")
                payload = (xml[:end] + body + xml[end:]).encode("utf-8")
            dst.writestr(item, payload)
    return buf.getvalue()


def _section(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(SECTION).decode("utf-8")


def _p(pid: int, inner: str, *, cache: bool = True) -> str:
    return (
        f'<hp:p id="{pid}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f"{inner}{_SEG if cache else ''}</hp:p>"
    )


def _run(char_pr: str, text: str | None) -> str:
    if text is None:
        return f'<hp:run charPrIDRef="{char_pr}"/>'
    return f'<hp:run charPrIDRef="{char_pr}"><hp:t>{text}</hp:t></hp:run>'


def _table(cell_inner: str) -> str:
    return (
        '<hp:tbl id="900" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" '
        'lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="1" colCnt="1" cellSpacing="0" '
        'borderFillIDRef="1" noAdjust="0">'
        '<hp:sz width="42520" widthRelTo="ABSOLUTE" height="2000" heightRelTo="ABSOLUTE" protect="0"/>'
        '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
        'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        '<hp:outMargin left="0" right="0" top="0" bottom="0"/><hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        '<hp:tr><hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" '
        'linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f"{cell_inner}</hp:subList>"
        '<hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        '<hp:cellSz width="42520" height="2000"/><hp:cellMargin left="0" right="0" top="0" bottom="0"/>'
        "</hp:tc></hp:tr></hp:tbl>"
    )


def _paragraph_block(xml: str, pid: int) -> str:
    """id가 *pid*인 문단의 XML(안쪽 문단 포함)."""

    start = xml.index(f'<hp:p id="{pid}"')
    depth = 0
    for match in re.finditer(r"<hp:p[ >]|</hp:p>", xml[start:]):
        depth += -1 if match.group().startswith("</") else 1
        if depth == 0:
            return xml[start : start + match.end()]
    raise AssertionError("문단이 닫히지 않음")


def test_strip_keeps_other_colour_text_inside_a_table_held_by_a_target_run() -> None:
    data, red = _base()
    cell = _p(11, _run("0", "칸 검은 글 KEEP")) + _p(12, _run(red, "칸 빨강 글 DROP"))
    holder = (
        f'<hp:run charPrIDRef="{red}"><hp:t>표 앞 빨강 DROP</hp:t>{_table(cell)}'
        "<hp:t>표 뒤 빨강 DROP</hp:t></hp:run>"
    )
    source = _with_body(data, _p(10, holder) + _p(13, _run("0", "꼬리 검은 글 KEEP")))

    result = strip_runs_by_color(source, ["#FF0000"])

    xml = _section(result.data)
    assert result.open_safety.get("ok") is True
    assert "칸 검은 글 KEEP" in xml and "꼬리 검은 글 KEEP" in xml
    assert "DROP" not in xml
    entry = result.transcript[0]
    assert entry["status"] == "applied"
    assert entry["runsBlanked"] == 2
    # 표를 품은 run은 그 run의 글만 비웠다는 사실을 결과에 싣는다.
    assert entry["runsHoldingNestedRuns"] == 1


def test_strip_does_not_pair_a_self_closing_target_run_with_the_next_run() -> None:
    data, red = _base()
    source = _with_body(data, _p(20, _run(red, None) + _run("0", "빈 빨강 run 뒤 검은 글 KEEP")))

    result = strip_runs_by_color(source, ["#FF0000"])

    assert result.byte_identical is True
    assert result.transcript == ()
    assert "빈 빨강 run 뒤 검은 글 KEEP" in _section(result.data)


def test_strip_clears_only_the_layout_cache_of_paragraphs_whose_text_changed() -> None:
    data, red = _base()
    cell = _p(31, _run("0", "칸 글 KEEP"))
    holder = f'<hp:run charPrIDRef="{red}">{_table(cell)}<hp:t>표 뒤 빨강 DROP</hp:t></hp:run>'
    body = (
        _p(30, holder)
        + _p(32, _run(red, "빨강 문단 DROP"))
        + _p(33, _run("0", "검은 문단 KEEP"))
        + _p(34, '<hp:run charPrIDRef="0"><hp:t></hp:t></hp:run>')  # 원래 비어 있던 문단
    )
    source = _with_body(data, body)

    xml = _section(strip_runs_by_color(source, ["#FF0000"]).data)

    # 글이 바뀐 문단: 캐시가 없어야 한다(표를 품은 문단은 안쪽 문단 뒤에 캐시가 온다).
    holder_block = _paragraph_block(xml, 30)
    cell_block = _paragraph_block(xml, 31)
    assert holder_block.count("<hp:linesegarray") == 1
    assert cell_block.count("<hp:linesegarray") == 1, "안쪽 칸 문단의 캐시는 그대로"
    assert "<hp:linesegarray" not in _paragraph_block(xml, 32)
    # 건드리지 않은 문단: 캐시가 그대로.
    assert "<hp:linesegarray" in _paragraph_block(xml, 33)
    assert "<hp:linesegarray" in _paragraph_block(xml, 34)


def test_strip_ignores_run_like_text_inside_comments() -> None:
    data, red = _base()
    comment = f'<!-- <hp:run charPrIDRef="{red}"> -->'
    source = _with_body(data, _p(40, comment + _run("0", "주석 뒤 검은 글 KEEP")))

    result = strip_runs_by_color(source, ["#FF0000"])

    assert result.byte_identical is True
    assert "주석 뒤 검은 글 KEEP" in _section(result.data)


def test_strip_dry_run_reports_without_writing(tmp_path: Path) -> None:
    data, red = _base()
    source = _with_body(data, _p(50, _run(red, "빨강 DROP")))
    target = tmp_path / "out.hwpx"

    result = strip_runs_by_color(source, ["#FF0000"], output_path=target, dry_run=True)

    assert result.transcript[0]["status"] == "would_apply"
    assert not target.exists()
    assert "DROP" not in _section(result.data)


def test_strip_matches_the_colour_family_and_leaves_the_rest_byte_identical() -> None:
    doc = HwpxDocument.new()
    red = str(doc.styles.ensure_run(color="#FF0000"))
    blue = str(doc.styles.ensure_run(color="#0000FF"))
    data = doc.to_bytes()
    doc.close()
    source = _with_body(data, _p(60, _run(red, "빨강 DROP") + _run(blue, "파랑 KEEP")))

    result = strip_runs_by_color(source, ["#FF0000"])

    assert result.changed_parts == (SECTION,)
    assert "파랑 KEEP" in _section(result.data) and "DROP" not in _section(result.data)
    with zipfile.ZipFile(io.BytesIO(source)) as before, zipfile.ZipFile(io.BytesIO(result.data)) as after:
        for name in before.namelist():
            if name != SECTION:
                assert before.read(name) == after.read(name), name
