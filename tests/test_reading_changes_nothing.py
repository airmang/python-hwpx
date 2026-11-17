# SPDX-License-Identifier: Apache-2.0
"""Reading never changes a document (asks10a): a document only read saves the bytes it was read from.

The one read that wrote, before: ``section.properties`` on a section without ``hp:secPr`` put an empty one in
the section's first run and marked the section changed. Hancom writes ``hp:secPr`` in every section, so this
only ever reached documents other writers made (``tests/fixtures/reader_robustness/irb_form_*``)."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from hwpx import HwpxDocument

FIXTURES = Path(__file__).parent / "fixtures"
NO_SECPR = FIXTURES / "reader_robustness" / "irb_form_blank.hwpx"


@pytest.fixture
def no_secpr() -> HwpxDocument:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = HwpxDocument.open(NO_SECPR)
    yield doc
    doc.close()


def _section_xml(doc: HwpxDocument) -> bytes:
    from lxml import etree

    return etree.tostring(doc.sections[0].element)


def test_reading_the_settings_of_a_section_without_them_changes_nothing(no_secpr: HwpxDocument) -> None:
    section = no_secpr.sections[0]
    before = _section_xml(no_secpr)
    properties = section.properties
    # what the file has: nothing written
    assert properties.page_size.width is None and properties.page_size.height is None
    assert no_secpr.page.size() == properties.page_size
    margins = no_secpr.page.margins()
    assert (margins.left, margins.right, margins.top, margins.bottom) == (None, None, None, None)
    assert properties.headers == () and properties.footers == ()
    assert _section_xml(no_secpr) == before
    assert not section.dirty


def test_a_write_puts_the_settings_in_the_section(no_secpr: HwpxDocument) -> None:
    section = no_secpr.sections[0]
    section.properties.set_page_size(width=59528, height=84188)
    assert section.dirty
    written = section.element.find(".//{http://www.hancom.co.kr/hwpml/2011/paragraph}secPr")
    assert written is not None and written is section.properties.element
    assert no_secpr.page.size().width == 59528
