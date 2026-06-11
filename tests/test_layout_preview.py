# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hwpx.tools.layout_preview import render_layout_preview


CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))


def _sample_ids() -> list[str]:
    return [sample["file"] for sample in MANIFEST["samples"]]


def test_layout_preview_renders_page_box_and_margins() -> None:
    preview = render_layout_preview(CORPUS / "reader_writer__PageSize_Margin.hwpx")

    page = preview.pages[0]
    assert page.width_mm > 250
    assert page.height_mm > 350
    assert page.margins_mm["left"] == pytest.approx(30.0, abs=0.2)
    assert page.margins_mm["top"] == pytest.approx(20.0, abs=0.2)
    assert "hwpx-preview-page" in preview.html
    assert "padding:" in preview.html


def test_layout_preview_renders_table_geometry_and_borders() -> None:
    preview = render_layout_preview(CORPUS / "reader_writer__SimpleTable.hwpx")

    assert '<table class="hwpx-table"' in preview.html
    assert 'colspan="2"' in preview.html
    assert 'rowspan="2"' in preview.html
    assert "border-left:" in preview.html
    assert "width:" in preview.html
    assert preview.pages[0].table_count == 1


def test_layout_preview_long_mode_uses_single_page_box() -> None:
    preview = render_layout_preview(
        CORPUS / "reader_writer__SimpleTable.hwpx",
        mode="long",
    )

    assert preview.mode == "long"
    assert preview.as_dict()["pageCount"] == 1


@pytest.mark.parametrize("sample", _sample_ids())
def test_hwpxlib_corpus_layout_preview_does_not_crash(sample: str) -> None:
    preview = render_layout_preview(CORPUS / sample)

    assert preview.html.startswith("<!DOCTYPE html>")
    assert preview.as_dict()["pageCount"] == len(preview.pages)
