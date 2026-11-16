"""Objects in a paragraph: remove, placement and geometry, pictures, equations, descriptions, groups.

New and Hancom-saved documents alike: each edit keeps the document valid after a save and reopen,
leaves the other parts byte for byte, and drops the line layout cache of the paragraph it changed and
of the paragraphs holding it.
"""

from __future__ import annotations

import math
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.equation.measure import measure_equation
from hwpx.errors import HwpxValueError
from hwpx.model import Equation, InlineObject, Paragraph, Picture, Shape, Table
from hwpx.objects import ObjectPosition
from hwpx.oxml import PictureGlow, PictureShadow
from hwpx.oxml.namespaces import HC, HP

FIXTURES = Path(__file__).parent / "fixtures"
HANCOM = FIXTURES / "hancom_saved"

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000010806000000f478d4fa0000000d49444154789c63f8cfc0f01f0005000201"
    "a5f6b3a50000000049454e44ae426082"
)


def _reopen(doc: HwpxDocument) -> HwpxDocument:
    again = HwpxDocument.open(doc.to_bytes())
    assert not again.validate().issues
    return again


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _has_cache(paragraph_element) -> bool:
    return paragraph_element.find(f"{HP}linesegarray") is not None


# -- remove ---------------------------------------------------------------------------------------


def test_remove_takes_each_kind_of_object_out_and_keeps_the_paragraph() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("앞 ")
    equation = paragraph.add_equation("{a} over {b}")
    rectangle = paragraph.add_rectangle(4000, 2000)
    picture = doc.add_picture(PNG, "png", width=4000)
    group_paragraph = doc.add_paragraph("")
    assert {type(o) for o in paragraph.objects} == {Equation, Shape}

    equation.remove()
    rectangle.remove()
    picture.remove()
    assert paragraph.objects == ()
    assert paragraph.text == "앞 "
    assert picture.paragraph.element in list(doc.sections[0].element)  # the picture's paragraph stays
    assert doc.media.pictures == ()
    equation.remove()  # a second call does nothing
    assert group_paragraph.objects == ()

    again = _reopen(doc)
    assert again.shapes.equations == ()
    assert [p.text for p in again.sections[0].paragraphs][-3:] == ["앞 ", "", ""]


def test_remove_drops_an_empty_run_but_not_the_last_one() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("글")
    equation = paragraph.add_equation("x")
    runs = len(paragraph.element.findall(f"{HP}run"))
    equation.remove()
    assert len(paragraph.element.findall(f"{HP}run")) == runs - 1

    lone = doc.add_paragraph("", include_run=False)
    only = lone.add_equation("y")
    only.remove()
    assert len(lone.element.findall(f"{HP}run")) == 1


def test_remove_keeps_the_image_when_asked_until_unused_images_are_removed() -> None:
    doc = HwpxDocument.new()
    picture = doc.add_picture(PNG, "png")
    item = picture.item_id
    picture.remove(remove_orphaned=False)
    assert [str(i) for i in doc.media.images] == [item]
    assert [str(i) for i in doc.media.remove_unused_images()] == [item]
    _reopen(doc)


def test_remove_in_a_hancom_table_cell_drops_the_cell_and_table_paragraph_caches() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_wrapped_pictures_in_cached_cells.hwpx")
    before = _parts(doc.to_bytes())
    picture = doc.media.pictures[0]
    cell_paragraph = picture.paragraph.element
    holder = next(p for p in doc.sections[0].paragraphs if any(isinstance(o, Table) for o in p.objects))
    assert _has_cache(cell_paragraph) and _has_cache(holder.element)
    count = len(doc.media.pictures)

    picture.remove()
    assert len(doc.media.pictures) == count - 1
    assert not _has_cache(cell_paragraph)
    assert not _has_cache(holder.element)

    after = _parts(_reopen(doc).to_bytes())
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed <= {"Contents/section0.xml"}


def test_remove_lets_go_of_attached_connectors() -> None:
    doc = HwpxDocument.open(HANCOM / "shape_curves_and_connectors.hwpx")
    paragraph = next(p for p in doc.sections[0].paragraphs if any(o.element.tag == f"{HP}connectLine"
                                                                   for o in p.objects))
    shapes = [o for o in paragraph.objects if isinstance(o, Shape)]
    target = shapes[0]
    target_id = target.element.get("instid")
    connectors = [s for s in shapes if s.shape_type == "connectLine"]
    ends = [end for c in connectors for end in c.element if end.get("subjectIDRef") == target_id]
    assert ends
    target.remove()
    assert all(end.get("subjectIDRef") == "0" for end in ends)
    _reopen(doc)


def test_a_group_member_is_refused_and_the_group_removes_whole() -> None:
    doc = HwpxDocument.open(HANCOM / "group_in_a_group.hwpx")
    group = doc.sections[0].paragraphs[0].objects[0]
    assert isinstance(group, Shape) and group.shape_type == "container"
    member = group.members[0]
    for call in (lambda: setattr(member, "rotation", 10), lambda: setattr(member, "description", "x")):
        with pytest.raises(HwpxValueError) as caught:
            call()
        assert caught.value.code == "shape-group-member-unsupported"
    group.remove()
    assert doc.sections[0].paragraphs[0].objects == ()
    _reopen(doc)


# -- equations -------------------------------------------------------------------------------------


def test_equation_reads_its_script_font_and_box() -> None:
    doc = HwpxDocument.new()
    equation = doc.shapes.add_equation("{a} over {b}", font_size=12.0, font="HYhwpEQ")
    assert isinstance(equation, Equation)
    assert equation.script == "{a} over {b}"
    assert equation.font == "HYhwpEQ"
    assert equation.font_size == 12.0
    measured = measure_equation("{a} over {b}", base_unit=1200)
    assert (equation.width, equation.height, equation.base_line) == (
        measured.width, measured.height, measured.base_line)


def test_set_script_measures_the_box_again_and_drops_the_line_cache() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_objects_among_text_equation.hwpx")
    equation = doc.shapes.equations[0]
    paragraph = equation.paragraph.element
    assert _has_cache(paragraph)
    equation.script = "sum from {k=1} to {n} k^2"
    measured = measure_equation("sum from {k=1} to {n} k^2", base_unit=round(equation.font_size * 100))
    assert equation.script == "sum from {k=1} to {n} k^2"
    assert (equation.width, equation.height, equation.base_line) == (
        measured.width, measured.height, measured.base_line)
    assert not _has_cache(paragraph)
    again = _reopen(doc)
    assert again.shapes.equations[0].script == "sum from {k=1} to {n} k^2"


@pytest.mark.parametrize(("script", "code"), [
    ("", "shape-equation-script-empty"),
    (r"\frac{1}{2}", "shape-equation-script-latex"),
    ("{a over b", "shape-equation-script-unbalanced"),
])
def test_set_script_refuses_before_any_change(script: str, code: str) -> None:
    doc = HwpxDocument.new()
    equation = doc.shapes.add_equation("x")
    with pytest.raises(HwpxValueError) as caught:
        equation.script = script
    assert caught.value.code == code
    assert equation.script == "x"


@pytest.mark.parametrize("name", [
    "equation_attached_font_commands.hwpx", "equation_font_command_case.hwpx",
    "equation_font_command_boundaries.hwpx", "pages_objects_among_text_equation.hwpx",
])
def test_every_equation_of_a_hancom_document_is_reached(name: str) -> None:
    doc = HwpxDocument.open(HANCOM / name)
    elements = [e for s in doc.sections for e in s.element.iter(f"{HP}equation")]
    found = doc.shapes.equations
    assert [e.element for e in found] == elements
    assert all(e.script == (x.find(f"{HP}script").text or "") for e, x in zip(found, elements))
    by_paragraph = [e for s in doc.sections for p in s.paragraphs for e in p.equations]
    assert len(by_paragraph) == len(elements)


def test_equations_in_cells_text_boxes_and_notes_are_reached() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    cell_equation = table.cell(0, 0).paragraphs[0].add_equation("x^2")
    box = doc.add_paragraph("").add_rectangle(8000, 4000)
    box_equation = box.set_draw_text("").paragraphs[0].add_equation("y^2")
    found = doc.shapes.equations
    assert [e.script for e in found] == ["x^2", "y^2"]
    assert table.cell(0, 0).paragraphs[0].equations[0].element is cell_equation.element
    assert box.draw_text is not None and box.draw_text.paragraphs[0].equations[0].element is box_equation.element
    cell_equation.script = "x^3"
    _reopen(doc)


# -- placement and geometry ---------------------------------------------------------------------------


def test_position_reads_a_hancom_floating_picture() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_floating_pictures_in_cells.hwpx")
    picture = doc.media.pictures[0]
    assert isinstance(picture, Picture)
    position = picture.position
    assert isinstance(position, ObjectPosition)
    assert position.treat_as_char is False
    assert position.text_wrap == "IN_FRONT_OF_TEXT"
    assert (position.horizontal_relative_to, position.vertical_relative_to) == ("PARA", "PARA")
    assert position.horizontal_offset == 300
    assert position.to_dict()["horizontalOffset"] == 300
    assert position.to_dict()["horizontalRelativeTo"] == "PARA"


def test_set_position_and_position_use_the_same_names_on_shapes_and_objects() -> None:
    doc = HwpxDocument.new()
    shape = doc.add_paragraph("").add_rectangle(4000, 2000)
    picture = doc.add_picture(PNG, "png")
    for obj in (shape, picture):
        obj.set_position(treat_as_char=False, text_wrap="BEHIND_TEXT", horizontal_offset=-500,
                         vertical_offset=1200, horizontal_relative_to="PAPER", vertical_relative_to="PAPER")
        position = obj.position
        assert position.treat_as_char is False
        assert position.text_wrap == "BEHIND_TEXT"
        assert (position.horizontal_offset, position.vertical_offset) == (-500, 1200)
        assert (position.horizontal_relative_to, position.vertical_relative_to) == ("PAPER", "PAPER")
        assert not _has_cache(obj.paragraph.element)
        obj.set_position(treat_as_char=True)
        assert obj.position.treat_as_char is True
    with pytest.raises(HwpxValueError) as caught:
        shape.set_position(horizontal_offset=10, vertical_offset=10)
    assert caught.value.code == "shape-position-unsupported"
    _reopen(doc)


def _turn_record(element) -> dict[str, float]:
    """What a turn writes: the box (hp:sz, its ABSOLUTE sides), the offset, the centre, the matrices."""

    record: dict[str, float] = {}
    size = element.find(f"{HP}sz")
    for side in ("width", "height") if size is not None else ():
        if size.get(f"{side}RelTo", "ABSOLUTE") == "ABSOLUTE":
            record[f"sz.{side}"] = float(size.get(side))
    info = element.find(f"{HP}rotationInfo")
    record.update({"angle": float(info.get("angle")), "centerX": float(info.get("centerX")),
                   "centerY": float(info.get("centerY"))})
    offset = element.find(f"{HP}offset")
    for axis in ("x", "y"):
        value = int(offset.get(axis))
        record[f"offset.{axis}"] = float(value - 2**32 if value >= 2**31 else value)
    for matrix in list(element.find(f"{HP}renderingInfo"))[:3]:
        name = str(matrix.tag).rsplit("}", 1)[-1]
        record.update({f"{name}.{key}": float(matrix.get(key)) for key in ("e1", "e2", "e3", "e4", "e5", "e6")})
    return record


#: Every turned object (rotationInfo angle != 0) of the fixtures: (document, how many turned objects
#: set_rotation writes back exactly as Hancom saved them, how many it refuses).
TURNED_FIXTURES = [
    (FIXTURES / "hwpxlib_corpus" / "reader_writer__SimplePolygon.hwpx", 1, 0),
    (FIXTURES / "hwpxlib_corpus" / "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx", 0, 8),
]


@pytest.mark.parametrize(("path", "reproduced", "refused"), TURNED_FIXTURES, ids=lambda v: getattr(v, "stem", v))
def test_set_rotation_writes_back_every_hancom_turn_it_accepts_and_refuses_the_rest(
    path: Path, reproduced: int, refused: int
) -> None:
    from hwpx.oxml.objects import wrap_object

    doc = HwpxDocument.open(path)
    counts = {"reproduced": 0, "refused": 0}
    for section in doc.sections:
        for info in list(section.element.iter(f"{HP}rotationInfo")):
            if info.get("angle") == "0":
                continue
            element = info.getparent()
            holder = element.getparent()
            while str(holder.tag).rsplit("}", 1)[-1] != "p":
                holder = holder.getparent()
            obj = wrap_object(element, Paragraph(holder, section))
            angle = obj.rotation
            hancom = _turn_record(element)
            try:
                obj.rotation = 0
            except HwpxValueError as caught:
                assert caught.code in {"shape-rotation-unsupported", "shape-group-member-unsupported"}
                assert _turn_record(element) == hancom  # refused before any change
                counts["refused"] += 1
                continue
            obj.rotation = angle
            written = _turn_record(element)
            for key, value in hancom.items():
                assert math.isclose(written[key], value, abs_tol=1.5), (key, written[key], value)
            counts["reproduced"] += 1
    assert counts == {"reproduced": reproduced, "refused": refused}


@pytest.mark.parametrize("angle", [30, 45, 90, 135, 270, 359])
@pytest.mark.parametrize("size", [(8000, 3000), (3000, 8000), (5000, 5000)])
def test_a_turned_shape_fills_its_box_exactly(angle: int, size: tuple[int, int]) -> None:
    doc = HwpxDocument.new()
    shape = doc.add_paragraph("").add_rectangle(*size)
    shape.set_position(treat_as_char=False, horizontal_offset=0, vertical_offset=0)
    shape.rotation = angle
    record = _turn_record(shape.element)
    width, height = size
    rot = [record[f"rotMatrix.e{i}"] for i in range(1, 7)]
    assert math.isclose(rot[0] ** 2 + rot[3] ** 2, 1, abs_tol=1e-5)  # a turn, no stretch:
    assert math.isclose(rot[0] * rot[1] + rot[3] * rot[4], 0, abs_tol=1e-5)  # the sides stay square
    corners = [(x * rot[0] + y * rot[1] + rot[2] + record["transMatrix.e3"],
                x * rot[3] + y * rot[4] + rot[5] + record["transMatrix.e6"])
               for x, y in ((0, 0), (width, 0), (width, height), (0, height))]
    xs, ys = [x for x, _ in corners], [y for _, y in corners]
    assert math.isclose(min(xs), 0, abs_tol=1.5) and math.isclose(max(xs), record["sz.width"], abs_tol=1.5)
    assert math.isclose(min(ys), 0, abs_tol=1.5) and math.isclose(max(ys), record["sz.height"], abs_tol=1.5)
    assert abs(record["centerX"] - record["sz.width"] / 2) <= 1
    assert abs(record["centerY"] - record["sz.height"] / 2) <= 1
    shape.rotation = 0
    assert (shape.width, shape.height) == size
    _reopen(doc)


def test_a_shape_holding_text_turns_like_one_without() -> None:
    # Hancom 2024 turns a text box as an empty shape and lays its text level across the turned box
    # (tests/test_turn_text_shapes_and_groups.py compares with the files it saved).
    doc = HwpxDocument.new()
    box = doc.add_paragraph("").add_rectangle(8000, 3000)
    box.set_draw_text("글상자")
    empty = doc.add_paragraph("").add_rectangle(8000, 3000)
    box.rotation = 30
    empty.rotation = 30
    assert _turn_record(box.element) == _turn_record(empty.element)
    assert box.element.find(f"{HP}drawText").get("lastWidth") == box.element.find(f"{HP}sz").get("width")
    box.rotation = 0
    assert box.element.find(f"{HP}drawText").get("lastWidth") == "8000"


def test_resize_and_turn_in_either_order_give_the_same_shape() -> None:
    doc = HwpxDocument.new()
    first = doc.add_paragraph("").add_rectangle(8000, 3000)
    second = doc.add_paragraph("").add_rectangle(8000, 3000)
    first.resize(width=4000)
    first.rotation = 30
    second.rotation = 30
    second.resize(width=4000)
    assert _turn_record(first.element) == _turn_record(second.element)
    turned_first = doc.add_picture(PNG, "png", width=6000, height=3000)
    stretched_first = doc.add_picture(PNG, "png", width=6000, height=3000)
    turned_first.rotation = 30
    turned_first.resize(width=3000)  # a turned picture resizes as drawn and turns again
    stretched_first.resize(width=3000)
    stretched_first.rotation = 30  # a stretched picture turns as drawn
    assert _turn_record(turned_first.element) == _turn_record(stretched_first.element)
    assert turned_first.rotation == 30
    turned_first.rotation = 0
    assert (turned_first.width, turned_first.height) == (3000, 1500)


def test_z_order_and_rotation_read_and_write() -> None:
    doc = HwpxDocument.open(FIXTURES / "hwpxlib_corpus" / "reader_writer__SimplePolygon.hwpx")
    polygon = doc.sections[0].paragraphs[0].objects[0]
    assert isinstance(polygon, Shape)
    assert polygon.rotation == 40
    polygon.z_order = 7
    assert polygon.z_order == 7
    for call, code in ((lambda: setattr(polygon, "rotation", 36.5), "shape-rotation-value"),
                       (lambda: setattr(polygon, "z_order", True), "shape-z-order-value")):
        with pytest.raises(HwpxValueError) as caught:
            call()
        assert caught.value.code == code
    equation = doc.shapes.add_equation("x")
    with pytest.raises(HwpxValueError) as caught:
        equation.rotation = 90
    assert caught.value.code == "shape-rotation-unsupported"
    _reopen(doc)


def test_resize_keeps_the_aspect_ratio_when_one_side_is_given() -> None:
    doc = HwpxDocument.new()
    picture = doc.add_picture(PNG, "png", width=10000, height=5000)
    picture.resize(width=4000)
    assert (picture.width, picture.height) == (4000, 2000)
    scale = picture.element.find(f"{HP}renderingInfo/{HC}scaMatrix")
    assert (scale.get("e1"), scale.get("e5")) == ("0.4", "0.4")
    picture.resize(height=1000)
    assert (picture.width, picture.height) == (2000, 1000)
    shape = doc.add_paragraph("").add_rectangle(6000, 3000)
    shape.resize(width=3000)
    assert (shape.width, shape.height) == (3000, 1500)
    with pytest.raises(HwpxValueError) as caught:
        picture.resize()
    assert caught.value.code == "shape-size-value"
    _reopen(doc)


# -- pictures ---------------------------------------------------------------------------------------


def test_picture_crop_reads_a_hancom_crop_and_set_crop_keeps_the_scale() -> None:
    doc = HwpxDocument.open(FIXTURES / "exam" / "A_form.hwpx")
    picture = next(p for p in doc.media.pictures if p.crop != (0, 0, 0, 0))
    assert picture.crop == (0, 326, 0, 753)
    assert picture.original_size == (24180, 22260)
    width, height = picture.width, picture.height
    picture.crop = None
    assert picture.crop == (0, 0, 0, 0)
    assert picture.width == width
    assert picture.height == round(height * 22260 / (22260 - 326 - 753))
    _reopen(doc)


def test_set_crop_on_a_new_picture() -> None:
    doc = HwpxDocument.new()
    picture = doc.add_picture(PNG, "png", width=10000, height=5000)
    picture.crop = (1000, 500, 1000, 500)
    assert picture.crop == (1000, 500, 1000, 500)
    assert (picture.width, picture.height) == (8000, 4000)
    with pytest.raises(HwpxValueError) as caught:
        picture.crop = (6000, 0, 6000, 0)
    assert caught.value.code == "shape-picture-crop-value"
    _reopen(doc)


def test_picture_and_shape_read_what_their_creation_wrote() -> None:
    doc = HwpxDocument.new()
    shadow = PictureShadow(color="#336699", alpha=0.25, blur=300, direction=90, distance=400, inside=True)
    glow = PictureGlow(color="#FF0000", alpha=0.5, radius=200)
    picture = doc.add_picture(PNG, "png", brightness=10, contrast=-20, effect="GRAY_SCALE", alpha=30,
                              line_color="#112233", line_width_mm=0.18, shadow=shadow, glow=glow)
    assert (picture.brightness, picture.contrast, picture.effect, picture.alpha) == (10, -20, "GRAY_SCALE", 30)
    assert (picture.line_color, picture.line_width_mm) == ("#112233", 0.18)
    assert picture.element.find(f"{HP}lineShape").get("width") == "50"
    assert picture.shadow == shadow and picture.glow == glow
    plain = doc.add_picture(PNG, "png")
    assert (plain.line_color, plain.line_width_mm, plain.shadow, plain.glow) == (None, None, None, None)
    rectangle = doc.add_paragraph("").add_rectangle(3000, 2000, line_width_mm=0.25, fill_color="#00FF00")
    assert (rectangle.line_width_mm, rectangle.fill_color) == (0.25, "#00FF00")
    assert rectangle.element.find(f"{HP}lineShape").get("width") == "70"
    assert doc.add_paragraph("").add_ellipse(3000, 2000).fill_color is None


def test_media_pictures_read_each_picture_element_in_order() -> None:
    # 7.0: doc.media.pictures replaces picture_references(): the same pictures, in document order.
    doc = HwpxDocument.open(HANCOM / "pages_wrapped_pictures_in_cached_cells.hwpx")
    elements = [element for section in doc.sections for element in section.element.iter(f"{HP}pic")
                if element.find(f"{HC}img") is not None]
    pictures = doc.media.pictures
    assert len(pictures) == len(elements) > 0
    for element, picture in zip(elements, pictures):
        assert picture.item_id == element.find(f"{HC}img").get("binaryItemIDRef")
        size = element.find(f"{HP}sz")
        assert (picture.width, picture.height) == (int(size.get("width")), int(size.get("height")))


def test_picture_caption_is_read() -> None:
    doc = HwpxDocument.new()
    picture = doc.add_picture(PNG, "png")
    picture.set_caption("그림 1. 시험")
    assert picture.caption is not None and picture.caption.text == "그림 1. 시험"
    again = _reopen(doc)
    assert again.media.pictures[0].caption.text == "그림 1. 시험"


# -- descriptions, groups ---------------------------------------------------------------------------


def test_description_reads_hancom_and_writes_alternative_text() -> None:
    doc = HwpxDocument.open(FIXTURES / "hwpxlib_corpus" / "reader_writer__SimplePolygon.hwpx")
    polygon = doc.sections[0].paragraphs[0].objects[0]
    assert polygon.description == "다각형입니다."
    polygon.description = "오각 별"
    assert polygon.description == "오각 별"
    new = HwpxDocument.new()
    shape = new.add_paragraph("").add_ellipse(3000, 3000)
    assert shape.description == ""
    shape.description = "동그라미"
    names = [str(child.tag).rsplit("}", 1)[-1] for child in shape.element]
    assert names.index("shapeComment") > names.index("outMargin")
    assert _reopen(new).sections[0].paragraphs[-1].objects[0].description == "동그라미"


def test_group_members_are_model_objects() -> None:
    doc = HwpxDocument.open(HANCOM / "group_in_a_group.hwpx")
    group = doc.sections[0].paragraphs[0].objects[0]
    inner, line = group.members
    assert isinstance(inner, Shape) and inner.shape_type == "container"
    assert line.shape_type == "line"
    assert all(isinstance(m, (Shape, InlineObject)) for m in inner.members)
    assert line.members == ()
    assert group.position.treat_as_char is False


def test_paragraph_objects_hold_tables_too() -> None:
    doc = HwpxDocument.new()
    paragraph: Paragraph = doc.add_paragraph("")
    table = paragraph.add_table(1, 1)
    picture = paragraph.add_picture(str(doc.media.add_image(PNG, "png")))
    objects = paragraph.objects
    assert isinstance(objects[0], Table) and objects[0].element is table.element
    assert isinstance(objects[1], Picture) and objects[1].element is picture.element
    assert paragraph.pictures[0].element is picture.element
