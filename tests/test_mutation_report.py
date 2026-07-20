"""Safe Write Contract (S-089 P1) — MutationReport measurement + enforcement.

Covers the ``mode``/``fallback``/``return_report`` additions to the save funnel:
the default return is unchanged, ``mode="patch"`` publishes when preservation
holds, and a downgrade is rejected before any byte is written (``fallback=
"error"``) or accepted with ``fallbackUsed`` (``fallback="rebuild"``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.mutation_report import (
    MUTATION_REPORT_SCHEMA,
    ChangedPart,
    MutationReport,
    PreservationCounts,
    PreservationDowngradeError,
    PreservationMeasurement,
    PreservationSummary,
)


def _base_document(path: Path) -> None:
    """Write a small table document to *path* as a reopen source."""

    document = HwpxDocument.new()
    document.add_paragraph("도입")
    table = document.add_table(2, 2)
    table.cell(0, 0).text = "a"
    table.cell(0, 1).text = "b"
    document.save_to_path(path)


def _first_table(document: HwpxDocument):
    return next(table for paragraph in document.paragraphs for table in paragraph.tables)


# --------------------------------------------------------------------------- #
# 1. Default save is unchanged (the wider suite green is the real proof).
# --------------------------------------------------------------------------- #
def test_default_save_to_path_still_returns_path(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("x")
    target = tmp_path / "out.hwpx"

    result = document.save_to_path(target)

    assert result == target
    assert target.exists()
    assert not isinstance(result, MutationReport)


def test_default_to_bytes_still_returns_bytes() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("x")

    assert isinstance(document.to_bytes(), bytes)


# --------------------------------------------------------------------------- #
# 2. No-op save: patch publishes, whole-package identical, no changed parts.
# --------------------------------------------------------------------------- #
def test_noop_patch_save_reports_whole_package_identical(tmp_path: Path) -> None:
    base = tmp_path / "base.hwpx"
    _base_document(base)

    reopened = HwpxDocument.open(base)
    target = tmp_path / "noop.hwpx"
    report = reopened.save_to_path(target, mode="patch", return_report=True)

    assert isinstance(report, MutationReport)
    assert target.exists()
    assert report.actual_mode == "patch"
    assert report.fallback_used is False
    assert report.changed_parts == ()
    assert report.preservation.whole_package_identical is True
    assert report.preservation.untouched_part_payloads.changed == 0


# --------------------------------------------------------------------------- #
# 3. One-cell edit: patch publishes, the dirty section is a predeclared change.
# --------------------------------------------------------------------------- #
def test_one_cell_edit_patch_lists_dirty_section(tmp_path: Path) -> None:
    base = tmp_path / "base.hwpx"
    _base_document(base)

    reopened = HwpxDocument.open(base)
    _first_table(reopened).cell(0, 0).text = "EDITED"
    target = tmp_path / "edited.hwpx"
    report = reopened.save_to_path(target, mode="patch", return_report=True)

    assert isinstance(report, MutationReport)
    assert target.exists()
    assert report.actual_mode == "patch"
    changed = {part.path: part.reason for part in report.changed_parts}
    assert changed == {"Contents/section0.xml": "dirty-part"}
    assert report.changed_parts[0].ranges is None
    assert report.preservation.untouched_part_payloads.changed == 0
    assert report.preservation.untouched_part_payloads.verified > 0
    assert report.preservation.whole_package_identical is False


def test_one_cell_edit_patch_does_not_raise_via_to_bytes(tmp_path: Path) -> None:
    base = tmp_path / "base.hwpx"
    _base_document(base)

    reopened = HwpxDocument.open(base)
    _first_table(reopened).cell(0, 0).text = "EDITED"

    # A predeclared single-section edit is patch-grade, so to_bytes must not raise.
    assert isinstance(reopened.to_bytes(mode="patch", fallback="error"), bytes)


# --------------------------------------------------------------------------- #
# 4. Injected unexpected-part change → error rejects (no file), rebuild accepts.
# --------------------------------------------------------------------------- #
def _injected_measurement(*_args: object, **_kwargs: object) -> PreservationMeasurement:
    return PreservationMeasurement(
        changed_parts=(
            ChangedPart(path="Contents/header.xml", reason="unexpected", ranges=None),
        ),
        preservation=PreservationSummary(
            untouched_part_payloads=PreservationCounts(verified=9, changed=1),
            untouched_local_zip_records=PreservationCounts(verified=10, changed=0),
            whole_package_identical=False,
        ),
        offending_parts=("Contents/header.xml",),
    )


def test_patch_error_rejects_downgrade_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hwpx._document.persistence.measure_save", _injected_measurement
    )
    document = HwpxDocument.new()
    document.add_paragraph("x")
    target = tmp_path / "rejected.hwpx"

    with pytest.raises(PreservationDowngradeError) as excinfo:
        document.save_to_path(target, mode="patch", fallback="error")

    assert not target.exists()
    error = excinfo.value
    assert error.requested_mode == "patch"
    assert error.achieved_grade == "rebuild"
    assert error.offending_parts == ("Contents/header.xml",)


def test_patch_error_via_to_bytes_raises_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hwpx._document.persistence.measure_save", _injected_measurement
    )
    document = HwpxDocument.new()
    document.add_paragraph("x")

    with pytest.raises(PreservationDowngradeError):
        document.to_bytes(mode="patch", fallback="error")


def test_patch_rebuild_fallback_publishes_with_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hwpx._document.persistence.measure_save", _injected_measurement
    )
    document = HwpxDocument.new()
    document.add_paragraph("x")
    target = tmp_path / "rebuilt.hwpx"

    report = document.save_to_path(
        target, mode="patch", fallback="rebuild", return_report=True
    )

    assert isinstance(report, MutationReport)
    assert target.exists()
    assert report.actual_mode == "rebuild"
    assert report.fallback_used is True


# --------------------------------------------------------------------------- #
# 5. return_report overload + camelCase to_dict round-trip.
# --------------------------------------------------------------------------- #
def test_return_report_to_dict_camel_case_round_trip(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    target = tmp_path / "report.hwpx"

    report = document.save_to_path(target, return_report=True)

    assert isinstance(report, MutationReport)
    payload = report.to_dict()
    # Survives a JSON round-trip (all values are JSON-native).
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
    assert payload["schemaVersion"] == MUTATION_REPORT_SCHEMA
    assert set(payload) == {
        "schemaVersion",
        "ok",
        "path",
        "requestedMode",
        "actualMode",
        "fallbackUsed",
        "changedParts",
        "preservation",
        "verification",
    }
    assert payload["requestedMode"] == "auto"
    assert set(payload["preservation"]) == {
        "untouchedPartPayloads",
        "untouchedLocalZipRecords",
        "wholePackageIdentical",
    }
    assert set(payload["verification"]) == {
        "package",
        "openSafety",
        "reopen",
        "visual",
    }
    assert payload["verification"]["visual"] == "not_performed"


def test_stream_return_report_has_null_path() -> None:
    import io

    document = HwpxDocument.new()
    document.add_paragraph("stream")
    buffer = io.BytesIO()

    report = document.save_to_stream(buffer, return_report=True)

    assert isinstance(report, MutationReport)
    assert report.path is None
    assert report.to_dict()["path"] is None
    assert buffer.getvalue() != b""


def test_byte_splice_projection_accepts_path_source(tmp_path) -> None:
    from pathlib import Path as _P

    from hwpx.table_patch import fill_cells

    fixture = _P(__file__).parent / "fixtures" / "m2_corpus" / "form_002.hwpx"
    out = tmp_path / "filled.hwpx"
    result = fill_cells(
        fixture, [{"table_index": 0, "row": 1, "col": 1, "text": "검증"}],
        output_path=out,
    )
    # A caller naturally holds the source *path*; the projection must accept it
    # (str and Path) and measure the same preservation as raw bytes.
    for source in (fixture, str(fixture), fixture.read_bytes()):
        report = result.as_mutation_report(source=source)
        payload = report.to_dict()
        assert payload["actualMode"] == "patch"
        assert payload["preservation"]["untouchedPartPayloads"]["changed"] == 0
        parts = [p["path"] for p in payload["changedParts"]]
        assert any(p.endswith("section0.xml") for p in parts)
        ranges = payload["changedParts"][0]["ranges"]
        assert ranges and ranges[0]["coordinateSpace"] == "uncompressed-part-bytes"


def test_sneaky_low_level_part_swap_is_refused_under_patch_mode(tmp_path) -> None:
    """A set_part applied before save must not launder through mode="patch".

    The measurement baseline is the OPEN-TIME archive: without it, the swapped
    part is already inside the package when the pre-save snapshot is taken and
    the downgrade goes undetected (found live by the demo prototype).
    """
    from pathlib import Path as _P

    from hwpx.document import HwpxDocument
    from hwpx.mutation_report import PreservationDowngradeError

    fixture = _P(__file__).parent / "fixtures" / "m2_corpus" / "form_002.hwpx"
    target = tmp_path / "refused.hwpx"

    doc = HwpxDocument.open(fixture)
    try:
        payload = doc._package.read("Contents/header.xml")
        doc._package.set_part("Contents/header.xml", payload + b"<!-- sneaky -->")
        with pytest.raises(PreservationDowngradeError):
            doc.save_to_path(target, mode="patch")
        assert not target.exists()
        # fallback="rebuild" is the explicit consent path — publishes + reports.
        report = doc.save_to_path(
            target, mode="patch", fallback="rebuild", return_report=True
        )
        assert target.exists()
        payload_dict = report.to_dict()
        assert payload_dict["fallbackUsed"] is True
        assert any(
            part["path"].endswith("header.xml")
            for part in payload_dict["changedParts"]
        )
    finally:
        doc.close()


def test_second_save_measures_against_the_published_baseline(tmp_path) -> None:
    from pathlib import Path as _P

    from hwpx.document import HwpxDocument

    fixture = _P(__file__).parent / "fixtures" / "m2_corpus" / "form_002.hwpx"
    doc = HwpxDocument.open(fixture)
    try:
        doc.add_paragraph("첫 저장")
        doc.save_to_path(tmp_path / "one.hwpx")
        # After a successful publish the baseline advances: an immediate
        # unchanged save is whole-package quiet, not a re-report of save one.
        report = doc.save_to_path(
            tmp_path / "two.hwpx", mode="patch", return_report=True
        )
        assert report.to_dict()["preservation"]["untouchedPartPayloads"]["changed"] == 0
    finally:
        doc.close()
