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


# --------------------------------------------------------------------------- #
# Item 3: semantic (value-level) IR equality                                   #
# --------------------------------------------------------------------------- #
_NS = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
_TWO_RUNS = (
    f"<sec {_NS}><hp:p><hp:run><hp:t>Hello</hp:t></hp:run>"
    f"<hp:run><hp:t>World</hp:t></hp:run></hp:p></sec>"
)
_FLATTENED = (
    f"<sec {_NS}><hp:p><hp:run><hp:t>HelloWorld</hp:t></hp:run></hp:p></sec>"
)


def _doc_bytes(section_xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Contents/section0.xml", section_xml)
    return buffer.getvalue()


def test_projection_keeps_run_sequence() -> None:
    from hwpx.tools.ir_equality import project_section_xml

    assert project_section_xml(_TWO_RUNS) == [[("t", "Hello"), ("t", "World")]]


def test_semantic_compare_detects_run_flattening() -> None:
    from hwpx.tools.ir_equality import compare_documents_semantic

    report = compare_documents_semantic(_doc_bytes(_TWO_RUNS), _doc_bytes(_FLATTENED))
    assert not report.ok
    # the flatten collapses 2 runs -> 1, surfaced as a length difference on para 0
    assert any("doc[0]" in d and "!= 1" in d for d in report.differences)


def test_semantic_compare_equal_documents() -> None:
    from hwpx.tools.ir_equality import compare_documents_semantic

    report = compare_documents_semantic(_doc_bytes(_TWO_RUNS), _doc_bytes(_TWO_RUNS))
    assert report.ok


def test_real_document_roundtrip_is_semantically_equal() -> None:
    from hwpx.tools.ir_equality import compare_documents_semantic

    document = HwpxDocument.new()
    document.add_paragraph("문단 하나")
    document.add_table(2, 2)
    data = document.to_bytes()
    rt = HwpxDocument.open(data).to_bytes()
    assert compare_documents_semantic(data, rt).ok


# --------------------------------------------------------------------------- #
# Item 4: ranked roundtrip batch harness                                       #
# --------------------------------------------------------------------------- #
from pathlib import Path  # noqa: E402

_CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def test_classify_generated_document_passes(tmp_path) -> None:
    from hwpx.conformance.roundtrip_batch import classify_sample

    document = HwpxDocument.new()
    document.add_paragraph("본문")
    path = tmp_path / "gen.hwpx"
    document.save_to_path(path)
    result = classify_sample(path)
    assert result.status == "PASS"
    assert not result.is_hard_fail


def test_corpus_batch_has_no_structural_failures() -> None:
    from hwpx.conformance.roundtrip_batch import run_corpus

    report = run_corpus(_CORPUS)
    assert len(report.results) == 47
    # No PARSE/SERIALIZE/REPARSE failures across the corpus.
    assert report.ok, report.counts
    assert report.hard_fail_count == 0
    # Every sample is at worst a gradable diff, never a hard fail.
    assert all(r.status in {"PASS", "ROUND2_DIFF"} for r in report.results), report.counts


def test_batch_report_tsv_and_json_shape() -> None:
    from hwpx.conformance.roundtrip_batch import BatchReport, SampleResult

    report = BatchReport(results=[SampleResult("a.hwpx", "PASS", source_semantic_drift=True)])
    tsv = report.to_tsv()
    assert tsv.startswith("sample\tstatus\tsource_drift\tdetail")
    assert "a.hwpx\tPASS\t1\t" in tsv
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["counts"] == {"PASS": 1}
    assert payload["sourceDriftCount"] == 1


# --------------------------------------------------------------------------- #
# Item 5: forward-compatible plan schemaVersion handling                       #
# --------------------------------------------------------------------------- #
def test_newer_plan_schema_version_warns_not_rejects() -> None:
    from hwpx.authoring import validate_document_plan

    plan = {
        "schemaVersion": "hwpx.document_plan.v3",  # newer than latest known (v2)
        "title": "테스트",
        "blocks": [{"type": "paragraph", "text": "본문"}],
    }
    report = validate_document_plan(plan)
    codes = {issue.code for issue in report.issues}
    assert "invalid_schema_version" not in codes  # not hard-rejected
    assert "forward_schema_version" in codes  # warned instead
    forward = next(i for i in report.issues if i.code == "forward_schema_version")
    assert forward.severity == "warning"
    assert report.schema_version == "hwpx.document_plan.v3"


def test_garbage_plan_schema_version_still_errors() -> None:
    from hwpx.authoring import validate_document_plan

    report = validate_document_plan(
        {"schemaVersion": "not-a-version", "title": "x", "blocks": [{"type": "paragraph", "text": "y"}]}
    )
    codes = {issue.code for issue in report.issues}
    assert "invalid_schema_version" in codes
    assert not report.ok
