# SPDX-License-Identifier: Apache-2.0
"""Numbering and bullet definitions, and a paragraph's place in a list (7.0).

``doc.styles.add_numbering`` / ``ensure_bullet`` / ``set_numbering_level`` make and change the
definitions; ``Paragraph.set_numbering`` / ``set_bullet`` put one paragraph in a list keeping the
rest of its shape; ``SectionProperties.outline_shape_id_ref`` names the numbering a section draws
its outline numbers with. The defaults are what Hancom saves: ``list_number_level1.hwpx`` is a new
numbered list Hancom made (it numbers it with the document's definition 1), and
``pages_empty_numbered_paragraphs.hwpx`` holds bullets Hancom saved.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxLookupError, HwpxValueError
from hwpx.oxml.numbering_kinds import HANCOM_NUMBERING_LEVELS

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"


def _open(name: str) -> HwpxDocument:
    return HwpxDocument.open((FIXTURES / f"{name}.hwpx").read_bytes())


def _heading(doc: HwpxDocument, paragraph) -> tuple[str | None, int | None, int | None]:
    shape = doc.styles.paragraph_property(paragraph.para_pr_id_ref)
    heading = None if shape is None else shape.heading
    if heading is None:
        return None, None, None
    return heading.type, heading.id_ref, heading.level


def _cached(paragraph) -> bool:
    return paragraph.element.find(f"{HP}linesegarray") is not None


def _header_xml(doc: HwpxDocument) -> bytes:
    import xml.etree.ElementTree as ET

    return ET.tostring(doc.oxml.headers[0].element)


def _new(*texts: str) -> HwpxDocument:
    doc = HwpxDocument.new()
    for text in texts:
        doc.add_paragraph(text)
    return doc


def _numbering(doc: HwpxDocument, numbering_id):
    """The numbering read as a value (``doc.styles.numbering``; 7.0 folded ``numbering_info`` into it, D12)."""

    return doc.styles.numbering(numbering_id)


def _level_values(level) -> tuple[object, ...]:
    return (level.level, level.start, level.number_format, level.text, level.alignment, level.char_pr_id_ref,
            level.auto_indent, level.width_adjust, level.text_offset, level.text_offset_type, level.checkable)


# -- add_numbering ---------------------------------------------------------------------------


def test_a_new_numbering_is_hancoms_own_numbering() -> None:
    # The new-document skeleton is a file Hancom 2024 (13.0) saved; its numbering 1 is the one
    # Hancom gives a new numbered list (list_number_level1.hwpx numbers its list with id 1).
    hancom = HwpxDocument.new()
    own = _numbering(hancom, 1)
    assert own is not None and len(own.levels) == 10
    assert all(_heading(_open("list_number_level1"), p)[:2] == ("NUMBER", 1)
               for p in _open("list_number_level1").paragraphs if p.text)

    made = hancom.styles.add_numbering()

    assert made.id != own.id
    assert [_level_values(level) for level in made.levels] == [_level_values(level) for level in own.levels]
    assert made.start == own.start == 0
    assert [(level.text, level.number_format, level.checkable) for level in made.levels] == list(
        HANCOM_NUMBERING_LEVELS
    )


def test_every_call_makes_a_new_list() -> None:
    doc = _new("가")

    first = doc.styles.add_numbering()
    second = doc.styles.add_numbering()

    assert first.id != second.id
    assert set(doc.styles.numberings) >= {first.id, second.id}


def test_levels_change_the_levels_of_their_place_and_leave_the_rest_hancoms() -> None:
    doc = _new("가")

    made = doc.styles.add_numbering(
        [{"text": "^1)", "start": 3}, {"text": "(^2)", "number_format": "latin_small"}, {}]
    )

    assert (made.levels[0].text, made.levels[0].number_format, made.levels[0].start) == ("^1)", "DIGIT", 3)
    assert (made.levels[1].text, made.levels[1].number_format) == ("(^2)", "LATIN_SMALL")
    assert (made.levels[2].text, made.levels[2].number_format) == ("^3)", "DIGIT")
    assert made.start == 3  # a list's start is the definition's (16 bits), as for apply_list_format
    assert len(made.levels) == 10


def test_an_empty_pattern_draws_no_number() -> None:
    doc = _new("가")

    made = doc.styles.add_numbering([{"text": ""}])

    head = next(
        item for item in doc.oxml.headers[0].element.iter(f"{HH}numbering") if item.get("id") == made.id
    ).find(f"{HH}paraHead")
    assert head is not None and head.text is None  # written as Hancom writes its levels 9 and 10


@pytest.mark.parametrize(
    ("levels", "code"),
    [
        ([{"txt": "^1."}], "style-numbering-level-invalid"),
        ([{"text": 1}], "style-numbering-level-invalid"),
        (["^1."], "style-numbering-level-invalid"),
        ({"text": "^1."}, "style-numbering-level-invalid"),
        ([{}] * 11, "style-list-level-invalid"),
        ([{"number_format": "BOGUS"}], "style-number-format-invalid"),
        ([{"start": 65536}], "style-list-start-value"),
        ([{"start": True}], "style-list-start-value"),
    ],
)
def test_bad_levels_are_refused_before_the_header_changes(levels, code: str) -> None:
    doc = _new("가")
    before = _header_xml(doc)

    with pytest.raises(HwpxValueError) as caught:
        doc.styles.add_numbering(levels)

    assert caught.value.code == code
    assert _header_xml(doc) == before


# -- ensure_bullet ---------------------------------------------------------------------------


def test_a_bullet_hancom_saved_is_found_again() -> None:
    doc = _open("pages_empty_numbered_paragraphs")
    chars = {bullet.char: key for key, bullet in doc.styles.bullets.items()}
    before = _header_xml(doc)

    assert doc.styles.ensure_bullet("○") == chars["○"]
    assert doc.styles.ensure_bullet("●") == chars["●"]
    assert _header_xml(doc) == before


def test_a_new_bullet_is_written_as_hancom_writes_one() -> None:
    doc = _new("가")

    bullet_id = doc.styles.ensure_bullet("◆")

    assert doc.styles.ensure_bullet("◆") == bullet_id
    element = next(item for item in doc.oxml.headers[0].element.iter(f"{HH}bullet") if item.get("id") == bullet_id)
    assert dict(element.attrib) == {"id": bullet_id, "char": "◆", "useImage": "0"}
    head = element.find(f"{HH}paraHead")
    assert head is not None and dict(head.attrib) == {
        "level": "0", "align": "LEFT", "useInstWidth": "0", "autoIndent": "1", "widthAdjust": "0",
        "textOffsetType": "PERCENT", "textOffset": "50", "numFormat": "DIGIT",
        "charPrIDRef": "4294967295", "checkable": "0",
    }
    assert doc.styles.ensure_bullet() != bullet_id  # "●", the bullet Hancom gives a new list


def test_a_bullet_with_its_own_character_shape_is_another_definition() -> None:
    doc = _new("가")
    shape = doc.styles.ensure_run(font="Wingdings")

    plain = doc.styles.ensure_bullet("■")
    shaped = doc.styles.ensure_bullet("■", char_pr_id_ref=shape)

    assert plain != shaped
    assert doc.styles.bullet(shaped).para_head.attributes["charPrIDRef"] == shape
    assert doc.styles.ensure_bullet("■", char_pr_id_ref=int(shape)) == shaped


@pytest.mark.parametrize("char", ["", "●●", 7, None])
def test_a_bullet_is_one_character(char) -> None:
    doc = _new("가")

    with pytest.raises(HwpxValueError) as caught:
        doc.styles.ensure_bullet(char)

    assert caught.value.code == "style-bullet-char-invalid"


def test_a_bullet_shape_the_header_lacks_is_refused() -> None:
    doc = _new("가")

    with pytest.raises(HwpxLookupError) as caught:
        doc.styles.ensure_bullet("●", char_pr_id_ref=9999)

    assert caught.value.code == "style-definition-not-found"


# -- Paragraph.set_numbering / set_bullet ------------------------------------------------------


def test_paragraphs_given_one_numbering_make_one_list() -> None:
    doc = _new("하나", "둘", "셋")
    numbering = doc.styles.add_numbering()
    first, second, third = doc.paragraphs

    first.set_numbering(numbering)
    second.set_numbering(numbering, level=2)
    third.set_numbering(numbering.id)

    assert _heading(doc, first) == ("NUMBER", int(numbering.id), 0)
    assert _heading(doc, second) == ("NUMBER", int(numbering.id), 1)
    assert _heading(doc, third) == ("NUMBER", int(numbering.id), 0)
    assert first.para_pr_id_ref == third.para_pr_id_ref  # one shape for the alike


def test_the_rest_of_the_paragraph_shape_stays() -> None:
    doc = _new("들여 쓴 항목")
    paragraph = doc.paragraphs[0]
    paragraph.indent_left_mm = 10.0
    paragraph.alignment = "CENTER"
    paragraph.keep_with_next = True

    paragraph.set_bullet(doc.styles.ensure_bullet("○"), level=2)

    assert paragraph.indent_left_mm == pytest.approx(10.0, abs=0.01)
    assert str(paragraph.alignment) == "CENTER" or paragraph.alignment.value == "CENTER"
    assert paragraph.keep_with_next is True
    assert _heading(doc, paragraph)[0::2] == ("BULLET", 1)


def test_a_bullet_read_from_the_document_is_taken() -> None:
    doc = _open("pages_empty_numbered_paragraphs")
    bullet = next(item for item in doc.styles.bullets.values() if item.char == "■")
    paragraph = next(p for p in doc.paragraphs if p.text)

    paragraph.set_bullet(bullet)

    assert _heading(doc, paragraph) == ("BULLET", bullet.id, 0)


def test_none_takes_the_head_away() -> None:
    doc = _new("가")
    paragraph = doc.paragraphs[0]
    paragraph.set_numbering(doc.styles.add_numbering(), level=3)

    paragraph.set_numbering(None)

    assert _heading(doc, paragraph)[0] == "NONE"
    assert paragraph.outline_level == 0


def test_a_numbered_paragraph_is_laid_out_again() -> None:
    doc = _open("pages_number_in_its_own_16pt_shape")
    paragraph = next(p for p in doc.paragraphs if _heading(doc, p)[0] == "NONE" and p.text)
    assert _cached(paragraph)

    paragraph.set_numbering(2)

    assert not _cached(paragraph)


def test_a_cell_paragraph_takes_a_list_and_its_table_is_laid_out_again() -> None:
    doc = _new("가")
    table = doc.add_table(2, 2)
    cell_paragraph = table.cell(0, 0).paragraphs[0]
    cell_paragraph.text = "칸 항목"

    cell_paragraph.set_bullet(doc.styles.ensure_bullet())

    assert _heading(doc, cell_paragraph)[0] == "BULLET"
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok


@pytest.mark.parametrize(("kind", "definition"), [("numbering", 999), ("bullet", "77")])
def test_a_definition_the_header_lacks_is_refused(kind: str, definition) -> None:
    doc = _new("가")
    paragraph = doc.paragraphs[0]
    before = paragraph.para_pr_id_ref

    with pytest.raises(HwpxLookupError) as caught:
        getattr(paragraph, f"set_{kind}")(definition)

    assert caught.value.code == "style-definition-not-found"
    assert caught.value.context["kind"] == kind
    assert paragraph.para_pr_id_ref == before


@pytest.mark.parametrize("level", [0, 11, True, "1"])
def test_a_list_level_is_1_to_10(level) -> None:
    doc = _new("가")

    with pytest.raises(HwpxValueError) as caught:
        doc.paragraphs[0].set_numbering(doc.styles.add_numbering(), level=level)

    assert caught.value.code == "style-list-level-invalid"


# -- set_numbering_level and the outline numbering ---------------------------------------------


def test_a_level_changes_and_its_numbered_paragraphs_are_laid_out_again() -> None:
    doc = _open("pages_number_in_its_own_16pt_shape")
    numbered = [p for p in doc.paragraphs if _heading(doc, p)[:2] == ("NUMBER", 2)]
    others = [p for p in doc.paragraphs if _heading(doc, p)[0] == "NONE"]
    assert numbered and all(map(_cached, numbered)) and all(map(_cached, others))

    doc.styles.set_numbering_level(2, 1, text="^1)", number_format="CIRCLED_DIGIT", start=5)

    level = _numbering(doc, 2).level(1)
    assert (level.text, level.number_format, level.start) == ("^1)", "CIRCLED_DIGIT", 5)
    assert _numbering(doc, 2).start == 5
    assert not any(map(_cached, numbered))
    assert all(map(_cached, others))


def test_a_section_names_its_outline_numbering() -> None:
    doc = _open("line_cache_labels")

    assert doc.sections[0].properties.outline_shape_id_ref == "1"
    assert HwpxDocument.new().sections[0].properties.outline_shape_id_ref == "1"


def test_emptying_the_outline_numbering_lays_the_outline_paragraphs_out_again() -> None:
    doc = _open("line_cache_labels")
    outline_id = doc.sections[0].properties.outline_shape_id_ref
    outlined = [p for p in doc.paragraphs if p.outline_level]
    plain = [p for p in doc.paragraphs if _heading(doc, p)[0] == "NONE" and _cached(p)]
    assert outlined and all(map(_cached, outlined)) and plain

    for level in range(1, 11):
        doc.styles.set_numbering_level(outline_id, level, text="")

    assert all(level.text == "" for level in _numbering(doc, outline_id).levels)
    assert not any(map(_cached, outlined))
    assert all(map(_cached, plain))
    reopened = HwpxDocument.open(doc.to_bytes())
    assert reopened.validate().ok
    assert all(level.text == "" for level in _numbering(reopened, outline_id).levels)


def test_the_same_values_change_nothing() -> None:
    doc = _open("pages_number_in_its_own_16pt_shape")
    before = _header_xml(doc)

    doc.styles.set_numbering_level(2, 1, text="^1.", number_format="DIGIT")

    assert _header_xml(doc) == before
    assert not doc.oxml.headers[0].dirty


@pytest.mark.parametrize(
    ("call", "error", "code"),
    [
        (lambda d: d.styles.set_numbering_level(1, 1), HwpxValueError, "style-numbering-level-invalid"),
        (lambda d: d.styles.set_numbering_level(1, 11, text=""), HwpxValueError, "style-list-level-invalid"),
        (lambda d: d.styles.set_numbering_level(99, 1, text=""), HwpxLookupError, "style-definition-not-found"),
        (lambda d: d.styles.set_numbering_level(1, 1, start=-1), HwpxValueError, "style-list-start-value"),
    ],
)
def test_set_numbering_level_refuses_before_changing(call, error, code: str) -> None:
    doc = _new("가")
    before = _header_xml(doc)

    with pytest.raises(error) as caught:
        call(doc)

    assert caught.value.code == code
    assert _header_xml(doc) == before


def test_a_level_a_definition_lacks_is_named() -> None:
    doc = _new("가")
    short = doc.styles.ensure_numbering(kind="number", levels=[{}])  # the 6.x verb makes one level
    numbering_id = doc.styles.paragraph_property(short[0]).heading.id_ref

    with pytest.raises(HwpxLookupError) as caught:
        doc.styles.set_numbering_level(numbering_id, 2, text="^2)")

    assert caught.value.code == "style-numbering-level-missing"
    assert caught.value.context["levels"] == [1]


# -- saving --------------------------------------------------------------------------------------


def test_a_list_document_saves_reopens_and_keeps_its_other_parts() -> None:
    source = (FIXTURES / "pages_number_in_its_own_16pt_shape.hwpx").read_bytes()
    doc = HwpxDocument.open(source)
    numbering = doc.styles.add_numbering([{"text": "^1)"}])
    bullet = doc.styles.ensure_bullet("□")
    texts = [p for p in doc.paragraphs if p.text]
    texts[0].set_numbering(numbering)
    texts[1].set_bullet(bullet, level=2)

    saved = doc.to_bytes()

    reopened = HwpxDocument.open(saved)
    assert reopened.validate().ok
    assert _heading(reopened, [p for p in reopened.paragraphs if p.text][0])[:2] == ("NUMBER", int(numbering.id))
    with zipfile.ZipFile(io.BytesIO(source)) as before, zipfile.ZipFile(io.BytesIO(saved)) as after:
        changed = {name for name in before.namelist() if before.read(name) != after.read(name)}
    assert changed <= {"Contents/header.xml", "Contents/section0.xml"}
