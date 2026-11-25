# SPDX-License-Identifier: Apache-2.0
"""What a write that is refused leaves behind: the target as it was, and no other file.

Each test here is the reproduction of one finding of the 2026-11 write-path audit (issue 834),
made with documents built in the test.
"""

from __future__ import annotations

import io
import os
import re
import warnings
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import Hwp5Error
from hwpx.body_patch import apply_body_ops, recolor_runs_by_color, strip_runs_by_color
from hwpx.opc.package import HwpxPackage
from hwpx.patch import paragraph_patch, replace_package_text
from hwpx.plan import apply_edit_plan, validate_edit_plan
from hwpx.quality import QualityPolicy, SavePipeline, write_bytes_atomically
from hwpx.table_patch import (
    apply_table_ops,
    fill_cells,
    strip_trailing_table_captions,
    strip_trailing_table_text,
)
from hwpx.tools.archive_cli import pack_hwpx
from hwpx.tools.repair import normalize_package_namespaces, repair_from_recovered, repair_repack
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


# --------------------------------------------------------------------------- #
# W2: the .hwp file a document was opened from is not written over, whatever the format.
# --------------------------------------------------------------------------- #
def _hwp_file(path: Path) -> bytes:
    """An HWP 5.0 file at *path*, made by the engine's writer from the synthetic document."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        HwpxDocument.open(_base()).save(path)
    data = path.read_bytes()
    assert data[:8] == bytes.fromhex("d0cf11e0a1b11ae1")
    return data


@pytest.mark.parametrize(
    "save",
    [
        lambda doc, path: doc.save(path, format="hwpx"),
        lambda doc, path: doc.save(str(path).upper(), format="hwpx"),
        lambda doc, path: doc.save(path, format="hwp"),
        lambda doc, path: doc.save(path),
    ],
    ids=["format=hwpx", "format=hwpx, other spelling", "format=hwp", "format by name"],
)
def test_the_hwp_a_document_was_opened_from_is_not_written_over_in_any_format(save, tmp_path: Path) -> None:
    original = tmp_path / "original.hwp"
    before = _hwp_file(original)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        document = HwpxDocument.open(original)
        document.add_paragraph("edited")
        with pytest.raises(Hwp5Error) as refused:
            save(document, original)

    assert refused.value.code == "hwp5-overwrite-source"
    assert original.read_bytes() == before
    assert _names(tmp_path) == ["original.hwp"]
    # the way out is another file name, not another format for this path
    suggestion = refused.value.suggestion or ""
    assert "another file name" in suggestion and ".hwpx" in suggestion
    assert "save as .hwpx and keep" not in suggestion


# --------------------------------------------------------------------------- #
# W3: an .hwp file that is already there is not written over by anything.
# --------------------------------------------------------------------------- #
def _plan(source: Path, output: Path) -> dict:
    return {
        "schemaVersion": "hwpx.edit-plan/v1",
        "source": str(source),
        "output": str(output),
        "steps": [{"id": "s", "op": "paragraph_patch", "args": {"patches": [{"paragraph_index": 1, "text": "N"}]}}],
    }


def _unpacked(source: Path, folder: Path) -> Path:
    from hwpx.tools.archive_cli import unpack_hwpx

    unpack_hwpx(source, folder)
    return folder


def _fresh() -> HwpxDocument:
    return HwpxDocument.open(_base())


#: Every way the engine puts a document on a path. Each takes the .hwpx source and the .hwp target.
_WRITES_TO_A_PATH = {
    "doc.save": lambda source, target: _fresh().save(target),
    "doc.save format=hwp": lambda source, target: _fresh().save(target, format="hwp"),
    "doc.save format=hwpx": lambda source, target: _fresh().save(target, format="hwpx"),
    "doc.save quality": lambda source, target: _fresh().save(target, quality=QualityPolicy.transparent()),
    "doc.package.save": lambda source, target: _fresh().package.save(str(target)),
    "doc.package.save Path": lambda source, target: _fresh().package.save(target),
    "HwpxPackage.save updates": lambda source, target: HwpxPackage.open(source).save(target, {"extra.txt": b"x"}),
    "paragraph_patch": lambda source, target: paragraph_patch(
        source, [{"paragraph_index": 1, "text": "N"}], output_path=target),
    "paragraph_patch nothing to do": lambda source, target: paragraph_patch(source, [], output_path=target),
    "fill_cells": lambda source, target: fill_cells(
        source, [{"table_index": 0, "row": 0, "col": 0, "text": "N"}], output_path=target),
    "fill_cells nothing to do": lambda source, target: fill_cells(source, [], output_path=target),
    "apply_table_ops": lambda source, target: apply_table_ops(
        source, [{"op": "delete_row", "table_index": 0, "row": 1}], output_path=target),
    "apply_table_ops dry_run": lambda source, target: apply_table_ops(
        source, [{"op": "delete_row", "table_index": 0, "row": 1}], output_path=target, dry_run=True),
    "apply_body_ops": lambda source, target: apply_body_ops(
        source, [{"op": "set_paragraph_text", "index": 1, "text": "N"}], output_path=target),
    "apply_body_ops dry_run": lambda source, target: apply_body_ops(
        source, [{"op": "set_paragraph_text", "index": 1, "text": "N"}], output_path=target, dry_run=True),
    "recolor_runs_by_color": lambda source, target: recolor_runs_by_color(
        source, ["#000000"], "#FF0000", output_path=target),
    "strip_runs_by_color": lambda source, target: strip_runs_by_color(source, ["#000000"], output_path=target),
    "strip_trailing_table_captions": lambda source, target: strip_trailing_table_captions(source, output_path=target),
    "strip_trailing_table_text": lambda source, target: strip_trailing_table_text(
        source, predicate=lambda text: False, output_path=target),
    "replace_package_text": lambda source, target: replace_package_text(source, {"alpha": "N"}, output_path=target),
    "normalize_package_namespaces": lambda source, target: normalize_package_namespaces(source, output_path=target),
    "apply_edit_plan": lambda source, target: apply_edit_plan(_plan(source, target)),
    "apply_edit_plan dry_run": lambda source, target: apply_edit_plan(_plan(source, target), dry_run=True),
    "validate_edit_plan": lambda source, target: validate_edit_plan(_plan(source, target)),
    "repair_repack overwrite": lambda source, target: repair_repack(source, target, overwrite=True),
    "repair_repack": lambda source, target: repair_repack(source, target),
    "repair_from_recovered overwrite": lambda source, target: repair_from_recovered(source, target, overwrite=True),
    "pack_hwpx overwrite": lambda source, target: pack_hwpx(
        _unpacked(source, source.parent.parent / "unpacked"), target, overwrite=True),
    "SavePipeline.run": lambda source, target: SavePipeline().run(
        source.read_bytes(), output_path=target, quality=QualityPolicy.transparent()),
    "write_bytes_atomically": lambda source, target: write_bytes_atomically(target, source.read_bytes()),
}


@pytest.mark.parametrize("route", list(_WRITES_TO_A_PATH))
def test_no_route_writes_over_an_hwp_file_that_is_already_there(route: str, tmp_path: Path) -> None:
    folder = tmp_path / "docs"
    folder.mkdir()
    source = folder / "doc.hwpx"
    original = _base()
    source.write_bytes(original)
    target = folder / "other.hwp"
    before = _hwp_file(target)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(Hwp5Error) as refused:
            _WRITES_TO_A_PATH[route](source, target)

    assert refused.value.code == "hwp5-overwrite-existing"
    assert refused.value.context["path"] == os.path.abspath(target)
    suggestion = refused.value.suggestion or ""
    assert "does not exist yet" in suggestion and "other.hwpx" in suggestion
    assert target.read_bytes() == before
    assert source.read_bytes() == original
    assert _names(folder) == ["doc.hwpx", "other.hwp"]


@pytest.mark.parametrize("tool", ["hwpx-repair", "hwpx-repair --recover", "hwpx-pack"])
def test_force_does_not_let_the_command_line_tools_write_over_an_hwp(tool: str, tmp_path: Path, capsys) -> None:
    from hwpx.tools import archive_cli, repair

    folder = tmp_path / "docs"
    folder.mkdir()
    source = folder / "doc.hwpx"
    source.write_bytes(_base())
    target = folder / "other.hwp"
    before = _hwp_file(target)

    if tool == "hwpx-pack":
        unpacked = _unpacked(source, tmp_path / "unpacked")
        code = archive_cli.pack_main([str(unpacked), str(target), "--force"])
    else:
        extra = ["--recover"] if tool.endswith("--recover") else []
        code = repair.main([str(source), str(target), "--force", *extra])

    said = capsys.readouterr()
    assert code != 0
    assert "existing .hwp" in said.out + said.err
    assert target.read_bytes() == before
    assert _names(folder) == ["doc.hwpx", "other.hwp"]


@pytest.mark.skipif(os.name != "nt", reason="spellings Windows resolves to the same file")
@pytest.mark.parametrize("spelling", ["OTHER.HWP", "other.hwp.", "other.hwp "])
def test_another_spelling_of_the_same_hwp_file_is_refused_too(spelling: str, tmp_path: Path) -> None:
    source = tmp_path / "doc.hwpx"
    source.write_bytes(_base())
    target = tmp_path / "other.hwp"
    before = _hwp_file(target)
    spelled = str(tmp_path / spelling)

    for write in (
        lambda: _fresh().save(spelled, format="hwpx"),
        lambda: _fresh().package.save(spelled),
        lambda: paragraph_patch(source, [{"paragraph_index": 1, "text": "N"}], output_path=spelled),
        lambda: repair_repack(source, spelled, overwrite=True),
    ):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(Hwp5Error) as refused:
                write()
        assert refused.value.code == "hwp5-overwrite-existing"
    assert target.read_bytes() == before
    assert _names(tmp_path) == ["doc.hwpx", "other.hwp"]


def test_the_package_save_of_a_document_opened_from_an_hwp_does_not_write_over_it(tmp_path: Path) -> None:
    original = tmp_path / "original.hwp"
    before = _hwp_file(original)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        document = HwpxDocument.open(original)

    with pytest.raises(Hwp5Error) as refused:
        document.package.save(str(original))

    assert refused.value.code == "hwp5-overwrite-existing"
    assert original.read_bytes() == before
    assert _names(tmp_path) == ["original.hwp"]


def test_a_refused_package_save_does_not_take_its_updates(tmp_path: Path) -> None:
    target = tmp_path / "other.hwp"
    _hwp_file(target)
    package = HwpxPackage.open(_base())
    names = package.part_names()

    with pytest.raises(Hwp5Error):
        package.save(target, {"extra.txt": b"x"})

    assert package.part_names() == names


def test_a_new_hwp_name_is_still_written(tmp_path: Path) -> None:
    """The experimental HWP 5.0 writer keeps writing new files; only files already there are kept."""

    new = tmp_path / "new.hwp"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = _fresh().save(new)
    assert report.path == str(new)
    assert new.read_bytes()[:8] == bytes.fromhex("d0cf11e0a1b11ae1")

    # and the same name a second time is the file that is already there
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(Hwp5Error) as refused:
            _fresh().save(new)
    assert refused.value.code == "hwp5-overwrite-existing"

    # a save to a stream has no path: it is not judged
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _fresh().save(stream, format="hwp")
    assert stream.getvalue()[:8] == bytes.fromhex("d0cf11e0a1b11ae1")


def test_an_existing_hwpx_is_written_over_as_before(tmp_path: Path) -> None:
    target = tmp_path / "doc.hwpx"
    target.write_bytes(_base())
    document = _fresh()
    document.add_paragraph("edited")
    document.save(target)
    assert "edited" in HwpxDocument.open(target).text.plain()
    result = paragraph_patch(target, [{"paragraph_index": 1, "text": "N"}], output_path=target)
    assert result.ok and target.read_bytes() == result.data
