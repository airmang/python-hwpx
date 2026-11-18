"""asks11: three requests to ``doc.styles`` met with the form Hancom saves.

1. A border fill ``ensure_border_fill`` builds writes the ``hh:diagonal`` every Hancom-saved border fill has
   (all 3,511 in the 1,265 fixtures: ``SOLID 0.1 mm #000000``), not ``NONE`` at the side's width; one derived
   from another keeps the diagonal it read.
"""

from __future__ import annotations

from lxml import etree

from hwpx import HwpxDocument

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
