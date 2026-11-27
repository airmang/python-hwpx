# SPDX-License-Identifier: Apache-2.0
"""A command that writes text, JSON or XML to a path does not write it over a document.

``hwpx-text-extract in.hwpx --output in.hwpx`` and ``hwpx-analyze-template in.hwpx --extract-header
in.hwpx`` used to exit 0 with the document replaced by its own text or header XML (finding W13 of
the 2026-11 write-path audit, issue 834). Every such output argument now refuses, before anything is
written, an output that is the input file under any spelling, and an ``.hwp`` file that is already
there. The documents here are built in the test.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from typing import Callable

import pytest

from hwpx import HwpxDocument
from hwpx.errors import ERROR_CODES, Hwp5Error, HwpxError
from hwpx.tools import generic_inventory, template_analyzer, text_extract_cli
from hwpx.tools.template_analyzer import extract_template_parts

CODE = "package-output-is-input"


def _document_bytes(text: str = "synthetic paragraph") -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph(text)
    return document.to_bytes()


def _hwp_file(path: Path) -> bytes:
    """An HWP 5.0 file at *path*, made by the engine's writer from the synthetic document."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        HwpxDocument.open(_document_bytes()).save(path)
    data = path.read_bytes()
    assert data[:8] == bytes.fromhex("d0cf11e0a1b11ae1")
    return data


def _tree(root: Path) -> dict[str, bytes | None]:
    """Every folder (``None``) and file (its bytes) under *root*, by relative path."""

    return {
        path.relative_to(root).as_posix(): (path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    }


def _refusal(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    text = (captured.out + captured.err).strip()
    assert "Traceback" not in text
    assert len(text.splitlines()) == 1, text
    return text


#: Each command-line output argument that writes text, JSON or XML to a file: the arguments that
#: send it to *output* for the document *source*.
_OUTPUT_ARGUMENTS: dict[str, Callable[[str, str], int]] = {
    "hwpx-text-extract --output": lambda source, output: text_extract_cli.main([source, "--output", output]),
    "hwpx-text-extract -o": lambda source, output: text_extract_cli.main([source, "-o", output]),
    "hwpx-analyze-template --extract-header": lambda source, output: template_analyzer.main(
        [source, "--extract-header", output]
    ),
    "hwpx-analyze-template --extract-section": lambda source, output: template_analyzer.main(
        [source, "--extract-section", output]
    ),
    "hwpx-analyze-template --output-json": lambda source, output: template_analyzer.main(
        [source, "--output-json", output]
    ),
}


def test_the_refusal_code_is_registered() -> None:
    assert CODE in ERROR_CODES


@pytest.mark.parametrize("argument", list(_OUTPUT_ARGUMENTS))
def test_an_output_that_is_the_input_is_refused(
    argument: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    before = _tree(tmp_path)

    code = _OUTPUT_ARGUMENTS[argument](str(source), str(source))

    said = _refusal(capsys)
    assert code != 0
    assert CODE in said and "input" in said
    assert _tree(tmp_path) == before


def _other_spellings(folder: Path, source: Path) -> dict[str, str]:
    spellings = {
        "relative": os.path.relpath(source, Path.cwd()) if source.drive == Path.cwd().drive else str(source),
        "through a folder and back": str(folder / "sub" / ".." / source.name),
    }
    if os.name == "nt":
        spellings["upper case"] = str(folder / source.name.upper())
        spellings["trailing dot"] = str(source) + "."
    link = folder / "link-to-in.hwpx"
    try:
        os.link(source, link)
    except OSError:  # a file system without hard links
        pass
    else:
        spellings["hard link"] = str(link)
    return spellings


@pytest.mark.parametrize("argument", ["hwpx-text-extract --output", "hwpx-analyze-template --extract-header"])
def test_another_spelling_of_the_input_is_refused_too(
    argument: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sub").mkdir()
    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    spellings = _other_spellings(tmp_path, source)
    before = _tree(tmp_path)

    for name, spelled in spellings.items():
        code = _OUTPUT_ARGUMENTS[argument](str(source), spelled)

        said = _refusal(capsys)
        assert code != 0, name
        assert CODE in said, name
        assert _tree(tmp_path) == before, name


@pytest.mark.parametrize("argument", list(_OUTPUT_ARGUMENTS))
def test_an_hwp_file_that_is_already_there_is_not_written_over(
    argument: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    _hwp_file(tmp_path / "other.hwp")
    before = _tree(tmp_path)

    code = _OUTPUT_ARGUMENTS[argument](str(source), str(tmp_path / "other.hwp"))

    said = _refusal(capsys)
    assert code != 0
    assert "hwp5-overwrite-existing" in said and "existing .hwp" in said
    assert _tree(tmp_path) == before


def test_a_refused_output_leaves_no_folder_behind(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """One refused argument stops the whole command: the other outputs are not written either."""

    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    before = _tree(tmp_path)

    code = template_analyzer.main(
        [
            str(source),
            "--extract-dir", str(tmp_path / "unpacked"),
            "--extract-section", str(tmp_path / "new" / "section.xml"),
            "--output-json", str(tmp_path / "made" / "summary.json"),
            "--extract-header", str(source),
        ]
    )

    assert code != 0
    assert CODE in _refusal(capsys)
    assert _tree(tmp_path) == before


def test_the_section_folder_does_not_take_a_document_named_like_a_section(tmp_path: Path) -> None:
    """``--extract-section-dir`` writes ``section0.xml`` into the folder: an input of that name there
    is the same file."""

    source = tmp_path / "section0.xml"
    source.write_bytes(_document_bytes())
    before = _tree(tmp_path)

    with pytest.raises(HwpxError) as refused:
        extract_template_parts(source, extract_section_dir=tmp_path)

    assert refused.value.code == CODE
    assert _tree(tmp_path) == before


def test_the_library_call_refuses_with_a_coded_error(tmp_path: Path) -> None:
    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    _hwp_file(tmp_path / "other.hwp")
    before = _tree(tmp_path)

    with pytest.raises(HwpxError) as same:
        extract_template_parts(source, extract_header=source)
    assert same.value.code == CODE
    assert isinstance(same.value, ValueError)
    assert same.value.context == {"input": str(source), "output": str(source)}
    assert "another" in (same.value.suggestion or "")

    with pytest.raises(Hwp5Error) as existing:
        extract_template_parts(source, extract_section=tmp_path / "other.hwp")
    assert existing.value.code == "hwp5-overwrite-existing"
    assert _tree(tmp_path) == before


def test_the_inventory_report_is_not_written_over_a_document_it_read(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.hwpx").write_bytes(_document_bytes())
    _hwp_file(tmp_path / "other.hwp")
    before = _tree(tmp_path)

    with pytest.raises(HwpxError) as same:
        generic_inventory.write_inventory(corpus, corpus / "one.hwpx")
    assert same.value.code == CODE
    with pytest.raises(Hwp5Error) as existing:
        generic_inventory.write_inventory(corpus, tmp_path / "other.hwp")
    assert existing.value.code == "hwp5-overwrite-existing"
    assert _tree(tmp_path) == before


# -- what stays allowed ---------------------------------------------------------------


def test_a_new_output_path_is_still_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "in.hwpx"
    original = _document_bytes("synthetic paragraph")
    source.write_bytes(original)

    assert text_extract_cli.main([str(source), "--output", str(tmp_path / "out.txt")]) == 0
    assert "synthetic paragraph" in (tmp_path / "out.txt").read_text(encoding="utf-8")
    # a second run replaces the text file it wrote before
    assert text_extract_cli.main([str(source), "--output", str(tmp_path / "out.txt")]) == 0

    assert (
        template_analyzer.main(
            [
                str(source),
                "--extract-header", str(tmp_path / "parts" / "header.xml"),
                "--extract-section", str(tmp_path / "parts" / "section.xml"),
                "--extract-section-dir", str(tmp_path / "sections"),
                "--output-json", str(tmp_path / "summary.json"),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (tmp_path / "parts" / "header.xml").read_bytes().lstrip().startswith(b"<")
    assert (tmp_path / "parts" / "section.xml").read_bytes().lstrip().startswith(b"<")
    assert (tmp_path / "sections" / "section0.xml").is_file()
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["source_name"] == "in.hwpx"
    assert source.read_bytes() == original


def test_an_empty_placeholder_named_hwp_is_filled(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A file with no bytes holds no document (the rule ``refuse_existing_hwp_target`` already has)."""

    source = tmp_path / "in.hwpx"
    source.write_bytes(_document_bytes())
    placeholder = tmp_path / "empty.hwp"
    placeholder.write_bytes(b"")

    assert text_extract_cli.main([str(source), "--output", str(placeholder)]) == 0
    capsys.readouterr()
    assert "synthetic paragraph" in placeholder.read_text(encoding="utf-8")
