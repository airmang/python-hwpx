"""Looking one definition up costs the same however many the header has, and still reads the header
as it is now.

``doc.styles.char_properties`` re-signed every ``hh:charPr`` on each read (7.0 dev, #748), so a
caller asking once per paragraph (rich Markdown, ingest) went quadratic; paragraph shapes, styles,
tab definitions and border fills were found by walking their whole list per lookup. The counts
below are of the work a lookup does on the list (signatures made, children named), compared
between a small and a large header: equal counts mean the lookup does not walk the list.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Callable

import pytest

from hwpx import HwpxDocument
from hwpx.oxml import formatting, header_part, run

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_BOXES = {"charPr": "charProperties", "paraPr": "paraProperties", "style": "styles",
          "tabPr": "tabProperties", "borderFill": "borderFills"}


def _box(doc: HwpxDocument, tag: str):
    return doc.oxml.headers[0].element.find(f"{HH}refList/{HH}{_BOXES[tag]}")


def _add_copies(doc: HwpxDocument, tag: str, count: int) -> list[str]:
    """*count* copies of the first ``hh:<tag>`` added through the XML, each its own id."""

    box = _box(doc, tag)
    first = box.find(f"{HH}{tag}")
    next_id = max(int(child.get("id")) for child in box.findall(f"{HH}{tag}")) + 1
    ids = []
    for offset in range(count):
        copy = deepcopy(first)
        copy.set("id", str(next_id + offset))
        if tag == "charPr":
            copy.set("height", str(1000 + offset))
        if tag == "style":
            copy.set("name", f"copy {offset}")
            copy.set("engName", f"copy {offset}")
        box.append(copy)
        ids.append(str(next_id + offset))
    box.set("itemCnt", str(len(box)))
    return ids


def _counting(monkeypatch: pytest.MonkeyPatch, module: object, name: str) -> list[int]:
    calls: list[int] = []
    original = getattr(module, name)

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, counted)
    return calls


def _char_work(monkeypatch: pytest.MonkeyPatch, shapes: int) -> int:
    doc = HwpxDocument.new()
    ids = _add_copies(doc, "charPr", shapes)
    asked = [ids[0], ids[-1], "0"]
    doc.styles.char_property(asked[0])  # the first read parses them all
    with monkeypatch.context() as patch:
        calls = _counting(patch, run, "_char_property_signature")
        for _ in range(200):
            chars = doc.styles.char_properties
            for key in asked:
                assert chars.get(key) is not None
                assert doc.styles.char_property(int(key)) is not None
        return len(calls)


def test_char_shape_lookups_do_not_walk_every_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    small = _char_work(monkeypatch, 10)
    assert small == _char_work(monkeypatch, 400)
    assert small <= 200 * 3 * 2  # one shape's signature per lookup


def _definition_work(monkeypatch: pytest.MonkeyPatch, count: int) -> int:
    doc = HwpxDocument.new()
    ids = {tag: _add_copies(doc, tag, count) for tag in ("paraPr", "style", "tabPr", "borderFill")}
    header = doc.oxml.headers[0]
    lookups: list[Callable[[], object]] = [
        lambda: doc.styles.paragraph_property(ids["paraPr"][-1]),
        lambda: doc.oxml.style(ids["style"][-1]),
        lambda: header.style(int(ids["style"][0])),
        lambda: doc.styles.tab_property(ids["tabPr"][-1]),
        lambda: doc.styles.border_fill(ids["borderFill"][-1]),
        lambda: doc.oxml.border_fill(ids["borderFill"][0]),
        lambda: formatting.find_definition(header, "paraPr", ids["paraPr"][0]),
    ]
    for lookup in lookups:  # the first lookup of a kind reads its ids once
        assert lookup() is not None
    with monkeypatch.context() as patch:
        calls = _counting(patch, header_part, "_element_local_name")
        for _ in range(100):
            for lookup in lookups:
                assert lookup() is not None
        return len(calls)


def test_definition_lookups_do_not_walk_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _definition_work(monkeypatch, 5) == _definition_work(monkeypatch, 300)


# -- the lookups still read the header as it is now ---------------------------------------


def test_char_properties_is_a_view_of_the_header_now() -> None:
    doc = HwpxDocument.new()
    ids = _add_copies(doc, "charPr", 3)
    chars = doc.styles.char_properties
    before = dict(chars)
    box = _box(doc, "charPr")

    box.find(f"{HH}charPr[@id='{ids[0]}']").set("height", "3100")
    assert chars[ids[0]].size == 31.0 and before[ids[0]].size == 10.0  # dict() keeps the copy

    box.find(f"{HH}charPr[@id='{ids[1]}']").set("id", "900")  # an id changed in place
    assert ids[1] not in chars and chars["900"].size == 10.01
    assert doc.styles.char_property(900) == chars["900"]

    box.remove(box.find(f"{HH}charPr[@id='{ids[2]}']"))
    assert ids[2] not in chars and doc.styles.char_property(ids[2]) is None
    assert len(chars) == len(before) - 1
    assert set(chars) == (set(before) - {ids[1], ids[2]}) | {"900"}


def test_a_font_renamed_through_the_xml_is_read() -> None:
    doc = HwpxDocument.new()
    font = doc.styles.char_property("0").font
    assert font
    for face in doc.oxml.headers[0].element.iter(f"{HH}font"):
        if face.get("face") == font:
            face.set("face", "바뀐 글꼴")
    assert doc.styles.char_property("0").font == "바뀐 글꼴"
    assert doc.styles.char_properties["0"].fonts["HANGUL"] == "바뀐 글꼴"


@pytest.mark.parametrize("tag", ["paraPr", "style", "tabPr", "borderFill"])
def test_definition_lookups_see_xml_edits(tag: str) -> None:
    doc = HwpxDocument.new()
    ids = _add_copies(doc, tag, 3)
    header = doc.oxml.headers[0]
    read = {
        "paraPr": lambda key: doc.styles.paragraph_property(key),
        "style": lambda key: doc.oxml.style(key),
        "tabPr": lambda key: doc.styles.tab_property(key),
        "borderFill": lambda key: doc.styles.border_fill(key),
    }[tag]
    box = _box(doc, tag)

    def element(key: str):
        # formatting.find_definition takes the refList kinds; a style is found by its value only
        if tag == "style":
            return box.find(f"{HH}style[@id='{key}']") if read(key) is not None else None
        return formatting.find_definition(header, tag, key)

    assert read(ids[0]) is not None and element(ids[0]) is not None

    box.find(f"{HH}{tag}[@id='{ids[0]}']").set("id", "900")  # given another id in place
    assert read(ids[0]) is None and element(ids[0]) is None
    assert read("900") is not None and read(900) == read("900")
    assert element("900") is box.find(f"{HH}{tag}[@id='900']")

    box.remove(box.find(f"{HH}{tag}[@id='{ids[1]}']"))
    assert read(ids[1]) is None and element(ids[1]) is None

    replacement = deepcopy(box.find(f"{HH}{tag}[@id='{ids[2]}']"))
    box.replace(box.find(f"{HH}{tag}[@id='{ids[2]}']"), replacement)
    assert element(ids[2]) is replacement and read(ids[2]) is not None


def test_a_changed_style_reads_its_new_values() -> None:
    doc = HwpxDocument.new()
    ids = _add_copies(doc, "style", 2)
    assert doc.oxml.style(ids[0]).name == "copy 0"
    _box(doc, "style").find(f"{HH}style[@id='{ids[0]}']").set("name", "고친 이름")
    assert doc.oxml.style(ids[0]).name == "고친 이름"
    assert doc.oxml.headers[0].style(ids[0]) == doc.oxml.styles[ids[0]]
