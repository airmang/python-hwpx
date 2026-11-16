"""``doc.save(path, format="hwpx")`` to a name that is not ``.hwpx`` saves without the name warning:
the caller said what the file holds. A ``.hwp`` name still warns (the name says another format), and a
save that leaves the format to the name warns as before."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument


def _warnings_of(doc: HwpxDocument, path: Path, **kwargs: object) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        doc.save(path, **kwargs)  # type: ignore[arg-type]
    return [str(item.message) for item in caught if "Saving HWPX data" in str(item.message)]


@pytest.mark.parametrize("name", ["out.tmp", "out.hwpx.tmp", "out", "out.zip"])
def test_stated_hwpx_to_another_name_saves_quietly(tmp_path: Path, name: str) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("합성 문단")
    assert _warnings_of(doc, tmp_path / name, format="hwpx") == []
    assert HwpxDocument.open(tmp_path / name).paragraphs[-1].text == "합성 문단"


def test_stated_hwpx_to_a_hwp_name_still_warns(tmp_path: Path) -> None:
    assert len(_warnings_of(HwpxDocument.new(), tmp_path / "out.hwp", format="hwpx")) == 1


@pytest.mark.parametrize("name", ["out.tmp", "out"])
def test_a_name_left_to_say_the_format_warns(tmp_path: Path, name: str) -> None:
    assert len(_warnings_of(HwpxDocument.new(), tmp_path / name)) == 1


def test_a_hwpx_name_never_warns(tmp_path: Path) -> None:
    assert _warnings_of(HwpxDocument.new(), tmp_path / "out.hwpx") == []
    assert _warnings_of(HwpxDocument.new(), tmp_path / "again.HWPX", format="hwpx") == []
