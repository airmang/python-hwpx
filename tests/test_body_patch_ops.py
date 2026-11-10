# SPDX-License-Identifier: Apache-2.0
"""``hwpx.body_patch.apply_body_ops``의 연산별 계약.

2026-11 점검 ARC-16: `insert_paragraph_by_clone`·`reorder_paragraphs`·
`set_paragraph_text`는 어느 저장소의 테스트도 실행하지 않았고,
`delete_paragraph`·`restyle_text`·`recolor_runs_by_color`는 core 테스트에서
0줄이었다. 사용자 문서를 바이트 수준으로 고치는 연산이므로 core에서 지킨다.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx.body_patch import apply_body_ops, direct_paragraph_spans, recolor_runs_by_color
from hwpx.document import HwpxDocument
from tests.test_body_patch_color_runs import SECTION, _p, _paragraph_block, _run, _section, _table, _with_body

HEADER = "Contents/header.xml"


def _doc(*texts: str) -> bytes:
    """구역 정의 문단 뒤에 캐시가 있는 한 줄 문단들(id 100, 101, …)."""

    doc = HwpxDocument.new()
    data = doc.to_bytes()
    doc.close()
    return _with_body(data, "".join(_p(100 + i, _run("0", text)) for i, text in enumerate(texts)))


def _texts(data: bytes) -> list[str]:
    """구역 직속 문단의 글(안쪽 문단의 글 포함), 구역 정의 문단은 뺀다."""

    xml = _section(data)
    out = []
    for a, b in direct_paragraph_spans(xml)[1:]:
        out.append("".join(re.findall(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", xml[a:b], re.S)))
    return out


def _header(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(HEADER).decode("utf-8")


def _only_section_changed(source: bytes, result_data: bytes, *also: str) -> None:
    with zipfile.ZipFile(io.BytesIO(source)) as before, zipfile.ZipFile(io.BytesIO(result_data)) as after:
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name not in (SECTION, *also):
                assert before.read(name) == after.read(name), name


# -- insert_paragraph_by_clone ------------------------------------------------


def test_insert_by_clone_copies_the_reference_paragraph_after_it() -> None:
    source = _doc("가", "나", "다")

    result = apply_body_ops(source, [{"op": "insert_paragraph_by_clone", "ref_index": 2, "count": 2}])

    assert result.ok
    assert _texts(result.data) == ["가", "나", "나", "나", "다"]
    entry = result.transcript[0]
    assert (entry["status"], entry["refIndex"], entry["count"]) == ("applied", 2, 2)
    _only_section_changed(source, result.data)


def test_insert_by_clone_sets_the_texts_and_keeps_the_reference_formatting() -> None:
    doc = HwpxDocument.new()
    bold = str(doc.styles.ensure_run(bold=True))
    data = doc.to_bytes()
    doc.close()
    source = _with_body(data, _p(100, _run(bold, "본보기")) + _p(101, _run("0", "끝")))

    result = apply_body_ops(
        source,
        [{"op": "insert_paragraph_by_clone", "ref_index": 1, "count": 2, "texts": ["첫째\n줄", "둘째 & <셋째>"]}],
    )

    assert result.ok
    xml = _section(result.data)
    blocks = [xml[a:b] for a, b in direct_paragraph_spans(xml)[1:]]
    assert len(blocks) == 4
    assert "<hp:t>본보기</hp:t>" in blocks[0]
    assert "<hp:t>첫째<hp:lineBreak/>줄</hp:t>" in blocks[1]
    assert "<hp:t>둘째 &amp; &lt;셋째&gt;</hp:t>" in blocks[2]
    for clone in blocks[1:3]:
        assert f'charPrIDRef="{bold}"' in clone
        assert 'paraPrIDRef="0"' in clone


def test_insert_by_clone_gives_each_copy_its_own_id_and_no_line_cache() -> None:
    source = _doc("가", "나")

    result = apply_body_ops(source, [{"op": "insert_paragraph_by_clone", "ref_index": 1, "count": 3}])

    xml = _section(result.data)
    blocks = [xml[a:b] for a, b in direct_paragraph_spans(xml)[1:]]
    ids = [re.match(r'<hp:p id="(\d+)"', block).group(1) for block in blocks]
    assert len(set(ids)) == len(ids) == 5
    assert "<hp:linesegarray" in blocks[0]  # 본보기 문단의 캐시는 그대로
    assert all("<hp:linesegarray" not in clone for clone in blocks[1:4])  # 복제본은 한/글이 다시 배치
    assert "<hp:linesegarray" in blocks[4]


@pytest.mark.parametrize(
    ("op", "reason"),
    [
        ({"ref_index": 9}, "out of range"),
        ({"ref_index": 1, "count": 0}, "count must be >= 1"),
        ({"ref_index": 1, "count": 2, "texts": ["하나"]}, "len(texts) must equal count"),
    ],
)
def test_insert_by_clone_refuses_what_it_cannot_do_safely(op: dict, reason: str) -> None:
    source = _doc("가", "나")

    result = apply_body_ops(source, [{"op": "insert_paragraph_by_clone", **op}])

    assert not result.ok
    assert result.byte_identical
    assert reason in result.skipped[0]["status"]


def test_insert_by_clone_refuses_a_reference_paragraph_that_holds_a_table() -> None:
    doc = HwpxDocument.new()
    data = doc.to_bytes()
    doc.close()
    source = _with_body(data, _p(100, f'<hp:run charPrIDRef="0">{_table(_p(101, _run("0", "칸")))}</hp:run>'))

    result = apply_body_ops(source, [{"op": "insert_paragraph_by_clone", "ref_index": 1}])

    assert not result.ok and result.byte_identical
    assert "wraps a table" in result.skipped[0]["status"]


# -- reorder_paragraphs -------------------------------------------------------


def test_reorder_moves_the_paragraph_blocks_without_changing_them() -> None:
    source = _doc("가", "나", "다", "라")
    before = _section(source)
    blocks = [_paragraph_block(before, pid) for pid in (100, 101, 102, 103)]

    result = apply_body_ops(source, [{"op": "reorder_paragraphs", "start": 1, "end": 3, "order": [2, 0, 1]}])

    assert result.ok
    assert _texts(result.data) == ["다", "가", "나", "라"]
    after = _section(result.data)
    assert after == before.replace("".join(blocks[:3]), blocks[2] + blocks[0] + blocks[1])
    _only_section_changed(source, result.data)


@pytest.mark.parametrize(
    ("op", "reason"),
    [
        ({"start": 1, "end": 9, "order": [0]}, "out of bounds"),
        ({"start": 3, "end": 1, "order": [0]}, "out of bounds"),
        ({"start": 1, "end": 2, "order": [0, 0]}, "permutation"),
        ({"start": 1, "end": 2, "order": [0, 1, 2]}, "permutation"),
    ],
)
def test_reorder_refuses_a_bad_range_or_order(op: dict, reason: str) -> None:
    source = _doc("가", "나", "다")

    result = apply_body_ops(source, [{"op": "reorder_paragraphs", **op}])

    assert not result.ok and result.byte_identical
    assert reason in result.skipped[0]["status"]


def test_reorder_keeps_the_section_settings_paragraph_in_place_when_it_does_not_move() -> None:
    source = _doc("가", "나")

    result = apply_body_ops(source, [{"op": "reorder_paragraphs", "start": 0, "end": 2, "order": [0, 2, 1]}])

    assert result.ok
    assert _texts(result.data) == ["나", "가"]


# -- set_paragraph_text -------------------------------------------------------


def test_set_paragraph_text_replaces_the_text_and_drops_the_line_cache() -> None:
    source = _doc("가", "나", "다")

    result = apply_body_ops(source, [{"op": "set_paragraph_text", "index": 2, "text": "새 글\t탭 & 줄\n바꿈"}])

    assert result.ok
    xml = _section(result.data)
    block = _paragraph_block(xml, 101)
    assert "<hp:t>새 글<hp:tab/>탭 &amp; 줄<hp:lineBreak/>바꿈</hp:t>" in block
    assert "<hp:linesegarray" not in block
    assert "<hp:linesegarray" in _paragraph_block(xml, 100) and "<hp:linesegarray" in _paragraph_block(xml, 102)
    entry = result.transcript[0]
    assert (entry["old"], entry["status"]) == ("나", "applied")
    assert HwpxDocument.open(result.data).paragraphs[2].text == "새 글\t탭 & 줄\n바꿈"


def test_set_paragraph_text_puts_the_text_in_the_first_run_and_empties_the_others() -> None:
    doc = HwpxDocument.new()
    bold = str(doc.styles.ensure_run(bold=True))
    data = doc.to_bytes()
    doc.close()
    source = _with_body(data, _p(100, _run(bold, "굵은") + _run("0", " 보통")))

    result = apply_body_ops(source, [{"op": "set_paragraph_text", "index": 1, "text": "새 글"}])

    block = _paragraph_block(_section(result.data), 100)
    assert f'<hp:run charPrIDRef="{bold}"><hp:t>새 글</hp:t></hp:run>' in block
    assert '<hp:run charPrIDRef="0"><hp:t></hp:t></hp:run>' in block


def test_set_paragraph_text_fills_a_paragraph_whose_run_is_empty() -> None:
    doc = HwpxDocument.new()
    data = doc.to_bytes()
    doc.close()
    source = _with_body(data, _p(100, _run("0", None)))

    result = apply_body_ops(source, [{"op": "set_paragraph_text", "index": 1, "text": "채움"}])

    assert result.ok
    assert '<hp:run charPrIDRef="0"><hp:t>채움</hp:t></hp:run>' in _section(result.data)


# -- delete_paragraph ---------------------------------------------------------


def test_delete_paragraph_removes_that_block_only() -> None:
    source = _doc("가", "나", "다")
    before = _section(source)

    result = apply_body_ops(source, [{"op": "delete_paragraph", "index": 2}])

    assert result.ok
    assert _section(result.data) == before.replace(_paragraph_block(before, 101), "")
    assert result.transcript[0]["old"] == "나"
    _only_section_changed(source, result.data)


# -- restyle_text -------------------------------------------------------------


def _blue_italic_doc() -> tuple[bytes, str]:
    doc = HwpxDocument.new()
    blue = str(doc.styles.ensure_run(color="#0000FF", italic=True))
    data = doc.to_bytes()
    doc.close()
    return data, blue


def test_restyle_text_points_the_run_at_a_new_shape_and_leaves_the_old_one() -> None:
    data, blue = _blue_italic_doc()
    source = _with_body(data, _p(100, _run(blue, "채운 글")) + _p(101, _run(blue, "안내 글")))
    header_before = _header(source)

    result = apply_body_ops(source, [{"op": "restyle_text", "find": "채운", "text_color": "#000000"}])

    assert result.ok
    assert result.changed_parts == (SECTION,)
    xml = _section(result.data)
    new_id = re.search(r'<hp:run charPrIDRef="(\d+)"><hp:t>채운 글', xml).group(1)
    assert new_id != blue
    assert f'<hp:run charPrIDRef="{blue}"><hp:t>안내 글' in xml
    header = _header(result.data)
    assert header.count("<hh:charPr ") == header_before.count("<hh:charPr ") + 1
    count = lambda text: int(re.search(r'<hh:charProperties\b[^>]*\bitemCnt="(\d+)"', text).group(1))  # noqa: E731
    assert count(header) == count(header_before) + 1
    shape = re.search(rf'<hh:charPr\b[^>]*\bid="{new_id}".*?</hh:charPr>', header, re.S).group(0)
    assert 'textColor="#000000"' in shape and "<hh:italic" not in shape
    original = re.search(rf'<hh:charPr\b[^>]*\bid="{blue}".*?</hh:charPr>', header, re.S).group(0)
    assert 'textColor="#0000FF"' in original and "<hh:italic" in original
    _only_section_changed(source, result.data, HEADER)

    reopened = HwpxDocument.open(result.data)
    assert reopened.paragraphs[1].text == "채운 글"


def test_restyle_text_reuses_one_new_shape_for_the_same_change() -> None:
    data, blue = _blue_italic_doc()
    source = _with_body(data, _p(100, _run(blue, "하나")) + _p(101, _run(blue, "둘")))

    result = apply_body_ops(
        source,
        [
            {"op": "restyle_text", "find": "하나", "text_color": "#000000"},
            {"op": "restyle_text", "find": "둘", "text_color": "#000000"},
        ],
    )

    assert result.ok
    ids = re.findall(r'<hp:run charPrIDRef="(\d+)"><hp:t>(?:하나|둘)', _section(result.data))
    assert len(ids) == 2 and ids[0] == ids[1] != blue
    assert _header(result.data).count("<hh:charPr ") == _header(source).count("<hh:charPr ") + 1


def test_restyle_text_refuses_a_count_mismatch() -> None:
    data, blue = _blue_italic_doc()
    source = _with_body(data, _p(100, _run(blue, "같은 글")) + _p(101, _run(blue, "같은 글")))

    result = apply_body_ops(source, [{"op": "restyle_text", "find": "같은 글"}])

    assert not result.ok and result.byte_identical
    assert "matched 2 time(s)" in result.skipped[0]["status"]


# -- recolor_runs_by_color ----------------------------------------------------


def test_recolor_remaps_runs_of_the_exact_colour_only() -> None:
    doc = HwpxDocument.new()
    blue = str(doc.styles.ensure_run(color="#0000FF", bold=True))
    navy = str(doc.styles.ensure_run(color="#0000CC"))
    data = doc.to_bytes()
    doc.close()
    cell = _p(101, _run(blue, "칸 파랑"))
    source = _with_body(
        data,
        _p(100, f'<hp:run charPrIDRef="{blue}">{_table(cell)}<hp:t>표 뒤 파랑</hp:t></hp:run>')
        + _p(102, _run(navy, "남색") + _run("0", "검정") + f'<hp:run charPrIDRef="{blue}"/>'),
    )

    result = recolor_runs_by_color(source, ["#0000ff"], "#000000")

    assert result.ok
    xml = _section(result.data)
    assert f'charPrIDRef="{blue}"' not in xml
    assert f'<hp:run charPrIDRef="{navy}"><hp:t>남색' in xml and '<hp:run charPrIDRef="0"><hp:t>검정' in xml
    new_id = re.search(r'<hp:run charPrIDRef="(\d+)"><hp:t>칸 파랑', xml).group(1)
    shape = re.search(rf'<hh:charPr\b[^>]*\bid="{new_id}".*?</hh:charPr>', _header(result.data), re.S).group(0)
    assert 'textColor="#000000"' in shape and "<hh:bold" in shape  # 색만 바뀌고 나머지 서식은 그대로
    assert result.transcript[0]["runsRecolored"] == 3
    assert xml.count("<hp:linesegarray") == _section(source).count("<hp:linesegarray")  # 색은 줄 배치를 바꾸지 않는다
    _only_section_changed(source, result.data, HEADER)


def test_recolor_without_a_match_changes_nothing_and_dry_run_writes_nothing(tmp_path: Path) -> None:
    doc = HwpxDocument.new()
    blue = str(doc.styles.ensure_run(color="#0000FF"))
    data = doc.to_bytes()
    doc.close()
    source = _with_body(data, _p(100, _run(blue, "파랑")))

    nothing = recolor_runs_by_color(source, ["#00FF00"], "#000000")
    assert nothing.byte_identical and nothing.transcript == ()

    target = tmp_path / "out.hwpx"
    dry = recolor_runs_by_color(source, ["#0000FF"], "#000000", output_path=target, dry_run=True)
    assert dry.transcript[0]["status"] == "would_apply"
    assert not target.exists()
    written = recolor_runs_by_color(source, ["#0000FF"], "#000000", output_path=target)
    assert target.read_bytes() == written.data


# -- 공통 계약 ----------------------------------------------------------------


def test_ops_run_in_order_against_the_current_state_and_a_refusal_skips_only_that_op() -> None:
    source = _doc("가", "나", "다")

    result = apply_body_ops(
        source,
        [
            {"op": "delete_paragraph", "index": 1},  # 가 삭제 → 나, 다
            {"op": "no_such_op"},
            {"op": "set_paragraph_text", "index": 1, "text": "나2"},  # 지금의 1번은 '나'
            {"op": "replace_text", "find": "다", "replace": "다2", "section_path": "Contents/section9.xml"},
        ],
    )

    assert not result.ok  # 거부된 op가 있으면 ok가 아니다
    assert _texts(result.data) == ["나2", "다"]
    assert [entry["status"].split(":")[0] for entry in result.transcript] == ["applied", "refused", "applied", "refused"]
    assert [entry["op"] for entry in result.skipped] == ["no_such_op", "replace_text"]
    assert result.to_dict()["changedParts"] == [SECTION]


def test_dry_run_resolves_everything_and_writes_nothing(tmp_path: Path) -> None:
    source = _doc("가", "나")
    target = tmp_path / "out.hwpx"

    dry = apply_body_ops(source, [{"op": "set_paragraph_text", "index": 1, "text": "새"}], output_path=target, dry_run=True)
    assert dry.transcript[0]["status"] == "would_apply"
    assert not target.exists()

    real = apply_body_ops(source, [{"op": "set_paragraph_text", "index": 1, "text": "새"}], output_path=target)
    assert target.read_bytes() == real.data == dry.data
    assert real.as_mutation_report(source=source).to_dict()["schemaVersion"].startswith("hwpx.mutation-report")
