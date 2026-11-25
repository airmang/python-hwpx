# SPDX-License-Identifier: Apache-2.0
"""What a write that is refused leaves behind: the target as it was, and no other file.

Each test here is the reproduction of one finding of the 2026-11 write-path audit (issue 834),
made with documents built in the test.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.body_patch import apply_body_ops, recolor_runs_by_color, strip_runs_by_color
from hwpx.patch import paragraph_patch
from hwpx.table_patch import apply_table_ops, fill_cells, strip_trailing_table_captions
from hwpx.tools import validator as validator_module
from hwpx.tools.package_validator import validate_editor_open_safety

SECTION = "Contents/section0.xml"


def _base() -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("alpha one")
    doc.add_paragraph("beta two")
    table = doc.add_table(2, 2)
    for row in range(2):
        for col in range(2):
            table.set_cell_text(row, col, f"c{row}{col}")
    doc.add_paragraph("gamma three")
    return doc.to_bytes()


def _section(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(SECTION).decode("utf-8")


def _with_section(data: bytes, xml: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            target.writestr(info, xml.encode("utf-8") if info.filename == SECTION else source.read(info.filename))
    return out.getvalue()


def _field_over_two_paragraphs() -> bytes:
    """A click-here field that begins in one paragraph and ends at the start of the next: deleting
    the first leaves an end without its begin, which Hancom refuses to open."""

    doc = HwpxDocument.new()
    doc.add_paragraph("first")
    host = doc.add_paragraph("host")
    doc.fields.add("f", paragraph=host)
    doc.add_paragraph("after")
    data = doc.to_bytes()
    xml = _section(data)
    found = re.search(r"(<hp:run [^>]*><hp:ctrl><hp:fieldEnd [^>]*/></hp:ctrl><hp:t/></hp:run>)</hp:p>", xml)
    assert found is not None
    paragraph = (
        '</hp:p><hp:p id="77700001" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        + found.group(1)
        + "</hp:p>"
    )
    made = _with_section(data, xml[: found.start(1)] + paragraph + xml[found.end():])
    assert validate_editor_open_safety(made).ok
    return made


def _names(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


# --------------------------------------------------------------------------- #
# W1: a byte patch that fails the open-safety check writes nothing.
# --------------------------------------------------------------------------- #
def test_a_body_op_whose_result_hancom_would_refuse_leaves_the_file_as_it_was(tmp_path: Path) -> None:
    source = _field_over_two_paragraphs()
    target = tmp_path / "doc.hwpx"
    target.write_bytes(source)

    result = apply_body_ops(target, [{"op": "delete_paragraph", "index": 1}], output_path=target)

    assert target.read_bytes() == source
    assert _names(tmp_path) == ["doc.hwpx"]
    assert not result.ok
    assert result.open_safety["ok"] is False
    assert result.open_safety["code"] == "open-safety-failed"
    assert "fieldEnd" in result.open_safety["summary"]


def test_a_body_op_whose_result_hancom_would_refuse_makes_no_new_file(tmp_path: Path) -> None:
    source = tmp_path / "doc.hwpx"
    source.write_bytes(_field_over_two_paragraphs())
    out = tmp_path / "out.hwpx"

    result = apply_body_ops(source, [{"op": "delete_paragraph", "index": 1}], output_path=out)

    assert _names(tmp_path) == ["doc.hwpx"]
    assert not result.ok


_BYTE_PATCH_ROUTES = {
    "paragraph_patch": lambda source, out: paragraph_patch(
        source, [{"paragraph_index": 1, "text": "NEW"}], output_path=out),
    "paragraph_patch, nothing to do": lambda source, out: paragraph_patch(source, [], output_path=out),
    "paragraph_patch, every patch skipped": lambda source, out: paragraph_patch(
        source, [{"paragraph_index": 99, "text": "NEW"}], output_path=out),
    "fill_cells": lambda source, out: fill_cells(
        source, [{"table_index": 0, "row": 0, "col": 0, "text": "NEW"}], output_path=out),
    "apply_table_ops": lambda source, out: apply_table_ops(
        source, [{"op": "delete_row", "table_index": 0, "row": 1}], output_path=out),
    "apply_body_ops": lambda source, out: apply_body_ops(
        source, [{"op": "set_paragraph_text", "index": 1, "text": "NEW"}], output_path=out),
    "recolor_runs_by_color": lambda source, out: recolor_runs_by_color(
        source, ["#000000"], "#FF0000", output_path=out),
    "strip_runs_by_color": lambda source, out: strip_runs_by_color(source, ["#000000"], output_path=out),
    "strip_trailing_table_captions": lambda source, out: strip_trailing_table_captions(source, output_path=out),
}


@pytest.mark.parametrize("route", list(_BYTE_PATCH_ROUTES))
@pytest.mark.parametrize("in_place", [True, False], ids=["in place", "new file"])
def test_no_byte_patch_route_writes_what_fails_the_open_safety_check(
    route: str, in_place: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _base()
    source = tmp_path / "doc.hwpx"
    source.write_bytes(original)
    out = source if in_place else tmp_path / "out.hwpx"

    def fail_validation(_source: object) -> object:
        raise RuntimeError("schema unavailable")

    monkeypatch.setattr(validator_module, "validate_document", fail_validation)
    result = _BYTE_PATCH_ROUTES[route](source, out)

    assert source.read_bytes() == original
    assert _names(tmp_path) == ["doc.hwpx"]
    assert not result.ok
    assert result.open_safety["ok"] is False
    assert result.open_safety["code"] == "open-safety-failed"
    assert "document validation could not run" in result.open_safety["summary"]
    assert getattr(result, "output_is_source_copy", False) is False


@pytest.mark.parametrize("route", list(_BYTE_PATCH_ROUTES))
def test_every_byte_patch_route_still_writes_what_passes(route: str, tmp_path: Path) -> None:
    source = tmp_path / "doc.hwpx"
    source.write_bytes(_base())
    out = tmp_path / "out.hwpx"

    result = _BYTE_PATCH_ROUTES[route](source, out)

    assert result.open_safety["ok"] is True
    assert "code" not in result.open_safety
    assert out.read_bytes() == result.data
    assert validate_editor_open_safety(out).ok
