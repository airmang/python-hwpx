# SPDX-License-Identifier: Apache-2.0
"""Public ``doc.styles`` verbs that mint style and paragraph-format ids.

Companion layers used to reach into ``HwpxOxmlHeader`` privates
(``_styles_element``, ``_allocate_ref_id``, ``_update_item_count``) to add a
style. These verbs keep id allocation, ``itemCnt`` and dirty state in core.
"""

from __future__ import annotations

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxStateError

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _styles_element(doc: HwpxDocument):
    return doc.oxml.headers[0].element.find(f"{_HH}refList/{_HH}styles")


def test_ensure_style_creates_counts_and_survives_reopen() -> None:
    doc = HwpxDocument.new()
    before = len(doc.styles)
    para_pr = doc.styles.ensure_paragraph_format(
        base_para_pr_id="0",
        alignment="CENTER",
        break_setting={"keep_with_next": True},
    )
    style_id = doc.styles.ensure_style(
        "청사진 스타일",
        eng_name="Blueprint",
        para_pr_id_ref=para_pr,
        char_pr_id_ref="0",
        lang_id=0,
        lock_form=False,
    )
    assert doc.styles.ensure_style("청사진 스타일", next_style_id_ref=style_id) == style_id

    styles = _styles_element(doc)
    assert len(doc.styles) == before + 1
    assert styles.get("itemCnt") == str(len(styles.findall(f"{_HH}style")))
    element = next(item for item in styles if item.get("id") == style_id)
    assert element.get("type") == "PARA"
    assert element.get("paraPrIDRef") == para_pr
    assert element.get("nextStyleIDRef") == style_id
    assert element.get("lockForm") in (None, "0")  # absent reads as off

    reopened = HwpxDocument.open(doc.to_bytes())
    style = reopened.styles.resolve("청사진 스타일")
    assert style.id == int(style_id)
    paragraph_property = reopened.styles.paragraph_property(para_pr)
    assert paragraph_property is not None
    assert paragraph_property.align.horizontal == "CENTER"


def test_ensure_style_reuses_an_existing_name_without_duplicating() -> None:
    doc = HwpxDocument.new()
    existing = next(iter(doc.styles.values()))
    count = len(doc.styles)
    assert doc.styles.ensure_style(existing.name) == str(existing.id)
    assert len(doc.styles) == count


def test_ensure_paragraph_format_dedupes_identical_requests() -> None:
    doc = HwpxDocument.new()
    first = doc.styles.ensure_paragraph_format(base_para_pr_id="0", alignment="RIGHT")
    second = doc.styles.ensure_paragraph_format(base_para_pr_id="0", alignment="RIGHT")
    assert first == second
    heading = doc.styles.ensure_paragraph_format(
        base_para_pr_id="0", heading={"type": "NUMBER", "idRef": 1, "level": 0}
    )
    assert doc.styles.paragraph_property(heading).heading.type == "NUMBER"


def test_numberings_read_the_definitions_a_heading_points_to() -> None:
    doc = HwpxDocument.new()
    assert set(doc.styles.numberings) == {"1"}
    definition = doc.styles.numbering(1)
    assert definition is not None and definition.name == "numbering"
    assert doc.styles.numbering("1") is not None
    assert doc.styles.numbering(" 1 ") is not None
    assert doc.styles.numbering(999) is None
    assert doc.styles.numbering(None) is None
    doc.styles.ensure_numbering(kind="number")
    assert len(doc.styles.numberings) == 2


def test_verbs_raise_a_typed_error_without_a_header() -> None:
    doc = HwpxDocument.new()
    doc.oxml._headers.clear()  # what a package without header.xml leaves behind
    assert doc.styles.numberings == {}
    with pytest.raises(HwpxStateError) as caught:
        doc.styles.ensure_style("x")
    assert caught.value.code == "document-header-missing"
    with pytest.raises(HwpxStateError):
        doc.styles.ensure_paragraph_format(alignment="LEFT")
