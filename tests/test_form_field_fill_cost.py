# SPDX-License-Identifier: Apache-2.0
"""A fill refreshes its result without rebuilding unrelated field payloads."""
from copy import deepcopy
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx._document import fields
from hwpx.errors import HwpxValueError

FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _snapshot(field) -> dict[str, object]:
    return {name: getattr(field, name) for name in (
        "field_id", "name", "prompt", "memo", "editable", "value", "field_type",
        "is_placeholder", "location", "parameters", "has_end",
    )}


@pytest.mark.parametrize("selector", ["name", "field_id", "index"])
@pytest.mark.parametrize("prompt", ["", "placeholder"])
def test_fill_builds_only_one_post_write_payload(
    monkeypatch: pytest.MonkeyPatch, selector: str, prompt: str
) -> None:
    doc = HwpxDocument.new()
    for index in range(10):
        doc.fields.add(f"field-{index}", prompt=prompt, paragraph=doc.add_paragraph(""))
    target = doc.fields.all[5]
    requested = {selector: {"name": target.name, "field_id": target.field_id, "index": 5}[selector]}
    original = fields._form_field_payload
    built = []

    def counted(*args, **kwargs):
        built.append(kwargs["field_begin"])
        return original(*args, **kwargs)

    monkeypatch.setattr(fields, "_form_field_payload", counted)
    result = doc.fields.fill("first\r\nsecond\x00", **requested)

    # Selecting reads only the named field's paragraph (#628) and refreshing the returned result needs just
    # the selected one. This budget guards the measured 2N, then N + 1, payloads per fill.
    assert len(built) == 2
    assert result.before == prompt
    assert result.after == "first\nsecond"
    assert _snapshot(result.field) == _snapshot(doc.fields.all[5])
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.fields.all[5].value == result.after
    assert result.field.location == reopened.fields.all[5].location


@pytest.mark.parametrize("fixture,name", [
    ("form_fields_spanning_before.hwpx", "본문"),
    ("form_fields_spanning_before.hwpx", "칸"),
    ("nested_field_saved.hwpx", "바깥"),
    ("nested_field_saved.hwpx", "안쪽"),
])
def test_refreshed_result_matches_a_fresh_listing_after_structural_fill(fixture: str, name: str) -> None:
    doc = HwpxDocument.open((FIXTURES / fixture).read_bytes())
    result = doc.fields.fill("first\r\nsecond", name=name)
    fresh = next(field for field in doc.fields.all if field.name == name)

    assert result.after == "first\nsecond"
    assert _snapshot(result.field) == _snapshot(fresh)
    reopened = HwpxDocument.open(doc.to_bytes())
    fresh = next(field for field in reopened.fields.all if field.name == name)
    assert _snapshot(result.field) == _snapshot(fresh)


# -- filling one field after another reads only the named field (#628) -----------------------------


def _same(left: object, right: object) -> bool:
    """Match payload values compared as the full read would give them: elements by identity, paragraph
    views by their element."""

    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return type(left) is type(right) and len(left) == len(right) and all(map(_same, left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same(left[key], right[key]) for key in left)
    if hasattr(left, "element") and hasattr(right, "element"):
        return left.element is right.element
    if isinstance(left, etree._Element) or isinstance(right, etree._Element):
        return left is right
    return left == right


def _full_read(doc: HwpxDocument, **selector: object) -> dict | None:
    try:
        return fields._select_form_field(doc, fields._iter_form_field_matches(doc), **selector)
    except HwpxValueError:
        return None


def _assert_quick_pick_is_the_full_read(doc: HwpxDocument) -> int:
    checked = 0
    for match in fields._iter_form_field_matches(doc):
        for selector in (
            {"index": match["index"], "field_id": None, "name": None},
            {"index": None, "field_id": match["field_id"], "name": None},
            {"index": None, "field_id": None, "name": match["name"]},
            {"index": None, "field_id": None, "name": match["prompt"]},
        ):
            full = _full_read(doc, **selector)
            quick = fields._pick_form_field(doc, **selector)
            # None from the quick read sends the call to the full read, which then words the error
            assert _same(quick, full), selector
            checked += 1
    return checked


def _nested_document() -> HwpxDocument:
    """Fields in table cells, one after a table in the paragraph that holds it, and one in a memo body."""

    doc = HwpxDocument.new()
    doc.fields.add("first", prompt="type here")
    holder = doc.add_paragraph("")
    table = holder.add_table(2, 2)
    doc.fields.add("cell", prompt="cell prompt", paragraph=table.cell(0, 0).paragraphs[0])
    inner = table.cell(1, 1).paragraphs[0].add_table(1, 1)
    doc.fields.add("inner", paragraph=inner.cell(0, 0).paragraphs[0])
    doc.fields.add("after table", paragraph=holder)
    doc.fields.add("last", prompt="first")  # its prompt is another field's name
    doc.fields.add("Twin")
    doc.fields.add("twin")  # a name that differs only in case is the same name to fill(name=)
    section = doc.sections[0].element
    hp = section.nsmap["hp"]
    memo_group = etree.SubElement(section, f"{{{hp}}}memogroup")
    memo_group.append(deepcopy(fields._iter_form_field_matches(doc)[0]["_paragraph"].element))
    return doc


def test_the_quick_pick_is_the_entry_the_full_read_gives_in_a_nested_document() -> None:
    doc = _nested_document()
    names = [field.name for field in doc.fields.all]
    # the paragraph holding the table lists its own field before the fields in its cells
    assert names == ["first", "after table", "cell", "inner", "last", "Twin", "twin"]
    assert _assert_quick_pick_is_the_full_read(doc) == 4 * len(names)


@pytest.mark.parametrize(
    "fixture",
    sorted(path.name for path in FIXTURES.glob("*field*.hwpx"))
    + ["pages_click_here_field_around_a_table_wider_than_the_line.hwpx"],
)
def test_the_quick_pick_is_the_entry_the_full_read_gives_in_hancom_files(fixture: str) -> None:
    doc = HwpxDocument.open((FIXTURES / fixture).read_bytes())
    _assert_quick_pick_is_the_full_read(doc)


def test_filling_fields_one_after_another_reads_no_other_field(monkeypatch: pytest.MonkeyPatch) -> None:
    source = HwpxDocument.new()
    for index in range(30):
        source.fields.add(f"f{index}", prompt="here")
    data = source.to_bytes()

    expected = HwpxDocument.open(data)
    with monkeypatch.context() as patched:
        patched.setattr(fields, "_pick_form_field", lambda doc, **selector: None)  # the full read every time
        for index in range(30):
            expected.fields.fill(f"value {index}", name=f"f{index}" if index % 2 else None, index=None if index % 2 else index)

    def full_read(_doc):
        raise AssertionError("a fill that names one field read every field")

    doc = HwpxDocument.open(data)
    monkeypatch.setattr(fields, "_iter_form_field_matches", full_read)
    for index in range(30):
        doc.fields.fill(f"value {index}", name=f"f{index}" if index % 2 else None, index=None if index % 2 else index)
    assert doc.to_bytes() == expected.to_bytes()
