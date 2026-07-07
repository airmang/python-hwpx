"""body_patch — 본문 직속 문단 바이트보존 op (KACE 스파이크 승격) 테스트."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

import pytest

from hwpx.body_patch import apply_body_ops, direct_paragraph_spans

BLANK = Path(__file__).parent / "fixtures" / "m105_evalplan" / "blank_form_3hak.hwpx"


def _section(data_or_path) -> str:
    if isinstance(data_or_path, (bytes, bytearray)):
        import io

        z = zipfile.ZipFile(io.BytesIO(bytes(data_or_path)))
    else:
        z = zipfile.ZipFile(data_or_path)
    return z.read("Contents/section0.xml").decode("utf-8")


def _texts(xml: str) -> list[str]:
    import html

    out = []
    for a, b in direct_paragraph_spans(xml):
        block = xml[a:b]
        out.append(html.unescape("".join(m.group(1) for m in re.finditer(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", block, re.S))))
    return out


@pytest.fixture()
def work(tmp_path):
    dst = tmp_path / "form.hwpx"
    shutil.copy(BLANK, dst)
    return dst


def test_replace_text_only_touches_t_content(work, tmp_path):
    out = tmp_path / "out.hwpx"
    res = apply_body_ops(
        work,
        [{"op": "replace_text", "find": "성취수준별 고정분할점수(5단계)", "replace": "[1] 성취수준별 고정분할점수(5단계)"}],
        output_path=out,
    )
    assert res.ok and not res.skipped
    assert res.transcript[0]["status"] == "applied" and res.transcript[0]["hits"] == 1
    xml = _section(out)
    assert "[1] 성취수준별 고정분할점수(5단계)" in xml
    # 태그/속성은 불가침 — hp:t 밖 어디에도 이 문자열이 새로 생기지 않음
    assert xml.count("[1] 성취수준별") == 1


def test_replace_text_refuses_wrong_count(work):
    res = apply_body_ops(work, [{"op": "replace_text", "find": "존재하지않는문자열XYZ", "replace": "x"}])
    assert res.skipped and "matched 0" in res.skipped[0]["status"]
    assert res.byte_identical


def test_delete_paragraph_refuses_table_wrapper(work):
    # ¶0은 제목 표를 품는다 — 무음 표 소실 방지 refuse
    res = apply_body_ops(work, [{"op": "delete_paragraph", "index": 0}])
    assert res.skipped and "wraps a table" in res.skipped[0]["status"]


def test_delete_paragraph_removes_block(work, tmp_path):
    before = _texts(_section(work))
    target_idx = next(i for i, t in enumerate(before) if "빨간 글씨 삭제!! (환경)" in t)
    out = tmp_path / "out.hwpx"
    res = apply_body_ops(work, [{"op": "delete_paragraph", "index": target_idx}], output_path=out)
    assert res.ok
    after = _texts(_section(out))
    assert len(after) == len(before) - 1
    assert not any("빨간 글씨 삭제!! (환경)" in t for t in after)


def test_insert_paragraph_by_clone_inherits_ref_format(work, tmp_path):
    xml = _section(work)
    spans = direct_paragraph_spans(xml)
    texts = _texts(xml)
    ref_idx = next(i for i, t in enumerate(texts) if "성취수준별 고정분할점수(5단계)" in t)
    ref_block = xml[spans[ref_idx][0]: spans[ref_idx][1]]
    ref_charpr = re.search(r'charPrIDRef="(\d+)"', ref_block).group(1)
    out = tmp_path / "out.hwpx"
    res = apply_body_ops(
        work,
        [{"op": "insert_paragraph_by_clone", "ref_index": ref_idx, "count": 2, "texts": ["복제 하나", "복제 둘"]}],
        output_path=out,
    )
    assert res.ok
    new_xml = _section(out)
    new_texts = _texts(new_xml)
    assert new_texts[ref_idx + 1] == "복제 하나" and new_texts[ref_idx + 2] == "복제 둘"
    clone_block = new_xml[direct_paragraph_spans(new_xml)[ref_idx + 1][0]: direct_paragraph_spans(new_xml)[ref_idx + 1][1]]
    assert f'charPrIDRef="{ref_charpr}"' in clone_block  # 이웃(참조) 서식 상속
    assert "linesegarray" not in clone_block  # 레이아웃 캐시 제거(한컴 재계산)
    # 문단 id는 재작성되어 원본과 달라야 함
    ref_id = re.search(r'<hp:p\b[^>]*\bid="(\d+)"', ref_block).group(1)
    clone_id = re.search(r'<hp:p\b[^>]*\bid="(\d+)"', clone_block).group(1)
    assert ref_id != clone_id


def test_reorder_paragraphs_permutes_range(work, tmp_path):
    before = _texts(_section(work))
    start = next(i for i, t in enumerate(before) if "성취수준별 고정분할점수(5단계)" in t)
    end = start + 2
    out = tmp_path / "out.hwpx"
    res = apply_body_ops(
        work,
        [{"op": "reorder_paragraphs", "start": start, "end": end, "order": [2, 1, 0]}],
        output_path=out,
    )
    assert res.ok
    after = _texts(_section(out))
    assert after[start] == before[end] and after[end] == before[start]
    assert after[:start] == before[:start] and after[end + 1:] == before[end + 1:]


def test_dry_run_writes_nothing(work, tmp_path):
    out = tmp_path / "out.hwpx"
    original = work.read_bytes()
    res = apply_body_ops(
        work,
        [{"op": "replace_text", "find": "성취수준별 고정분할점수(5단계)", "replace": "X"}],
        output_path=out,
        dry_run=True,
    )
    assert res.transcript[0]["status"] == "would_apply"
    assert not out.exists() and work.read_bytes() == original
    assert not res.byte_identical  # would-be 바이트는 실제로 달라짐(증거)
