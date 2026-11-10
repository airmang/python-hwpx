"""Header lookups keep their parsed result and follow every change to the header XML."""

from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.oxml import header_part

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


@pytest.fixture
def parses(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    for name in ("parse_paragraph_property", "parse_paragraph_properties", "parse_styles", "parse_tab_definitions", "parse_border_fills"):
        original = getattr(header_part, name)

        def counting(node, _original=original, _name=name):
            calls.append(_name)
            return _original(node)

        monkeypatch.setattr(header_part, name, counting)
    return calls


def test_repeated_lookups_parse_once(parses: list[str]) -> None:
    document = HwpxDocument.new()
    header = document.oxml.headers[0]

    first = header.paragraph_property(0)
    for _ in range(5):
        assert header.paragraph_property(0) == first
        assert header.style(0) is not None
        assert header.tab_property(0) is not None
        assert header.border_fill(1) is not None
        assert header.paragraph_properties

    assert sorted(parses) == sorted(
        ["parse_paragraph_property", "parse_styles", "parse_tab_definitions", "parse_border_fills", "parse_paragraph_properties"]
    )


def test_lookup_follows_an_edit_through_the_api() -> None:
    document = HwpxDocument.new()
    before = dict(document.styles.paragraph_properties)

    new_id = document.oxml.headers[0].ensure_paragraph_format(base_para_pr_id=0, alignment="CENTER")

    after = document.styles.paragraph_properties
    assert str(new_id) in after and str(new_id) not in before
    assert document.styles.paragraph_property(new_id) is not None


def test_lookup_follows_a_raw_xml_edit_without_mark_dirty() -> None:
    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    assert header.paragraph_property(0).tab_pr_id_ref == 0
    assert header.style(0).name
    assert header.paragraph_properties["0"].tab_pr_id_ref == 0

    para_pr = next(child for child in header._para_properties_element() if child.get("id") == "0")
    para_pr.set("tabPrIDRef", "1")
    style = next(child for child in header._styles_element() if child.get("id") == "0")
    style.set("name", "changed outside")

    assert header.paragraph_property(0).tab_pr_id_ref == 1
    assert header.paragraph_properties["0"].tab_pr_id_ref == 1
    assert header.style(0).name == "changed outside"
    assert document.styles.get(0).name == "changed outside"


def test_mark_dirty_drops_the_kept_results(parses: list[str]) -> None:
    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    header.paragraph_property(0)
    header.mark_dirty()
    header.paragraph_property(0)

    assert parses.count("parse_paragraph_property") == 2


def test_mappings_are_new_dicts_each_time() -> None:
    document = HwpxDocument.new()
    header = document.oxml.headers[0]

    styles = header.styles
    styles.clear()

    assert header.styles
    assert header.paragraph_properties is not header.paragraph_properties
