# SPDX-License-Identifier: Apache-2.0
"""Saving documents as HWP 5.0 (``.hwp``) through ``save_to_path``."""

from __future__ import annotations

import base64
import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.hwp5 import cfb
from hwpx.hwp5 import records as rec
from hwpx.hwp5.errors import Hwp5ConversionWarning, Hwp5Error
from hwpx.hwp5.fileheader import parse_file_header
from hwpx.hwp5.package import convert
from hwpx.hwp5.reader import read_hwp5
from hwpx.hwp5.writer import write_hwp5
from tests.test_hwp5_open import HP, make_hwp

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _texts(document: HwpxDocument) -> list[str]:
    return ["".join(p.itertext()) for s in document.sections for p in s.element.iter(f"{HP}p")]


def test_a_new_document_saves_as_hwp_and_reopens(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")
    document.add_paragraph("둘째 문단")
    table = document.add_table(2, 2)
    table.set_cell_text(0, 0, "왼쪽 위")
    table.set_cell_text(1, 1, "오른쪽 아래")
    target = tmp_path / "새 문서.hwp"

    assert document.save_to_path(target) == target

    data = target.read_bytes()
    assert data[:8] == cfb.SIGNATURE
    header = parse_file_header(cfb.CompoundFile(data).read("FileHeader"))
    assert header.version == (5, 1, 1, 0) and header.compressed
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        reopened = HwpxDocument.open(target)
    texts = _texts(reopened)
    assert "첫 문단" in texts and "둘째 문단" in texts
    cells = ["".join(tc.itertext()) for s in reopened.sections for tc in s.element.iter(f"{HP}tc")]
    assert cells == ["왼쪽 위", "", "", "오른쪽 아래"]


@pytest.mark.parametrize("extras", [{}, {"fields": True}, {"highlights": True}, {"label": True}])
def test_hwp_to_hwpx_to_hwp_keeps_the_section_records(extras: dict[str, bool]) -> None:
    original = make_hwp(**extras)
    written = write_hwp5(convert(original).files)

    before = read_hwp5(original).sections[0].records
    after = read_hwp5(written).sections[0].records
    assert [(r.tag, r.level) for r in after] == [(r.tag, r.level) for r in before]
    for a, b in zip(before, after):
        if a.tag == rec.PARA_HEADER:
            # Only the "last paragraph of the list" bit may differ: the sample leaves it unset.
            assert a.payload[4:] == b.payload[4:]
        else:
            assert a.payload == b.payload, rec.TAG_NAMES.get(a.tag)


def test_saving_as_hwp_keeps_text_formatting_and_tables(tmp_path: Path) -> None:
    source = HwpxDocument.open(make_hwp())
    target = tmp_path / "out.hwp"
    source.save_to_path(target)
    reopened = HwpxDocument.open(target)
    assert _texts(reopened) == _texts(source)
    runs = [
        (r.get("charPrIDRef"), "".join(r.itertext()))
        for s in reopened.sections
        for r in s.element.iter(f"{HP}run")
        if "".join(r.itertext())
    ]
    assert ("1", "abc") in runs


def test_content_the_writer_cannot_express_is_refused_before_writing(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("그림이 있는 문서")
    document.add_picture(_PNG, "png")
    target = tmp_path / "그림.hwp"
    with pytest.raises(Hwp5Error) as info:
        document.save_to_path(target)
    assert info.value.code == "hwp5-write-unsupported"
    assert info.value.context["unsupported"].get("pic") == 1
    assert not target.exists()


def test_memos_and_master_pages_are_refused_until_they_can_be_written(tmp_path: Path) -> None:
    with pytest.warns(Hwp5ConversionWarning):
        document = HwpxDocument.open(make_hwp(memo=True))
    [sec_pr] = list(document.sections[0].element.iter(f"{HP}secPr"))
    sec_pr.set("masterPageCnt", "1")
    document.sections[0].mark_dirty()
    target = tmp_path / "메모.hwp"
    with pytest.raises(Hwp5Error) as info:
        document.save_to_path(target)
    assert info.value.context["unsupported"] == {"field/MEMO": 1, "masterPage": 1}
    assert not target.exists()


def test_hwpx_targets_are_unchanged(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("HWPX로 저장")
    target = tmp_path / "out.hwpx"
    document.save_to_path(target)
    assert target.read_bytes()[:2] == b"PK"
