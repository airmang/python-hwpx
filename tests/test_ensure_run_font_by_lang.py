# SPDX-License-Identifier: Apache-2.0
"""`doc.styles.ensure_run(font_by_lang=...)`: a run style whose languages use different faces (#564).

Every ``hh:fontface`` block numbers its own fonts, so the same id can name a different face in
each language. The style is the base ``hh:charPr`` copied with each named language's face
declared in that language's block and referenced by that block's id; the base and every other
shared style stay as they were, and an equal finished style is reused.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")


def _header(doc: HwpxDocument) -> etree._Element:
    return doc.oxml.headers[0].element


def _char_pr(doc: HwpxDocument, char_pr_id: str) -> etree._Element:
    element = _header(doc).find(f".//{HH}charPr[@id='{char_pr_id}']")
    assert element is not None
    return element


def _char_pr_count(doc: HwpxDocument) -> int:
    return len(_header(doc).findall(f".//{HH}charPr"))


def _faces(doc: HwpxDocument, char_pr_id: str) -> dict[str, str | None]:
    return {lang: doc.styles.font_face(char_pr_id, lang) for lang in LANGS}


def _without(element: etree._Element, *, font_ref_attrs: tuple[str, ...]) -> etree._Element:
    """*element* without its id and the named ``fontRef`` attributes, to compare the rest."""

    copy = deepcopy(element)
    copy.attrib.pop("id", None)
    font_ref = copy.find(f"{HH}fontRef")
    assert font_ref is not None
    for name in font_ref_attrs:
        font_ref.attrib.pop(name, None)
    return copy


@pytest.mark.parametrize("lang", LANGS)
def test_each_language_gets_its_own_face_and_the_others_keep_the_base(lang: str) -> None:
    doc = HwpxDocument.new()
    base = _faces(doc, "0")

    style = doc.styles.ensure_run(font_by_lang={lang: "Arial"})

    assert _faces(doc, style) == {**base, lang: "Arial"}
    assert "Arial" in {font.face for font in doc.styles.fonts(lang).values()}
    for other in LANGS:
        if other != lang:  # declared only in the language it was given for
            assert "Arial" not in {font.face for font in doc.styles.fonts(other).values()}


def test_lang_names_are_case_insensitive() -> None:
    doc = HwpxDocument.new()

    upper = doc.styles.ensure_run(font_by_lang={"LATIN": "Arial"})

    assert doc.styles.ensure_run(font_by_lang={"latin": "Arial"}) == upper
    assert doc.styles.ensure_run(font_by_lang={" Latin ": " Arial "}) == upper


def test_the_base_style_values_are_kept() -> None:
    doc = HwpxDocument.new()
    base = doc.styles.ensure_run(bold=True, italic=True, color="#C00000", size=14, letter_spacing=-5)

    style = doc.styles.ensure_run(base_char_pr_id=base, font_by_lang={"HANGUL": "궁서", "LATIN": "Arial"})

    assert style != base
    assert etree.tostring(_without(_char_pr(doc, style), font_ref_attrs=("hangul", "latin"))) == etree.tostring(
        _without(_char_pr(doc, base), font_ref_attrs=("hangul", "latin"))
    )
    run_style = doc.styles.char_property(style)
    assert run_style is not None
    assert run_style.attributes["height"] == "1400"
    assert run_style.attributes["textColor"] == "#C00000"


def test_different_mappings_are_different_styles_and_the_same_mapping_is_reused() -> None:
    doc = HwpxDocument.new()
    count = _char_pr_count(doc)

    latin_arial = doc.styles.ensure_run(font_by_lang={"LATIN": "Arial"})
    latin_times = doc.styles.ensure_run(font_by_lang={"LATIN": "Times New Roman"})
    hangul_arial = doc.styles.ensure_run(font_by_lang={"HANGUL": "Arial"})
    both = doc.styles.ensure_run(font_by_lang={"HANGUL": "Arial", "LATIN": "Arial"})

    assert len({latin_arial, latin_times, hangul_arial, both}) == 4
    assert _char_pr_count(doc) == count + 4
    assert doc.styles.ensure_run(font_by_lang={"LATIN": "Arial"}) == latin_arial
    assert doc.styles.ensure_run(font_by_lang={"LATIN": "Arial", "HANGUL": "Arial"}) == both
    assert _char_pr_count(doc) == count + 4


def test_a_mapping_the_base_already_has_reuses_the_base() -> None:
    doc = HwpxDocument.new()
    count = _char_pr_count(doc)
    base_faces = _faces(doc, "0")

    assert doc.styles.ensure_run(font_by_lang={"HANGUL": base_faces["HANGUL"]}) == "0"
    assert _char_pr_count(doc) == count


def test_a_shared_style_is_not_changed_in_place() -> None:
    doc = HwpxDocument.new()
    base = doc.styles.ensure_run(bold=True)
    first = doc.add_paragraph("").add_run("첫 문단 run", char_pr_id_ref=base)
    second = doc.add_paragraph("").add_run("둘째 문단 run", char_pr_id_ref=base)
    before = etree.tostring(_char_pr(doc, base))

    style = doc.styles.ensure_run(base_char_pr_id=base, font_by_lang={"LATIN": "Arial"})

    assert style != base
    assert etree.tostring(_char_pr(doc, base)) == before
    assert first.char_pr_id_ref == base and second.char_pr_id_ref == base
    assert doc.styles.font_face(base, "LATIN") != "Arial"


def test_ids_are_resolved_in_each_languages_own_block() -> None:
    """Id 2 names 궁서 in HANGUL and Arial in LATIN: a face goes by its own block's id."""

    doc = HwpxDocument.new()
    assert doc.styles.ensure_font("궁서", lang="HANGUL") == "2"
    assert doc.styles.ensure_font("Arial", lang="LATIN") == "2"

    hangul_arial = doc.styles.ensure_run(font_by_lang={"HANGUL": "Arial"})
    latin_arial = doc.styles.ensure_run(font_by_lang={"LATIN": "Arial"})
    mixed = doc.styles.ensure_run(font_by_lang={"HANGUL": "궁서", "LATIN": "Arial"})

    hangul_ref = _char_pr(doc, hangul_arial).find(f"{HH}fontRef")
    assert hangul_ref is not None and hangul_ref.get("hangul") == "3"  # added to HANGUL, not LATIN's 2
    assert doc.styles.font_face(hangul_arial, "HANGUL") == "Arial"
    assert doc.styles.font_face(hangul_arial, "LATIN") == doc.styles.font_face("0", "LATIN")
    latin_ref = _char_pr(doc, latin_arial).find(f"{HH}fontRef")
    assert latin_ref is not None and latin_ref.get("latin") == "2"
    assert len(doc.styles.fonts("LATIN")) == 3  # Arial was already there
    assert (doc.styles.font_face(mixed, "HANGUL"), doc.styles.font_face(mixed, "LATIN")) == ("궁서", "Arial")


def test_font_by_lang_wins_over_font_for_the_languages_it_names() -> None:
    doc = HwpxDocument.new()

    style = doc.styles.ensure_run(font="궁서체", font_by_lang={"LATIN": "Arial"})

    faces = _faces(doc, style)
    assert faces["LATIN"] == "Arial"
    assert {faces[lang] for lang in LANGS if lang != "LATIN"} == {"궁서체"}
    assert doc.styles.ensure_run(font_by_lang={"LATIN": "Arial"}, font="궁서체") == style


@pytest.mark.parametrize(
    ("font_by_lang", "code"),
    [
        ({"KOREAN": "Arial"}, "style-font-lang-invalid"),
        ({"": "Arial"}, "style-font-lang-invalid"),
        ({"HANGUL": "새 글꼴", "ENGLISH": "Arial"}, "style-font-lang-invalid"),
        ({("LATIN", "HANJA"): "Arial"}, "style-run-font-by-lang-invalid"),
        ({1: "Arial"}, "style-run-font-by-lang-invalid"),
        ({"LATIN": "Arial", "latin": "Arial"}, "style-run-font-by-lang-invalid"),
        ({"HANGUL": "새 글꼴", "LATIN": None}, "style-run-font-by-lang-invalid"),
        ([("LATIN", "Arial")], "style-run-font-by-lang-invalid"),
        ("LATIN=Arial", "style-run-font-by-lang-invalid"),
        ({"HANGUL": "새 글꼴", "LATIN": ""}, "style-font-face-empty"),
        ({"LATIN": "   "}, "style-font-face-empty"),
    ],
)
def test_bad_mappings_are_rejected_before_anything_is_declared(font_by_lang: object, code: str) -> None:
    doc = HwpxDocument.new()
    before = etree.tostring(_header(doc))

    with pytest.raises(HwpxValueError) as caught:
        doc.styles.ensure_run(font="새 글꼴 둘", font_by_lang=font_by_lang)  # type: ignore[arg-type]

    assert caught.value.code == code
    assert etree.tostring(_header(doc)) == before


def test_an_empty_mapping_is_no_font_change() -> None:
    doc = HwpxDocument.new()

    assert doc.styles.ensure_run(bold=True, font_by_lang={}) == doc.styles.ensure_run(bold=True)


def _cache_paragraph(doc: HwpxDocument, text: str) -> etree._Element:
    paragraph = doc.add_paragraph(text).element
    cache = etree.SubElement(paragraph, f"{HP}linesegarray")
    etree.SubElement(cache, f"{HP}lineseg", {
        "textpos": "0", "vertpos": "0", "vertsize": "1000", "textheight": "1000",
        "baseline": "850", "spacing": "600", "horzpos": "0", "horzsize": "42520", "flags": "393216",
    })
    return paragraph


def test_making_the_style_keeps_line_caches_and_applying_it_drops_them() -> None:
    doc = HwpxDocument.new()
    applied = _cache_paragraph(doc, "적용할 문단 Text")
    untouched = _cache_paragraph(doc, "그대로인 문단 Text")

    style = doc.styles.ensure_run(font_by_lang={"LATIN": "Arial"})

    assert applied.find(f"{HP}linesegarray") is not None  # a new style changes no paragraph yet
    paragraph = next(p for p in doc.paragraphs if p.element is applied)
    paragraph.runs[0].char_pr_id_ref = style
    assert applied.find(f"{HP}linesegarray") is None  # its glyphs change: Hancom lays it out again
    assert untouched.find(f"{HP}linesegarray") is not None


def test_saved_and_reopened_the_references_hold(tmp_path: Path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    doc.styles.ensure_font("궁서", lang="HANGUL")
    doc.styles.ensure_font("Arial", lang="LATIN")
    style = doc.styles.ensure_run(size=11, font_by_lang={"HANGUL": "Arial", "LATIN": "Times New Roman"})
    doc.add_paragraph("").add_run("한글 English 漢字", char_pr_id_ref=style)
    faces = _faces(doc, style)
    path = tmp_path / "font-by-lang.hwpx"
    doc.save_to_path(path)

    reopened = HwpxDocument.open(path)
    run = reopened.paragraphs[-1].runs[-1]
    assert run.text == "한글 English 漢字"
    assert run.char_pr_id_ref == style
    assert _faces(reopened, style) == faces == {
        **_faces(reopened, "0"), "HANGUL": "Arial", "LATIN": "Times New Roman",
    }
    for lang in LANGS:  # every fontRef of every style names a declared font of its own block
        ids = set(reopened.styles.fonts(lang))
        for char_pr in _header(reopened).iter(f"{HH}charPr"):
            font_ref = char_pr.find(f"{HH}fontRef")
            assert font_ref is not None and font_ref.get(lang.lower()) in ids
    assert validate_editor_open_safety(path).to_dict()["ok"] is True
