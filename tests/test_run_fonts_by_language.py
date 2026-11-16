# SPDX-License-Identifier: Apache-2.0
"""``run.fonts``: the face of each of the seven language blocks, as one value.

``run.font`` reads the Hangul face only. A character shape names a face per language
(``hh:fontRef`` hangul/latin/hanja/japanese/other/symbol/user); Hangul-saved documents often use
another face for Latin text (5,312 character shapes of the public corpus name different faces).
"""

from __future__ import annotations

import dataclasses
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.objects import LanguageFonts

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")


def test_set_font_for_one_language_reads_back_per_language() -> None:
    doc = HwpxDocument.new()
    run = doc.add_paragraph("").add_run("한글 Latin")
    base = run.fonts
    assert isinstance(base, LanguageFonts) and base.hangul == run.font

    run.set_font("Arial", lang="LATIN")

    fonts = run.fonts
    assert fonts.latin == "Arial"
    assert fonts.hangul == base.hangul and run.font == base.hangul
    assert dataclasses.replace(fonts, latin=base.latin) == base
    reopened = HwpxDocument.open(doc.to_bytes())
    (again,) = [r for r in reopened.paragraphs[-1].runs if r.text == "한글 Latin"]
    assert again.fonts == fonts


def test_one_face_for_every_language() -> None:
    doc = HwpxDocument.new()
    run = doc.add_paragraph("").add_run("글")
    run.set_font("맑은 고딕")
    assert set(run.fonts.to_dict().values()) == {"맑은 고딕"}
    assert list(run.fonts.to_dict()) == list(LANGS)


def test_a_run_without_a_character_shape_reads_no_faces() -> None:
    doc = HwpxDocument.new()
    run = doc.add_paragraph("").add_run("글")
    run.element.attrib.pop("charPrIDRef", None)
    assert run.fonts == LanguageFonts()
    with pytest.raises(dataclasses.FrozenInstanceError):
        run.fonts.latin = "Arial"  # type: ignore[misc]


def _faces_from_xml(path: Path) -> dict[str, dict[str, str | None]]:
    """charPr id -> language -> face, read straight from header.xml."""

    with zipfile.ZipFile(path) as archive:
        head = etree.fromstring(archive.read("Contents/header.xml"))
    blocks = {
        (fontface.get("lang") or "").lower(): {font.get("id"): font.get("face") for font in fontface.findall(f"{HH}font")}
        for fontface in head.iter(f"{HH}fontface")
    }
    shapes = {}
    for char_pr in head.iter(f"{HH}charPr"):
        ref = char_pr.find(f"{HH}fontRef")
        shapes[char_pr.get("id")] = {
            lang: (blocks.get(lang, {}).get(ref.get(lang)) if ref is not None else None) for lang in LANGS
        }
    return shapes


def test_hangul_saved_runs_read_each_language_face() -> None:
    # a Hangul-saved document whose body text uses a shape with another face in its user block
    path = FIXTURES / "hwpxlib_corpus" / "error__20230413__test.hwpx"
    truth = _faces_from_xml(path)
    doc = HwpxDocument.open(path)
    runs = [run for paragraph in doc.paragraphs for run in paragraph.runs if run.char_pr_id_ref in truth]
    assert runs
    for run in runs:
        assert run.fonts.to_dict() == truth[run.char_pr_id_ref]
    mixed = [run for run in runs if len(set(run.fonts.to_dict().values())) > 1]
    assert mixed and all(run.font == run.fonts.hangul for run in mixed)
