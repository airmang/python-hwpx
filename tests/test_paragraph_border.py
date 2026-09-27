# SPDX-License-Identifier: Apache-2.0
"""Paragraph borders: sides, line, gap to the text and connected boxes.

``styles.apply_paragraph_format(border={...})`` writes ``hh:paraPr/hh:border``
with a ``hh:borderFill`` for the chosen sides. ``connect=True`` lets Hancom
draw consecutive paragraphs that share the paragraph shape as one box.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.package_validator import validate_editor_open_safety

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SIDES = ("leftBorder", "rightBorder", "topBorder", "bottomBorder")


def _parts(document: HwpxDocument) -> tuple[etree._Element, etree._Element]:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return (
            etree.fromstring(archive.read("Contents/header.xml")),
            etree.fromstring(archive.read("Contents/section0.xml")),
        )


def _para_pr_ids(section: etree._Element) -> list[str | None]:
    return [paragraph.get("paraPrIDRef") for paragraph in section.findall(f"{HP}p")]


def _border(header: etree._Element, para_pr_id: str | None) -> dict[str, str]:
    para_pr = next(el for el in header.iter(f"{HH}paraPr") if el.get("id") == para_pr_id)
    border = para_pr.find(f"{HH}border")
    assert border is not None
    return dict(border.attrib)


def _sides(header: etree._Element, border_fill_id: str) -> dict[str, tuple[str | None, ...]]:
    border_fill = next(el for el in header.iter(f"{HH}borderFill") if el.get("id") == border_fill_id)
    return {
        side: (line.get("type"), line.get("width"), line.get("color"))
        for side in SIDES
        if (line := border_fill.find(f"{HH}{side}")) is not None
    }


def _document(paragraphs: int = 4) -> HwpxDocument:
    document = HwpxDocument.new()
    for index in range(paragraphs):
        document.add_paragraph(f"지문 {index}")
    return document


def test_a_connected_box_writes_hancom_border_attributes() -> None:
    document = _document()

    document.styles.apply_paragraph_format(
        paragraph_indexes=[1, 2, 3], border={"connect": True, "offset_mm": (2, 2, 1, 1)}
    )

    header, section = _parts(document)
    ids = _para_pr_ids(section)
    assert ids[1] == ids[2] == ids[3] != ids[0]
    border = _border(header, ids[1])
    assert {key: value for key, value in border.items() if key != "borderFillIDRef"} == {
        "offsetLeft": "567",
        "offsetRight": "567",
        "offsetTop": "283",
        "offsetBottom": "283",
        "connect": "1",
        "ignoreMargin": "0",
    }
    assert _sides(header, border["borderFillIDRef"]) == {
        side: ("SOLID", "0.12 mm", "#000000") for side in SIDES
    }


def test_chosen_sides_line_and_margin_flag() -> None:
    document = _document()

    document.styles.apply_paragraph_format(
        paragraph_index=1,
        border={"sides": ("top", "bottom"), "color": "#FF0000", "width": "0.4 mm", "type": "DASH", "ignore_margin": True},
    )

    header, section = _parts(document)
    border = _border(header, _para_pr_ids(section)[1])
    assert (border["connect"], border["ignoreMargin"], border["offsetLeft"]) == ("0", "1", "0")
    sides = _sides(header, border["borderFillIDRef"])
    assert sides["topBorder"] == sides["bottomBorder"] == ("DASH", "0.4 mm", "#FF0000")
    assert sides["leftBorder"][0] == sides["rightBorder"][0] == "NONE"


def test_an_empty_paragraph_with_the_same_border_shares_the_shape() -> None:
    document = _document()
    document.add_paragraph("")
    box = {"connect": True, "offset_mm": (2, 2, 1, 1)}

    document.styles.apply_paragraph_format(paragraph_indexes=[1, 2], border=box)
    document.styles.apply_paragraph_format(paragraph_index=4, border=box)

    ids = _para_pr_ids(_parts(document)[1])
    assert ids[1] == ids[2] == ids[4]


def test_one_offset_and_one_side_may_be_given_alone() -> None:
    document = _document()

    document.styles.apply_paragraph_format(paragraph_index=1, border={"sides": "left", "offset_mm": 2})

    header, section = _parts(document)
    border = _border(header, _para_pr_ids(section)[1])
    assert {border[key] for key in ("offsetLeft", "offsetRight", "offsetTop", "offsetBottom")} == {"567"}
    sides = _sides(header, border["borderFillIDRef"])
    assert [side for side, line in sides.items() if line[0] != "NONE"] == ["leftBorder"]


def test_bottom_border_keeps_its_bottom_only_line() -> None:
    document = _document()

    document.styles.apply_paragraph_format(paragraph_index=1, bottom_border=True)

    header, section = _parts(document)
    border = _border(header, _para_pr_ids(section)[1])
    assert (border["offsetBottom"], border["connect"]) == ("0", "0")
    sides = _sides(header, border["borderFillIDRef"])
    assert sides["bottomBorder"] == ("SOLID", "0.12 mm", "#BFBFBF")
    assert {sides[side][0] for side in ("leftBorder", "rightBorder", "topBorder")} == {"NONE"}


def test_a_bordered_box_survives_a_save_and_stays_open_safe(tmp_path: Path) -> None:
    document = _document()
    document.styles.apply_paragraph_format(paragraph_indexes=[1, 2, 3], border={"connect": True})
    path = tmp_path / "box.hwpx"
    document.save_to_path(path)

    assert validate_editor_open_safety(path).ok
    header, section = _parts(HwpxDocument.open(path))
    assert _border(header, _para_pr_ids(section)[2])["connect"] == "1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"border": {"sides": ("left",), "colour": "#000000"}},
        {"border": {"sides": ("inside",)}},
        {"border": {"sides": ()}},
        {"border": {"offset_mm": (1, 1, 1)}},
        {"border": {"offset_mm": (1, 1, 1, -1)}},
        {"border": {"offset_mm": (1, 1, 1, "2")}},
        {"border": {}, "bottom_border": True},
    ],
)
def test_an_invalid_border_is_rejected(kwargs: dict[str, Any]) -> None:
    document = _document()

    with pytest.raises(HwpxValueError) as caught:
        document.styles.apply_paragraph_format(paragraph_index=1, **kwargs)

    assert caught.value.code == "paragraph-border-invalid"
