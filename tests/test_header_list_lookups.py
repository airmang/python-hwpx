"""Font faces, character shapes and border fills are looked up in their ``hh:refList`` lists.

``font_face()`` and ``border_fill_info()`` walked the whole header for each lookup, every paragraph shape and
style included; FormFit and the page estimate call ``font_face()`` for each character shape they meet, so a
large header made them slow. They now read the children of the header's ``hh:fontfaces``,
``hh:charProperties`` and ``hh:borderFills`` lists, and the whole header only when it has no such list.

``error__20230728__test.hwpx`` is a Hancom document with some two hundred paragraph shapes.
"""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument
from hwpx.oxml import header_fonts

FIXTURE = Path(__file__).parent / "fixtures" / "hwpxlib_corpus" / "error__20230728__test.hwpx"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")


def _whole_header_face(header, char_pr_id: str, lang: str) -> str | None:
    """font_face() as it read the header before: every hh:charPr and hh:fontface of the whole tree."""

    char_pr = next((c for c in header.element.iter(f"{HH}charPr") if c.get("id") == char_pr_id), None)
    font_ref = char_pr.find(f"{HH}fontRef") if char_pr is not None else None
    font_id = font_ref.get(header_fonts._FONT_FACE_LANG_TO_REF[lang]) if font_ref is not None else None
    block = next((f for f in header.element.iter(f"{HH}fontface") if f.get("lang") == lang), None)
    if font_id is None or block is None:
        return None
    return next((f.get("face") for f in block.findall(f"{HH}font") if f.get("id") == font_id), None)


def test_the_lists_hold_every_entry_the_whole_header_holds() -> None:
    header = HwpxDocument.open(FIXTURE)._root.headers[0]

    for container, tag in (
        (header._fontfaces_element(), "fontface"),
        (header._char_properties_element(), "charPr"),
        (header._border_fills_element(), "borderFill"),
    ):
        assert container is not None
        assert header_fonts._listed(header, container, tag) == list(header.element.iter(f"{HH}{tag}"))


def test_each_face_is_the_one_the_whole_header_names() -> None:
    document = HwpxDocument.open(FIXTURE)
    header = document._root.headers[0]
    ids = [c.get("id") for c in header.element.iter(f"{HH}charPr")]

    assert len(ids) > 20
    for char_pr_id in ids:
        for lang in LANGS:
            assert document.styles.font_face(char_pr_id, lang=lang) == _whole_header_face(header, char_pr_id, lang)


def test_a_header_without_its_lists_is_read_whole() -> None:
    document = HwpxDocument.new()
    header = document._root.headers[0]
    expected = {lang: document.styles.font_face(0, lang=lang) for lang in LANGS}
    ref_list = header.element.find(f"{HH}refList")
    for name in ("fontfaces", "charProperties"):
        container = ref_list.find(f"{HH}{name}")
        ref_list.remove(container)
        for child in list(container):
            ref_list.append(child)

    assert header._fontfaces_element() is None and header._char_properties_element() is None
    assert {lang: document.styles.font_face(0, lang=lang) for lang in LANGS} == expected
    assert expected["HANGUL"]
