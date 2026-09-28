# SPDX-License-Identifier: Apache-2.0
"""What Hancom writes for a new bullet or numbered list, next to what ``apply_list_format`` writes.

The fixtures are lists Hancom saved: paragraphs given a bullet (level 1 or 2) or a number (level 1 or 3)
in a new document. ``docs/known-traps.md`` describes the differences checked here.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _heading(doc: HwpxDocument, paragraph) -> tuple[str | None, str | None, str | None]:
    element = doc.oxml.headers[0].element.find(f".//{HH}paraPr[@id='{paragraph.para_pr_id_ref}']/{HH}heading")
    if element is None:
        return None, None, None
    return element.get("type"), element.get("idRef"), element.get("level")


def _listed(doc: HwpxDocument) -> list:
    return [p for p in doc.paragraphs if _heading(doc, p)[0] not in (None, "NONE")]


def _number_levels(doc: HwpxDocument, numbering_id: str) -> dict[int, tuple[str | None, str | None]]:
    numbering = doc.oxml.headers[0].element.find(f".//{HH}numbering[@id='{numbering_id}']")
    assert numbering is not None
    return {int(head.get("level")): (head.get("numFormat"), head.text) for head in numbering.findall(f"{HH}paraHead")}


@pytest.mark.parametrize(("fixture", "level"), [("list_bullet_level1", "0"), ("list_bullet_level2", "1")])
def test_hancom_gives_a_new_bullet_list_its_built_in_bullet_at_every_level(fixture: str, level: str) -> None:
    doc = HwpxDocument.open((FIXTURES / f"{fixture}.hwpx").read_bytes())

    listed = _listed(doc)

    assert listed
    assert all(_heading(doc, paragraph) == ("BULLET", "0", level) for paragraph in listed)
    assert doc.oxml.headers[0].element.find(f".//{HH}bullet") is None


@pytest.mark.parametrize(("fixture", "level"), [("list_number_level1", "0"), ("list_number_level3", "2")])
def test_hancom_numbers_a_new_list_with_the_documents_default_definition(fixture: str, level: str) -> None:
    doc = HwpxDocument.open((FIXTURES / f"{fixture}.hwpx").read_bytes())

    listed = _listed(doc)

    assert listed
    assert all(_heading(doc, paragraph) == ("NUMBER", "1", level) for paragraph in listed)
    levels = _number_levels(doc, "1")
    assert (levels[1], levels[2], levels[3]) == (("DIGIT", "^1."), ("HANGUL_SYLLABLE", "^2."), ("DIGIT", "^3)"))


def _apply(kind: str, level: int) -> tuple[HwpxDocument, tuple[str | None, str | None, str | None]]:
    doc = HwpxDocument.new()
    doc.add_paragraph("항목")
    doc.styles.apply_list_format(paragraph_index=len(doc.paragraphs) - 1, kind=kind, level=level)
    return doc, _heading(doc, doc.paragraphs[-1])


@pytest.mark.parametrize(("level", "char"), [(1, "-"), (2, "○")])
def test_apply_list_format_writes_its_own_bullet(level: int, char: str) -> None:
    doc, (kind, ref, _) = _apply("bullet", level)

    bullet = doc.oxml.headers[0].element.find(f".//{HH}bullet[@id='{ref}']")

    assert kind == "BULLET" and bullet is not None and bullet.get("char") == char


@pytest.mark.parametrize(("level", "text"), [(1, "^1."), (2, "^1.^2."), (3, "^1.^2.^3.")])
def test_apply_list_format_joins_the_levels_of_a_number(level: int, text: str) -> None:
    doc, (kind, ref, head_level) = _apply("number", level)

    assert kind == "NUMBER" and ref is not None and head_level == str(level - 1)
    assert _number_levels(doc, ref)[level] == ("DIGIT", text)
