# SPDX-License-Identifier: Apache-2.0
from hwpx.tools.validator import ValidationIssue, ValidationReport, validate_document


def test_issue_has_severity_default_error():
    issue = ValidationIssue(part_name="Contents/section0.xml", message="x")
    assert issue.severity == "error"


def test_report_separates_errors_and_warnings():
    warn = ValidationIssue("p", "schema lint", severity="warning")
    err = ValidationIssue("p", "broken", severity="error")
    assert ValidationReport(("p",), (warn,)).ok is True
    assert ValidationReport(("p",), (warn,)).warnings == (warn,)
    assert ValidationReport(("p",), (err,)).ok is False
    assert ValidationReport(("p",), (err,)).errors == (err,)


def test_schema_failures_are_warnings_not_errors(tmp_path):
    # A structurally valid doc whose XML the schema rejects must still report ok:
    # schema failures are lint warnings, not hard errors.
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    path = tmp_path / "d.hwpx"
    doc.save_to_path(path)
    report = validate_document(path)
    assert all(i.severity == "warning" for i in report.issues)
    assert report.ok is True
