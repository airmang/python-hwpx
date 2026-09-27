# SPDX-License-Identifier: Apache-2.0
"""A save validates the archive it builds once; bytes the package did not verify are still checked."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

from hwpx import HwpxDocument
from hwpx.errors import SaveError
from hwpx.opc.package import HwpxPackage
from hwpx.tools import package_validator


def _count_validations(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = package_validator.validate_editor_open_safety

    def counting(source: Any) -> Any:
        calls.append(type(source).__name__)
        return real(source)

    monkeypatch.setattr(package_validator, "validate_editor_open_safety", counting)
    return calls


@pytest.mark.parametrize("how", ["to_bytes", "save_to_path", "save_to_stream"])
def test_save_validates_the_archive_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, how: str) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("한 번만 검증")
    calls = _count_validations(monkeypatch)
    if how == "to_bytes":
        doc.to_bytes()
    elif how == "save_to_path":
        doc.save_to_path(tmp_path / "out.hwpx")
    else:
        doc.save_to_stream(io.BytesIO())
    assert len(calls) == 1


def test_bytes_the_package_did_not_verify_are_still_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = HwpxDocument.new()
    # a package whose save does not verify (e.g. a custom implementation)
    monkeypatch.setattr(HwpxPackage, "_verify_editor_open_safe_archive", classmethod(lambda cls, source: None))

    class Failing:
        ok = False
        summary = "blocked for the test"

    monkeypatch.setattr(package_validator, "validate_editor_open_safety", lambda source: Failing())
    with pytest.raises(SaveError, match="open-safety validation"):
        doc.to_bytes()


def test_other_bytes_than_the_verified_archive_are_checked() -> None:
    doc = HwpxDocument.new()
    doc.to_bytes()
    with pytest.raises(SaveError, match="open-safety validation"):
        doc._run_open_safety_validation(b"PK not an archive")
