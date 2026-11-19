"""asks11: three requests to ``doc.styles`` met with the form Hancom saves.

1. A border fill ``ensure_border_fill`` builds writes the ``hh:diagonal`` every Hancom-saved border fill has
   (all 3,511 in the 1,265 fixtures: ``SOLID 0.1 mm #000000``), not ``NONE`` at the side's width; one derived
   from another keeps the diagonal it read.
2. ``ensure_run(letter_spacing_by_lang=)`` takes a 자간 per language under ``font_by_lang``'s rules; a language
   it does not name keeps the base's value.
"""

from __future__ import annotations

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
HH = f"{{{HH_NS}}}"


def _header(doc: HwpxDocument):
    return doc.oxml.headers[0].element


def _border_fill(doc: HwpxDocument, fill_id: str):
    return next(node for node in _header(doc).iter(f"{HH}borderFill") if node.get("id") == fill_id)


def _diagonal(doc: HwpxDocument, fill_id: str) -> dict[str, str]:
    node = _border_fill(doc, fill_id).find(f"{HH}diagonal")
    assert node is not None
    return dict(node.attrib)


# -- 1. diagonal ------------------------------------------------------------------------------------------


def test_a_new_border_fill_writes_hancoms_diagonal_whatever_its_sides() -> None:
    doc = HwpxDocument.new()
    hancom = {"type": "SOLID", "width": "0.1 mm", "color": "#000000"}
    plain = doc.styles.ensure_border_fill()
    thick = doc.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.4, border_type="DASH")
    sided = doc.styles.ensure_border_fill(sides={"top": {"width_mm": 0.5}, "left": None}, fill_color="#DDEBF7")
    for fill_id in (plain, thick, sided):
        assert _diagonal(doc, fill_id) == hancom
    # slash/backSlash stay NONE: the diagonal line draws nothing.
    for name in ("slash", "backSlash"):
        node = _border_fill(doc, thick).find(f"{HH}{name}")
        assert node is not None and node.get("type") == "NONE"


def test_the_same_request_again_reuses_the_definition_it_built() -> None:
    doc = HwpxDocument.new()
    first = doc.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.4)
    count = len(list(_header(doc).iter(f"{HH}borderFill")))
    assert doc.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.4) == first
    assert len(list(_header(doc).iter(f"{HH}borderFill"))) == count


def test_a_definition_with_a_drawn_slash_is_not_taken_for_a_plain_one() -> None:
    doc = HwpxDocument.new()
    plain = doc.styles.ensure_border_fill(border_color="#123456")
    slash = _border_fill(doc, plain).find(f"{HH}slash")
    assert slash is not None
    slash.set("type", "CENTER")
    again = doc.styles.ensure_border_fill(border_color="#123456")
    assert again != plain
    assert _diagonal(doc, again) == {"type": "SOLID", "width": "0.1 mm", "color": "#000000"}


def test_a_border_fill_derived_from_another_keeps_the_diagonal_it_read() -> None:
    doc = HwpxDocument.new()
    container = _header(doc).find(f".//{HH}borderFills")
    assert container is not None
    wrapped = (
        f'<root xmlns:hh="{HH_NS}" xmlns:hc="{HC_NS}">'
        '<hh:borderFill id="77" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:diagonal type="DASH" width="0.5 mm" color="#00FF00"/>'
        "</hh:borderFill></root>"
    )
    container.append(etree.fromstring(wrapped)[0])
    derived = doc.styles.ensure_border_fill(base_border_fill_id_ref="77", sides={"bottom": {"width_mm": 0.4}})
    assert derived != "77"
    assert _diagonal(doc, derived) == {"type": "DASH", "width": "0.5 mm", "color": "#00FF00"}


# -- 2. letter_spacing_by_lang ---------------------------------------------------------------------------

LANG_ATTRS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")


def _char_pr(doc: HwpxDocument, char_pr_id: str):
    element = _header(doc).find(f".//{HH}charPr[@id='{char_pr_id}']")
    assert element is not None
    return element


def _spacing(doc: HwpxDocument, char_pr_id: str) -> dict[str, str]:
    node = _char_pr(doc, char_pr_id).find(f"{HH}spacing")
    assert node is not None
    return {attr: node.get(attr) for attr in LANG_ATTRS}


def _base_with_spacing(doc: HwpxDocument, values: dict[str, int]) -> str:
    """A shape like the template's tight placeholder runs: -50 in some languages."""

    base = doc.styles.ensure_run(letter_spacing=0, color="#123456")
    node = _char_pr(doc, base).find(f"{HH}spacing")
    for attr, value in values.items():
        node.set(attr, str(value))
    return base


def test_letter_spacing_by_lang_changes_only_the_languages_it_names() -> None:
    doc = HwpxDocument.new()
    base = _base_with_spacing(doc, {"hangul": -50, "latin": -45, "hanja": -10})
    before = etree.tostring(_char_pr(doc, base))
    fixed = doc.styles.ensure_run(base_char_pr_id_ref=base, letter_spacing_by_lang={"hangul": 0, "LATIN": -5})
    assert fixed != base
    assert _spacing(doc, fixed) == {"hangul": "0", "latin": "-5", "hanja": "-10", "japanese": "0", "other": "0",
                                    "symbol": "0", "user": "0"}
    assert etree.tostring(_char_pr(doc, base)) == before  # the base stays as it was
    assert _char_pr(doc, fixed).get("textColor") == "#123456"  # the rest follows the base
    again = doc.styles.ensure_run(base_char_pr_id_ref=base, letter_spacing_by_lang={"LATIN": -5, "Hangul": 0})
    assert again == fixed  # the same request reuses it


def test_letter_spacing_by_lang_wins_over_letter_spacing() -> None:
    doc = HwpxDocument.new()
    both = doc.styles.ensure_run(letter_spacing=-10, letter_spacing_by_lang={"HANGUL": 5})
    assert _spacing(doc, both) == {attr: ("5" if attr == "hangul" else "-10") for attr in LANG_ATTRS}


def test_a_base_without_spacing_gets_all_seven_with_the_schema_default() -> None:
    doc = HwpxDocument.new()
    base = _char_pr(doc, "0")
    spacing = base.find(f"{HH}spacing")
    if spacing is not None:
        base.remove(spacing)
    made = doc.styles.ensure_run(base_char_pr_id_ref="0", letter_spacing_by_lang={"USER": 3})
    assert _spacing(doc, made) == {attr: ("3" if attr == "user" else "0") for attr in LANG_ATTRS}
    children = [etree.QName(child).localname for child in _char_pr(doc, made)]
    assert children.index("spacing") == children.index("fontRef") + 2  # schema order: fontRef, ratio, spacing


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ([("HANGUL", 0)], "style-run-letter-spacing-by-lang-invalid"),
        ({1: 0}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": 0, "hangul": 1}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": "0"}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": True}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": 1.5}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": -51}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": 51}, "style-run-letter-spacing-by-lang-invalid"),
        ({"KOREAN": 0}, "style-font-lang-invalid"),
    ],
)
def test_letter_spacing_by_lang_is_checked_before_anything_changes(value: object, code: str) -> None:
    doc = HwpxDocument.new()
    before = etree.tostring(_header(doc))
    with pytest.raises(HwpxValueError) as caught:
        doc.styles.ensure_run(font="새글꼴", letter_spacing_by_lang=value)  # type: ignore[arg-type]
    assert caught.value.code == code
    assert etree.tostring(_header(doc)) == before
