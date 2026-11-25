# SPDX-License-Identifier: Apache-2.0
"""hwpx-unpack and hwpx-pack leave the disk as it was when they refuse or fail.

``hwpx-unpack input <folder> --force`` used to empty the folder before it had looked
at the input: an input inside that folder took its neighbours with it, and a broken
input cost the folder's old contents. ``hwpx-pack`` with its output inside the input
folder packed the earlier output as a part, and a refused pack left the output's
parent folders behind.
"""

from __future__ import annotations

import os
from pathlib import Path
from zipfile import ZIP_STORED, BadZipFile, ZipFile

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.tools import archive_cli
from hwpx.tools.archive_cli import pack_hwpx, unpack_hwpx


def _tree(root: Path) -> dict[str, bytes | None]:
    """Every folder (``None``) and file (its bytes) under *root*, by relative path."""

    return {
        path.relative_to(root).as_posix(): (path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    }


def _document_bytes(text: str = "synthetic paragraph") -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph(text)
    return document.to_bytes()


def _archive_with_a_damaged_last_member(path: Path) -> None:
    """A ZIP whose first member reads and whose last member fails its CRC check."""

    marker = b"DAMAGE-ME-" * 8
    with ZipFile(path, "w", ZIP_STORED) as archive:
        archive.writestr("mimetype", b"application/hwp+zip")
        archive.writestr("first.txt", b"first member reads fine")
        archive.writestr("last.txt", marker)
    data = bytearray(path.read_bytes())
    at = data.index(marker)
    data[at] ^= 0xFF
    path.write_bytes(bytes(data))


def _one_error_line(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    text = (captured.out + captured.err).strip()
    assert "Traceback" not in text
    assert len(text.splitlines()) == 1 and text.startswith("ERROR: ")
    return text


# -- hwpx-unpack: the input inside the output folder ---------------------------------


def test_unpack_force_refuses_an_input_inside_the_output_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    docs = tmp_path / "docs"
    (docs / "sub").mkdir(parents=True)
    (docs / "in.hwpx").write_bytes(_document_bytes())
    (docs / "neighbour.hwpx").write_bytes(_document_bytes("another synthetic document"))
    (docs / "sub" / "notes.txt").write_bytes(b"keep me")
    before = _tree(tmp_path)

    code = archive_cli.unpack_main([str(docs / "in.hwpx"), str(docs), "--force"])

    assert code == 1
    assert "inside the output folder" in _one_error_line(capsys)
    assert _tree(tmp_path) == before


def test_unpack_refuses_an_input_in_a_subfolder_of_the_output_folder(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "deep" / "er").mkdir(parents=True)
    source = docs / "deep" / "er" / "in.hwpx"
    source.write_bytes(_document_bytes())
    before = _tree(tmp_path)

    for overwrite in (True, False):
        with pytest.raises(HwpxError) as caught:
            unpack_hwpx(source, docs, overwrite=overwrite)
        assert caught.value.code == "package-unpack-input-inside-output"
        assert caught.value.context == {"input": str(source), "output": str(docs)}
        assert isinstance(caught.value, ValueError)
    assert _tree(tmp_path) == before


def test_unpack_refuses_an_input_inside_the_output_folder_given_as_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "in.hwpx").write_bytes(_document_bytes())
    (docs / "neighbour.txt").write_bytes(b"keep me")
    before = _tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert archive_cli.unpack_main(["docs/in.hwpx", "docs/../docs", "--force"]) == 1
    assert "inside the output folder" in _one_error_line(capsys)
    monkeypatch.chdir(docs)
    assert archive_cli.unpack_main(["in.hwpx", ".", "--force"]) == 1
    assert "inside the output folder" in _one_error_line(capsys)

    assert _tree(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="file names differ only by case on Windows")
def test_unpack_refuses_an_input_inside_the_output_folder_spelled_in_another_case(tmp_path: Path) -> None:
    docs = tmp_path / "Docs"
    docs.mkdir()
    (docs / "in.hwpx").write_bytes(_document_bytes())
    before = _tree(tmp_path)

    with pytest.raises(HwpxError) as caught:
        unpack_hwpx(tmp_path / "docs" / "IN.HWPX", tmp_path / "DOCS", overwrite=True)

    assert caught.value.code == "package-unpack-input-inside-output"
    assert _tree(tmp_path) == before


def test_unpack_refuses_the_input_path_as_the_output_folder(tmp_path: Path) -> None:
    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    before = _tree(tmp_path)

    with pytest.raises(HwpxError) as caught:
        unpack_hwpx(source, source, overwrite=True)

    assert caught.value.code == "package-unpack-input-inside-output"
    assert _tree(tmp_path) == before


# -- hwpx-unpack: an input that does not unpack --------------------------------------


def test_unpack_force_keeps_the_output_folder_when_the_input_is_not_a_zip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.hwpx"
    bad.write_bytes(b"this is not a zip archive")
    out = tmp_path / "unpacked"
    (out / "Contents").mkdir(parents=True)
    (out / "Contents" / "section0.xml").write_bytes(b"<old/>")
    (out / "keep.txt").write_bytes(b"keep me")
    before = _tree(tmp_path)

    code = archive_cli.unpack_main([str(bad), str(out), "--force"])

    assert code == 1
    _one_error_line(capsys)
    assert _tree(tmp_path) == before


def test_unpack_force_keeps_the_output_folder_when_a_member_fails_to_read(tmp_path: Path) -> None:
    bad = tmp_path / "damaged.hwpx"
    _archive_with_a_damaged_last_member(bad)
    out = tmp_path / "unpacked"
    out.mkdir()
    (out / "keep.txt").write_bytes(b"keep me")
    before = _tree(tmp_path)

    with pytest.raises(BadZipFile):
        unpack_hwpx(bad, out, overwrite=True)

    assert _tree(tmp_path) == before


def test_unpack_of_an_input_that_does_not_unpack_creates_no_folder(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "bad.hwpx"
    not_a_zip.write_bytes(b"this is not a zip archive")
    damaged = tmp_path / "damaged.hwpx"
    _archive_with_a_damaged_last_member(damaged)
    empty = tmp_path / "empty"
    empty.mkdir()
    before = _tree(tmp_path)

    for source in (not_a_zip, damaged):
        for target in (tmp_path / "new" / "sub" / "out", tmp_path / "fresh", empty):
            with pytest.raises(BadZipFile):
                unpack_hwpx(source, target)

    assert _tree(tmp_path) == before


# -- hwpx-unpack: replacing the old contents -----------------------------------------


def test_unpack_force_replaces_the_old_contents_and_leaves_nothing_else(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    source.write_bytes(_document_bytes())
    out = tmp_path / "unpacked"
    (out / "old").mkdir(parents=True)
    (out / "old" / "stale.txt").write_bytes(b"stale")
    (out / "mimetype").write_bytes(b"stale")

    result = unpack_hwpx(source, out, overwrite=True)

    assert result.output_dir == out
    assert result.metadata_path == out / archive_cli._PACK_METADATA_NAME
    assert sorted(path.name for path in tmp_path.iterdir()) == ["source.hwpx", "unpacked"]
    unpacked = _tree(out)
    with ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    files = {name: data for name, data in unpacked.items() if data is not None}
    metadata = files.pop(archive_cli._PACK_METADATA_NAME)
    assert files == members
    assert b"stale" not in metadata and "old" not in unpacked


def test_unpack_into_an_empty_or_a_new_nested_folder(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    source.write_bytes(_document_bytes())
    empty = tmp_path / "empty"
    empty.mkdir()
    nested = tmp_path / "new" / "sub" / "out"

    unpack_hwpx(source, empty)
    unpack_hwpx(source, nested)

    assert (empty / "mimetype").is_file() and (nested / "mimetype").is_file()
    assert _tree(empty) == _tree(nested)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["empty", "new", "source.hwpx"]
    assert [path.name for path in (tmp_path / "new" / "sub").iterdir()] == ["out"]


def test_unpack_force_puts_the_old_contents_back_when_the_new_ones_cannot_move_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.hwpx"
    source.write_bytes(_document_bytes())
    out = tmp_path / "unpacked"
    out.mkdir()
    (out / "keep.txt").write_bytes(b"keep me")
    before = _tree(tmp_path)
    real_rename = os.rename
    refused: list[str] = []

    def rename(src: str, dst: str) -> None:
        if Path(dst) == out and not refused:
            refused.append(src)
            raise PermissionError(13, "simulated: the new folder cannot move in", dst)
        real_rename(src, dst)

    monkeypatch.setattr(archive_cli.os, "rename", rename)

    with pytest.raises(PermissionError):
        unpack_hwpx(source, out, overwrite=True)

    monkeypatch.undo()
    assert len(refused) == 1
    assert _tree(tmp_path) == before


def test_unpack_force_warns_when_the_old_contents_cannot_be_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.hwpx"
    source.write_bytes(_document_bytes())
    out = tmp_path / "unpacked"
    out.mkdir()
    (out / "keep.txt").write_bytes(b"keep me")

    def rmtree(path: object, *args: object, **kwargs: object) -> None:
        raise PermissionError(13, "simulated: a file in the old folder is in use", str(path))

    monkeypatch.setattr(archive_cli.shutil, "rmtree", rmtree)

    with pytest.warns(RuntimeWarning, match="could not be removed"):
        unpack_hwpx(source, out, overwrite=True)

    monkeypatch.undo()
    assert (out / "mimetype").is_file() and not (out / "keep.txt").exists()
    left = [path for path in tmp_path.iterdir() if path.name not in {"source.hwpx", "unpacked"}]
    assert len(left) == 1 and (left[0] / "keep.txt").read_bytes() == b"keep me"


# -- hwpx-pack ------------------------------------------------------------------------


def _unpacked(tmp_path: Path) -> Path:
    source = tmp_path / "source.hwpx"
    source.write_bytes(_document_bytes())
    folder = tmp_path / "unpacked"
    unpack_hwpx(source, folder)
    source.unlink()
    return folder


def test_pack_refuses_an_output_inside_the_input_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _unpacked(tmp_path)
    before = _tree(tmp_path)

    for target in (folder / "out.hwpx", folder / "Contents" / "out.hwpx", folder / "new" / "out.hwpx"):
        with pytest.raises(HwpxError) as caught:
            pack_hwpx(folder, target, overwrite=True)
        assert caught.value.code == "package-pack-output-inside-input"
        assert caught.value.context == {"input": str(folder), "output": str(target)}
        assert isinstance(caught.value, ValueError)
    code = archive_cli.pack_main([str(folder), str(folder / "out.hwpx"), "--force"])

    assert code == 1
    assert "inside the input folder" in _one_error_line(capsys)
    assert _tree(tmp_path) == before


def test_pack_refuses_the_input_folder_as_the_output(tmp_path: Path) -> None:
    folder = _unpacked(tmp_path)
    before = _tree(tmp_path)

    with pytest.raises(HwpxError) as caught:
        pack_hwpx(folder, folder, overwrite=True)

    assert caught.value.code == "package-pack-output-inside-input"
    assert _tree(tmp_path) == before


def test_a_refused_pack_does_not_create_the_output_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _unpacked(tmp_path)
    no_mimetype = tmp_path / "no-mimetype"
    no_mimetype.mkdir()
    (no_mimetype / "version.xml").write_bytes(b"<version/>")
    before = _tree(tmp_path)
    target = tmp_path / "new" / "sub" / "out.hwpx"

    with pytest.raises(FileNotFoundError, match="mimetype"):
        pack_hwpx(no_mimetype, target)
    assert archive_cli.pack_main([str(tmp_path / "missing"), str(target)]) == 1
    assert _tree(tmp_path) == before

    class _FailedOpenSafety:
        ok = False
        summary = "forced reopen failure"

    monkeypatch.setattr(archive_cli, "validate_editor_open_safety", lambda _path: _FailedOpenSafety())
    with pytest.raises(ValueError, match="editor-open safety"):
        pack_hwpx(folder, target)

    assert _tree(tmp_path) == before


def test_pack_creates_the_output_folder_when_it_writes(tmp_path: Path) -> None:
    folder = _unpacked(tmp_path)
    target = tmp_path / "new" / "sub" / "out.hwpx"

    result = pack_hwpx(folder, target)

    assert result.output_path == target and result.open_safety["ok"] is True
    assert [path.name for path in target.parent.iterdir()] == ["out.hwpx"]
    assert HwpxDocument.open(target).text.plain().strip().endswith("synthetic paragraph")
