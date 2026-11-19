"""asks11: three requests to ``doc.styles`` met with the form Hancom saves.

1. A border fill ``ensure_border_fill`` builds writes the ``hh:diagonal`` every Hancom-saved border fill has
   (all 3,511 in the 1,265 fixtures: ``SOLID 0.1 mm #000000``), not ``NONE`` at the side's width; one derived
   from another keeps the diagonal it read.
2. ``ensure_run(letter_spacing_by_lang=)`` takes a 자간 per language under ``font_by_lang``'s rules; a language
   it does not name keeps the base's value.
3. ``ensure_run(font=)`` gives the face to all seven languages, as the docstring says and as Hancom's own run
   shapes do (12,187 of the 12,188 ``hh:fontRef`` in the fixtures name one face in all seven languages); a
   language whose block lacks the face gets it declared, copied from the face's existing declaration.
4. add_form_field(start=k, end=k, prompt=...) writes the prompt run between begin and end, as without a range
   (the 12 empty Hancom-saved click-here fields with an 안내문 all hold one).
"""

from __future__ import annotations

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
HH = f"{{{HH_NS}}}"


def _header(doc: HwpxDocument):
    return doc.oxml.headers[0].element


def _border_fill(doc: HwpxDocument, fill_id: str):
    return next(node for node in _header(doc).iter(f"{HH}borderFill") if node.get("id") == fill_id)


def _diagonal(doc: HwpxDocument, fill_id: str) -> dict[str, str]:
    node = _border_fill(doc, fill_id).find(f"{HH}diagonal")
    assert node is not None
    return dict(node.attrib)


# -- 1. diagonal ------------------------------------------------------------------------------------------


def test_a_new_border_fill_writes_hancoms_diagonal_whatever_its_sides() -> None:
    doc = HwpxDocument.new()
    hancom = {"type": "SOLID", "width": "0.1 mm", "color": "#000000"}
    plain = doc.styles.ensure_border_fill()
    thick = doc.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.4, border_type="DASH")
    sided = doc.styles.ensure_border_fill(sides={"top": {"width_mm": 0.5}, "left": None}, fill_color="#DDEBF7")
    for fill_id in (plain, thick, sided):
        assert _diagonal(doc, fill_id) == hancom
    # slash/backSlash stay NONE: the diagonal line draws nothing.
    for name in ("slash", "backSlash"):
        node = _border_fill(doc, thick).find(f"{HH}{name}")
        assert node is not None and node.get("type") == "NONE"


def test_the_same_request_again_reuses_the_definition_it_built() -> None:
    doc = HwpxDocument.new()
    first = doc.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.4)
    count = len(list(_header(doc).iter(f"{HH}borderFill")))
    assert doc.styles.ensure_border_fill(border_color="#FF0000", border_width_mm=0.4) == first
    assert len(list(_header(doc).iter(f"{HH}borderFill"))) == count


def test_a_definition_with_a_drawn_slash_is_not_taken_for_a_plain_one() -> None:
    doc = HwpxDocument.new()
    plain = doc.styles.ensure_border_fill(border_color="#123456")
    slash = _border_fill(doc, plain).find(f"{HH}slash")
    assert slash is not None
    slash.set("type", "CENTER")
    again = doc.styles.ensure_border_fill(border_color="#123456")
    assert again != plain
    assert _diagonal(doc, again) == {"type": "SOLID", "width": "0.1 mm", "color": "#000000"}


def test_a_border_fill_derived_from_another_keeps_the_diagonal_it_read() -> None:
    doc = HwpxDocument.new()
    container = _header(doc).find(f".//{HH}borderFills")
    assert container is not None
    wrapped = (
        f'<root xmlns:hh="{HH_NS}" xmlns:hc="{HC_NS}">'
        '<hh:borderFill id="77" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:diagonal type="DASH" width="0.5 mm" color="#00FF00"/>'
        "</hh:borderFill></root>"
    )
    container.append(etree.fromstring(wrapped)[0])
    derived = doc.styles.ensure_border_fill(base_border_fill_id_ref="77", sides={"bottom": {"width_mm": 0.4}})
    assert derived != "77"
    assert _diagonal(doc, derived) == {"type": "DASH", "width": "0.5 mm", "color": "#00FF00"}


# -- 2. letter_spacing_by_lang ---------------------------------------------------------------------------

LANG_ATTRS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")


def _char_pr(doc: HwpxDocument, char_pr_id: str):
    element = _header(doc).find(f".//{HH}charPr[@id='{char_pr_id}']")
    assert element is not None
    return element


def _spacing(doc: HwpxDocument, char_pr_id: str) -> dict[str, str]:
    node = _char_pr(doc, char_pr_id).find(f"{HH}spacing")
    assert node is not None
    return {attr: node.get(attr) for attr in LANG_ATTRS}


def _base_with_spacing(doc: HwpxDocument, values: dict[str, int]) -> str:
    """A shape like the template's tight placeholder runs: -50 in some languages."""

    base = doc.styles.ensure_run(letter_spacing=0, color="#123456")
    node = _char_pr(doc, base).find(f"{HH}spacing")
    for attr, value in values.items():
        node.set(attr, str(value))
    return base


def test_letter_spacing_by_lang_changes_only_the_languages_it_names() -> None:
    doc = HwpxDocument.new()
    base = _base_with_spacing(doc, {"hangul": -50, "latin": -45, "hanja": -10})
    before = etree.tostring(_char_pr(doc, base))
    fixed = doc.styles.ensure_run(base_char_pr_id_ref=base, letter_spacing_by_lang={"hangul": 0, "LATIN": -5})
    assert fixed != base
    assert _spacing(doc, fixed) == {"hangul": "0", "latin": "-5", "hanja": "-10", "japanese": "0", "other": "0",
                                    "symbol": "0", "user": "0"}
    assert etree.tostring(_char_pr(doc, base)) == before  # the base stays as it was
    assert _char_pr(doc, fixed).get("textColor") == "#123456"  # the rest follows the base
    again = doc.styles.ensure_run(base_char_pr_id_ref=base, letter_spacing_by_lang={"LATIN": -5, "Hangul": 0})
    assert again == fixed  # the same request reuses it


def test_letter_spacing_by_lang_wins_over_letter_spacing() -> None:
    doc = HwpxDocument.new()
    both = doc.styles.ensure_run(letter_spacing=-10, letter_spacing_by_lang={"HANGUL": 5})
    assert _spacing(doc, both) == {attr: ("5" if attr == "hangul" else "-10") for attr in LANG_ATTRS}


def test_a_base_without_spacing_gets_all_seven_with_the_schema_default() -> None:
    doc = HwpxDocument.new()
    base = _char_pr(doc, "0")
    spacing = base.find(f"{HH}spacing")
    if spacing is not None:
        base.remove(spacing)
    made = doc.styles.ensure_run(base_char_pr_id_ref="0", letter_spacing_by_lang={"USER": 3})
    assert _spacing(doc, made) == {attr: ("3" if attr == "user" else "0") for attr in LANG_ATTRS}
    children = [etree.QName(child).localname for child in _char_pr(doc, made)]
    assert children.index("spacing") == children.index("fontRef") + 2  # schema order: fontRef, ratio, spacing


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ([("HANGUL", 0)], "style-run-letter-spacing-by-lang-invalid"),
        ({1: 0}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": 0, "hangul": 1}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": "0"}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": True}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": 1.5}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": -51}, "style-run-letter-spacing-by-lang-invalid"),
        ({"HANGUL": 101}, "style-run-letter-spacing-by-lang-invalid"),
        ({"KOREAN": 0}, "style-font-lang-invalid"),
    ],
)
def test_letter_spacing_by_lang_is_checked_before_anything_changes(value: object, code: str) -> None:
    doc = HwpxDocument.new()
    before = etree.tostring(_header(doc))
    with pytest.raises(HwpxValueError) as caught:
        doc.styles.ensure_run(font="새글꼴", letter_spacing_by_lang=value)  # type: ignore[arg-type]
    assert caught.value.code == code
    assert etree.tostring(_header(doc)) == before


# -- 3. font= reaches all seven languages -----------------------------------------------------------------

FACE_LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")


def _declarations(doc: HwpxDocument, face: str) -> dict[str, list[dict[str, str]]]:
    found: dict[str, list[dict[str, str]]] = {}
    for fontface in _header(doc).iter(f"{HH}fontface"):
        for font in fontface.findall(f"{HH}font"):
            if font.get("face") == face:
                found.setdefault(fontface.get("lang"), []).append(
                    {k: v for k, v in font.attrib.items() if k != "id"} | {"children": str(len(font))})
    return found


def test_font_reaches_every_language_even_one_whose_list_lacks_it() -> None:
    doc = HwpxDocument.new()
    doc.styles.ensure_font("바탕", lang="LATIN")  # latin: 함초롬바탕 0 and others, then 바탕
    doc.styles.ensure_font("맑은 고딕", lang=["LATIN", "HANJA"])
    made = doc.styles.ensure_run(font="맑은 고딕")
    assert {lang: doc.styles.font_face(made, lang) for lang in FACE_LANGS} == dict.fromkeys(FACE_LANGS, "맑은 고딕")
    declared = _declarations(doc, "맑은 고딕")
    assert set(declared) == set(FACE_LANGS)
    assert all(len(forms) == 1 for forms in declared.values())  # declared once per block, nothing doubled


def test_a_face_declared_in_some_languages_is_copied_into_the_others() -> None:
    doc = HwpxDocument.new()
    doc.styles.ensure_font("한양신명조", lang="LATIN", font_type="HFT", subst_face="함초롬바탕", subst_type="TTF")
    made = doc.styles.ensure_run(font="한양신명조", bold=True)
    assert doc.styles.font_face(made, "HANGUL") == "한양신명조"
    forms = _declarations(doc, "한양신명조")
    assert set(forms) == set(FACE_LANGS)
    assert len({str(sorted(form.items())) for lang_forms in forms.values() for form in lang_forms}) == 1
    for lang in FACE_LANGS:  # each block's count follows its fonts
        block = next(ff for ff in _header(doc).iter(f"{HH}fontface") if ff.get("lang") == lang)
        assert block.get("fontCnt") == str(len(block.findall(f"{HH}font")))
    assert doc.styles.ensure_run(font="한양신명조", bold=True) == made  # the same request again
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.styles.font_face(made, "USER") == "한양신명조"


# -- 4. an empty-range click-here field writes its prompt run -----------------------------------------------

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _shape(paragraph) -> list[tuple[str | None, list[str]]]:
    """Runs as (charPrIDRef, [t:<text> | fieldBegin | fieldEnd ...])."""

    out = []
    for run in paragraph.element.findall(f"{HP}run"):
        parts = []
        for child in run:
            name = etree.QName(child).localname
            if name == "t":
                parts.append("t:" + "".join(child.itertext()))
            elif name == "ctrl":
                parts.extend(etree.QName(c).localname for c in child)
        if not set(parts) <= {"secPr", "colPr"}:  # the section settings run of a document's first paragraph
            out.append((run.get("charPrIDRef"), parts))
    return out


def test_an_empty_range_field_writes_its_prompt_run_between_begin_and_end() -> None:
    doc = HwpxDocument.new()
    prompt_style = doc.styles.ensure_run(italic=True, color="#FF0000")
    paragraph = doc.add_paragraph("abc")
    field = paragraph.add_form_field("G", start=1, end=1, prompt="pp", prompt_char_pr_id_ref=prompt_style)
    assert field.element.get("dirty") == "0"
    assert _shape(paragraph) == [
        ("0", ["t:a", "fieldBegin"]),
        (prompt_style, ["t:pp"]),
        ("0", ["fieldEnd", "t:bc"]),
    ]
    assert paragraph.text == "appbc"
    # the same run an appended field writes
    appended = doc.add_paragraph("abc")
    appended.add_form_field("H", prompt="pp", prompt_char_pr_id_ref=prompt_style)
    assert (prompt_style, ["t:pp"]) in _shape(appended)
    reopened = {f.name: f for f in HwpxDocument.open(doc.to_bytes()).fields.all}
    assert reopened["G"].filled is False and reopened["G"].prompt == "pp"


def test_an_empty_range_at_either_end_and_one_without_a_prompt() -> None:
    doc = HwpxDocument.new()
    first = doc.add_paragraph("abc")
    first.add_form_field("A", start=0, end=0, prompt="p")
    assert [parts for _, parts in _shape(first)] == [["fieldBegin"], ["t:p"], ["fieldEnd", "t:abc"]]
    last = doc.add_paragraph("abc")
    last.add_form_field("B", start=3, end=3, prompt="p")
    assert [parts for _, parts in _shape(last)][-2:] == [["t:p"], ["fieldEnd"]]
    assert last.text == "abcp"
    bare = doc.add_paragraph("abc")
    bare.add_form_field("C", start=1, end=1)  # no prompt: begin and end stay side by side
    assert [parts for _, parts in _shape(bare)] == [["t:a", "fieldBegin", "fieldEnd", "t:bc"]]
