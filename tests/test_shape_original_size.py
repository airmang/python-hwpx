# SPDX-License-Identifier: Apache-2.0
"""``original_size`` on ``add_rectangle``/``add_ellipse`` sets ``hp:orgSz``
apart from the drawn size.

The expected layout is the one Hancom-saved corpus files use for a resized
shape: geometry in ``orgSz`` space, ``curSz`` equal to ``sz``, ``scaMatrix``
``e1``/``e5`` equal to ``curSz/orgSz``, and the rotation centre at half of
``curSz``. The first test reads that layout straight from the fixtures.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def _size(element: etree._Element, tag: str) -> tuple[int, int]:
    child = element.find(f"{HP}{tag}")
    assert child is not None
    return int(child.get("width")), int(child.get("height"))


def _point(element: etree._Element, tag: str) -> tuple[int, int]:
    child = element.find(f"{HC}{tag}")
    assert child is not None
    return int(child.get("x")), int(child.get("y"))


def _scale(element: etree._Element) -> dict[str, str]:
    matrix = element.find(f"{HP}renderingInfo/{HC}scaMatrix")
    assert matrix is not None
    return dict(matrix.attrib)


def _rotation_centre(element: etree._Element) -> tuple[int, int]:
    rotation = element.find(f"{HP}rotationInfo")
    assert rotation is not None
    return int(rotation.get("centerX")), int(rotation.get("centerY"))


@pytest.mark.parametrize(
    "fixture,tag,geometry",
    [
        ("error__20240305__2022.hwpx", "rect", "pt2"),
        ("error__20230728__test.hwpx", "rect", "pt2"),
        ("error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx", "ellipse", "ax2"),
    ],
)
def test_the_corpus_writes_resized_shapes_in_this_layout(fixture: str, tag: str, geometry: str) -> None:
    with zipfile.ZipFile(CORPUS / fixture) as archive:
        roots = [
            etree.fromstring(archive.read(name))
            for name in archive.namelist()
            if name.startswith("Contents/section")
        ]
    shape = next(
        el for root in roots for el in root.iter(f"{HP}{tag}")
        if _size(el, "orgSz") != _size(el, "curSz") and _size(el, "curSz")[1] != 0
    )
    org_w, org_h = _size(shape, "orgSz")
    cur_w, cur_h = _size(shape, "curSz")

    assert _point(shape, geometry) == (org_w, org_h if tag == "rect" else org_h // 2)
    assert _size(shape, "sz") == (cur_w, cur_h)
    assert _rotation_centre(shape) == (cur_w // 2, cur_h // 2)
    scale = _scale(shape)
    assert float(scale["e1"]) == pytest.approx(cur_w / org_w, abs=1e-6)
    assert float(scale["e5"]) == pytest.approx(cur_h / org_h, abs=1e-6)


def _only_shape(doc: HwpxDocument, tag: str) -> etree._Element:
    root = etree.fromstring(doc.oxml.sections[0].to_bytes())
    return next(root.iter(f"{HP}{tag}"))


def test_rectangle_original_size_is_written_apart_from_the_drawn_size() -> None:
    doc = HwpxDocument.new()
    shape = doc.shapes.add_rectangle(8503, 5446, original_size=(15182, 4070), treat_as_char=False)

    rect = _only_shape(doc, "rect")
    assert _size(rect, "orgSz") == (15182, 4070)
    assert _size(rect, "curSz") == (8503, 5446)
    assert _size(rect, "sz") == (8503, 5446)
    assert [_point(rect, f"pt{i}") for i in range(4)] == [
        (0, 0), (15182, 0), (15182, 4070), (0, 4070),
    ]
    assert _rotation_centre(rect) == (4251, 2723)
    assert _scale(rect) == {
        "e1": "0.560071", "e2": "0", "e3": "0", "e4": "0", "e5": "1.338084", "e6": "0",
    }
    assert (shape.width, shape.height) == (8503, 5446)


def test_ellipse_original_size_from_the_paragraph_api() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("", include_run=False)
    paragraph.add_ellipse(1713, 1712, original_size=(1672, 1670), fill_color="#783E94")

    ellipse = _only_shape(doc, "ellipse")
    assert _size(ellipse, "orgSz") == (1672, 1670)
    assert _size(ellipse, "curSz") == (1713, 1712)
    assert _point(ellipse, "center") == (836, 835)
    assert _point(ellipse, "ax1") == (1672, 835)
    assert _point(ellipse, "ax2") == (836, 1670)
    assert _scale(ellipse)["e1"] == "1.024522"
    assert _scale(ellipse)["e5"] == "1.02515"


def test_without_original_size_the_output_is_unchanged() -> None:
    plain, same = HwpxDocument.new(), HwpxDocument.new()
    plain.shapes.add_ellipse(1713, 1712)
    same.shapes.add_ellipse(1713, 1712, original_size=(1713, 1712))

    for doc in (plain, same):
        ellipse = _only_shape(doc, "ellipse")
        assert _size(ellipse, "orgSz") == _size(ellipse, "curSz") == (1713, 1712)
        assert _scale(ellipse)["e1"] == _scale(ellipse)["e5"] == "1"
    strip = {"id", "instid"}
    a, b = _only_shape(plain, "ellipse"), _only_shape(same, "ellipse")
    for el in (a, b):
        for key in strip:
            el.attrib.pop(key, None)
    assert etree.tostring(a) == etree.tostring(b)


def test_the_original_size_survives_save_reopen_and_resize() -> None:
    doc = HwpxDocument.new()
    doc.shapes.add_rectangle(8503, 5446, original_size=(15182, 4070))
    reopened = HwpxDocument.open(doc.to_bytes())
    rect = _only_shape(reopened, "rect")
    assert _size(rect, "orgSz") == (15182, 4070)

    shape = next(s for p in reopened.paragraphs for s in p.shapes)
    shape.resize(9000, 6000)
    rect = _only_shape(reopened, "rect")
    # resize() already rescales orgSz-space geometry and resets scaMatrix
    assert _size(rect, "orgSz") == _size(rect, "curSz") == (9000, 6000)
    assert _point(rect, "pt2") == (9000, 6000)
    assert _scale(rect)["e1"] == "1"


@pytest.mark.parametrize(
    "value", [(0, 10), (10, -1), (10,), (10.5, 3), (True, 3), "10x3", 10],
)
def test_a_bad_original_size_is_refused_before_anything_is_added(value: object) -> None:
    doc = HwpxDocument.new()
    before = len(doc.paragraphs)

    with pytest.raises(HwpxValueError) as caught:
        doc.shapes.add_rectangle(100, 100, original_size=value)  # type: ignore[arg-type]
    assert caught.value.code == "shape-original-size-invalid"
    assert len(doc.paragraphs) == before

    paragraph = doc.add_paragraph("", include_run=False)
    with pytest.raises(HwpxValueError):
        paragraph.add_ellipse(100, 100, original_size=value)  # type: ignore[arg-type]
    assert not paragraph.shapes
