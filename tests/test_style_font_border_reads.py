# SPDX-License-Identifier: Apache-2.0
"""`doc.styles` font and border-fill reads, plus `replace_font`.

`fonts()`/`font_face()` read the `hh:fontface` tables, `border_fill_info()`
reads one `hh:borderFill` as typed values, and `replace_font()` swaps one
font face for another across the tables and every `hh:charPr/hh:fontRef`.
A typesetting engine that converts HWPX output to DOCX relies on the exact
values and on `replace_font` leaving header bytes identical to the plain
algorithm spelled out in its docstring — the reference implementation at
the bottom of this file is that algorithm, written against raw XML.
"""

from __future__ import annotations

import io
import re
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects import BorderFillInfo, BorderLine, FontReplaceReport
from hwpx.oxml import Font

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
HH = f"{{{HH_NS}}}"
HC = f"{{{HC_NS}}}"

LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")
ATTRS = {lang: lang.lower() for lang in LANGS}

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


# ---------------------------------------------------------------------------
# fixture helpers


def _header(doc: HwpxDocument) -> etree._Element:
    return doc.oxml.headers[0].element


def _set_fontfaces(doc: HwpxDocument, blocks: Mapping[str, Sequence[str]]) -> None:
    """Replace every fontface block's fonts with *blocks* (ids 0..N-1)."""

    for fontface in _header(doc).iter(f"{HH}fontface"):
        for font in fontface.findall(f"{HH}font"):
            fontface.remove(font)
        faces = blocks.get(fontface.get("lang", ""), ())
        for index, face in enumerate(faces):
            font = etree.SubElement(
                fontface,
                f"{HH}font",
                {"id": str(index), "face": face, "type": "TTF", "isEmbedded": "0"},
            )
            # a child element proves renumbering keeps the rest of the font intact
            etree.SubElement(font, f"{HH}typeInfo", {"familyType": "FCAT_GOTHIC"})
        fontface.set("fontCnt", str(len(faces)))


def _set_font_refs(doc: HwpxDocument, refs: Mapping[str, Mapping[str, str]]) -> None:
    for char_pr in _header(doc).iter(f"{HH}charPr"):
        wanted = refs.get(char_pr.get("id", ""))
        if wanted is None:
            continue
        font_ref = char_pr.find(f"{HH}fontRef")
        assert font_ref is not None
        for attr, value in wanted.items():
            font_ref.set(attr, value)


def _font_refs(doc: HwpxDocument) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for char_pr in _header(doc).iter(f"{HH}charPr"):
        font_ref = char_pr.find(f"{HH}fontRef")
        if font_ref is not None:
            result[char_pr.get("id", "")] = dict(font_ref.attrib)
    return result


def _fontface_xml(doc: HwpxDocument, lang: str) -> str:
    for fontface in _header(doc).iter(f"{HH}fontface"):
        if fontface.get("lang") == lang:
            text = etree.tostring(fontface, encoding="unicode")
            return re.sub(r' xmlns:\w+="[^"]*"', "", text)
    raise AssertionError(f"no {lang} fontface")


def _expected_fontface(lang: str, fonts: Sequence[tuple[str, bool]]) -> str:
    """*fonts* is (face, has_type_info) in order; ids are 0..N-1."""

    parts = [f'<hh:fontface lang="{lang}" fontCnt="{len(fonts)}">']
    for index, (face, has_type_info) in enumerate(fonts):
        head = f'<hh:font id="{index}" face="{face}" type="TTF" isEmbedded="0"'
        if has_type_info:
            parts.append(head + '><hh:typeInfo familyType="FCAT_GOTHIC"/></hh:font>')
        else:
            parts.append(head + "/>")
    parts.append("</hh:fontface>")
    return "".join(parts)


def _face_snapshot(doc: HwpxDocument) -> dict[tuple[str, str], str | None]:
    """(charPr id, lang attr) -> the face that reference names right now."""

    tables: dict[str, dict[str, str]] = {}
    for fontface in _header(doc).iter(f"{HH}fontface"):
        attr = ATTRS.get(fontface.get("lang", ""))
        if attr is not None:
            tables[attr] = {
                font.get("id", ""): font.get("face", "")
                for font in fontface.findall(f"{HH}font")
            }
    snapshot: dict[tuple[str, str], str | None] = {}
    for char_pr_id, refs in _font_refs(doc).items():
        for attr in ATTRS.values():
            snapshot[(char_pr_id, attr)] = tables.get(attr, {}).get(refs.get(attr, ""))
    return snapshot


DECOR = "장식체"
DST = "맑은 고딕"
DOTUM = "함초롬돋움"
BATANG = "함초롬바탕"
GULIM = "굴림"

#: the decorative face sits at a different position in every block
BLOCKS: dict[str, list[str]] = {
    "HANGUL": [DOTUM, DECOR, BATANG],
    "LATIN": [DECOR, DOTUM, BATANG],
    "HANJA": [DOTUM, BATANG, DECOR],
    "JAPANESE": [DOTUM, DECOR, BATANG, GULIM],
    "OTHER": [DECOR, BATANG],
    "SYMBOL": [BATANG, DOTUM, DECOR, GULIM],
    "USER": [GULIM, DECOR],
}

ZERO = {attr: "0" for attr in ATTRS.values()}
REFS: dict[str, dict[str, str]] = {
    # every language points at the decorative face
    "0": {"hangul": "1", "latin": "0", "hanja": "2", "japanese": "1",
          "other": "0", "symbol": "2", "user": "1"},
    # the font right after the decorative face (hanja: decor is last, use 0)
    "1": {"hangul": "2", "latin": "1", "hanja": "0", "japanese": "2",
          "other": "1", "symbol": "3", "user": "0"},
    # the font right before the decorative face
    "2": {"hangul": "0", "latin": "2", "hanja": "1", "japanese": "3",
          "other": "1", "symbol": "0", "user": "0"},
    "3": dict(ZERO),
    "4": dict(ZERO),
    "5": dict(ZERO),
    "6": dict(ZERO),
}


def _decor_doc(blocks: Mapping[str, Sequence[str]] = BLOCKS) -> HwpxDocument:
    doc = HwpxDocument.new()
    _set_fontfaces(doc, blocks)
    _set_font_refs(doc, REFS)
    doc.oxml.headers[0].reset_dirty()
    return doc


# ---------------------------------------------------------------------------
# fonts()


def test_fonts_returns_the_lang_block_keyed_by_raw_id() -> None:
    doc = _decor_doc()

    fonts = doc.styles.fonts("LATIN")

    assert list(fonts) == ["0", "1", "2"]
    assert all(isinstance(font, Font) for font in fonts.values())
    assert [font.face for font in fonts.values()] == [DECOR, DOTUM, BATANG]
    assert fonts["0"].id == 0 and fonts["0"].type == "TTF"
    assert fonts["0"].type_info is not None
    assert doc.styles.fonts() == doc.styles.fonts("HANGUL")
    assert [font.face for font in doc.styles.fonts("hangul").values()] == BLOCKS["HANGUL"]


def test_fonts_of_a_missing_block_is_empty() -> None:
    doc = HwpxDocument.new()
    for fontface in list(_header(doc).iter(f"{HH}fontface")):
        if fontface.get("lang") == "USER":
            fontface.getparent().remove(fontface)

    assert doc.styles.fonts("USER") == {}


def test_fonts_rejects_an_unknown_lang() -> None:
    doc = HwpxDocument.new()

    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.fonts("KOREAN")
    assert excinfo.value.code == "style-font-lang-invalid"


def test_fonts_follows_in_memory_edits() -> None:
    doc = HwpxDocument.new()
    before = len(doc.styles.fonts("SYMBOL"))

    font_id = doc.styles.ensure_font("나눔고딕", lang="SYMBOL")

    fonts = doc.styles.fonts("SYMBOL")
    assert len(fonts) == before + 1
    assert fonts[font_id].face == "나눔고딕"


# ---------------------------------------------------------------------------
# font_face()


def test_font_face_names_the_face_each_lang_points_at() -> None:
    doc = _decor_doc()

    assert doc.styles.font_face(0) == DECOR
    assert doc.styles.font_face("1") == BATANG
    assert doc.styles.font_face(1, lang="LATIN") == DOTUM
    assert doc.styles.font_face("2", lang="symbol") == BATANG
    assert doc.styles.font_face(2, lang="USER") == GULIM


def test_font_face_is_none_when_anything_is_missing() -> None:
    doc = _decor_doc()
    header = _header(doc)
    font_ref = header.find(f".//{HH}charPr[@id='3']/{HH}fontRef")
    assert font_ref is not None
    del font_ref.attrib["user"]
    font_ref.set("latin", "99")
    char_pr_4 = header.find(f".//{HH}charPr[@id='4']")
    assert char_pr_4 is not None
    char_pr_4.remove(char_pr_4.find(f"{HH}fontRef"))

    assert doc.styles.font_face(999) is None
    assert doc.styles.font_face(None) is None
    assert doc.styles.font_face(3, lang="USER") is None
    assert doc.styles.font_face(3, lang="LATIN") is None
    assert doc.styles.font_face(4) is None


def test_font_face_rejects_an_unknown_lang() -> None:
    doc = HwpxDocument.new()

    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.font_face(0, lang="nope")
    assert excinfo.value.code == "style-font-lang-invalid"


# ---------------------------------------------------------------------------
# border_fill_info()


def _add_border_fill(doc: HwpxDocument, xml: str) -> None:
    container = _header(doc).find(f".//{HH}borderFills")
    assert container is not None
    wrapped = f'<root xmlns:hh="{HH_NS}" xmlns:hc="{HC_NS}">{xml}</root>'
    container.append(etree.fromstring(wrapped)[0])


def test_border_fill_info_reads_sides_raw_and_fill() -> None:
    doc = HwpxDocument.new()
    _add_border_fill(
        doc,
        '<hh:borderFill id="7" threeD="0" shadow="0">'
        '<hh:slash type="NONE"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="#ff0000"/>'
        '<hh:rightBorder type="DASH" width="0.4 mm" color="#00FF00"/>'
        '<hh:topBorder type="DOUBLE_SLIM" width="1.0 mm"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        '<hc:fillBrush><hc:winBrush faceColor="#DDEBF7" hatchColor="#000000" alpha="0"/>'
        "</hc:fillBrush></hh:borderFill>",
    )

    info = doc.styles.border_fill_info(7)

    assert info == BorderFillInfo(
        id="7",
        left=BorderLine("SOLID", 0.12, "#ff0000"),
        right=BorderLine("DASH", 0.4, "#00FF00"),
        top=BorderLine("DOUBLE_SLIM", 1.0, "#000000"),
        bottom=BorderLine("NONE", 0.0, "#000000"),
        diagonal=BorderLine("SOLID", 0.1, "#000000"),
        fill="#DDEBF7",
    )
    assert doc.styles.border_fill_info("7") == info
    assert info.to_dict() == {
        "id": "7",
        "left": {"type": "SOLID", "widthMm": 0.12, "color": "#ff0000"},
        "right": {"type": "DASH", "widthMm": 0.4, "color": "#00FF00"},
        "top": {"type": "DOUBLE_SLIM", "widthMm": 1.0, "color": "#000000"},
        "bottom": {"type": "NONE", "widthMm": 0.0, "color": "#000000"},
        "diagonal": {"type": "SOLID", "widthMm": 0.1, "color": "#000000"},
        "fill": "#DDEBF7",
    }


def test_border_fill_info_defaults_and_fill_none() -> None:
    doc = HwpxDocument.new()
    _add_border_fill(
        doc,
        '<hh:borderFill id="8"><hh:leftBorder/>'
        '<hc:fillBrush><hc:winBrush faceColor="NONE"/></hc:fillBrush></hh:borderFill>',
    )
    _add_border_fill(doc, '<hh:borderFill id="9"/>')

    eight = doc.styles.border_fill_info(8)
    assert eight is not None
    assert eight.left == BorderLine("NONE", 0.0, "#000000")
    assert eight.fill is None
    nine = doc.styles.border_fill_info(9)
    assert nine is not None
    assert nine.fill is None
    assert nine.diagonal == BorderLine("NONE", 0.0, "#000000")


def test_border_fill_info_ignores_nested_side_elements() -> None:
    """Only direct children describe the cell's sides."""

    doc = HwpxDocument.new()
    _add_border_fill(
        doc,
        '<hh:borderFill id="10"><hh:slash><hh:leftBorder type="SOLID" width="3 mm"/>'
        "</hh:slash></hh:borderFill>",
    )

    info = doc.styles.border_fill_info(10)
    assert info is not None
    assert info.left == BorderLine("NONE", 0.0, "#000000")


def test_border_fill_info_gradient_fill_is_not_described() -> None:
    doc = HwpxDocument.new()
    _add_border_fill(
        doc,
        '<hh:borderFill id="11"><hc:fillBrush><hc:gradation type="LINEAR">'
        '<hc:color value="#FF0000"/><hc:color value="#0000FF"/></hc:gradation>'
        "</hc:fillBrush></hh:borderFill>",
    )

    info = doc.styles.border_fill_info(11)
    assert info is not None
    assert info.fill is None


def test_border_fill_info_rejects_an_unparseable_width() -> None:
    doc = HwpxDocument.new()
    _add_border_fill(
        doc, '<hh:borderFill id="12"><hh:topBorder type="SOLID" width="thick"/></hh:borderFill>'
    )

    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.border_fill_info(12)
    assert excinfo.value.code == "style-border-fill-width-invalid"
    assert excinfo.value.context["id"] == "12"
    assert excinfo.value.context["width"] == "thick"


def test_border_fill_info_unknown_id_is_none() -> None:
    doc = HwpxDocument.new()

    assert doc.styles.border_fill_info(999) is None
    assert doc.styles.border_fill_info(None) is None


def test_border_fill_info_follows_ensure_border_fill() -> None:
    doc = HwpxDocument.new()

    new_id = doc.styles.ensure_border_fill(
        border_color="#123456", border_width="0.5 mm", fill_color="#ABCDEF"
    )

    info = doc.styles.border_fill_info(new_id)
    assert info is not None
    assert info.id == new_id
    assert info.left == BorderLine("SOLID", 0.5, "#123456")
    assert info.fill == "#ABCDEF"
    # border_fill() keeps returning the raw element view
    assert type(doc.styles.border_fill(new_id)).__name__ == "GenericElement"


# ---------------------------------------------------------------------------
# replace_font()


def test_replace_font_all_blocks_exact_xml_and_refs() -> None:
    doc = _decor_doc()

    report = doc.styles.replace_font(DECOR, DST)

    assert report == FontReplaceReport(
        src_face=DECOR, dst_face=DST, langs=LANGS, repointed=15, declared=LANGS
    )
    assert report.to_dict() == {
        "srcFace": DECOR,
        "dstFace": DST,
        "langs": list(LANGS),
        "repointed": 15,
        "declared": list(LANGS),
    }
    t, n = True, False
    assert _fontface_xml(doc, "HANGUL") == _expected_fontface(
        "HANGUL", [(DOTUM, t), (BATANG, t), (DST, n)]
    )
    assert _fontface_xml(doc, "LATIN") == _expected_fontface(
        "LATIN", [(DOTUM, t), (BATANG, t), (DST, n)]
    )
    assert _fontface_xml(doc, "HANJA") == _expected_fontface(
        "HANJA", [(DOTUM, t), (BATANG, t), (DST, n)]
    )
    assert _fontface_xml(doc, "JAPANESE") == _expected_fontface(
        "JAPANESE", [(DOTUM, t), (BATANG, t), (GULIM, t), (DST, n)]
    )
    assert _fontface_xml(doc, "OTHER") == _expected_fontface(
        "OTHER", [(BATANG, t), (DST, n)]
    )
    assert _fontface_xml(doc, "SYMBOL") == _expected_fontface(
        "SYMBOL", [(BATANG, t), (DOTUM, t), (GULIM, t), (DST, n)]
    )
    assert _fontface_xml(doc, "USER") == _expected_fontface("USER", [(GULIM, t), (DST, n)])

    refs = _font_refs(doc)
    assert refs["0"] == {"hangul": "2", "latin": "2", "hanja": "2", "japanese": "3",
                         "other": "1", "symbol": "3", "user": "1"}
    assert refs["1"] == {"hangul": "1", "latin": "0", "hanja": "0", "japanese": "1",
                         "other": "0", "symbol": "2", "user": "0"}
    assert refs["2"] == {"hangul": "0", "latin": "1", "hanja": "1", "japanese": "2",
                         "other": "0", "symbol": "0", "user": "0"}
    for char_pr_id in ("3", "4", "5", "6"):
        assert refs[char_pr_id] == {"hangul": "0", "latin": "2", "hanja": "0",
                                    "japanese": "0", "other": "1", "symbol": "0",
                                    "user": "0"}
    assert doc.oxml.headers[0].dirty
    # the char-property cache sees the new references, not stale ones
    style = doc.styles.char_property(0)
    assert style is not None
    assert style.child_attributes["fontRef"]["latin"] == "2"
    assert doc.styles.font_face(0, lang="SYMBOL") == DST


def test_replace_font_reuses_dst_where_already_declared() -> None:
    doc = _decor_doc()

    report = doc.styles.replace_font(DECOR, GULIM)

    assert report.langs == LANGS
    assert report.declared == ("HANGUL", "LATIN", "HANJA", "OTHER")
    assert report.repointed == 15
    t = True
    assert _fontface_xml(doc, "JAPANESE") == _expected_fontface(
        "JAPANESE", [(DOTUM, t), (BATANG, t), (GULIM, t)]
    )
    assert _fontface_xml(doc, "USER") == _expected_fontface("USER", [(GULIM, t)])
    # the appended 굴림 copies the JAPANESE declaration, typeInfo included
    assert _fontface_xml(doc, "HANGUL") == _expected_fontface(
        "HANGUL", [(DOTUM, t), (BATANG, t), (GULIM, t)]
    )
    refs = _font_refs(doc)
    assert refs["0"]["japanese"] == "2"
    assert refs["0"]["user"] == "0"
    assert refs["0"]["symbol"] == "2"
    assert refs["1"]["symbol"] == "2"  # 굴림 moved from id 3 to id 2


def test_replace_font_skips_blocks_without_src() -> None:
    blocks = dict(BLOCKS)
    blocks["HANJA"] = [DOTUM, BATANG]
    blocks["USER"] = [GULIM]
    doc = _decor_doc(blocks)
    # keep the references valid for the two blocks without the decorative face
    _set_font_refs(doc, {"0": {"hanja": "1", "user": "0"}, "2": {"hanja": "1"}})
    untouched = {lang: _fontface_xml(doc, lang) for lang in ("HANJA", "USER")}
    hanja_refs = {cid: refs["hanja"] for cid, refs in _font_refs(doc).items()}

    report = doc.styles.replace_font(DECOR, DST)

    assert report.langs == ("HANGUL", "LATIN", "JAPANESE", "OTHER", "SYMBOL")
    assert report.declared == report.langs
    assert {lang: _fontface_xml(doc, lang) for lang in ("HANJA", "USER")} == untouched
    assert {cid: refs["hanja"] for cid, refs in _font_refs(doc).items()} == hanja_refs


def test_replace_font_langs_restriction() -> None:
    doc = _decor_doc()
    untouched = {lang: _fontface_xml(doc, lang) for lang in LANGS[2:]}
    before = _font_refs(doc)

    report = doc.styles.replace_font(DECOR, DST, langs=["latin", "HANGUL"])

    assert report.langs == ("HANGUL", "LATIN")  # document order, not argument order
    assert report.declared == ("HANGUL", "LATIN")
    assert report.repointed == 2 + 4  # charPr 0 twice, charPr 3..6 latin
    assert {lang: _fontface_xml(doc, lang) for lang in LANGS[2:]} == untouched
    after = _font_refs(doc)
    for char_pr_id, refs in before.items():
        for attr in ("hanja", "japanese", "other", "symbol", "user"):
            assert after[char_pr_id][attr] == refs[attr]


def test_replace_font_absent_everywhere_changes_nothing() -> None:
    doc = _decor_doc()
    before = etree.tostring(_header(doc))

    report = doc.styles.replace_font("없는 글꼴", DST)

    assert report == FontReplaceReport("없는 글꼴", DST, (), 0, ())
    assert etree.tostring(_header(doc)) == before
    assert not doc.oxml.headers[0].dirty


def test_replace_font_with_non_contiguous_ids() -> None:
    """The appended font's placeholder id may equal an existing id."""

    doc = _decor_doc({**BLOCKS, "HANGUL": [DECOR, DOTUM]})
    hangul = next(f for f in _header(doc).iter(f"{HH}fontface") if f.get("lang") == "HANGUL")
    hangul.findall(f"{HH}font")[1].set("id", "2")  # HANGUL: 0=장식체, 2=함초롬돋움
    # the new font's placeholder id is len(fonts) == "2", the same as 함초롬돋움's
    _set_font_refs(doc, {cid: {"hangul": "2"} for cid in ("1", "2", "3", "4", "5", "6")})
    _set_font_refs(doc, {"0": {"hangul": "0"}})

    report = doc.styles.replace_font(DECOR, DST, langs=["HANGUL"])

    assert report.repointed == 1
    assert _fontface_xml(doc, "HANGUL") == _expected_fontface(
        "HANGUL", [(DOTUM, True), (DST, False)]
    )
    refs = _font_refs(doc)
    assert refs["0"]["hangul"] == "1"  # was 장식체, now 맑은 고딕
    assert all(refs[cid]["hangul"] == "0" for cid in ("1", "2", "3", "4", "5", "6"))


def test_replace_font_leaves_a_dangling_reference_dangling() -> None:
    """A value that named no font must not start naming the new font."""

    doc = _decor_doc()
    _set_font_refs(doc, {"1": {"user": "2"}})  # USER has two fonts: 0, 1

    doc.styles.replace_font(DECOR, DST, langs=["USER"])

    assert _fontface_xml(doc, "USER") == _expected_fontface(
        "USER", [(GULIM, True), (DST, False)]
    )
    assert _font_refs(doc)["1"]["user"] == "2"
    assert doc.styles.font_face(1, lang="USER") is None


@pytest.mark.parametrize(
    "src,dst,langs,code",
    [
        ("", DST, None, "style-font-face-empty"),
        (DECOR, "   ", None, "style-font-face-empty"),
        (DECOR, DECOR, None, "style-font-replace-same-face"),
        (DECOR, DST, ["KOREAN"], "style-font-lang-invalid"),
    ],
)
def test_replace_font_validates_before_mutating(
    src: str, dst: str, langs: list[str] | None, code: str
) -> None:
    doc = _decor_doc()
    before = etree.tostring(_header(doc))

    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.replace_font(src, dst, langs=langs)

    assert excinfo.value.code == code
    assert etree.tostring(_header(doc)) == before
    assert not doc.oxml.headers[0].dirty


def test_replace_font_survives_save_and_reopen() -> None:
    doc = _decor_doc()
    font_map = {DECOR: DST}
    before = _face_snapshot(doc)

    doc.styles.replace_font(DECOR, DST)
    reopened = HwpxDocument.open(io.BytesIO(doc.to_bytes()))

    assert reopened.validate().ok
    for fontface in _header(reopened).iter(f"{HH}fontface"):
        fonts = fontface.findall(f"{HH}font")
        assert [font.get("id") for font in fonts] == [str(i) for i in range(len(fonts))]
        assert fontface.get("fontCnt") == str(len(fonts))
        assert all(font.get("face") != DECOR for font in fonts)
    for refs in _font_refs(reopened).values():
        for attr, value in refs.items():
            count = len(reopened.styles.fonts(attr.upper()))
            assert 0 <= int(value) < count
    after = _face_snapshot(reopened)
    assert after.keys() == before.keys()
    for key, old_face in before.items():
        expected = font_map.get(old_face, old_face) if old_face is not None else None
        assert after[key] == expected, key


# ---------------------------------------------------------------------------
# byte-for-byte against a plain reference implementation


def _reference_replace(
    header: etree._Element, src: str, dst: str, langs: Iterable[str] | None = None
) -> None:
    """Steps 1-4 of `replace_font`, written directly against raw XML."""

    wanted = set(langs) if langs is not None else set(LANGS)
    char_prs = list(header.iter(f"{HH}charPr"))
    template = next(
        (f for f in header.iter(f"{HH}font") if f.get("face") == dst), None
    )
    for fontface in header.iter(f"{HH}fontface"):
        lang = fontface.get("lang", "")
        if lang not in wanted:
            continue
        attr = ATTRS[lang]
        fonts = fontface.findall(f"{HH}font")
        src_font = next((f for f in fonts if f.get("face") == src), None)
        if src_font is None:
            continue
        src_id = src_font.get("id")
        dst_font = next((f for f in fonts if f.get("face") == dst), None)
        if dst_font is None and template is not None:
            dst_font = deepcopy(template)
            dst_font.tail = None
            dst_font.set("id", str(len(fonts)))
            fontface.append(dst_font)
            fonts.append(dst_font)
        elif dst_font is None:
            dst_font = fontface.makeelement(
                f"{HH}font",
                {"id": str(len(fonts)), "face": dst, "type": "TTF", "isEmbedded": "0"},
            )
            fontface.append(dst_font)
            fonts.append(dst_font)
        dst_id = dst_font.get("id")
        for char_pr in char_prs:
            font_ref = char_pr.find(f"{HH}fontRef")
            if font_ref is not None and font_ref.get(attr) == src_id:
                font_ref.set(attr, dst_id)
        fontface.remove(src_font)
        remaining = [f for f in fonts if f is not src_font]
        new_ids = {f.get("id"): str(index) for index, f in enumerate(remaining)}
        for font in remaining:
            font.set("id", new_ids[font.get("id")])
        fontface.set("fontCnt", str(len(remaining)))
        for char_pr in char_prs:
            font_ref = char_pr.find(f"{HH}fontRef")
            if font_ref is not None and font_ref.get(attr) in new_ids:
                font_ref.set(attr, new_ids[font_ref.get(attr)])


def _saved_header(doc: HwpxDocument) -> bytes:
    with zipfile.ZipFile(io.BytesIO(doc.to_bytes())) as archive:
        return archive.read("Contents/header.xml")


def _open_twice(source: Path | None) -> tuple[HwpxDocument, HwpxDocument]:
    if source is None:
        return _decor_doc(), _decor_doc()
    return HwpxDocument.open(source), HwpxDocument.open(source)


@pytest.mark.parametrize(
    "source,src,dst,langs",
    [
        (None, DECOR, DST, None),
        (None, DECOR, GULIM, ["HANGUL", "SYMBOL", "USER"]),
        # real corpus: dst already declared in every block
        (CORPUS / "error__20230818__test.hwpx", "HY헤드라인M", "맑은 고딕", None),
        # real corpus: src missing from some blocks, dst appended
        (CORPUS / "error__20241104__mot.hwpx", "#신명조", "나눔명조", None),
        (CORPUS / "error__20241104__mot.hwpx", "HY각헤드라인M", "굴림", None),
    ],
)
def test_replace_font_matches_reference_byte_for_byte(
    source: Path | None, src: str, dst: str, langs: list[str] | None
) -> None:
    api_doc, ref_doc = _open_twice(source)
    header_before = deepcopy(_header(ref_doc))

    api_doc.styles.replace_font(src, dst, langs=langs)
    _reference_replace(_header(ref_doc), src, dst, langs)
    ref_doc.oxml.headers[0].mark_dirty()

    assert etree.tostring(_header(api_doc)) == etree.tostring(_header(ref_doc))
    assert etree.tostring(_header(api_doc)) != etree.tostring(header_before)
    assert _saved_header(api_doc) == _saved_header(ref_doc)


def test_replace_font_replaces_every_copy_of_a_face_listed_twice() -> None:
    # Hancom-saved blocks often list one face twice: SimpleEdit's HANJA block
    # declares 함초롬바탕 at id 0 and id 2, and character shapes use both.
    document = HwpxDocument.open(CORPUS / "reader_writer__SimpleEdit.hwpx")
    header = document.oxml.headers[0].element
    ids = [char_pr.get("id") for char_pr in header.iter(f"{HH}charPr")]
    before = {char_pr: document.styles.font_face(char_pr, "HANJA") for char_pr in ids}
    assert [font.face for font in document.styles.fonts("HANJA").values()].count("함초롬바탕") == 2

    report = document.styles.replace_font("함초롬바탕", "맑은 고딕", langs=["HANJA"])

    faces = [font.face for font in document.styles.fonts("HANJA").values()]
    assert "함초롬바탕" not in faces
    assert report.langs == ("HANJA",)
    for char_pr, face in before.items():
        expected = "맑은 고딕" if face == "함초롬바탕" else face
        assert document.styles.font_face(char_pr, "HANJA") == expected

    reopened = HwpxDocument.open(document.to_bytes())
    assert "함초롬바탕" not in [font.face for font in reopened.styles.fonts("HANJA").values()]


# ---------------------------------------------------------------------------
# replace_font() declares dst the way the document already declares it


def _declared_fonts(doc: HwpxDocument, face: str) -> dict[str, dict[str, str]]:
    return {
        fontface.get("lang", ""): dict(font.attrib)
        for fontface in _header(doc).iter(f"{HH}fontface")
        for font in fontface.findall(f"{HH}font")
        if font.get("face") == face
    }


def test_replace_font_copies_dst_type_from_another_block() -> None:
    # 한양신명조 is declared HFT in six blocks; USER lacks it but has 함초롬돋움.
    doc = HwpxDocument.open(CORPUS / "error__20251107__test.hwpx")
    before = _declared_fonts(doc, "한양신명조")
    assert "USER" not in before and {a["type"] for a in before.values()} == {"HFT"}

    report = doc.styles.replace_font("함초롬돋움", "한양신명조")

    assert report.declared == ("USER",)
    user = next(
        fontface for fontface in _header(doc).iter(f"{HH}fontface")
        if fontface.get("lang") == "USER"
    )
    added = next(f for f in user.findall(f"{HH}font") if f.get("face") == "한양신명조")
    assert added.get("type") == "HFT" and added.get("isEmbedded") == "0"
    type_info = added.find(f"{HH}typeInfo")
    assert type_info is not None and type_info.get("familyType") == "FCAT_MYUNGJO"
    assert {a["type"] for a in _declared_fonts(doc, "한양신명조").values()} == {"HFT"}

    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.styles.fonts("USER")[added.get("id")].type == "HFT"


def test_replace_font_keeps_ttf_when_no_block_declares_dst() -> None:
    doc = _decor_doc()

    doc.styles.replace_font(DECOR, DST)

    assert {a["type"] for a in _declared_fonts(doc, DST).values()} == {"TTF"}


def test_replace_font_font_type_sets_the_type_of_appended_fonts() -> None:
    doc = _decor_doc()

    report = doc.styles.replace_font(DECOR, GULIM, font_type="hft")

    declared = _declared_fonts(doc, GULIM)
    assert {declared[lang]["type"] for lang in report.declared} == {"HFT"}
    # fonts that already declared 굴림 are left as they were
    assert {declared[lang]["type"] for lang in ("JAPANESE", "SYMBOL", "USER")} == {"TTF"}


def test_replace_font_rejects_an_unknown_font_type_before_mutating() -> None:
    doc = _decor_doc()
    header_before = etree.tostring(_header(doc))

    with pytest.raises(HwpxValueError) as caught:
        doc.styles.replace_font(DECOR, DST, font_type="OTF")

    assert caught.value.code == "style-font-type-invalid"
    assert etree.tostring(_header(doc)) == header_before
