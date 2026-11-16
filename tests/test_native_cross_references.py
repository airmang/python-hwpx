# SPDX-License-Identifier: Apache-2.0
"""상호 참조(``fieldBegin type="CROSSREF"``) 고치기·지우기·만들기.

The parameters are written as Hancom writes them: ``Command`` is
``<path>;<type>;<content>;<hyperlink>;<open>;`` with the codes Hancom Office 2024 reads out of an
.hwp cross reference, and the path is ``?#<paragraph id>`` for an outline paragraph (the
Hancom-saved m7_toc_gold pair), ``?#<table id>`` for a table and ``?<name>`` for a bookmark (the
cross references of Hancom-made public .hwp samples). Other targets are refused. When what a cross
reference shows changes, its shown text is emptied for Hancom to fill in.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxError
from hwpx.objects import CrossReference

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
GOLD = Path(__file__).parent / "fixtures" / "m7_toc_gold" / "hancom-native-toc-A.hwpx"


def _reopen(document: HwpxDocument) -> HwpxDocument:
    reopened = HwpxDocument.open(document.to_bytes())
    assert not reopened.validate().issues
    return reopened


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _changed_parts(before: bytes, after: bytes) -> set[str]:
    old, new = _parts(before), _parts(after)
    return {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}


def _params(reference: CrossReference) -> dict[str, str]:
    return {p.name: p.value for p in reference.parameters}


def _headings(document: HwpxDocument):
    return [p for p in document.paragraphs if p.outline_level]


def test_a_hancom_saved_cross_reference_reads_as_before() -> None:
    (reference,) = HwpxDocument.open(GOLD).refs.cross_references
    assert (reference.ref_type, reference.content_type, reference.target, reference.text, reference.hyperlink) == (
        "TARGET_OUTLINE", "OBJECT_TYPE_PAGE", "#56578352", "2", False)
    assert reference.to_dict()["location"]["paragraphIndex"] == 0
    assert _params(reference)["Command"] == "?#56578352;5;0;0;0;"


def test_changing_what_it_shows_empties_its_text_for_hancom_to_fill() -> None:
    document = HwpxDocument.open(GOLD)
    before = document.to_bytes()
    (reference,) = document.refs.cross_references
    paragraph = document.paragraphs[0].element
    assert paragraph.find(f"{HP}linesegarray") is not None
    reference.content_type = "OBJECT_TYPE_NUMBER"
    assert (reference.content_type, reference.text) == ("OBJECT_TYPE_NUMBER", "")
    assert _params(reference)["Command"] == "?#56578352;5;1;0;0;"
    assert paragraph.find(f"{HP}linesegarray") is None
    (again,) = _reopen(document).refs.cross_references
    assert (again.content_type, again.text, again.target) == ("OBJECT_TYPE_NUMBER", "", "#56578352")
    assert _changed_parts(before, document.to_bytes()) == {"Contents/section0.xml"}


def test_the_hyperlink_flag_changes_alone_and_keeps_the_text() -> None:
    document = HwpxDocument.open(GOLD)
    (reference,) = document.refs.cross_references
    reference.hyperlink = True
    assert (reference.hyperlink, reference.text) == (True, "2")
    assert _params(reference)["Command"] == "?#56578352;5;0;1;0;" and _params(reference)["RefHyperLink"] == "true"


def test_writing_the_same_values_changes_nothing() -> None:
    document = HwpxDocument.open(GOLD)
    before = document.to_bytes()
    (reference,) = document.refs.cross_references
    reference.content_type = reference.content_type
    reference.hyperlink = reference.hyperlink
    reference.set_target(_headings(document)[1])  # the heading it already points at
    assert reference.text == "2"
    assert document.to_bytes() == before


def test_set_target_points_at_another_heading_a_bookmark_or_a_table() -> None:
    document = HwpxDocument.open(GOLD)
    (reference,) = document.refs.cross_references
    third = _headings(document)[2]
    reference.set_target(third)
    assert (reference.ref_type, reference.target, reference.text) == ("TARGET_OUTLINE", f"#{third.element.get('id')}", "")
    document.refs.add_bookmark("끝", paragraph=_headings(document)[3])
    reference.set_target("끝")
    assert (reference.ref_type, reference.target) == ("TARGET_BOOKMARK", "끝")
    assert _params(reference)["Command"] == "?끝;6;0;0;0;" and _params(reference)["RefPath"] == "?끝;"
    table = document.add_table(1, 1)
    reference.set_target(table)
    assert (reference.ref_type, reference.target) == ("TARGET_TABLE", f"#{table.element.get('id')}")
    assert _params(reference)["Command"] == f"?#{table.element.get('id')};0;0;0;0;"
    bookmark = document.refs.bookmarks[0]
    reference.set_target(bookmark)
    assert reference.target == "끝"
    _reopen(document)


@pytest.mark.parametrize(
    "make_target",
    [
        lambda d: d.paragraphs[-1],  # a body paragraph that is no heading
        lambda d: "없는 책갈피",
        lambda d: "#123",
        lambda d: d.shapes.add_rectangle(),
        lambda d: 3,
    ],
)
def test_targets_never_seen_in_a_hancom_file_are_refused(make_target) -> None:
    document = HwpxDocument.open(GOLD)
    (reference,) = document.refs.cross_references
    target = make_target(document)
    before = document.to_bytes()
    with pytest.raises(HwpxError) as excinfo:
        reference.set_target(target)
    assert excinfo.value.code == "ref-cross-reference-target-unsupported" and excinfo.value.suggestion
    with pytest.raises(HwpxError):
        document.refs.add_cross_reference(target)
    assert document.to_bytes() == before


def test_bad_content_type_and_hyperlink_values_are_refused() -> None:
    document = HwpxDocument.open(GOLD)
    (reference,) = document.refs.cross_references
    with pytest.raises(HwpxError) as excinfo:
        reference.content_type = "PAGE"
    assert excinfo.value.code == "ref-cross-reference-content-value"
    with pytest.raises(HwpxError) as excinfo:
        reference.hyperlink = "yes"
    assert excinfo.value.code == "ref-cross-reference-hyperlink-value"


def test_remove_keeps_the_shown_text_unless_told_not_to() -> None:
    document = HwpxDocument.open(GOLD)
    (reference,) = document.refs.cross_references
    paragraph = document.paragraphs[0]
    reference.remove()
    assert document.refs.cross_references == ()
    assert paragraph.text.endswith("2")
    assert paragraph.element.find(f"{HP}linesegarray") is None
    _reopen(document)
    other = HwpxDocument.open(GOLD)
    other.refs.cross_references[0].remove(keep_text=False)
    assert not other.paragraphs[0].text.endswith("2")


def test_add_cross_reference_writes_hancoms_parameters_and_reads_back() -> None:
    document = HwpxDocument.new()
    heading = document.add_heading("제목", level=1)
    document.add_paragraph("본문")
    reference = document.refs.add_cross_reference(heading, content_type="OBJECT_TYPE_PAGE")
    assert isinstance(reference, CrossReference)
    anchor = heading.element.get("id")
    assert anchor.isdigit() and anchor != "2147483648"
    assert list(_params(reference).items()) == [
        ("Fiexde", "1"), ("Prop", "0"), ("Command", f"?#{anchor};5;0;0;0;"), ("RefPath", f"?#{anchor};"),
        ("RefType", "TARGET_OUTLINE"), ("RefContentType", "OBJECT_TYPE_PAGE"), ("RefHyperLink", "false"),
        ("RefOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB"),
    ]
    begin = reference.element
    assert (begin.get("type"), begin.get("fieldid"), begin.get("editable"), begin.get("dirty")) == (
        "CROSSREF", "628650598", "0", "0")
    assert reference.text == ""
    into = document.add_paragraph("앞 글 ")
    second = document.refs.add_cross_reference(heading, content_type="OBJECT_TYPE_CONTENTS", hyperlink=True,
                                               paragraph=into)
    assert second.element.getparent().getparent().getparent() is into.element
    reopened = _reopen(document)
    assert [(r.target, r.content_type, r.hyperlink) for r in reopened.refs.cross_references] == [
        (f"#{anchor}", "OBJECT_TYPE_PAGE", False), (f"#{anchor}", "OBJECT_TYPE_CONTENTS", True),
    ]


def test_a_shared_paragraph_id_gets_a_unique_one_before_it_is_pointed_at() -> None:
    document = HwpxDocument.new()
    first = document.add_heading("하나", level=1)
    second = document.add_heading("둘", level=1)
    first.element.set("id", "2147483648")
    second.element.set("id", "2147483648")
    reference = document.refs.add_cross_reference(second)
    assert second.element.get("id") not in ("2147483648", first.element.get("id"))
    assert reference.target == f"#{second.element.get('id')}"
