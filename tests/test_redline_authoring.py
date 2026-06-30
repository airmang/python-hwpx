from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.oxml.body import TrackChangeMark, parse_paragraph_element, serialize_paragraph


DATE = "2026-06-30T00:00:00Z"


def _p0_before_fixture() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    p0_fixture = (
        repo_root.parent
        / "specs"
        / "005-redline-authoring"
        / "evidence"
        / "p0"
        / "before.hwpx"
    )
    if p0_fixture.exists():
        return p0_fixture
    return repo_root / "tests" / "fixtures" / "hwpxlib_corpus" / "tool__blank.hwpx"


def _zip_payloads(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _zip_payloads_from_bytes(payload: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(payload)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _paragraph_track_marks(document: HwpxDocument) -> list[tuple[str | None, TrackChangeMark, str]]:
    marks: list[tuple[str | None, TrackChangeMark, str]] = []
    paragraph = document.paragraphs[-1]
    for run in paragraph.runs:
        run_model = run.to_model()
        for span in run_model.text_spans:
            for markup in span.marks:
                if isinstance(markup.element, TrackChangeMark):
                    marks.append((run.char_pr_id_ref, markup.element, markup.trailing_text))
    return marks


def test_tracked_insert_delete_replace_roundtrip_links_header_and_body() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("alpha beta gamma", char_pr_id_ref="0")

    insert_id = document.add_tracked_insert(paragraph, " INSERT", date=DATE)
    delete_id = document.add_tracked_delete(paragraph, match="beta", date=DATE)
    replace_delete_id, replace_insert_id = document.add_tracked_replace(
        paragraph,
        "gamma",
        " delta",
        date=DATE,
    )

    reopened = HwpxDocument.open(document.to_bytes())

    assert reopened.track_change(insert_id).change_type == "Insert"
    assert reopened.track_change(delete_id).change_type == "Delete"
    assert reopened.track_change(replace_delete_id).change_type == "Delete"
    assert reopened.track_change(replace_insert_id).change_type == "Insert"
    assert reopened.track_change(insert_id).date == DATE
    assert reopened.track_change(insert_id).author_id == 1

    header_model = reopened.headers[0].to_model()
    assert header_model.ref_list is not None
    assert header_model.ref_list.track_change_authors is not None
    assert len(header_model.ref_list.track_change_authors.authors) == 1
    assert header_model.ref_list.track_change_authors.authors[0].name == "AI Agent"
    assert header_model.track_change_config is not None
    assert header_model.track_change_config.flags is not None
    assert header_model.track_change_config.flags & 1

    marks = _paragraph_track_marks(reopened)
    insert_begins = [
        item
        for item in marks
        if item[1].name == "insertBegin" and item[1].tc_id in {insert_id, replace_insert_id}
    ]
    delete_begins = [
        item
        for item in marks
        if item[1].name == "deleteBegin" and item[1].tc_id in {delete_id, replace_delete_id}
    ]

    assert {(mark.tc_id, text) for _, mark, text in insert_begins} == {
        (insert_id, " INSERT"),
        (replace_insert_id, " delta"),
    }
    assert all(char_pr_id_ref == "0" for char_pr_id_ref, _, _ in insert_begins)
    assert {(mark.tc_id, text) for _, mark, text in delete_begins} == {
        (delete_id, "beta"),
        (replace_delete_id, "gamma"),
    }


def test_tracked_insert_only_rewrites_header_and_edited_section(tmp_path: Path) -> None:
    source = _p0_before_fixture()
    original_payloads = _zip_payloads(source)

    document = HwpxDocument.open(source)
    document.add_tracked_insert(document.paragraphs[0], " BYTE-ID", date=DATE)
    output = tmp_path / "edited.hwpx"
    document.save_to_path(output)

    edited_payloads = _zip_payloads(output)
    assert edited_payloads.keys() == original_payloads.keys()

    allowed = {"Contents/header.xml", "Contents/section0.xml"}
    for name, original in original_payloads.items():
        if name in allowed:
            continue
        assert edited_payloads[name] == original, name


@pytest.mark.xfail(
    reason=(
        "The current paragraph model changes namespace prefixes and boolean "
        "attribute spellings on serialize."
    ),
    strict=False,
)
def test_unedited_paragraph_model_roundtrip_is_byte_stable() -> None:
    section_payload = _zip_payloads(_p0_before_fixture())["Contents/section0.xml"]
    root = etree.fromstring(section_payload)
    paragraph = next(child for child in root if etree.QName(child).localname == "p")

    original = etree.tostring(paragraph, encoding="utf-8")
    serialized = etree.tostring(
        serialize_paragraph(parse_paragraph_element(paragraph)),
        encoding="utf-8",
    )

    assert serialized == original


def test_unedited_document_save_has_no_spurious_part_payload_diffs() -> None:
    source = _p0_before_fixture()
    original_payloads = _zip_payloads(source)

    document = HwpxDocument.open(source)
    saved_payloads = _zip_payloads_from_bytes(document.to_bytes())

    assert saved_payloads == original_payloads
