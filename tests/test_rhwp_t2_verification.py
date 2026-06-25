"""rhwp T2 — verification-depth batch (nibble-class, no Hancom needed).

Item 1: prove authored documents HONOR the canonical OWPML default traps
(the gap the analysis flagged was "we cannot prove we honor snapToGrid /
numbering start"). These lock it as evidence.
"""

from __future__ import annotations

import io
import zipfile

from hwpx.document import HwpxDocument
from hwpx.oxml.canonical_defaults import (
    CELL_COL_SPAN_DEFAULT,
    CELL_ROW_SPAN_DEFAULT,
    NUMBERING_START_DEFAULT,
)


def _section_xml(document: HwpxDocument) -> str:
    data = document.to_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        return archive.read(name).decode("utf-8")


def test_authored_table_cells_honor_span_defaults() -> None:
    document = HwpxDocument.new()
    document.add_table(2, 2)
    xml = _section_xml(document)
    assert f'colSpan="{CELL_COL_SPAN_DEFAULT}"' in xml
    assert f'rowSpan="{CELL_ROW_SPAN_DEFAULT}"' in xml
    # Never the corrupting 0-span.
    assert 'colSpan="0"' not in xml
    assert 'rowSpan="0"' not in xml


def test_authored_paragraphs_never_disable_snap_to_grid() -> None:
    # snapToGrid defaults TRUE in OWPML; honoring it means never emitting
    # snapToGrid="0" on an authored document.
    document = HwpxDocument.new()
    document.add_paragraph("본문 한 줄")
    data = document.to_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if name.endswith(".xml"):
                assert 'snapToGrid="0"' not in archive.read(name).decode("utf-8")


def test_canonical_numbering_start_default_is_one() -> None:
    # The audited table is the single source; the emit path uses "1".
    assert NUMBERING_START_DEFAULT == 1


# --------------------------------------------------------------------------- #
# Item 2: output-vs-intent section reconciliation                              #
# --------------------------------------------------------------------------- #
def test_reconcile_matches_for_authored_document() -> None:
    from hwpx.tools.package_reconcile import reconcile_package_with_document

    document = HwpxDocument.new()
    document.add_paragraph("a")
    report = reconcile_package_with_document(document.to_bytes(), document)
    assert report.ok
    assert report.expected_sections == report.produced_sections == 1


def test_reconcile_detects_section_count_mismatch() -> None:
    from hwpx.tools.package_reconcile import reconcile_package_with_document

    document = HwpxDocument.new()
    data = document.to_bytes()  # 1 section part

    class _FakeModel:
        sections = (object(), object())  # claims 2 sections

    report = reconcile_package_with_document(data, _FakeModel())
    assert not report.ok
    assert report.expected_sections == 2
    assert report.produced_sections == 1
    assert "section part count mismatch" in report.summary()


def test_builder_verify_reports_section_reconciliation() -> None:
    from hwpx.builder import Document, Paragraph, Section

    report = Document(sections=[Section(children=[Paragraph(text="x")])]).verify()
    assert report.ok
    assert report.sections_reconciled is True
    assert report.to_dict()["reconcile"]["ok"] is True
