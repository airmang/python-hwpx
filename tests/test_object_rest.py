"""Objects, the rest for 7.0: an object's outer margins, an equation's font and size written, a removed object's
images leaving the package, and the reads tables share with objects."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.equation.measure import measure_equation
from hwpx.errors import HwpxValueError
from hwpx.objects import CellMargins
from hwpx.oxml.namespaces import HP

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


def _has_cache(element) -> bool:
    return element.find(f"{HP}linesegarray") is not None


# -- outer margins ------------------------------------------------------------------------------------------


def test_out_margins_read_hancom_equations_and_write_on_every_object() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_objects_among_text_equation.hwpx")
    equation = doc.shapes.equations[0]
    margin = equation.element.find(f"{HP}outMargin")
    assert equation.out_margins == CellMargins(*(int(margin.get(s)) for s in ("left", "right", "top", "bottom")))
    paragraph = equation.paragraph.element
    assert _has_cache(paragraph)
    before = _parts(doc.to_bytes())
    assert equation.set_out_margins(left=500, bottom=100) == CellMargins(500, equation.out_margins.right, 0, 100)
    assert not _has_cache(paragraph)
    after = _parts(_reopen(doc).to_bytes())
    assert {name for name in before if before[name] != after.get(name)} <= {"Contents/section0.xml"}

    new = HwpxDocument.new()
    paragraph = new.add_paragraph("")
    for obj in (paragraph.add_equation("x"), paragraph.add_rectangle(2000, 1000), new.add_picture(PNG, "png")):
        obj.set_out_margins(left=10, right=20, top=30, bottom=40)
        assert obj.out_margins == CellMargins(10, 20, 30, 40)
        assert obj.set_out_margins() == CellMargins(10, 20, 30, 40)  # nothing given: nothing changes
    table = new.add_table(1, 1)
    assert type(table.out_margins) is type(paragraph.objects[0].out_margins)  # the same value type as tables
    _reopen(new)


@pytest.mark.parametrize("value", [-1, 2**31, 1.0, True, "5"])
def test_out_margins_refuse_other_values(value) -> None:
    doc = HwpxDocument.new()
    equation = doc.add_paragraph("").add_equation("x")
    before = equation.out_margins
    with pytest.raises(HwpxValueError) as caught:
        equation.set_out_margins(top=value)
    assert caught.value.code == "shape-out-margin-value"
    assert equation.out_margins == before


def test_a_group_member_has_no_outer_margins_of_its_own() -> None:
    doc = HwpxDocument.open(HANCOM / "group_in_a_group.hwpx")
    member = doc.sections[0].paragraphs[0].objects[0].members[0]
    assert member.out_margins == CellMargins(0, 0, 0, 0)
    with pytest.raises(HwpxValueError) as caught:
        member.set_out_margins(left=10)
    assert caught.value.code == "shape-group-member-unsupported"


# -- equation font and size -----------------------------------------------------------------------------------


def test_base_unit_measures_the_box_again_as_add_equation_does() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_objects_among_text_equation.hwpx")
    equation = doc.shapes.equations[0]
    script = equation.script
    paragraph = equation.paragraph.element
    equation.base_unit = 2000
    measured = measure_equation(script, base_unit=2000)
    assert equation.base_unit == 2000
    assert (equation.width, equation.height, equation.base_line) == (measured.width, measured.height,
                                                                     measured.base_line)
    assert equation.script == script and not _has_cache(paragraph)
    made = doc.add_paragraph("").add_equation(script, base_unit=2000)
    assert (made.width, made.height, made.base_line) == (equation.width, equation.height, equation.base_line)
    again = _reopen(doc)
    assert again.shapes.equations[0].base_unit == 2000


@pytest.mark.parametrize("value", [0, -5, 1.5, True, "1200"])
def test_base_unit_refuses_other_values(value) -> None:
    doc = HwpxDocument.new()
    equation = doc.add_paragraph("").add_equation("x", base_unit=1200)
    with pytest.raises(HwpxValueError) as caught:
        equation.base_unit = value
    assert caught.value.code == "shape-equation-base-unit-value"
    assert equation.base_unit == 1200


def test_font_writes_and_keeps_the_box() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_objects_among_text_equation.hwpx")
    equation = doc.shapes.equations[0]
    box = (equation.width, equation.height, equation.base_line)
    equation.font = "HancomEQN" if equation.font != "HancomEQN" else "HYhwpEQ"
    wanted = equation.font
    assert (equation.width, equation.height, equation.base_line) == box
    assert not _has_cache(equation.paragraph.element)
    assert _reopen(doc).shapes.equations[0].font == wanted
    for value in ("", "  ", None, 5):
        with pytest.raises(HwpxValueError) as caught:
            equation.font = value
        assert caught.value.code == "shape-equation-font-empty"
    assert equation.font == wanted


# -- removed objects take their images with them ----------------------------------------------------------------


def test_remove_takes_an_image_nothing_else_shows_out_of_the_package() -> None:
    doc = HwpxDocument.new()
    first = doc.add_picture(PNG, "png")
    other = doc.add_picture(PNG, "png")
    again = doc.add_paragraph("").add_picture(first.item_id, width=1000, height=1000)  # shows the same image
    first.remove()
    assert {str(i) for i in doc.media.images} == {again.item_id, other.item_id}
    again.remove()
    assert [str(i) for i in doc.media.images] == [other.item_id]
    other.remove(remove_orphaned=False)
    assert [str(i) for i in doc.media.images] == [other.item_id]
    saved = _reopen(doc)
    assert [name for name in _parts(saved.to_bytes()) if name.startswith("BinData/")] == [
        f"BinData/{other.item_id}.png"]


def test_a_removed_table_and_group_take_their_images() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    table.cell(0, 0).paragraphs[0].add_picture(str(doc.media.add_image(PNG, "png")), width=500, height=500)
    assert len(doc.media.images) == 1
    table.remove()
    assert doc.media.images == ()
    _reopen(doc)


def test_remove_on_a_hancom_document_keeps_an_image_another_picture_shows() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_wrapped_pictures_in_cached_cells.hwpx")
    images = {str(i) for i in doc.media.images}
    picture = doc.media.pictures[0]
    assert [p.item_id for p in doc.media.pictures].count(picture.item_id) > 1
    picture.remove()
    assert {str(i) for i in doc.media.images} == images
    _reopen(doc)


def test_remove_on_a_hancom_document_drops_only_its_own_image() -> None:
    doc = HwpxDocument.open(HANCOM / "pages_cell_two_pictures_on_one_line.hwpx")
    target = doc.media.pictures[0]
    item = target.item_id
    before = _parts(doc.to_bytes())
    target.remove()
    assert item not in {str(i) for i in doc.media.images}
    after = _parts(_reopen(doc).to_bytes())
    gone = {name for name in before if name not in after}
    assert len(gone) == 1 and item in next(iter(gone))
    changed = {name for name in before if name in after and before[name] != after[name]}
    assert changed <= {"Contents/section0.xml", "Contents/content.hpf", "Contents/header.xml"}
