# SPDX-License-Identifier: Apache-2.0
"""version.xml at its fixed path and not in the manifest is how Hancom saves; it is not a warning."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_package

HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"


def test_a_new_document_validates_without_warnings() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")

    report = validate_package(document.to_bytes())

    assert report.errors == ()
    assert [str(issue) for issue in report.warnings] == []


def test_a_hancom_saved_document_has_no_version_warning() -> None:
    sample = next(iter(sorted(HANCOM_SAVED.glob("*.hwpx"))), None)
    if sample is None:
        pytest.skip("no Hancom-saved fixture")
    with zipfile.ZipFile(sample) as archive:
        assert "version.xml" in archive.namelist()
        assert "version.xml" not in archive.read("Contents/content.hpf").decode("utf-8")

    report = validate_package(sample)

    assert not any("version" in str(issue) for issue in report.issues)


def test_a_manifest_naming_a_missing_version_part_is_still_an_error() -> None:
    source = HwpxDocument.new().to_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as archive, zipfile.ZipFile(out, "w") as target:
        for info in archive.infolist():
            data = archive.read(info)
            if info.filename == "Contents/content.hpf":
                data = data.replace(
                    b"<opf:manifest>",
                    b'<opf:manifest><opf:item id="version" href="Contents/ver.xml" media-type="application/xml"/>',
                    1,
                )
            target.writestr(info, data)

    report = validate_package(out.getvalue())

    assert any("version" in str(issue) for issue in report.errors)
