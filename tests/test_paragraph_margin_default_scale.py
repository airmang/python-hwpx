# SPDX-License-Identifier: Apache-2.0
"""Paragraph margins in ``hp:switch``: ``hp:default`` holds twice the ``hp:case`` value.

Hancom writes every paragraph margin twice, the ``hp:case`` branch in HWPUNIT and the
``hp:default`` branch at twice that value; readers that do not know the case branch read
the default one. A margin written outside ``hp:switch`` is kept as given.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
FIXTURES = Path(__file__).parent / "fixtures"


def _para_pr(document: HwpxDocument, para_pr_id: object) -> ET.Element:
    return next(
        el for el in document.oxml.headers[0].element.iter(f"{HH}paraPr") if el.get("id") == str(para_pr_id)
    )


def _values(para_pr: ET.Element, branch: str) -> dict[str, int]:
    margin = para_pr.find(f"{HP}switch/{HP}{branch}/{HH}margin")
    assert margin is not None
    return {child.tag.split("}")[1]: int(child.get("value", "0")) for child in margin}


@pytest.mark.parametrize(
    ("option", "value", "side", "case_value"),
    [
        ("indent_left_mm", 10, "left", 2835),
        ("indent_right_mm", 10, "right", 2835),
        ("first_line_indent_mm", -5, "intent", -1417),
        ("spacing_before_pt", 4, "prev", 400),
        ("spacing_after_pt", 6, "next", 600),
    ],
)
def test_default_branch_holds_twice_the_case_value(option: str, value: float, side: str, case_value: int) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("여백을 바꾼 문단")

    document.styles.apply_paragraph_format(paragraphs=[paragraph], **{option: value})

    para_pr = _para_pr(document, paragraph.para_pr_id_ref)
    assert _values(para_pr, "case")[side] == case_value
    assert _values(para_pr, "default")[side] == 2 * case_value


@pytest.mark.parametrize(
    "fixture", ["m7_toc_gold/hancom-native-toc-A.hwpx", "m3_gongmun_gold/seoul_sihaengmun.hwpx"]
)
def test_edited_margins_are_written_like_the_documents_own(fixture: str) -> None:
    document = HwpxDocument.open((FIXTURES / fixture).read_bytes())

    document.styles.apply_paragraph_format(indent_left_mm=12, first_line_indent_mm=-3, spacing_after_pt=5)
    reopened = HwpxDocument.open(document.to_bytes())

    for paragraph in reopened.paragraphs:
        para_pr = _para_pr(reopened, paragraph.para_pr_id_ref)
        case, default = _values(para_pr, "case"), _values(para_pr, "default")
        assert (case["left"], case["intent"], case["next"]) == (3402, -850, 500)
        assert default == {side: 2 * number for side, number in case.items()}


def test_a_margin_outside_the_switch_is_kept_as_given() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("여백")
    para_pr = _para_pr(document, paragraph.para_pr_id_ref)
    switch = para_pr.find(f"{HP}switch")
    assert switch is not None
    direct = copy.deepcopy(switch.find(f"{HP}case/{HH}margin"))
    assert direct is not None
    para_pr.remove(switch)
    para_pr.append(direct)

    document.styles.apply_paragraph_format(paragraphs=[paragraph], indent_left_mm=10)

    edited = _para_pr(document, paragraph.para_pr_id_ref)
    left = edited.find(f"{HH}margin/{HC}left")
    assert left is not None
    assert left.get("value") == "2835"
