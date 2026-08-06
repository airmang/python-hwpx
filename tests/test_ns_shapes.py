# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-B3 게이트 — `doc.shapes`."""

from __future__ import annotations

import warnings

import pytest

from hwpx import model
from hwpx.document import HwpxDocument
from hwpx.errors import HwpxError

CHART = b'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"/>'
MEMBERS = {
    "add_line": ((), model.Shape),
    "add_rectangle": ((), model.Shape),
    "add_ellipse": ((), model.Shape),
    "add_polygon": (([(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)],), model.Shape),
    "add_arc": ((), model.Shape),
    "add_chart": ((CHART,), model.InlineObject),
    "add_equation": (("x=1",), model.InlineObject),
    "add_raw": (("rect",), model.InlineObject),
    "add_control": ((), model.InlineObject),
}


@pytest.fixture()
def document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    return doc


@pytest.mark.parametrize("name", sorted(MEMBERS))
def test_every_shape_verb_delegates_and_returns_a_model_type(
    name: str, document: HwpxDocument
) -> None:
    args, expected = MEMBERS[name]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # 탈출구는 스스로 위험을 경고한다
        created = getattr(document.shapes, name)(*args, section=0)
    assert isinstance(created, expected)


@pytest.mark.parametrize("name", sorted(MEMBERS))
@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"section": 999}, "section-not-found"),
        ({"section": "0"}, "section-invalid-type"),
        ({"section": 0, "section_index": 0}, "section-argument-conflict"),
    ],
    ids=["out-of-range", "wrong-type", "conflict"],
)
def test_bad_sections_are_typed_errors(name, kwargs, code, document) -> None:
    args, _ = MEMBERS[name]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with pytest.raises(HwpxError) as excinfo:
            getattr(document.shapes, name)(*args, **kwargs)
    assert excinfo.value.code == code


def test_add_raw_is_named_for_what_it_is(document: HwpxDocument) -> None:
    """탈출구는 이름이 탈출구임을 말해야 한다 — 5.x 는 ``add_shape`` 였다."""

    assert hasattr(document.shapes, "add_raw")
    with pytest.warns(UserWarning) as record:
        document.shapes.add_raw("rect", section=0)
    assert "Hancom refuses to open" in str(record[0].message)


def test_the_moved_root_names_still_answer(document: HwpxDocument) -> None:
    for name, args in [("add_line", ()), ("add_rectangle", ()), ("add_chart", (CHART,))]:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with pytest.warns(DeprecationWarning):
                getattr(document, name)(*args, section_index=0)
