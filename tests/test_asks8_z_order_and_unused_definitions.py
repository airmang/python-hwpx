# SPDX-License-Identifier: Apache-2.0
"""asks8: new objects stack as Hancom numbers them, and unused definitions at the end of a list go.

- Hancom gives each object it makes the next ``zOrder`` of the document: in tests/fixtures/hancom_saved the
  documents whose objects Hancom made number them in the order they were made, tables and objects placed
  like characters included (``memos_in_fields``: the table 0, the ellipse 1), a group after its members,
  and the members of a group 0; a later section goes on from the earlier ones (hwpxlib_corpus
  ``error__20251107__test``: 0-4, then 5-30). The engine gave every new object 0.
- ``doc.styles.remove_unused_definitions()`` drops the unused definitions that end a list (Hancom's saves
  number them 0..N-1 with no gap and drop the ones nothing points at).
"""

from __future__ import annotations

import io

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _orders(doc: HwpxDocument) -> list[int]:
    return [int(node.get("zOrder")) for section in doc.oxml.sections for node in section.element.iter()
            if node.get("zOrder") is not None and node.getparent().tag != f"{_HP}container"]


def test_new_objects_stack_in_the_order_they_are_made() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    made = [
        paragraph.add_rectangle(width=2000, height=1000, treat_as_char=False),
        paragraph.add_ellipse(width=2000, height=1000, treat_as_char=False),
        doc.add_table(2, 2),
        doc.add_paragraph("").add_equation("x + y"),
        doc.add_paragraph("").add_line(),
    ]

    assert [int(obj.element.get("zOrder")) for obj in made] == [0, 1, 2, 3, 4]


def test_a_nested_table_and_a_later_object_go_on_counting() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    inner = table.cell(0, 0).add_table(1, 1)
    rect = doc.add_paragraph("").add_rectangle(width=2000, height=1000)

    assert (table.element.get("zOrder"), inner.element.get("zOrder"), rect.element.get("zOrder")) == ("0", "1", "2")


def test_a_group_takes_the_next_number_and_its_members_keep_zero() -> None:
    from hwpx.oxml import ContainerMember

    doc = HwpxDocument.new()
    doc.add_paragraph("").add_rectangle(width=2000, height=1000)
    members = [ContainerMember.rect(0, 0, 1000, 1000), ContainerMember.ellipse(1500, 0, 1000, 1000)]
    group = doc.add_paragraph("").add_container(members)

    assert group.element.get("zOrder") == "1"
    assert {node.get("zOrder") for node in group.element if node.get("zOrder") is not None} == {"0"}


def test_a_later_section_goes_on_from_the_earlier_ones() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("").add_rectangle(width=2000, height=1000)
    doc.add_paragraph("").add_rectangle(width=2000, height=1000)
    section = doc.oxml.add_section()
    rect = section.add_paragraph("").add_rectangle(width=2000, height=1000)

    assert rect.element.get("zOrder") == "2"


def test_copies_go_on_top() -> None:
    doc = HwpxDocument.new()
    rect = doc.add_paragraph("").add_rectangle(width=2000, height=1000)
    table = doc.add_table(1, 1)
    doc.add_paragraph("").add_ellipse(width=2000, height=1000)

    copy = rect.copy_to(doc.add_paragraph(""))
    table_copy = table.copy_to(doc.add_paragraph(""))
    after = table.copy_after()

    assert [copy.element.get("zOrder"), table_copy.element.get("zOrder"), after.element.get("zOrder")] == ["3", "4", "5"]


def test_moving_a_table_keeps_its_number() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    doc.add_paragraph("").add_rectangle(width=2000, height=1000)

    table.move_to(doc.add_paragraph(""))

    assert table.element.get("zOrder") == "0"


def test_numbers_are_the_same_on_every_run() -> None:
    def make() -> bytes:
        # closed at the end: a seeded document left open keeps its seed for every later document
        with HwpxDocument.new(seed=7) as doc:
            for _ in range(3):
                doc.add_paragraph("").add_rectangle(width=2000, height=1000)
            doc.add_table(1, 1)
            buffer = io.BytesIO()
            doc.save(buffer)
            return buffer.getvalue()

    assert make() == make()


def test_saved_numbers_survive_reopening() -> None:
    doc = HwpxDocument.new()
    for _ in range(3):
        doc.add_paragraph("").add_rectangle(width=2000, height=1000, treat_as_char=False)
    buffer = io.BytesIO()
    doc.save(buffer)
    reopened = HwpxDocument.open(buffer.getvalue())
    assert _orders(reopened) == [0, 1, 2]
    reopened.add_paragraph("").add_rectangle(width=2000, height=1000)
    assert _orders(reopened) == [0, 1, 2, 3]


# -- remove_unused_definitions ---------------------------------------------------------------------------


def _count(doc: HwpxDocument, kind: str) -> int:
    return len(doc.oxml.headers[0].element.findall(f".//{_HH}{kind}"))


def test_trial_copies_at_the_end_go() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가나다")
    run = paragraph.runs[0]
    base = run.char_pr_id_ref
    before = _count(doc, "charPr")
    for spacing in (-3, -5, -7):  # trial values, each a copy of the base
        run.char_pr_id_ref = base
        run.set_format(letter_spacing=spacing)
    assert _count(doc, "charPr") == before + 3
    run.char_pr_id_ref = base

    removed = doc.styles.remove_unused_definitions()

    assert removed["char_properties"] == tuple(str(before + i) for i in range(3))
    assert _count(doc, "charPr") == before
    box = doc.oxml.headers[0].element.find(f".//{_HH}charProperties")
    assert box.get("itemCnt") == str(before)
    assert doc.styles.remove_unused_definitions() == {name: () for name in removed}  # nothing more


def test_a_used_definition_stops_the_removal_and_middle_ones_stay() -> None:
    doc = HwpxDocument.new()
    first, second = doc.add_paragraph("가"), doc.add_paragraph("나")
    base = first.runs[0].char_pr_id_ref
    first.runs[0].set_format(bold=True)  # id N (unused once the run goes back)
    unused = first.runs[0].char_pr_id_ref
    second.runs[0].set_format(italic=True)  # id N + 1, still used
    first.runs[0].char_pr_id_ref = base

    removed = doc.styles.remove_unused_definitions(["char_properties"])

    assert removed == {"char_properties": ()}
    assert doc.oxml.headers[0].element.find(f".//{_HH}charPr[@id='{unused}']") is not None


def test_a_definition_named_by_a_style_or_another_definition_is_used() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가")
    paragraph.runs[0].set_format(bold=True)
    bold = paragraph.runs[0].char_pr_id_ref
    doc.styles.ensure_style("시험 스타일", char_pr_id_ref=bold)
    paragraph.runs[0].char_pr_id_ref = 0

    assert doc.styles.remove_unused_definitions(["char_properties"]) == {"char_properties": ()}


def test_the_first_definition_stays() -> None:
    doc = HwpxDocument.new()
    for kind, name in (("charPr", "char_properties"), ("paraPr", "paragraph_properties"),
                       ("borderFill", "border_fills"), ("tabPr", "tab_properties")):
        assert _count(doc, kind) >= 1
    doc.styles.remove_unused_definitions()
    for kind in ("charPr", "paraPr", "borderFill", "tabPr"):
        assert _count(doc, kind) >= 1


def test_saved_after_removal_opens_clean() -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    run = doc.add_paragraph("가").runs[0]
    base = run.char_pr_id_ref
    run.set_format(ratio=90)
    run.char_pr_id_ref = base
    doc.styles.remove_unused_definitions()
    buffer = io.BytesIO()
    doc.save(buffer)
    assert validate_editor_open_safety(buffer.getvalue()).ok


@pytest.mark.parametrize("kinds", [["char"], [], "nothing"])
def test_unknown_kinds_are_refused(kinds) -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxError) as refused:
        doc.styles.remove_unused_definitions(kinds)
    assert refused.value.code == "style-definition-kind-invalid"
