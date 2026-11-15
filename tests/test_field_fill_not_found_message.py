# SPDX-License-Identifier: Apache-2.0
"""fields.fill() says which name or index it could not find and what the document has."""

from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError


def _doc() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.fields.add("성명", section=0)
    doc.fields.add("학교", section=0)
    return doc


def test_an_unknown_name_names_itself_and_the_candidates() -> None:
    with pytest.raises(HwpxValueError) as excinfo:
        _doc().fields.fill(name="없는이름", value="x")

    message = str(excinfo.value)
    assert "없는이름" in message
    assert "'성명'" in message and "'학교'" in message
    assert "None" not in message
    assert excinfo.value.code == "field-not-found"
    assert excinfo.value.context["candidates"] == ["성명", "학교"]


def test_an_index_out_of_range_says_the_range() -> None:
    doc = _doc()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.fields.fill(field_index=99, value="x")

    message = str(excinfo.value)
    indexes = excinfo.value.context["indexes"]
    assert len(indexes) == 2
    assert "99" in message and "2 form fields" in message
    assert f"{indexes[0]}..{indexes[-1]}" in message


def test_a_document_without_fields_says_so() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError, match="no form fields"):
        doc.fields.fill(name="성명", value="x")
