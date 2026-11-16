# SPDX-License-Identifier: Apache-2.0
"""``doc.save()`` hands back the editor-open safety report it reached (``MutationReport.editor_open_safety``).

6.x callers read it from a private attribute of the package; running ``validate_editor_open_safety``
on the saved file again gives the same report at the cost of a second validation.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

from hwpx import EditorOpenSafetyReport, HwpxDocument, validate_editor_open_safety
from hwpx.opc.package import HwpxPackage
from hwpx.tools import package_validator

FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _count_validations(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = package_validator.validate_editor_open_safety

    def counting(source: Any) -> Any:
        calls.append(type(source).__name__)
        return real(source)

    monkeypatch.setattr(package_validator, "validate_editor_open_safety", counting)
    return calls


def _same_verdict(first: EditorOpenSafetyReport, second: EditorOpenSafetyReport) -> None:
    assert first.ok is second.ok is True
    assert first.summary == second.summary
    assert first.reopen_ok == second.reopen_ok
    assert first.blocking_package_errors == second.blocking_package_errors
    assert first.validate_package.ok == second.validate_package.ok


def test_a_path_save_returns_the_report_of_the_file_it_wrote(tmp_path: Path) -> None:
    doc = HwpxDocument.open((FIXTURES / "list_number_level1.hwpx").read_bytes())
    doc.add_paragraph("더한 문단")
    target = tmp_path / "out.hwpx"

    report = doc.save(target)

    assert isinstance(report.editor_open_safety, EditorOpenSafetyReport)
    assert report.verification.open_safety == "passed"
    _same_verdict(report.editor_open_safety, validate_editor_open_safety(target))


def test_the_report_costs_no_second_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("한 번만 검증")
    calls = _count_validations(monkeypatch)

    report = doc.save(tmp_path / "out.hwpx")

    assert len(calls) == 1
    assert report.editor_open_safety is not None and report.editor_open_safety.ok


def test_a_stream_save_returns_the_report_of_the_bytes_it_wrote() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("흐름")
    stream = io.BytesIO()

    report = doc.save(stream)

    assert report.path is None
    assert report.editor_open_safety is not None
    _same_verdict(report.editor_open_safety, validate_editor_open_safety(stream.getvalue()))


def test_every_save_returns_its_own_report(tmp_path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("첫 저장")
    first = doc.save(tmp_path / "first.hwpx")
    doc.add_paragraph("두 번째 저장")

    second = doc.save(tmp_path / "second.hwpx")

    assert first.editor_open_safety is not second.editor_open_safety
    assert second.editor_open_safety is not None and second.editor_open_safety.ok


def test_bytes_the_package_did_not_verify_are_validated_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("직접 검증")
    # a package whose save does not verify (a custom implementation): the document validates instead
    monkeypatch.setattr(HwpxPackage, "_verify_editor_open_safe_archive", classmethod(lambda cls, source: None))

    report = doc.save(io.BytesIO())

    assert report.editor_open_safety is not None and report.editor_open_safety.ok


def test_the_report_stays_out_of_the_receipts_dictionary(tmp_path: Path) -> None:
    doc = HwpxDocument.new()

    report = doc.save(tmp_path / "out.hwpx")

    assert "editorOpenSafety" not in report.to_dict()
    assert report.editor_open_safety is not None
    assert report.editor_open_safety.to_dict()["ok"] is True
