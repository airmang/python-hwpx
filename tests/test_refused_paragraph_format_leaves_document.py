"""A refused ``apply_paragraph_format`` leaves the document byte-identical (exec7/rv3).

#801 made the character-shape calls refuse whole. ``doc.styles.apply_paragraph_format`` still wrote the
tab definition (and the border's own definition) before it checked the alignment and the border, so a
call refused for either left a definition in the header. Every argument with one bad value among good
ones, on a document opened from bytes: when the call raises, ``to_bytes()`` is what it was.
"""

from __future__ import annotations

from typing import Any

import pytest

from hwpx import HwpxDocument

_GOOD: dict[str, Any] = {
    "alignment": "CENTER",
    "line_spacing": 180,
    "indent_left_mm": 3.0,
    "indent_right_mm": 3.0,
    "first_line_indent_mm": 2.0,
    "spacing_before_pt": 4,
    "spacing_after_pt": 4,
    "outline_level": 1,
    "keep_with_next": True,
    "keep_lines": True,
    "page_break_before": True,
    "column_break": True,
    "tab_stops": [{"pos_mm": 30, "type": "LEFT"}],
    "auto_tab_left": True,
    "auto_tab_right": True,
    "border": {"sides": ["bottom"], "width_mm": 0.4},
}
_BAD: tuple[Any, ...] = (
    {"sides": ["diagonal"]},
    {"sides": ["bottom"], "type": "WAVY-NOT-A-TYPE"},
    {"sides": ["bottom"], "color": "not-a-colour"},
    {"sides": ["bottom"], "width": "0.4 mm"},
    [{"pos_mm": 30, "type": "SIDEWAYS"}],
    [{"pos_mm": -5}],
    "bad-value",
    -99999,
    10**9,
    1.5,
    "",
    [],
    object(),
)


def _document() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("가나 ab")
    return HwpxDocument.open(document.to_bytes())


def test_the_good_call_formats_the_paragraph() -> None:
    document = _document()
    before = document.to_bytes()
    document.styles.apply_paragraph_format(paragraph=0, **_GOOD)
    assert document.to_bytes() != before


@pytest.mark.parametrize("argument", sorted(_GOOD))
def test_one_bad_argument_among_good_ones_changes_nothing(argument: str) -> None:
    refused = 0
    for bad in _BAD:
        document = _document()
        before = document.to_bytes()
        try:
            document.styles.apply_paragraph_format(paragraph=0, **{**_GOOD, argument: bad})
        except Exception:
            refused += 1
            assert document.to_bytes() == before, (argument, bad)
    if argument in {"alignment", "border", "tab_stops"}:
        assert refused  # these have values the call refuses


def test_the_reported_case_a_new_tab_stop_with_a_bad_border_side() -> None:
    document = _document()
    before = document.to_bytes()
    tab_definitions = len(document.styles.tab_properties)

    with pytest.raises(ValueError) as refused:
        document.styles.apply_paragraph_format(
            paragraph=0, tab_stops=[{"pos_mm": 17}], border={"sides": ["diagonal"]}
        )

    assert getattr(refused.value, "code", None) == "paragraph-border-invalid"
    assert len(document.styles.tab_properties) == tab_definitions
    assert document.to_bytes() == before


def test_a_refused_tab_stop_leaves_a_header_without_a_tab_list_as_it_is() -> None:
    """``hh:tabProperties`` is optional. A header without it gained an empty one before the tab stop was
    checked, on ``apply_paragraph_format`` and on ``ensure_tab_definition``."""

    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    tabs = header.element.find(".//{*}tabProperties")
    tabs.getparent().remove(tabs)
    for para_pr in header.element.iterfind(".//{*}paraPr"):
        para_pr.attrib.pop("tabPrIDRef", None)
    header.mark_dirty()
    document = HwpxDocument.open(document.to_bytes())
    before = document.to_bytes()

    with pytest.raises(ValueError) as refused:
        document.styles.apply_paragraph_format(paragraph=0, tab_stops=[{"pos_mm": 2, "type": "BAD"}])
    assert getattr(refused.value, "code", None) == "paragraph-tab-type-invalid"
    assert document.to_bytes() == before

    with pytest.raises(ValueError):
        document.styles.ensure_tab_definition(tab_stops=[{"pos": 2000, "type": "BAD"}])
    assert document.to_bytes() == before
