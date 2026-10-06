"""``HwpxOxmlHeader.paragraph_property`` parses only the paragraph shape asked for, found under the same
keys as ``paragraph_properties``, and so does the document's ``paragraph_property``, which FormFit and
the page estimate call for each paragraph shape they meet.

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


def test_the_document_finds_each_shape_its_merged_list_gives() -> None:
    root = HwpxDocument.open(FIXTURE)._root
    shapes = root.paragraph_properties

    assert all(root.paragraph_property(key) == shape for key, shape in shapes.items())
    assert root.paragraph_property(999999) is None
    assert root.paragraph_property(None) is None
    for key in ("07", "7", 7, " 7 "):
        assert root.paragraph_property(key) == header_part.HwpxOxmlHeader._lookup_by_id(shapes, key)


def test_a_document_lookup_parses_one_paragraph_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    root = HwpxDocument.open(FIXTURE)._root
    parsed = []
    real = header_part.parse_paragraph_property

    def counting(node: object) -> object:
        parsed.append(node)
        return real(node)

    def whole_list(node: object) -> object:
        raise AssertionError("the whole paragraph shape list was parsed for one lookup")

    monkeypatch.setattr(header_part, "parse_paragraph_property", counting)
    monkeypatch.setattr(header_part, "parse_paragraph_properties", whole_list)

    assert root.paragraph_property("0") is not None
    assert len(parsed) == 1
