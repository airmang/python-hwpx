# SPDX-License-Identifier: Apache-2.0
"""A failed open raises its error without first logging a traceback at warning level or above."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.opc.package import HwpxPackageError


def _loud(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name.startswith("hwpx") and r.levelno >= logging.WARNING]


def test_an_encrypted_document_logs_nothing_loud(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from tests.test_error_messages import _ENCRYPTED, _odf_manifest, _package

    caplog.set_level(logging.DEBUG)
    source = _package(tmp_path, manifest=_odf_manifest(_ENCRYPTED), garble=_ENCRYPTED)
    with pytest.raises(etree.XMLSyntaxError):
        HwpxDocument.open(source)

    assert _loud(caplog) == []
    assert all(r.exc_info is None or r.levelno == logging.DEBUG for r in caplog.records)


def _without(part: str) -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            if info.filename != part:
                target.writestr(info, source.read(info))
    return out.getvalue()


def test_a_missing_section_part_logs_nothing_loud(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(HwpxPackageError):
        HwpxDocument.open(_without("Contents/section0.xml"))
    assert _loud(caplog) == []


def test_a_missing_preview_opens_without_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    data = _without("Preview/PrvText.txt")  # container.xml names it as a rootfile
    caplog.set_level(logging.WARNING)
    HwpxDocument.open(data).close()
    assert _loud(caplog) == []
