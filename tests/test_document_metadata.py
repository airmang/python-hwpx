# SPDX-License-Identifier: Apache-2.0
"""Document metadata authoring (cycle 6.12 트레인㊸, 신규 갭 #1):
``Contents/content.hpf``'s ``opf:metadata`` -- title/creator/subject/
keyword/CreatedDate/ModifiedDate read+write.

Real-corpus reverse-engineering (67 fixtures, see
``hwpx.oxml.document_metadata``'s own docstring for the full census) found
this block always shares the same shape, and that ``CreatedDate``/
``ModifiedDate`` are single-format (ISO 8601) while ``date`` (the
human-readable field) is genuinely multi-format across at least 5 distinct
patterns depending on Hancom version/OS locale -- deliberately left
read-only/opaque rather than guessed at.
"""
from __future__ import annotations

import zipfile
import io
from pathlib import Path

from hwpx.document import HwpxDocument

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def test_metadata_read_on_a_fresh_document() -> None:
    document = HwpxDocument.new()

    metadata = document.parts.metadata

    assert metadata is not None
    assert metadata.language == "ko"
    # date/lastsaveby/created_date/modified_date come from the skeleton's
    # own frozen snapshot -- present, but not asserted on exact value here
    # (that's the skeleton's own business, not this feature's contract).
    assert metadata.date is not None
    assert metadata.created_date is not None


def test_set_document_metadata_updates_only_the_given_fields() -> None:
    document = HwpxDocument.new()
    before = document.parts.metadata
    assert before is not None
    original_date = before.date
    original_lastsaveby = before.lastsaveby

    document.parts.set_document_metadata(title="회의록", creator="홍길동")

    after = document.parts.metadata
    assert after is not None
    assert after.title == "회의록"
    assert after.creator == "홍길동"
    # untouched fields stay exactly as they were -- partial update, not a
    # full block replacement.
    assert after.date == original_date
    assert after.lastsaveby == original_lastsaveby
    assert after.subject is None
    assert after.keyword is None


def test_set_document_metadata_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()

    document.parts.set_document_metadata(
        title="정기 회의록",
        creator="홍길동",
        subject="분기 실적 보고",
        keyword="회의록, 분기보고",
        created_date="2026-08-10T00:00:00Z",
        modified_date="2026-08-10T00:05:00Z",
    )
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    metadata = reopened.parts.metadata
    assert metadata is not None
    assert metadata.title == "정기 회의록"
    assert metadata.creator == "홍길동"
    assert metadata.subject == "분기 실적 보고"
    assert metadata.keyword == "회의록, 분기보고"
    assert metadata.created_date == "2026-08-10T00:00:00Z"
    assert metadata.modified_date == "2026-08-10T00:05:00Z"


def test_untouched_document_preserves_content_hpf_byte_identical() -> None:
    """The round-trip-byte-preservation requirement: a document that never
    calls set_document_metadata must not have Contents/content.hpf change
    at all across a save/reopen/save cycle."""

    document = HwpxDocument.new()
    data_first = document.to_bytes()
    with zipfile.ZipFile(io.BytesIO(data_first)) as archive:
        hpf_first = archive.read("Contents/content.hpf")

    reopened = HwpxDocument.open(data_first)
    data_second = reopened.to_bytes()
    with zipfile.ZipFile(io.BytesIO(data_second)) as archive:
        hpf_second = archive.read("Contents/content.hpf")

    assert hpf_first == hpf_second


def test_setting_a_field_does_not_disturb_other_manifest_content() -> None:
    """set_document_metadata mutates the SAME live manifest tree
    add_manifest_item/remove_manifest_item use (opc/package.py's own
    manifest_tree()/_persist_manifest() machinery) -- this proves that
    sharing doesn't corrupt unrelated manifest entries (e.g. section/header
    items) when both get touched in the same session."""

    document = HwpxDocument.new()
    document.add_paragraph("본문")
    document.package.add_manifest_item("extra-part", "Extra/extra.xml", "application/xml")

    document.parts.set_document_metadata(title="제목")

    manifest_el = document.package._manifest_element()
    assert manifest_el is not None
    item_ids = {item.get("id") for item in manifest_el.findall("opf:item", {"opf": "http://www.idpf.org/2007/opf/"})}
    assert "extra-part" in item_ids
    assert document.parts.metadata.title == "제목"


def test_real_corpus_metadata_is_readable_without_error() -> None:
    """Sanity sweep over the real corpus this feature was reverse-engineered
    against -- every fixture must parse without raising, matching the
    census this module's docstring records (67/67 parsed ok)."""

    fixtures = sorted(CORPUS.glob("*.hwpx"))
    assert fixtures, "expected the vendored hwpxlib_corpus fixtures to be present"

    parsed = 0
    for fixture in fixtures:
        document = HwpxDocument.open(str(fixture))
        try:
            metadata = document.parts.metadata
            if metadata is not None:
                parsed += 1
                assert metadata.language in (None, "ko")
        finally:
            document.close()

    assert parsed > 0
