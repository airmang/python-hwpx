"""A list level outside Hancom's ten is refused before anything changes.

Hancom lists have levels 1 to 10. A document whose list paragraph uses an eleventh is one Hancom cannot save
again: it stops while laying the document out, so no Hancom-saved file of one exists; the document is built
here instead.
"""

from __future__ import annotations

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _document() -> HwpxDocument:
    document = HwpxDocument.new()
    for index in range(3):
        document.add_paragraph(f"항목 {index + 1}")
    return document


def _parts(document: HwpxDocument) -> list[bytes]:
    return [etree.tostring(part.element) for part in (*document.oxml.headers, *document.sections)]


@pytest.mark.parametrize("level", [0, -1, 11, 255, 1.0, True])
@pytest.mark.parametrize("kind", ["number", "bullet"])
def test_a_list_level_outside_1_to_10_is_refused_before_anything_changes(level: object, kind: str) -> None:
    document = _document()
    before = _parts(document)

    with pytest.raises(HwpxValueError) as caught:
        document.styles.apply_list_format(paragraph_indexes=[1, 2, 3], kind=kind, level=level)  # type: ignore[arg-type]

    assert caught.value.code == "style-list-level-invalid"
    assert _parts(document) == before


@pytest.mark.parametrize("level", [1, 10])
def test_the_list_levels_hancom_has_are_written(level: int) -> None:
    document = _document()

    document.styles.apply_list_format(paragraph_indexes=[1, 2, 3], kind="number", level=level)

    paragraph = document.paragraphs[1]
    para_pr = next(pr for pr in document.oxml.headers[0].element.iter(f"{HH}paraPr")
                   if pr.get("id") == str(paragraph.para_pr_id_ref))
    heading = para_pr.find(f"{HH}heading")
    assert (heading.get("type"), heading.get("level")) == ("NUMBER", str(level - 1))
