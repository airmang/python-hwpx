"""Style writes refused whole, fonts declared as the face already is, 자간 -50..100 on every path (exec7/rv2-styles).

1. A refused style call leaves the document byte-identical: every argument is checked before a font, a
   definition list or a container is written (one bad argument among good ones, for each style API).
2. A face declared in some ``hh:fontface`` blocks is copied -- ``type``, embedding, substitute font kept --
   into a block that lacks it, also one the header does not have, on every path that names a face for a run
   (``ensure_run(font=, font_by_lang=)``, ``run.set_format``, ``run.set_font``, ``set_style_format``,
   ``set_char_property``). All 1,265 Hancom-saved fixtures have the seven blocks; a file without one is
   still read and written as it is.
3. 자간 is -50..100 on every path (``ensure_run(letter_spacing=, letter_spacing_by_lang=)``,
   ``run.set_format``, ``set_char_property``, ``set_style_format``): Hancom 2024 keeps 51..100 when it saves the
   file again. The fixtures write -20..20 only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")


def _document() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("가나 ab")
    document.styles.ensure_font("Q", lang="LATIN")  # a face declared in one language only
    return HwpxDocument.open(document.to_bytes())


def _run(document: HwpxDocument) -> Any:
    return document.paragraphs[-1].runs[-1]


# -- 1. refused whole ----------------------------------------------------------------------------------------

REFUSED: list[tuple[str, Callable[[HwpxDocument], object]]] = []
for _face in ("Q", "NEWFACE"):  # declared in one language / nowhere
    for _name, _bad in (("color", "bad-color"), ("highlight", "bad"), ("underline_color", "bad"), ("shadow", "bad"),
                        ("size", -1), ("outline", "WAVY"), ("letter_spacing_by_lang", {"HANGUL": 101}),
                        ("font_by_lang", {"KLINGON": "X"})):
        REFUSED.append((f"ensure_run font={_face} {_name}",
                        lambda d, f=_face, n=_name, b=_bad: d.styles.ensure_run(font=f, bold=True, **{n: b})))
    REFUSED.append((f"ensure_run font_by_lang={_face} color",
                    lambda d, f=_face: d.styles.ensure_run(font_by_lang={"HANGUL": f}, color="bad")))
    for _name, _bad in (("color", "bad"), ("size", -5), ("letter_spacing", 101), ("ratio", 999)):
        REFUSED.append((f"run.set_format font={_face} {_name}",
                        lambda d, f=_face, n=_name, b=_bad: _run(d).set_format(font=f, **{n: b})))
        REFUSED.append((f"set_char_property font={_face} {_name}",
                        lambda d, f=_face, n=_name, b=_bad: d.styles.set_char_property(0, font=f, **{n: b})))
        REFUSED.append((f"set_style_format font={_face} {_name}",
                        lambda d, f=_face, n=_name, b=_bad: d.styles.set_style_format(0, font=f, **{n: b})))
    REFUSED.append((f"set_style_format font={_face} alignment",
                    lambda d, f=_face: d.styles.set_style_format(0, font=f, alignment="SIDEWAYS")))
REFUSED += [
    ("ensure_run font=123", lambda d: d.styles.ensure_run(font=123)),  # type: ignore[arg-type]
    ("ensure_border_fill border_color", lambda d: d.styles.ensure_border_fill(border_color="bad", fill_color="#FF0000")),
    ("ensure_border_fill side width", lambda d: d.styles.ensure_border_fill(
        sides={"top": {"width_mm": 0.4}, "bottom": {"width_mm": 0.33}})),
    ("ensure_border_fill base + fill", lambda d: d.styles.ensure_border_fill(
        base_border_fill_id_ref=1, sides={"top": {"width_mm": 0.4}}, fill_color="bad")),
    ("ensure_paragraph_format condense", lambda d: d.styles.ensure_paragraph_format(alignment="CENTER", condense=999)),
    ("apply_paragraph_format tab", lambda d: d.styles.apply_paragraph_format(
        paragraph=0, alignment="CENTER", tab_stops=[{"pos_mm": 10}, {"pos_mm": 20, "type": "BAD"}])),
    ("ensure_font subst", lambda d: d.styles.ensure_font("NEWFACE", subst_type="BAD")),
    ("replace_font langs", lambda d: d.styles.replace_font("Q", "NEWFACE", langs=["LATIN", "KLINGON"])),
    ("ensure_memo_shape line_color", lambda d: d.styles.ensure_memo_shape(width=20000, line_color="bad")),
    ("ensure_memo_shape fill_color", lambda d: d.styles.ensure_memo_shape(width=20000, fill_color="bad")),
    ("ensure_tab_definition", lambda d: d.styles.ensure_tab_definition(
        tab_stops=[{"pos_mm": 10}, {"pos_mm": 20, "type": "BAD"}])),
    ("add_numbering", lambda d: d.styles.add_numbering([{"text": "^1)"}, {"text": "(^2)", "number_format": "BAD"}])),
]


@pytest.mark.parametrize("call", [call for _, call in REFUSED], ids=[label for label, _ in REFUSED])
def test_a_refused_style_call_leaves_the_document_byte_identical(call: Callable[[HwpxDocument], object]) -> None:
    document = _document()
    before = document.to_bytes()
    with pytest.raises((ValueError, TypeError)):
        call(document)
    assert document.to_bytes() == before


# -- 2. a face is declared as it already is -------------------------------------------------------------------


def _without_user_block(drop: bool) -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("가나 ab")
    document.styles.ensure_font("Q", lang=["LATIN", "HANGUL"], font_type="HFT", subst_face="R", subst_type="TTF")
    header = document.oxml.headers[0]
    if drop:
        block = next(node for node in header.element.iter(f"{HH}fontface") if node.get("lang") == "USER")
        holder = block.getparent()
        holder.remove(block)
        holder.set("itemCnt", str(len(holder)))
        header.mark_dirty()
    return HwpxDocument.open(document.to_bytes())


def _forms(document: HwpxDocument) -> dict[str, list[tuple[str | None, int]]]:
    found: dict[str, list[tuple[str | None, int]]] = {}
    for block in document.oxml.headers[0].element.iter(f"{HH}fontface"):
        found[block.get("lang")] = [(font.get("type"), len(font.findall(f"{HH}substFont")))
                                    for font in block.findall(f"{HH}font") if font.get("face") == "Q"]
    return found


NAMING = {
    "ensure_run(font=)": lambda d: d.styles.ensure_run(font="Q"),
    "ensure_run(font_by_lang=)": lambda d: d.styles.ensure_run(font_by_lang={"USER": "Q"}),
    "run.set_format(font=)": lambda d: _run(d).set_format(font="Q"),
    "run.set_font(lang=)": lambda d: _run(d).set_font("Q", lang="USER"),
    "set_style_format(font=)": lambda d: d.styles.set_style_format(0, font="Q"),
    "set_char_property(font=)": lambda d: d.styles.set_char_property(0, font="Q"),
}


@pytest.mark.parametrize("drop", [True, False], ids=["block missing", "block without the face"])
@pytest.mark.parametrize("name", list(NAMING))
def test_a_face_reaches_a_language_as_it_is_declared_elsewhere(name: str, drop: bool) -> None:
    document = _without_user_block(drop)
    assert ("USER" in _forms(document)) is not drop
    NAMING[name](document)
    reopened = HwpxDocument.open(document.to_bytes())
    forms = _forms(reopened)
    assert forms["USER"] == [("HFT", 1)]
    assert [block.get("lang") for block in reopened.oxml.headers[0].element.iter(f"{HH}fontface")] == list(LANGS)
    holder = next(reopened.oxml.headers[0].element.iter(f"{HH}fontfaces"))
    assert holder.get("itemCnt") == "7"
    user = next(block for block in holder if block.get("lang") == "USER")
    assert user.get("fontCnt") == str(len(user.findall(f"{HH}font")))


def test_ensure_run_font_points_every_language_at_the_face_when_a_block_was_missing() -> None:
    document = _without_user_block(True)
    made = document.styles.ensure_run(font="Q")
    reopened = HwpxDocument.open(document.to_bytes())
    assert {lang: reopened.styles.font_face(made, lang) for lang in LANGS} == dict.fromkeys(LANGS, "Q")


# -- 3. 자간 -50..100 -----------------------------------------------------------------------------------------


def _spacing(document: HwpxDocument, char_pr_id: object) -> set[str]:
    element = document.oxml.headers[0].element.find(f".//{HH}charPr[@id='{char_pr_id}']")
    assert element is not None
    node = element.find(f"{HH}spacing")
    assert node is not None
    return set(node.attrib.values())


@pytest.mark.parametrize("value", [-50, 51, 75, 100])
def test_letter_spacing_takes_minus_50_to_100_on_every_path(value: int) -> None:
    document = _document()
    assert _spacing(document, document.styles.ensure_run(letter_spacing=value)) == {str(value)}
    by_lang = document.styles.ensure_run(letter_spacing_by_lang=dict.fromkeys(LANGS, value))
    assert _spacing(document, by_lang) == {str(value)}
    run = _run(document)
    run.set_format(letter_spacing=value)
    assert run.letter_spacing == value
    document.styles.set_char_property(0, letter_spacing=value)
    assert _spacing(document, 0) == {str(value)}
    document.styles.set_style_format(0, letter_spacing=value)


@pytest.mark.parametrize("value", [-51, 101])
def test_letter_spacing_out_of_minus_50_to_100_is_refused_on_every_path(value: int) -> None:
    document = _document()
    before = document.to_bytes()
    with pytest.raises(ValueError):
        document.styles.ensure_run(letter_spacing=value)
    with pytest.raises(HwpxValueError) as by_lang:
        document.styles.ensure_run(letter_spacing_by_lang={"HANGUL": value})
    assert by_lang.value.code == "style-run-letter-spacing-by-lang-invalid"
    for call in (lambda: _run(document).set_format(letter_spacing=value),
                 lambda: document.styles.set_char_property(0, letter_spacing=value),
                 lambda: document.styles.set_style_format(0, letter_spacing=value)):
        with pytest.raises(HwpxValueError) as refused:
            call()
        assert refused.value.code == "style-run-format-invalid"
    assert document.to_bytes() == before
