# SPDX-License-Identifier: Apache-2.0
"""Every hwpx-* command answers a missing file, a folder and an .hwp file with one line and a non-zero exit."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from hwpx import HwpxDocument
from hwpx.tools import archive_cli, package_validator, page_guard, repair, template_analyzer
from hwpx.tools import text_extract_cli, validator

HWP = Path(__file__).parent / "fixtures" / "hwp5" / "border_3d.hwp"


def _commands(tmp_path: Path) -> dict[str, Callable[[str], int]]:
    return {
        "hwpx-unpack": lambda f: archive_cli.unpack_main([f, str(tmp_path / "unpacked")]),
        "hwpx-validate": lambda f: validator.main([f]),
        "hwpx-validate-package": lambda f: package_validator.main([f]),
        "hwpx-page-guard": lambda f: page_guard.main(["--reference", f, "--output", f]),
        "hwpx-analyze-template": lambda f: template_analyzer.main([f]),
        "hwpx-text-extract": lambda f: text_extract_cli.main([f]),
        "hwpx-repair": lambda f: repair.main([f, str(tmp_path / "repaired.hwpx")]),
    }


NAMES = [
    "hwpx-unpack",
    "hwpx-validate",
    "hwpx-validate-package",
    "hwpx-page-guard",
    "hwpx-analyze-template",
    "hwpx-text-extract",
    "hwpx-repair",
]


def _one_line(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    text = (captured.out + captured.err).strip()
    assert "Traceback" not in text
    return text


@pytest.mark.parametrize("name", NAMES)
def test_a_missing_file_is_one_line_and_fails(name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _commands(tmp_path)[name](str(tmp_path / "없는파일.hwpx"))

    text = _one_line(capsys)
    assert code != 0
    assert len(text.splitlines()) == 1 and "not found" in text


@pytest.mark.parametrize("name", NAMES)
def test_a_folder_is_one_line_and_fails(name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "folder.hwpx"
    folder.mkdir()
    code = _commands(tmp_path)[name](str(folder))

    text = _one_line(capsys)
    assert code != 0 and len(text.splitlines()) == 1 and "folder" in text


@pytest.mark.parametrize(
    "name", [n for n in NAMES if n not in {"hwpx-validate", "hwpx-text-extract"}]
)
def test_an_hwp_file_gets_a_conversion_hint(name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _commands(tmp_path)[name](str(HWP))

    text = _one_line(capsys)
    assert code != 0 and len(text.splitlines()) == 1
    assert "HWP 5.0" in text and ".save(" in text
    assert "zip" not in text.lower()


def test_text_extract_reads_an_hwp_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    expected = HwpxDocument.open(HWP).text.plain().strip().splitlines()[0]

    assert text_extract_cli.main([str(HWP)]) == 0
    assert expected in capsys.readouterr().out


def test_validate_says_it_checked_the_conversion_of_an_hwp_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = validator.main([str(HWP)])

    out = capsys.readouterr().out
    assert "HWP 5.0" in out and "converted" in out
    if code == 0:
        assert out.strip().splitlines()[-1].endswith("(of the converted HWPX).")


def test_validate_help_names_the_schemas_it_uses(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        validator.main(["--help"])
    help_text = capsys.readouterr().out
    assert "DevDoc" not in help_text
    assert "header.xsd" in help_text and "owpml" in help_text


def test_validate_still_passes_a_good_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "ok.hwpx"
    HwpxDocument.new().save(path)
    assert validator.main([str(path)]) == 0
    assert "passed" in capsys.readouterr().out
