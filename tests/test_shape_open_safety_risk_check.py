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

The check was first a ``warning``. It is now an ``error``: Hancom refuses to
open such a shape and crashes on an empty ``hp:ctrl``, so the public save
paths refuse the document and ``validate_package``/
``validate_editor_open_safety`` report it as blocking. Building a document
incrementally through the escape hatch still works; only saving it before
the required children are in place is refused.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.opc.package import _UNCHECKED_SAVE_TOKEN, HwpxPackageError
from hwpx.tools.package_validator import validate_editor_open_safety, validate_package


def _bytes_without_open_safety_gate(document: HwpxDocument) -> bytes:
    """The public save paths refuse a document Hancom cannot open; build its
    bytes the same way minus that gate, to look at what the validator says."""

    for part_name, payload in document._root.serialize().items():
        document._package.set_part(part_name, payload)
    data = document._package._save_bytes_unchecked(_unchecked_token=_UNCHECKED_SAVE_TOKEN)
    assert isinstance(data, bytes)
    return data

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def test_add_shape_escape_hatch_is_refused_on_save_and_reported_as_an_error() -> None:
    document = HwpxDocument.new()
    document.shapes.add_raw("rect")  # UserWarning at creation time -- not under test here.
    with pytest.raises(HwpxPackageError, match="hp:rect missing"):
        document.to_bytes()

    report = validate_package(_bytes_without_open_safety_gate(document))

    assert not report.ok
    shape_errors = [
        issue for issue in report.errors if issue.message.startswith("hp:rect missing offset")
    ]
    assert len(shape_errors) == 1
    for required in ("offset", "orgSz", "curSz", "sz", "pos"):
        assert required in shape_errors[0].message


def test_add_control_escape_hatch_is_refused_on_save_and_reported_as_an_error() -> None:
    document = HwpxDocument.new()
    document.shapes.add_control(control_type="LINE")
    with pytest.raises(HwpxPackageError, match="no control child"):
        document.to_bytes()

    report = validate_package(_bytes_without_open_safety_gate(document))

    assert not report.ok
    ctrl_errors = [issue for issue in report.errors if "hp:ctrl" in issue.message]
    assert len(ctrl_errors) == 1
    assert "no control child" in ctrl_errors[0].message


def test_validate_editor_open_safety_blocks_the_same_risk() -> None:
    document = HwpxDocument.new()
    document.shapes.add_raw("ellipse")

    safety = validate_editor_open_safety(_bytes_without_open_safety_gate(document))

    assert not safety.ok
    assert any("hp:ellipse missing" in str(issue) for issue in safety.blocking_package_errors)


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


# 2026-11 audit ENG-23: an empty 글맵시, OLE object or video made through the
# escape hatch passed the save gate, and Hancom (desktop 2024) dies opening
# the file -- exit code 0xC0000005, no warning. An empty equation opens fine.
@pytest.mark.parametrize("kind", ["textart", "ole", "video"])
def test_an_empty_text_art_ole_or_video_is_refused_on_save(kind: str) -> None:
    document = HwpxDocument.new()
    with pytest.warns(UserWarning):
        document.shapes.add_raw(kind)
    with pytest.raises(HwpxPackageError, match=f"hp:{kind} missing"):
        document.to_bytes()

    safety = validate_editor_open_safety(_bytes_without_open_safety_gate(document))

    assert not safety.ok
    assert any(f"hp:{kind} missing offset" in str(issue) for issue in safety.blocking_package_errors)


def test_an_empty_equation_still_saves() -> None:
    document = HwpxDocument.new()
    document.shapes.add_raw("equation")

    assert validate_editor_open_safety(document.to_bytes()).ok


@pytest.mark.parametrize(
    ("fixture", "tag"),
    [
        ("reader_writer__SimpleTextArt.hwpx", b"<hp:textart"),
        ("reader_writer__SimpleOLE.hwpx", b"<hp:ole"),
        ("reader_writer__SimpleVideo.hwpx", b"<hp:video"),
        ("unused_chart_saved.hwpx", b"<hp:ole"),
    ],
)
def test_text_art_ole_and_video_as_hancom_saves_them_pass_and_save_again(fixture: str, tag: bytes) -> None:
    import io
    import zipfile

    path = next(Path(__file__).parent.glob(f"fixtures/**/{fixture}"))
    assert validate_editor_open_safety(path.read_bytes()).ok

    document = HwpxDocument.open(path)
    document.add_paragraph("고친 문단")  # the section is written again, through the gate
    saved = document.to_bytes()

    assert validate_editor_open_safety(saved).ok
    with zipfile.ZipFile(io.BytesIO(saved)) as archive:
        assert any(tag in archive.read(name) for name in archive.namelist() if "section" in name)
