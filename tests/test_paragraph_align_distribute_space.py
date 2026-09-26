# SPDX-License-Identifier: Apache-2.0
"""Hancom's space distribution (나눔 정렬, ``DISTRIBUTE_SPACE``) is a paragraph alignment."""
from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _horizontal(document: HwpxDocument, para_pr_id: object) -> str | None:
    element = next(
        el for el in document.oxml.headers[0].element.iter(f"{HH}paraPr") if el.get("id") == str(para_pr_id)
    )
    align = element.find(f"{HH}align")
    return None if align is None else align.get("horizontal")


@pytest.mark.parametrize("value", ["DISTRIBUTE_SPACE", "distribute_space"])
def test_space_distribution_is_accepted(value: str) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("나눔 정렬 문단입니다.")

    document.styles.apply_paragraph_format(paragraphs=[paragraph], alignment=value)

    assert _horizontal(document, paragraph.para_pr_id_ref) == "DISTRIBUTE_SPACE"


def test_space_distribution_and_distribution_stay_apart_and_survive_a_save() -> None:
    document = HwpxDocument.new()
    spaced = document.add_paragraph("나눔 정렬")
    spread = document.add_paragraph("배분 정렬")

    document.styles.apply_paragraph_format(paragraphs=[spaced], alignment="DISTRIBUTE_SPACE")
    document.styles.apply_paragraph_format(paragraphs=[spread], alignment="DISTRIBUTE")

    reopened = HwpxDocument.open(document.to_bytes())
    texts = {p.text: p for p in reopened.paragraphs}
    assert _horizontal(reopened, texts["나눔 정렬"].para_pr_id_ref) == "DISTRIBUTE_SPACE"
    assert _horizontal(reopened, texts["배분 정렬"].para_pr_id_ref) == "DISTRIBUTE"
