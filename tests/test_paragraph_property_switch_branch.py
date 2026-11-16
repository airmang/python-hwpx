"""A paragraph shape's margins and line spacing read from the ``hp:switch/hp:case`` branch, the one
Hancom (2016 and later) reads; ``version_switch`` keeps both branches as written.

Hancom writes the margins of the ``hp:default`` branch at twice the ``hp:case`` value (the HWPUNIT
before 2016 counted half units) and the line spacing the same in both. Writing goes through
``doc.styles.ensure_paragraph_format`` / ``paragraph.indent_left_mm`` and keeps that shape.
"""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument

SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


def _switched_ids(doc: HwpxDocument) -> list[str]:
    return [pp.get("id") for pp in doc.oxml.headers[0].element.iter(f"{HH}paraPr")
            if pp.find(f"{HP}switch/{HP}case/{HH}margin") is not None]


def test_hancom_saved_shapes_read_the_case_branch() -> None:
    doc = HwpxDocument.open(SAVED / "memos_in_fields.hwpx")
    ids = _switched_ids(doc)
    assert ids
    for pid in ids:
        element = doc.oxml.headers[0].element.find(f".//{HH}paraPr[@id='{pid}']")
        case = element.find(f"{HP}switch/{HP}case/{HH}margin")
        line = element.find(f"{HP}switch/{HP}case/{HH}lineSpacing")
        prop = doc.styles.paragraph_property(pid)
        for side in ("intent", "left", "right", "prev", "next"):
            assert getattr(prop.margin, side) == case.find(f"{HC}{side}").get("value")
            assert getattr(prop.version_switch.case.margin, side) == case.find(f"{HC}{side}").get("value")
        assert prop.line_spacing.value == int(line.get("value"))
        default = prop.version_switch.default.margin
        assert all(int(getattr(default, side)) == 2 * int(getattr(prop.margin, side))
                   for side in ("intent", "left", "right", "prev", "next"))


def test_a_derived_shape_keeps_the_hancom_branches() -> None:
    doc = HwpxDocument.open(SAVED / "memos_in_fields.hwpx")
    base = _switched_ids(doc)[0]
    pid = doc.styles.ensure_paragraph_format(base_para_pr_id_ref=base, margins={"left": 1000, "intent": -600},
                                             break_setting={"break_non_latin_word": "KEEP_WORD"}, condense=20)
    prop = doc.styles.paragraph_property(pid)
    assert (prop.margin.left, prop.margin.intent) == ("1000", "-600")
    assert (prop.version_switch.default.margin.left, prop.version_switch.default.margin.intent) == ("2000", "-1200")
    assert prop.break_setting.break_non_latin_word == "KEEP_WORD" and prop.condense == 20


def test_a_paragraph_reads_its_indent_from_the_case_branch() -> None:
    doc = HwpxDocument.open(SAVED / "memos_in_fields.hwpx")
    paragraph = doc.add_paragraph("합성 문단")
    paragraph.indent_left_mm = 10.0
    prop = doc.styles.paragraph_property(paragraph.para_pr_id_ref)
    assert int(prop.margin.left) == round(10.0 * 7200 / 25.4)
    assert int(prop.version_switch.default.margin.left) == 2 * int(prop.margin.left)
    assert round(paragraph.indent_left_mm, 1) == 10.0
