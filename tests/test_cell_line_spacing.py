"""set_cell_line_spacing — 셀 내부 문단 줄간격 (Stage 3 간격 프리미티브 P2b)."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

import pytest

from hwpx.table_patch import apply_table_ops

BLANK = Path(__file__).parent / "fixtures" / "m105_evalplan" / "blank_form_3hak.hwpx"


@pytest.fixture()
def work(tmp_path):
    dst = tmp_path / "form.hwpx"
    shutil.copy(BLANK, dst)
    return dst


def test_spacing_remaps_parapr_and_strips_lineseg(work, tmp_path):
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work,
        [{"op": "set_cell_line_spacing", "table_index": 2, "cells": [[2, 4]], "line_spacing": 130}],
        output_path=out,
    )
    assert res.ok, [s.reason for s in res.skipped]
    entry = next(t for t in res.transcript if t["op"] == "set_cell_line_spacing")
    assert entry["status"] == "applied" and entry["cellsTouched"] == 1

    z = zipfile.ZipFile(out)
    header = z.read("Contents/header.xml").decode("utf-8")
    sec = z.read("Contents/section0.xml").decode("utf-8")
    zb = zipfile.ZipFile(work)
    header0 = zb.read("Contents/header.xml").decode("utf-8")
    # 새 paraPr가 추가되고 lineSpacing=130
    n0 = len(re.findall(r"<hh:paraPr\b", header0))
    n1 = len(re.findall(r"<hh:paraPr\b", header))
    assert n1 > n0
    new_ids = set(re.findall(r'<hh:paraPr\b[^>]*\bid="(\d+)"', header)) - set(
        re.findall(r'<hh:paraPr\b[^>]*\bid="(\d+)"', header0))
    assert new_ids
    nid = new_ids.pop()
    blk = re.search(r'<hh:paraPr\b[^>]*\bid="' + nid + r'".*?</hh:paraPr>', header, re.S).group(0)
    assert re.search(r'<hh:lineSpacing\b[^>]*\bvalue="130"', blk)
    # 클론의 switch/case 분기까지 전부 130
    assert not re.search(r'<hh:lineSpacing\b[^>]*\bvalue="(?!130)\d+"', blk)
    # 대상 셀 문단이 새 paraPr를 참조 + lineseg 제거
    assert f'paraPrIDRef="{nid}"' in sec
    i = sec.find(f'paraPrIDRef="{nid}"')
    pstart = sec.rfind("<hp:p", 0, i)
    pend = sec.find("</hp:p>", i)
    assert "linesegarray" not in sec[pstart:pend]


def test_untouched_cells_unaffected_and_original_parapr_kept(work, tmp_path):
    out = tmp_path / "out.hwpx"
    apply_table_ops(
        work,
        [{"op": "set_cell_line_spacing", "table_index": 2, "rows": [3], "line_spacing": 115}],
        output_path=out,
    )
    header = zipfile.ZipFile(out).read("Contents/header.xml").decode("utf-8")
    # 원본 paraPr들은 그대로 존재(다른 문단 불변)
    header0 = zipfile.ZipFile(work).read("Contents/header.xml").decode("utf-8")
    for pid in re.findall(r'<hh:paraPr\b[^>]*\bid="(\d+)"', header0)[:5]:
        assert re.search(r'<hh:paraPr\b[^>]*\bid="' + pid + r'"', header)


def test_no_matching_cells_refused(work):
    res = apply_table_ops(
        work, [{"op": "set_cell_line_spacing", "table_index": 2, "cells": [[999, 999]], "line_spacing": 130}],
    )
    assert res.skipped and "no matching cells" in res.skipped[-1].reason


def test_dry_run_reports_would_apply(work, tmp_path):
    out = tmp_path / "out.hwpx"
    res = apply_table_ops(
        work,
        [{"op": "set_cell_line_spacing", "table_index": 2, "cells": [[2, 4]], "line_spacing": 130}],
        output_path=out, dry_run=True,
    )
    entry = next(t for t in res.transcript if t["op"] == "set_cell_line_spacing")
    assert entry["status"] == "would_apply"
    assert not out.exists()


_LINESEG = (b'<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
            b'baseline="850" spacing="600" horzpos="0" horzsize="40000" flags="393216"/></hp:linesegarray>')


def _nested_source() -> bytes:
    """A 3x3 table whose cell (1, 1) holds a 2x2 table and some text; every paragraph has a line cache."""
    import io

    from hwpx.document import HwpxDocument

    document = HwpxDocument.new()
    outer = document.add_table(3, 3)
    for row in range(3):
        for col in range(3):
            outer.cell(row, col).text = f"outer:{row}:{col}"
    inner = outer.cell(1, 1).paragraphs[0].add_table(2, 2)
    for row in range(2):
        for col in range(2):
            inner.cell(row, col).text = f"inner:{row}:{col}"
    data = document.to_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                payload = re.sub(rb"<hp:linesegarray>.*?</hp:linesegarray>", b"", payload, flags=re.S)
                payload = payload.replace(b"</hp:p>", _LINESEG + b"</hp:p>")
            target.writestr(info, payload)
    return out.getvalue()


def _tables(data: bytes) -> list[bytes]:
    from hwpx.table_patch import iter_table_spans, section_parts

    section = section_parts(data)["Contents/section0.xml"]
    return [section[s:e] for s, e in iter_table_spans(section)]


def _own_paragraphs(cell: bytes) -> list[bytes]:
    from hwpx.table_patch import cell_paragraph_spans

    return [cell[s:e] for s, e in cell_paragraph_spans(cell)]


def _cell(table: bytes, row: int, col: int) -> bytes:
    from hwpx.table_patch import direct_table_cells

    cell = next(c for c in direct_table_cells(table) if (c.row, c.col) == (row, col))
    return table[cell.start:cell.end]


def test_a_cell_holding_a_table_changes_only_its_own_paragraphs():
    source = _nested_source()
    res = apply_table_ops(source, [{"op": "set_cell_line_spacing", "table_index": 0, "cells": [[1, 1]], "line_spacing": 130}])
    assert res.ok and not res.skipped, [s.reason for s in res.skipped]
    before, after = _tables(source), _tables(res.data)
    assert after[1] == before[1]  # the inner table, line caches included
    holder = _cell(after[0], 1, 1)
    old_ids = {re.search(rb'paraPrIDRef="(\d+)"', p).group(1) for p in _own_paragraphs(_cell(before[0], 1, 1))}
    for paragraph in _own_paragraphs(holder):
        open_tag = paragraph[: paragraph.index(b">") + 1]
        assert re.search(rb'paraPrIDRef="(\d+)"', open_tag).group(1) not in old_ids
        assert not paragraph.endswith(_LINESEG + b"</hp:p>")  # own line cache dropped
    assert holder.count(_LINESEG) == before[1].count(_LINESEG)  # only the inner table's caches remain


def test_a_row_never_reaches_into_a_table_held_by_another_cell():
    source = _nested_source()
    res = apply_table_ops(source, [{"op": "set_cell_line_spacing", "table_index": 0, "rows": [0], "line_spacing": 130}])
    entry = next(t for t in res.transcript if t["op"] == "set_cell_line_spacing")
    assert entry["cellsTouched"] == 3
    before, after = _tables(source), _tables(res.data)
    assert after[1] == before[1]
    for row in (1, 2):
        for col in range(3):
            assert _cell(after[0], row, col) == _cell(before[0], row, col)


def test_the_inner_table_is_addressed_by_its_own_index():
    source = _nested_source()
    res = apply_table_ops(source, [{"op": "set_cell_line_spacing", "table_index": 1, "cells": [[0, 1]], "line_spacing": 130}])
    assert res.ok and not res.skipped
    before, after = _tables(source), _tables(res.data)
    assert _cell(after[1], 0, 1) != _cell(before[1], 0, 1)
    assert [_cell(after[1], r, c) for r, c in ((0, 0), (1, 0), (1, 1))] == [_cell(before[1], r, c) for r, c in ((0, 0), (1, 0), (1, 1))]
