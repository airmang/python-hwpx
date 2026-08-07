# SPDX-License-Identifier: Apache-2.0
"""Safety net for the low-level shape/control escape hatches (cycle 6.6
train 22, next-gap-map B.2-1).

Background: ``add_shape``/``add_control`` are documented low-level escape
hatches -- they write only the element and attributes they are handed, so a
shape missing OWPML's required children (``offset``/``orgSz``/``curSz``/
``sz``/``pos``) or an empty ``<hp:ctrl>`` is not openable by real Hancom
(12.30.0, confirmed by negative control -- see docs/support-matrix.md's
"저수준 도형·컨트롤 탈출구" row). The only existing signal was a
``UserWarning`` at *creation* time -- ephemeral, tied to the call stack, not
persisted in the saved file. Neither ``validate_package`` nor
``validate_editor_open_safety`` caught this at all before this train:
running either against a document built this way reported ``ok=True``.

This is an *honest signal*, not a gate: the new check adds a ``warning``
-level ``PackageValidationIssue``, never an ``error`` -- ``.ok`` on both
report types stays ``True`` for an otherwise-valid document. Making it a
blocking error would be a scope change to what "editor-open-safe" already
means for anyone currently building documents incrementally through the
escape hatch across multiple calls, which is exactly what the escape hatch
is documented to allow.
"""
from __future__ import annotations

from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety, validate_package

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def test_add_shape_escape_hatch_is_caught_by_validate_package_as_a_warning() -> None:
    document = HwpxDocument.new()
    document.shapes.add_raw("rect")  # UserWarning at creation time -- not under test here.
    data = document.to_bytes()

    report = validate_package(data)

    assert report.ok, "a missing-children shape must not become a blocking error"
    shape_warnings = [
        issue for issue in report.warnings if issue.message.startswith("hp:rect missing")
    ]
    assert len(shape_warnings) == 1
    warning = shape_warnings[0]
    assert warning.level == "warning"
    for required in ("offset", "orgSz", "curSz", "sz", "pos"):
        assert required in warning.message


def test_add_control_escape_hatch_is_caught_by_validate_package_as_a_warning() -> None:
    document = HwpxDocument.new()
    document.shapes.add_control(control_type="LINE")
    data = document.to_bytes()

    report = validate_package(data)

    assert report.ok
    ctrl_warnings = [issue for issue in report.warnings if "hp:ctrl" in issue.message]
    assert len(ctrl_warnings) == 1
    assert ctrl_warnings[0].level == "warning"
    assert "no control child" in ctrl_warnings[0].message


def test_validate_editor_open_safety_surfaces_the_same_risk_and_stays_ok() -> None:
    document = HwpxDocument.new()
    document.shapes.add_raw("ellipse")
    data = document.to_bytes()

    safety = validate_editor_open_safety(data)

    assert safety.ok, safety.summary
    payload = safety.to_dict()
    assert any(
        "hp:ellipse missing" in warning for warning in payload["validatePackage"]["warnings"]
    )


def test_dedicated_shape_helpers_produce_no_open_safety_risk_warnings() -> None:
    """Regression guard: the dedicated helpers this row's own docs point
    people to (``add_line``/``add_rectangle``/``add_ellipse``/``add_polygon``)
    always build the complete OWPML child set, so this new check must never
    fire against their output."""

    document = HwpxDocument.new()
    document.shapes.add_line(0, 0, 14400, 7200)
    document.shapes.add_rectangle(14400, 7200, fill_color="#CCE5FF")
    document.shapes.add_ellipse(10000, 6000, fill_color="#FFD9CC")
    document.shapes.add_polygon([(0, 7200), (14400, 7200), (7200, 0)])
    data = document.to_bytes()

    report = validate_package(data)

    assert report.ok
    shape_risk_warnings = [
        issue
        for issue in report.warnings
        if issue.message.startswith("hp:") and "missing" in issue.message
    ]
    assert shape_risk_warnings == []


def test_container_members_do_not_false_positive() -> None:
    """A group container's members legitimately omit offset/orgSz/curSz/sz/
    pos by design (DEV-016 -- the AbstractShapeObjectType tail belongs to
    the group, not its members) -- confirmed by a real-corpus sweep (179/179
    container-nested shapes "missing" these 5, by contract, not defect).
    The new check must skip anything nested inside hp:container entirely,
    or every container-authored document would falsely trip it."""

    from hwpx.oxml import ContainerMember

    document = HwpxDocument.new()
    members = [
        ContainerMember.rect(0, 0, 4000, 3000, fill_color="#A0BEE0"),
        ContainerMember.ellipse(4500, 0, 4000, 3000, fill_color="#F1CB7E"),
    ]
    document.shapes.add_container(members, section=0)
    data = document.to_bytes()

    report = validate_package(data)

    assert report.ok
    shape_risk_warnings = [
        issue
        for issue in report.warnings
        if issue.message.startswith("hp:") and "missing" in issue.message
    ]
    assert shape_risk_warnings == [], (
        "container members must not be flagged -- they correctly lack the "
        "AbstractShapeObjectType tail by design"
    )


def test_real_corpus_produces_zero_shape_open_safety_risk_warnings() -> None:
    """Sweep every vendored real document -- real Hancom output is complete
    by construction, so this new check must be silent across the whole
    corpus (47 files, including reader_writer__SimpleContainer.hwpx's 74
    real containers) or it is too aggressive to trust."""

    samples = sorted(CORPUS.glob("*.hwpx"))
    assert samples, "expected the vendored corpus to be present"

    offenders: list[str] = []
    for sample in samples:
        report = validate_package(sample)
        risky = [
            issue
            for issue in report.warnings
            if issue.message.startswith("hp:") and "missing" in issue.message
        ]
        if risky:
            offenders.append(f"{sample.name}: {[str(i) for i in risky]}")

    assert offenders == [], offenders
