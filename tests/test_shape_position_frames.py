"""Reference frames on ``Shape.set_position`` and paragraph/alignment control
for ``Shape.set_draw_text``.

The byte-for-byte test pins the new API to the direct ``hp:pos`` edit a
typesetting engine uses today to anchor a floating stamp rectangle to the
paper, so moving to the API cannot change its output.
"""

from __future__ import annotations

import io

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

#: OWPML enumerations (DevDoc/OWPML SCHEMA/ParaList XML schema.xml,
#: AbstractShapeObjectType/pos and ParaListType/@vertAlign).
VERT_REL_TO = ("PAPER", "PAGE", "PARA")
HORZ_REL_TO = ("PAPER", "PAGE", "COLUMN", "PARA")
VERT_ALIGN = ("TOP", "CENTER", "BOTTOM", "INSIDE", "OUTSIDE")
HORZ_ALIGN = ("LEFT", "CENTER", "RIGHT", "INSIDE", "OUTSIDE")
SUBLIST_VERT_ALIGN = ("TOP", "CENTER", "BOTTOM")


def _stamp_document() -> tuple[bytes, str]:
    """A document with a floating, text-bearing stamp rectangle, as bytes."""

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    rect = paragraph.add_rectangle(
        8503,
        5446,
        line_color="#000000",
        line_width="283",
        fill_color="#FFFFFF",
        treat_as_char=False,
        char_pr_id_ref=0,
    )
    rect.set_attribute("textWrap", "IN_FRONT_OF_TEXT")
    rect.set_draw_text("확인", char_pr_id_ref=0)
    inst_id = rect.inst_id
    assert inst_id is not None
    data = doc.to_bytes()
    doc.close()
    return data, inst_id


def _find_shape(doc: HwpxDocument, inst_id: str):
    for paragraph in doc.paragraphs:
        for shape in paragraph.shapes:
            if shape.inst_id == inst_id:
                return shape
    raise AssertionError(f"shape {inst_id} not found")


def _floating_shape(doc: HwpxDocument):
    rect = doc.add_paragraph("").add_rectangle(8503, 5446, treat_as_char=False)
    return rect


# --------------------------------------------------------------------------
# set_position reference frames


def test_paper_frame_matches_the_direct_pos_edit_byte_for_byte() -> None:
    base, inst_id = _stamp_document()

    workaround = HwpxDocument.open(io.BytesIO(base))
    shape = _find_shape(workaround, inst_id)
    shape.set_position(horizontal_offset=46774, vertical_offset=5961)
    pos = shape.element.find(f"{HP}pos")
    pos.set("vertRelTo", "PAPER")
    pos.set("horzRelTo", "PAPER")
    expected = workaround.to_bytes()
    workaround.close()

    api = HwpxDocument.open(io.BytesIO(base))
    _find_shape(api, inst_id).set_position(
        horizontal_offset=46774,
        vertical_offset=5961,
        horz_rel_to="PAPER",
        vert_rel_to="PAPER",
    )
    actual = api.to_bytes()
    api.close()

    assert expected != base
    assert actual == expected


def test_frames_and_alignment_survive_save_and_reopen() -> None:
    doc = HwpxDocument.new()
    shape = _floating_shape(doc)
    inst_id = shape.inst_id
    shape.set_position(
        horizontal_offset=1000,
        vertical_offset=-2000,
        horz_rel_to="PAGE",
        vert_rel_to="PAPER",
        horz_align="RIGHT",
        vert_align="BOTTOM",
    )
    data = doc.to_bytes()
    doc.close()

    with HwpxDocument.open(io.BytesIO(data)) as reopened:
        pos = _find_shape(reopened, inst_id).element.find(f"{HP}pos")
        assert {
            key: pos.get(key)
            for key in ("horzRelTo", "vertRelTo", "horzAlign", "vertAlign", "horzOffset", "vertOffset")
        } == {
            "horzRelTo": "PAGE",
            "vertRelTo": "PAPER",
            "horzAlign": "RIGHT",
            "vertAlign": "BOTTOM",
            "horzOffset": "1000",
            "vertOffset": "-2000",
        }


@pytest.mark.parametrize(
    "argument,attribute,value",
    [("vert_rel_to", "vertRelTo", v) for v in VERT_REL_TO]
    + [("horz_rel_to", "horzRelTo", v) for v in HORZ_REL_TO]
    + [("vert_align", "vertAlign", v) for v in VERT_ALIGN]
    + [("horz_align", "horzAlign", v) for v in HORZ_ALIGN],
)
def test_every_schema_value_is_written_to_its_pos_attribute(
    argument: str, attribute: str, value: str
) -> None:
    with HwpxDocument.new() as doc:
        shape = _floating_shape(doc)
        pos = shape.element.find(f"{HP}pos")
        others = {k: v for k, v in pos.attrib.items() if k not in {attribute, "horzOffset", "vertOffset"}}
        shape.set_position(horizontal_offset=0, vertical_offset=0, **{argument: value})
        assert pos.get(attribute) == value
        assert {k: v for k, v in pos.attrib.items() if k in others} == others


def test_omitted_frames_leave_the_existing_frames_untouched() -> None:
    with HwpxDocument.new() as doc:
        shape = _floating_shape(doc)
        shape.set_position(horizontal_offset=0, vertical_offset=0, horz_rel_to="PAPER")
        shape.set_position(horizontal_offset=5, vertical_offset=6)
        pos = shape.element.find(f"{HP}pos")
        assert (pos.get("horzRelTo"), pos.get("vertRelTo")) == ("PAPER", "PARA")
        assert (pos.get("horzAlign"), pos.get("vertAlign")) == ("LEFT", "TOP")


@pytest.mark.parametrize(
    "argument,bad",
    [
        ("vert_rel_to", "COLUMN"),  # the schema allows COLUMN only horizontally
        ("horz_rel_to", "paper"),  # exact match, no case folding
        ("horz_rel_to", ""),
        ("vert_rel_to", 1),
        ("horz_align", "TOP"),
        ("vert_align", "LEFT"),
        ("vert_align", " CENTER"),
    ],
)
def test_bad_frame_refuses_before_any_mutation(argument: str, bad: object) -> None:
    with HwpxDocument.new() as doc:
        shape = _floating_shape(doc)
        before = etree.tostring(shape.element)
        with pytest.raises(HwpxValueError) as excinfo:
            shape.set_position(horizontal_offset=77, vertical_offset=88, **{argument: bad})
        error = excinfo.value
        assert error.code == "shape-position-frame"
        assert error.context["argument"] == argument
        assert error.context["allowed"]
        assert argument in str(error)
        assert etree.tostring(shape.element) == before


def test_inline_shape_still_refuses_frames() -> None:
    with HwpxDocument.new() as doc:
        shape = doc.add_paragraph("").add_rectangle(1000, 1000, treat_as_char=True)
        before = etree.tostring(shape.element)
        with pytest.raises(HwpxValueError) as excinfo:
            shape.set_position(horizontal_offset=0, vertical_offset=0, horz_rel_to="PAPER")
        assert excinfo.value.code == "shape-position-unsupported"
        assert etree.tostring(shape.element) == before


# --------------------------------------------------------------------------
# set_draw_text paragraph property and vertical alignment


def _render(element) -> str:
    """Namespace-free rendering, with the random paragraph id masked."""

    tag = etree.QName(element).localname
    attrs = dict(element.attrib)
    if tag == "p" and "id" in attrs:
        attrs["id"] = "*"
    rendered = tag + "".join(f" {k}={v!r}" for k, v in attrs.items())
    if element.text:
        rendered += f" text={element.text!r}"
    children = "".join(_render(child) for child in element)
    return f"<{rendered}>{children}</{tag}>"


#: ``set_draw_text("확인", char_pr_id_ref=3)`` on an 8503-wide rectangle,
#: captured from the implementation before para_pr_id_ref/vert_align existed.
DEFAULT_DRAW_TEXT = (
    "<drawText name='' editable='0' lastWidth='8503'>"
    "<subList id='' textDirection='HORIZONTAL' lineWrap='BREAK' vertAlign='CENTER'"
    " linkListIDRef='0' linkListNextIDRef='0' textWidth='0' textHeight='0'"
    " hasTextRef='0' hasNumRef='0'>"
    "<p id='*' paraPrIDRef='0' styleIDRef='0' pageBreak='0' columnBreak='0' merged='0'>"
    "<run charPrIDRef='3'><t text='확인'></t></run></p></subList>"
    "<textMargin left='283' right='283' top='283' bottom='283'></textMargin>"
    "</drawText>"
)


def test_default_draw_text_output_is_unchanged_on_create_and_replace() -> None:
    with HwpxDocument.new() as doc:
        shape = _floating_shape(doc)
        shape.set_draw_text("확인", char_pr_id_ref=3)
        assert _render(shape.element.find(f"{HP}drawText")) == DEFAULT_DRAW_TEXT
        shape.set_draw_text("다른 글", char_pr_id_ref=1)
        shape.set_draw_text("확인", char_pr_id_ref=3)
        assert _render(shape.element.find(f"{HP}drawText")) == DEFAULT_DRAW_TEXT


def _sublist_and_paragraph(shape):
    sublist = shape.element.find(f"{HP}drawText/{HP}subList")
    return sublist, sublist.findall(f"{HP}p")


@pytest.mark.parametrize("replace", [False, True])
def test_para_pr_id_ref_and_vert_align_reach_the_draw_text(replace: bool) -> None:
    with HwpxDocument.new() as doc:
        shape = _floating_shape(doc)
        if replace:
            shape.set_draw_text("이전", char_pr_id_ref=1)
        draw_text = shape.set_draw_text(
            "7", char_pr_id_ref=2, para_pr_id_ref=21, vert_align="BOTTOM"
        )
        sublist, paragraphs = _sublist_and_paragraph(shape)
        assert sublist.get("vertAlign") == "BOTTOM"
        assert [p.get("paraPrIDRef") for p in paragraphs] == ["21"]
        assert draw_text.text == "7"
        assert paragraphs[0].find(f"{HP}run").get("charPrIDRef") == "2"


def test_replace_without_vert_align_keeps_the_existing_alignment() -> None:
    with HwpxDocument.new() as doc:
        shape = _floating_shape(doc)
        shape.set_draw_text("위", vert_align="TOP")
        shape.set_draw_text("다시")
        sublist, paragraphs = _sublist_and_paragraph(shape)
        assert sublist.get("vertAlign") == "TOP"
        assert [p.get("paraPrIDRef") for p in paragraphs] == ["0"]


@pytest.mark.parametrize("value", SUBLIST_VERT_ALIGN)
def test_every_sublist_vert_align_value_is_accepted(value: str) -> None:
    with HwpxDocument.new() as doc:
        shape = _floating_shape(doc)
        shape.set_draw_text("x", vert_align=value)
        assert _sublist_and_paragraph(shape)[0].get("vertAlign") == value


@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize("bad", ["MIDDLE", "center", "INSIDE", 0])
def test_bad_draw_text_vert_align_refuses_before_mutation(replace: bool, bad: object) -> None:
    with HwpxDocument.new() as doc:
        shape = _floating_shape(doc)
        if replace:
            shape.set_draw_text("그대로")
        before = etree.tostring(shape.element)
        with pytest.raises(HwpxValueError) as excinfo:
            shape.set_draw_text("새 글", vert_align=bad)
        assert excinfo.value.code == "shape-draw-text-vert-align"
        assert excinfo.value.context["allowed"] == list(SUBLIST_VERT_ALIGN)
        assert etree.tostring(shape.element) == before


def test_draw_text_options_survive_save_and_reopen() -> None:
    doc = HwpxDocument.new()
    shape = _floating_shape(doc)
    inst_id = shape.inst_id
    shape.set_draw_text("3", para_pr_id_ref=5, vert_align="TOP")
    data = doc.to_bytes()
    doc.close()

    with HwpxDocument.open(io.BytesIO(data)) as reopened:
        reopened_shape = _find_shape(reopened, inst_id)
        sublist, paragraphs = _sublist_and_paragraph(reopened_shape)
        assert sublist.get("vertAlign") == "TOP"
        assert [p.get("paraPrIDRef") for p in paragraphs] == ["5"]
        assert reopened_shape.draw_text.text == "3"


# --------------------------------------------------------------------------
# stable surface


def test_draw_text_is_a_contract_named_stable_type() -> None:
    import json
    from pathlib import Path

    import hwpx.model as model
    from hwpx.oxml.objects import DrawText

    assert model.DrawText is DrawText
    lock = json.loads(
        (Path(__file__).parent / "data" / "model_surface.json").read_text(encoding="utf-8")
    )["classes"]
    assert {"draw_text", "remove_draw_text", "set_draw_text"} <= set(lock["Shape"]["stable"])
    assert lock["DrawText"]["stable"] == sorted(
        ["add_paragraph", "editable", "name", "paragraphs", "text", "text_margin"]
    )
