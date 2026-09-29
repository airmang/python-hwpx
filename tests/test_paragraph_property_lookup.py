"""``HwpxOxmlHeader.paragraph_property`` parses only the paragraph shape asked for, found under the same
keys as ``paragraph_properties``.

``error__20230728__test.hwpx`` is a Hancom document with some two hundred paragraph shapes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import hwpx.oxml.header_part as header_part
from hwpx import HwpxDocument

FIXTURE = Path(__file__).parent / "fixtures" / "hwpxlib_corpus" / "error__20230728__test.hwpx"


def test_every_paragraph_shape_is_the_one_the_list_gives() -> None:
    header = HwpxDocument.open(FIXTURE)._root.headers[0]
    shapes = header.paragraph_properties

    assert len(shapes) > 200
    assert all(header.paragraph_property(key) == shape for key, shape in shapes.items())
    assert header.paragraph_property(999999) is None
    assert header.paragraph_property(None) is None


@pytest.mark.parametrize("key", ["07", "7", 7, " 7 "])
def test_a_zero_padded_id_is_found_as_the_list_finds_it(key: object) -> None:
    document = HwpxDocument.new()
    header = document._root.headers[0]
    shapes = [child for child in header._para_properties_element() if child.tag.endswith("paraPr")]
    shapes[-1].set("id", "07")

    assert header.paragraph_property(key) == header._lookup_by_id(header.paragraph_properties, key)


def test_a_lookup_parses_one_paragraph_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    header = HwpxDocument.open(FIXTURE)._root.headers[0]
    parsed = []
    real = header_part.parse_paragraph_property

    def counting(node: object) -> object:
        parsed.append(node)
        return real(node)

    monkeypatch.setattr(header_part, "parse_paragraph_property", counting)

    assert header.paragraph_property("0") is not None
    assert len(parsed) == 1
