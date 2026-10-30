# SPDX-License-Identifier: Apache-2.0
"""A fill refreshes its result without rebuilding unrelated field payloads."""
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx._document import fields

FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _snapshot(field) -> dict[str, object]:
    return {name: getattr(field, name) for name in (
        "field_id", "name", "prompt", "memo", "editable", "value", "field_type",
        "is_placeholder", "location", "parameters", "has_end",
    )}


@pytest.mark.parametrize("selector", ["name", "field_id", "field_index"])
@pytest.mark.parametrize("prompt", ["", "placeholder"])
def test_fill_builds_only_one_post_write_payload(
    monkeypatch: pytest.MonkeyPatch, selector: str, prompt: str
) -> None:
    doc = HwpxDocument.new()
    for index in range(10):
        doc.fields.add(f"field-{index}", prompt=prompt, paragraph=doc.add_paragraph(""))
    target = doc.fields.all[5]
    requested = {selector: {"name": target.name, "field_id": target.field_id, "field_index": 5}[selector]}
    original = fields._form_field_payload
    built = []

    def counted(*args, **kwargs):
        built.append(kwargs["field_begin"])
        return original(*args, **kwargs)

    monkeypatch.setattr(fields, "_form_field_payload", counted)
    result = doc.fields.fill("first\r\nsecond\x00", **requested)

    # Selection still checks every field (including duplicates), but refreshing the returned result needs
    # just the selected one. This budget guards the independently measured 2N payloads per fill regression.
    assert len(built) == 11
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
