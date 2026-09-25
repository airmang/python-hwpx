"""Image fills take the four positions Hancom writes that the OWPML schema's list leaves out.

Hancom's fill image codes 10-13 are saved as ``LEFT_TOP``, ``LEFT_BOTTOM``, ``RIGHT_CENTER`` and
``RIGHT_TOP`` (the HWP 5 reader already maps them); they sit next to the 12 schema values.
"""

from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument

HANCOM_ONLY_MODES = ["LEFT_TOP", "LEFT_BOTTOM", "RIGHT_CENTER", "RIGHT_TOP"]


def _document_with_image():
    document = HwpxDocument.new()
    image = document.media.add_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "png")
    return document, image


def _img_brush_mode(document: HwpxDocument, border_fill_id: str) -> str:
    fill_brush = next(c for c in document.styles.border_fill(border_fill_id).children if c.name == "fillBrush")
    return fill_brush.children[0].attributes["mode"]


@pytest.mark.parametrize("mode", HANCOM_ONLY_MODES)
def test_a_cell_fill_image_takes_the_mode(mode: str) -> None:
    document, image = _document_with_image()
    table = document.add_table(1, 1)

    table.set_cell_fill_image(0, 0, image, mode=mode.lower())

    assert _img_brush_mode(document, table.cell(0, 0).element.get("borderFillIDRef")) == mode


@pytest.mark.parametrize("mode", HANCOM_ONLY_MODES)
def test_a_border_fill_image_takes_the_mode_and_survives_reopening(mode: str) -> None:
    document, image = _document_with_image()
    border_fill_id = document.styles.ensure_border_fill(fill_image={"item": image, "mode": mode})

    reopened = HwpxDocument.open(document.to_bytes())

    assert _img_brush_mode(reopened, border_fill_id) == mode


def test_an_unknown_mode_is_still_refused() -> None:
    document, image = _document_with_image()

    with pytest.raises(ValueError):
        document.add_table(1, 1).set_cell_fill_image(0, 0, image, mode="LEFT_MIDDLE")
