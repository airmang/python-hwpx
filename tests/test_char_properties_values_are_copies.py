"""A character shape read from doc.styles.char_properties or char_property is a reading of the header: changing
its attributes changes nothing a later read answers (exec7/rv-ranges)."""
from __future__ import annotations

from hwpx import HwpxDocument


def test_changing_a_read_character_shape_changes_no_later_read() -> None:
    document = HwpxDocument.new()
    view = document.styles.char_properties
    key = next(iter(view))
    color = view[key].color
    view[key].attributes["textColor"] = "#ABCDEF"
    document.styles.char_property(key).attributes["textColor"] = "#ABCDEF"
    next(iter(view.values())).child_attributes.setdefault("x", {})["y"] = "z"
    assert view[key].color == color
    assert document.styles.char_property(key).color == color
    assert HwpxDocument.open(document.to_bytes()).styles.char_property(key).color == color
