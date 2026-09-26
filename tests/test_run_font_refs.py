# SPDX-License-Identifier: Apache-2.0
"""``styles.ensure_run(font=...)`` points every language at the right font.

``hh:fontRef`` numbers fonts per language, so a font declared in some
languages only must not lend its id to the others; and a font the header
does not declare yet is declared (as Hancom does) instead of being dropped.
"""
from __future__ import annotations

from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
LANGS = {"HANGUL": "hangul", "LATIN": "latin", "HANJA": "hanja", "JAPANESE": "japanese",
         "OTHER": "other", "SYMBOL": "symbol", "USER": "user"}


def _faces(doc: HwpxDocument, char_pr_id: str) -> dict[str, str | None]:
    header = doc.oxml.headers[0].element
    char_pr = header.find(f".//{HH}charPr[@id='{char_pr_id}']")
    ref = char_pr.find(f"{HH}fontRef")
    faces: dict[str, str | None] = {}
    for fontface in header.iter(f"{HH}fontface"):
        attr = LANGS.get(fontface.get("lang", ""))
        if attr is None:
            continue
        font = fontface.find(f"{HH}font[@id='{ref.get(attr)}']")
        faces[attr] = font.get("face") if font is not None else None
    return faces


def test_a_font_the_header_lacks_is_declared_and_applied() -> None:
    doc = HwpxDocument.new()
    char_pr_id = doc.styles.ensure_run(font="맑은 고딕")
    assert set(_faces(doc, char_pr_id).values()) == {"맑은 고딕"}


def test_a_font_declared_in_one_language_leaves_the_others_alone() -> None:
    doc = HwpxDocument.new()
    base = _faces(doc, "0")
    doc.styles.ensure_font("바탕", lang="LATIN")  # latin: 함초롬바탕 0, 바탕 1
    doc.styles.ensure_font("맑은 고딕", lang="HANGUL")  # hangul: 1
    char_pr_id = doc.styles.ensure_run(font="맑은 고딕")
    faces = _faces(doc, char_pr_id)
    assert faces["hangul"] == "맑은 고딕"
    assert {k: v for k, v in faces.items() if k != "hangul"} == {k: v for k, v in base.items() if k != "hangul"}


def test_a_font_declared_everywhere_is_used_everywhere() -> None:
    doc = HwpxDocument.new()
    doc.styles.ensure_font("맑은 고딕")
    char_pr_id = doc.styles.ensure_run(font="맑은 고딕", bold=True)
    assert set(_faces(doc, char_pr_id).values()) == {"맑은 고딕"}
    assert doc.styles.ensure_run(font="맑은 고딕", bold=True) == char_pr_id
