# SPDX-License-Identifier: Apache-2.0
"""Regression: validate_document must not crash on comment / PI nodes.

The validator serializes each header/section element back to XML before
running schema checks. lxml comment nodes carry a callable ``.tag`` that
stdlib's ``xml.etree.ElementTree.tostring`` cannot serialize, so it raised
``TypeError: cannot serialize <cyfunction Comment ...>``. The sibling reader
fix lived in ``hwpx.oxml`` (``_element_local_name``); this guards the
save/validation path.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.tools.validator import validate_document

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "reader_robustness"
    / "irb_form_blank.hwpx"
)


def _fixture_has_comment() -> bool:
    if not _FIXTURE.exists():
        return False
    with zipfile.ZipFile(_FIXTURE) as archive:
        section = archive.read("Contents/section0.xml")
    return b"<!--" in section


@pytest.mark.skipif(
    not _fixture_has_comment(),
    reason="fixture missing or no longer carries an XML comment node",
)
def test_validate_document_runs_on_comment_bearing_section():
    # Two comment-node crashes lived on this path and both must stay fixed:
    #   1. _iter_parts serialized lxml elements with stdlib ET.tostring, which
    #      raised TypeError on a comment's callable .tag.
    #   2. parse_section_xml's model build called utils.local_name on the
    #      comment, raising ValueError("Invalid input tag ...").
    # Either one turned a clean schema pass into a hard failure.
    report = validate_document(_FIXTURE)

    # Schema checking actually ran on the section part (it was not skipped).
    assert any(part.endswith("section0.xml") for part in report.validated_parts)

    # Honest schema result: comment handling must not surface as a hard error.
    # Schema-rule lint may still appear as warnings; only real errors fail .ok.
    assert report.errors == ()
    assert report.ok is True
