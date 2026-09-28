# SPDX-License-Identifier: Apache-2.0
"""``apply_list_format(continue_list=True)``: a numbered list applied in several calls numbers on.

Hancom counts a list per numbering definition. Each ``apply_list_format(kind="number")`` call makes a
new definition, so three calls on three paragraphs draw ``1.`` three times in Hancom; one call on the
three draws ``1.``, ``2.``, ``3.``. ``continue_list=True`` puts the paragraphs in the definition of the
numbered list before them.
"""
from __future__ import annotations

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _heading(doc: HwpxDocument, paragraph) -> tuple[str | None, str | None, str | None]:
    element = doc.oxml.headers[0].element.find(f".//{HH}paraPr[@id='{paragraph.para_pr_id_ref}']/{HH}heading")
    if element is None:
        return None, None, None
    return element.get("type"), element.get("idRef"), element.get("level")


def _numberings(doc: HwpxDocument) -> int:
    return len(doc.oxml.headers[0].element.findall(f".//{HH}numbering"))


def _items(doc: HwpxDocument, *texts: str) -> list[int]:
    indexes = []
    for text in texts:
        doc.add_paragraph(text)
        indexes.append(len(doc.paragraphs) - 1)
    return indexes


def test_separate_calls_start_a_new_list_each() -> None:
    doc = HwpxDocument.new()
    for index in _items(doc, "하나", "둘", "셋"):
        doc.styles.apply_list_format(paragraph_index=index, kind="number")

    refs = {_heading(doc, paragraph)[1] for paragraph in doc.paragraphs[-3:]}

    assert len(refs) == 3


def test_continue_list_numbers_on_in_the_list_before() -> None:
    doc = HwpxDocument.new()
    first, second, _body, third = _items(doc, "하나", "둘", "본문", "셋")
    doc.styles.apply_list_format(paragraph_index=first, kind="number")
    made = _numberings(doc)

    doc.styles.apply_list_format(paragraph_index=second, kind="number", continue_list=True)
    doc.styles.apply_list_format(paragraph_index=third, kind="number", continue_list=True)

    headings = [_heading(doc, doc.paragraphs[index]) for index in (first, second, third)]
    assert headings == [headings[0]] * 3
    assert headings[0][0] == "NUMBER"
    assert _numberings(doc) == made


def test_continue_list_at_a_deeper_level_stays_in_the_list() -> None:
    doc = HwpxDocument.new()
    first, second = _items(doc, "하나", "하나의 하나")
    doc.styles.apply_list_format(paragraph_index=first, kind="number")

    doc.styles.apply_list_format(paragraph_index=second, kind="number", level=2, continue_list=True)

    kind, ref, level = _heading(doc, doc.paragraphs[second])
    assert (kind, ref, level) == ("NUMBER", _heading(doc, doc.paragraphs[first])[1], "1")
    # The list's numbering now has a level-2 head too: Hancom draws no number for a missing level.
    numbering = doc.oxml.headers[0].element.find(f".//{HH}numbering[@id='{ref}']")
    assert [(head.get("level"), head.text) for head in numbering.findall(f"{HH}paraHead")] == [
        ("1", "^1."),
        ("2", "^1.^2."),
    ]


def test_continue_list_without_a_list_before_starts_one() -> None:
    doc = HwpxDocument.new()
    [only] = _items(doc, "하나")
    before = _numberings(doc)

    doc.styles.apply_list_format(paragraph_index=only, kind="number", continue_list=True)

    assert _heading(doc, doc.paragraphs[only])[0] == "NUMBER"
    assert _numberings(doc) == before + 1


@pytest.mark.parametrize("given", [{"number_format": "HANGUL_SYLLABLE"}, {"start": 3}])
def test_continue_list_with_a_number_format_or_start_is_refused(given: dict) -> None:
    doc = HwpxDocument.new()
    first, second = _items(doc, "하나", "둘")
    doc.styles.apply_list_format(paragraph_index=first, kind="number")
    before = (_numberings(doc), _heading(doc, doc.paragraphs[second]))

    with pytest.raises(HwpxValueError) as raised:
        doc.styles.apply_list_format(paragraph_index=second, kind="number", continue_list=True, **given)

    assert raised.value.code == "style-list-continue-conflict"
    assert (_numberings(doc), _heading(doc, doc.paragraphs[second])) == before


def test_continue_list_changes_nothing_for_bullets() -> None:
    plain, continued = HwpxDocument.new(), HwpxDocument.new()
    for doc, flag in ((plain, False), (continued, True)):
        first, second = _items(doc, "하나", "둘")
        doc.styles.apply_list_format(paragraph_index=first, kind="bullet")
        doc.styles.apply_list_format(paragraph_index=second, kind="bullet", continue_list=flag)

    assert [_heading(plain, p) for p in plain.paragraphs] == [_heading(continued, p) for p in continued.paragraphs]
