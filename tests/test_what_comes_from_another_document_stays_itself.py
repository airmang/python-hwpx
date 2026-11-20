# SPDX-License-Identifier: Apache-2.0
"""Content taken from another document, or kept across a save, stays what it was.

Each of these returned success and saved a document that reported itself sound:

* a paragraph copied between two documents Hangul saved came out showing the receiving document's
  picture (both name their picture ``image1``; the source's data was never copied), and appended to
  an empty document it pointed at no data at all;
* tracked changes merged in kept the source's change numbers, so they named the receiving document's
  changes: rejecting one's own insertion removed the other document's text;
* a tracked change accepted or rejected gave its number to the next change made, and the object held
  for the resolved one then resolved that one;
* a document saved and opened again with its seed was handed the ids it already held;
* one paragraph of a field running over several paragraphs, copied alone, left two begins for one end;
* a tracked deletion whose match crosses markup failed after it had added a change to the header.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument, validate_package
from hwpx.errors import HwpxValueError
from hwpx.tools.document_merge import append_document
from hwpx.tools.id_integrity import check_id_integrity

FIXTURES = Path(__file__).parent / "fixtures"
CORPUS = FIXTURES / "hwpxlib_corpus"
SAVED = FIXTURES / "hancom_saved"
PICTURE = CORPUS / "reader_writer__SimplePicture.hwpx"
TRACKED = CORPUS / "reader_writer__ChangeTrack.hwpx"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


def _archive(document: HwpxDocument) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(document.to_bytes()))


def _section(document: HwpxDocument, name: str = "Contents/section0.xml") -> etree._Element:
    return etree.fromstring(_archive(document).read(name))


def _pictures(document: HwpxDocument) -> dict[str, str]:
    """Each picture reference in the saved body, with the hash of the data it names."""

    archive = _archive(document)
    data = {Path(name).stem: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.startswith("BinData/")}
    return {image.get("binaryItemIDRef"): data.get(image.get("binaryItemIDRef"), "MISSING") for image in _section(document).iter(f"{HC}img")}


# -- a picture ----------------------------------------------------------------------------------


def test_a_paragraph_copied_between_documents_brings_its_own_picture() -> None:
    source = HwpxDocument.open(str(PICTURE))
    target = HwpxDocument.open(str(SAVED / "picture_cropped.hwpx"))
    (theirs,) = set(_pictures(source).values())
    (ours,) = set(_pictures(target).values())
    assert theirs != ours and set(_pictures(source)) == set(_pictures(target))  # both call theirs image1

    source.paragraphs[0].copy_to(target.paragraphs[-1])

    assert sorted(_pictures(target).values()) == sorted([ours, theirs])  # before: ours twice
    assert not check_id_integrity(target).dangling


def test_a_picture_appended_to_another_document_has_its_data() -> None:
    target = HwpxDocument.new()
    append_document(target, str(PICTURE))
    (theirs,) = set(_pictures(HwpxDocument.open(str(PICTURE))).values())
    assert list(_pictures(target).values()) == [theirs]  # before: a reference with no data
    assert validate_package(target.to_bytes()).ok
    assert list(_pictures(HwpxDocument.open(target.to_bytes())).values()) == [theirs]


def test_a_source_whose_picture_has_no_data_is_refused_before_the_target_changes() -> None:
    source = HwpxDocument.open(str(PICTURE))
    for image in source.sections[0].element.iter(f"{HC}img"):
        image.set("binaryItemIDRef", "nothing-of-this-name")
    target = HwpxDocument.new()
    target.add_paragraph("받는 문서")
    before = target.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        append_document(target, source)
    assert refused.value.code == "document-merge-unsupported-reference"
    assert target.to_bytes() == before


# -- tracked changes ----------------------------------------------------------------------------


def _change_ids(document: HwpxDocument) -> tuple[list[str], list[str]]:
    archive = _archive(document)
    header = etree.fromstring(archive.read("Contents/header.xml"))
    body = etree.fromstring(archive.read("Contents/section0.xml"))
    return [node.get("id") for node in header.iter(f"{HH}trackChange")], [node.get("TcId") for node in body.iter() if node.get("TcId")]


def test_merged_tracked_changes_get_definitions_of_their_own() -> None:
    target = HwpxDocument.new()
    local = target.tracking.insert(target.add_paragraph("TARGET"), "LOCAL", author="local reviewer")
    append_document(target, str(TRACKED))

    defined, used = _change_ids(target)
    assert set(used) <= set(defined) and len(defined) == 3  # before: one definition, marks 1 1 2 2 1 1
    kinds = {change.change_id: (change.kind, change.author) for change in target.tracking.changes}
    assert kinds[local.change_id] == ("INSERT", "local reviewer")
    assert sorted(kind for number, (kind, author) in kinds.items() if author == "fff") == ["DELETE", "INSERT"]

    target.tracking.reject(local)
    text = _archive(target).read("Contents/section0.xml").decode("utf-8")
    assert "LOCAL" not in text and "인간은" in text  # before: both gone
    assert [change.author for change in target.tracking.changes] == ["fff", "fff"]


def test_a_merged_change_can_be_rejected_alone() -> None:
    target = HwpxDocument.new()
    target.tracking.insert(target.add_paragraph("TARGET"), "LOCAL", author="local reviewer")
    append_document(target, str(TRACKED))
    theirs = next(change for change in target.tracking.changes if change.author == "fff" and change.kind == "INSERT")
    target.tracking.reject(theirs)
    text = _archive(target).read("Contents/section0.xml").decode("utf-8")
    assert "LOCAL" in text and "인간은" not in text


def test_a_resolved_change_does_not_lend_its_number_to_the_next() -> None:
    document = HwpxDocument.open(str(TRACKED))
    first = document.tracking.insert(0, "FIRST", author="Writer A")
    document.tracking.accept(first)
    second = document.tracking.insert(0, "SECOND", author="Writer B")
    assert second.change_id != first.change_id
    with pytest.raises(HwpxValueError) as refused:
        document.tracking.reject(first)  # before: rejected Writer B's insertion
    assert refused.value.code == "track-change-not-found"
    text = _archive(document).read("Contents/section0.xml").decode("utf-8")
    assert "FIRST" in text and "SECOND" in text


def test_a_change_resolved_before_any_was_added_keeps_its_number_too() -> None:
    document = HwpxDocument.open(str(TRACKED))
    existing = max(document.tracking.changes, key=lambda change: change.change_id)
    document.tracking.accept(existing)
    added = document.tracking.insert(0, "NEW", author="Writer")
    assert added.change_id > existing.change_id
    with pytest.raises(HwpxValueError):
        document.tracking.reject(existing)
    assert "NEW" in document.text.plain()


def test_a_tracked_deletion_across_markup_is_refused_before_the_header_changes() -> None:
    document = HwpxDocument.open(str(TRACKED))
    before = document.to_bytes()
    with pytest.raises(HwpxValueError) as refused:  # before: a bare ValueError, after adding change 3
        document.tracking.delete(0, match="경 추")
    assert refused.value.code == "track-match-crosses-markup"
    assert document.to_bytes() == before


# -- ids across a save --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 7, 20261120])
def test_a_document_opened_again_with_its_seed_is_not_handed_the_ids_it_holds(seed: int) -> None:
    source = str(SAVED / "table_insert_row_base.hwpx")
    document = HwpxDocument.open(source, seed=seed)
    first = document.fields.add("A", paragraph=0)
    document = HwpxDocument.open(document.to_bytes(), seed=seed)
    second = document.fields.add("B", paragraph=0)
    assert second.field_id != first.field_id  # before: the same id, and neither could be filled by it
    document.fields.fill("answer", field_id=first.field_id)
    ids = [node.get("id") for node in _section(document).iter(f"{HP}fieldBegin")]
    assert len(ids) == len(set(ids))


def test_opening_with_a_seed_still_writes_the_same_bytes_each_time() -> None:
    source = (SAVED / "table_insert_row_base.hwpx").read_bytes()

    def edited() -> bytes:
        document = HwpxDocument.open(source, seed=7)
        document.fields.add("A", paragraph=0)
        document.add_paragraph("덧붙임")
        return document.to_bytes()

    assert edited() == edited()


# -- half of a field ----------------------------------------------------------------------------

SPANNING = "658590940"  # begins in paragraph 2 and ends in paragraph 5 of the form


def _field_marks(document: HwpxDocument) -> tuple[list[str], list[str]]:
    body = _section(document)
    return [node.get("id") for node in body.iter(f"{HP}fieldBegin")], [node.get("beginIDRef") for node in body.iter(f"{HP}fieldEnd")]


@pytest.mark.parametrize("paragraph", [2, 3, 4, 5])
def test_a_copy_of_one_paragraph_of_a_field_leaves_the_field_one_begin_and_one_end(paragraph: int) -> None:
    document = HwpxDocument.open(str(SAVED / "form_fields_spanning_before.hwpx"))
    document.paragraphs[paragraph].insert_after()

    begins, ends = _field_marks(document)
    assert begins.count(SPANNING) == 1 and ends.count(SPANNING) == 1  # before: two begins when 2 was copied
    assert len(begins) == len(set(begins)) and set(ends) <= set(begins)
    assert not any(len(control) == 0 for control in _section(document).iter(f"{HP}ctrl"))  # no emptied control
    document.fields.fill("answer", field_id=SPANNING)  # before: field-ambiguous
    reopened = HwpxDocument.open(document.to_bytes())
    assert [field.has_end for field in reopened.fields.all if field.field_id == SPANNING] == [True]
    assert validate_package(document.to_bytes()).ok


# -- an angle it already has --------------------------------------------------------------------


def test_setting_the_angle_an_object_already_has_moves_nothing() -> None:
    document = HwpxDocument.open(str(SAVED / "flip_turned_group_up_down.hwpx"))
    group = document.paragraphs[1].shapes[0]
    before = etree.tostring(group.element)
    assert group.rotation == 330
    group.rotation = 330  # before: the flipped group moved 866 down
    group.rotation = -30
    assert etree.tostring(group.element) == before


# -- the documented conditions of a seeded document ---------------------------------------------


def test_the_engine_contract_states_when_seeded_bytes_are_the_same() -> None:
    contract = (Path(__file__).parents[1] / "docs" / "stable-api.md").read_text(encoding="utf-8")
    assert "시간대(`TZ`)가 같을 때" in contract and "파일에 이미 있는 id 를 피해서" in contract
