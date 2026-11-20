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


# -- what the second look at these fixes found ---------------------------------------------------


def test_changes_carried_in_leave_the_receivers_changes_with_their_author() -> None:
    """The one Hancom-saved file with tracked changes gives its author id 0 and its changes authorID 1.
    An author added after that took id 1, and with it the file's own changes."""

    target = HwpxDocument.open(str(TRACKED))
    theirs = sorted((change.change_id, change.author) for change in target.tracking.changes)
    source = HwpxDocument.new()
    source.tracking.insert(source.add_paragraph("draft"), "PENDING", author="Alice")
    append_document(target, source)
    now = sorted((change.change_id, change.author) for change in target.tracking.changes)
    assert now[: len(theirs)] == theirs and now[-1][1] == "Alice"
    rejected = target.tracking.reject(author="Alice")
    assert [change.author for change in rejected] == ["Alice"]
    assert sorted((change.change_id, change.author) for change in target.tracking.changes) == theirs


def test_a_change_by_a_new_author_leaves_the_others_with_theirs_across_a_save() -> None:
    document = HwpxDocument.open(str(TRACKED))
    before = sorted((change.change_id, change.author) for change in document.tracking.changes)
    added = document.tracking.insert(0, "X", author="Alice")
    reopened = HwpxDocument.open(document.to_bytes())
    after = {change.change_id: change.author for change in reopened.tracking.changes}
    assert after[added.change_id] == "Alice"
    assert sorted((number, author) for number, author in after.items() if number != added.change_id) == before


def test_changes_carried_in_do_not_change_how_the_receiver_shows_changes() -> None:
    def flags(document: HwpxDocument) -> str | None:
        return next(document.oxml.headers[0].element.iter(f"{HH}trackchageConfig")).get("flags")

    target = HwpxDocument.open(str(SAVED / "formfit_inline_objects.hwpx"))
    before = flags(target)
    append_document(target, HwpxDocument.open(str(TRACKED)))
    assert flags(HwpxDocument.open(target.to_bytes())) == before


def test_a_field_brought_in_two_pieces_keeps_its_end() -> None:
    source = HwpxDocument.open(str(SAVED / "form_fields_spanning_before.hwpx"))
    target = HwpxDocument.new()
    target.add_paragraph("받는 문서")
    section = target.sections[0]
    section.insert_paragraphs(len(section.paragraphs), [paragraph.element for paragraph in source.paragraphs[2:5]])
    section.insert_paragraphs(len(section.paragraphs), [paragraph.element for paragraph in source.paragraphs[5:7]])
    reopened = HwpxDocument.open(target.to_bytes())
    begins, ends = _field_marks(reopened)
    assert begins.count(SPANNING) == ends.count(SPANNING) == 1
    reopened.fields.fill("answer", field_id=SPANNING)


def test_an_ole_item_carried_in_keeps_its_kind() -> None:
    chart = SAVED / "pages_chart_case_narrower_than_its_default.hwpx"
    target = HwpxDocument.open(str(chart))
    append_document(target, HwpxDocument.open(str(chart)))
    target = HwpxDocument.open(target.to_bytes())
    listed = {item.get("id"): item for item in target.package._manifest_items()}
    kinds = [
        (listed[ole.get("binaryItemIDRef")].get("media-type"), listed[ole.get("binaryItemIDRef")].get("isEmbeded"))
        for ole in target.sections[0].element.iter(f"{HP}ole")
    ]
    assert len(kinds) == 2 and len(set(kinds)) == 1 and kinds[0][0] == "application/ole"


def test_a_seeded_reopen_does_not_repeat_a_notes_instance_id() -> None:
    document = HwpxDocument.open(str(SAVED / "table_insert_row_base.hwpx"), seed=7)
    document.paragraphs[0].add_footnote("a")
    document = HwpxDocument.open(document.to_bytes(), seed=7)
    document.paragraphs[0].add_footnote("b")
    instances = [note.get("instId") for note in _section(document).iter(f"{HP}footNote")]
    assert len(instances) == len(set(instances)) == 2


def test_a_tracked_delete_whose_first_place_crosses_markup_is_refused_though_a_later_one_does_not() -> None:
    document = HwpxDocument.open(str(TRACKED))
    document.paragraphs[0].add_run("경 추")
    before = document.to_bytes()
    for call in (lambda: document.tracking.delete(0, match="경 추"), lambda: document.tracking.replace(0, "경 추", "x")):
        with pytest.raises(HwpxValueError) as refused:
            call()
        assert refused.value.code == "track-match-crosses-markup"
        assert document.to_bytes() == before


def test_marks_that_name_no_change_are_refused_before_the_target_changes() -> None:
    source = HwpxDocument.open(str(TRACKED))
    for mark in source.sections[0].element.iter(f"{HP}insertBegin", f"{HP}insertEnd", f"{HP}deleteBegin", f"{HP}deleteEnd"):
        mark.attrib.pop("TcId", None)
    target = HwpxDocument.new()
    before = target.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        append_document(target, source)
    assert refused.value.code == "document-merge-unsupported-reference"
    assert target.to_bytes() == before


def test_a_missing_picture_in_a_memo_body_is_refused_before_the_target_changes() -> None:
    import copy

    source = HwpxDocument.new(empty_first_line=True)
    paragraph = source.add_paragraph("annotated text")
    source.notes.add_memo("old text", paragraph=paragraph)
    field = next(source.sections[0].element.iter(f"{HP}fieldBegin"))
    memo_id = next(param.text for param in field.iter(f"{HP}stringParam") if param.get("name") == "ID")
    group = source.sections[0].element.makeelement(f"{HP}memogroup", {})
    entry = group.makeelement(f"{HP}memo", {"id": memo_id})
    body = entry.makeelement(f"{HP}paraList", {})
    body.append(copy.deepcopy(field.find(f"{HP}subList").find(f"{HP}p")))
    picture = body.find(f".//{HP}run").makeelement(f"{HC}img", {"binaryItemIDRef": "nothing-of-this-name"})
    body.find(f".//{HP}run").append(picture)
    entry.append(body)
    group.append(entry)
    source.sections[0].element.append(group)
    source.sections[0].mark_dirty()

    target = HwpxDocument.new(empty_first_line=True)
    before = target.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        append_document(target, source)
    assert refused.value.code == "document-merge-unsupported-reference"
    assert target.to_bytes() == before


# -- what the third look found: the author rule, a stored name, a split match --------------------


def _with_part(data: bytes, part: str, change, rename: dict[str, str] | None = None) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == part:
                payload = change(payload)
            name = (rename or {}).get(info.filename, info.filename)
            target.writestr(name, payload, zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED)
    return out.getvalue()


def test_a_change_whose_author_is_gone_is_nobodys_not_the_next_authors() -> None:
    import re

    document = HwpxDocument.new()
    for name in "ABC":
        document.tracking.insert(document.add_paragraph("p" + name), "ins" + name, author=name)

    def renumber(header: bytes) -> bytes:
        wanted = {b"A": b"10", b"B": b"2", b"C": b"30"}
        authors = re.findall(rb"<hh:trackChangeAuthor[^>]*/>", header)
        was = {re.search(rb'name="(\w)"', a).group(1): re.search(rb' id="(\d+)"', a).group(1) for a in authors}
        for author in authors:
            name = re.search(rb'name="(\w)"', author).group(1)
            header = header.replace(
                author, b"" if name == b"B" else author.replace(b' id="' + was[name] + b'"', b' id="' + wanted[name] + b'"')
            )
        for name, number in was.items():
            header = header.replace(b'authorID="' + number + b'"', b'authorID="@' + name + b'"')
        for name in was:
            header = header.replace(b'authorID="@' + name + b'"', b'authorID="' + wanted[name] + b'"')
        return header

    reopened = HwpxDocument.open(_with_part(document.to_bytes(), "Contents/header.xml", renumber))
    assert [change.author for change in reopened.tracking.changes] == ["A", "", "C"]
    assert [change.author for change in reopened.tracking.reject(author="C")] == ["C"]
    assert "insB" in reopened.text.plain()


def test_a_new_author_does_not_become_the_author_of_changes_numbered_past_the_only_author() -> None:
    data = _with_part(TRACKED.read_bytes(), "Contents/header.xml", lambda header: header.replace(b'authorID="1"', b'authorID="2"'))
    document = HwpxDocument.open(data)
    assert {change.author for change in document.tracking.changes} == {"fff"}
    added = document.tracking.insert(0, "X", author="Alice")
    assert [change.change_id for change in document.tracking.reject(author="Alice")] == [added.change_id]


@pytest.mark.parametrize("carried", [b"65535", b"65536"])
def test_a_new_authors_id_is_the_next_free_one_not_one_past_the_largest_number_carried(carried: bytes) -> None:
    import re

    document = HwpxDocument.new()
    document.tracking.insert(document.add_paragraph("pa"), "insA", author="A")
    data = _with_part(
        document.to_bytes(), "Contents/header.xml", lambda header: re.sub(rb'authorID="\d+"', b'authorID="' + carried + b'"', header)
    )
    reopened = HwpxDocument.open(data)
    reopened.tracking.insert(0, "insB", author="B")
    ids = sorted(int(author.get("id")) for author in reopened.oxml.headers[0].element.iter(f"{HH}trackChangeAuthor"))
    assert ids[-1] < 100  # before: 65537, which an .hwp file cannot hold
    back = HwpxDocument.open(reopened.to_bytes(format="hwp"))
    assert "B" in [change.author for change in back.tracking.changes]


def test_an_item_carried_in_is_not_stored_over_a_part_the_receiver_has() -> None:
    wide = SAVED / "pages_chart_case_wider_than_its_default.hwpx"
    narrow = SAVED / "pages_chart_case_narrower_than_its_default.hwpx"
    data = _with_part(
        wide.read_bytes(),
        "Contents/content.hpf",
        lambda manifest: manifest.replace(b"BinData/ole1.ole", b"BinData/BIN0001.ole"),
        rename={"BinData/ole1.ole": "BinData/BIN0001.ole"},
    )
    target = HwpxDocument.open(data)
    theirs = hashlib.sha256(target.package.read("BinData/BIN0001.ole")).hexdigest()
    append_document(target, HwpxDocument.open(str(narrow)))
    target = HwpxDocument.open(target.to_bytes())
    assert hashlib.sha256(target.package.read("BinData/BIN0001.ole")).hexdigest() == theirs
    stored = {item.get("id"): item.get("href") for item in target.package._manifest_items()}
    places = [stored[ole.get("binaryItemIDRef")] for ole in target.sections[0].element.iter(f"{HP}ole")]
    assert len(places) == len(set(places)) == 2


def test_a_row_count_written_with_leading_zeros_is_that_number() -> None:
    from hwpx.oxml.table_sizes import declared_count

    assert declared_count("0000002") == 2 and declared_count("65535") == 65535
    with pytest.raises(HwpxValueError):
        declared_count("65536")
    document = HwpxDocument.new()
    document.add_table(2, 3)
    data = _with_part(document.to_bytes(), "Contents/section0.xml", lambda xml: xml.replace(b'rowCnt="2"', b'rowCnt="0000002"'))
    assert b'rowCnt="0000002"' in zipfile.ZipFile(io.BytesIO(data)).read("Contents/section0.xml")
    table = HwpxDocument.open(data).tables[0]
    assert table.row_count == 2 and [len(row) for row in table.cell_map] == [3, 3]


def test_a_tracked_replacement_goes_on_to_the_place_that_holds_the_match_whole() -> None:
    """Split over two text elements of the first run and whole in the second run: the replace writer
    takes the second (as before), the delete writer stops at the first and is refused untouched."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("red ")
    run = paragraph.runs[-1].element
    second = run.makeelement(f"{HP}t", {})
    second.text = "fox"
    run.append(second)
    paragraph.add_run(" red fox later")
    before = document.to_bytes()
    with pytest.raises(HwpxValueError) as refused:
        document.tracking.delete(paragraph, match="red fox")
    assert refused.value.code == "track-match-crosses-markup" and document.to_bytes() == before
    document.tracking.replace(paragraph, "red fox", "X")
    assert len(document.oxml.track_changes) == 2
