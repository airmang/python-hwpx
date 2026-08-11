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


def _project_tracked_text(document: HwpxDocument, *, accept: bool) -> str:
    """Project the last paragraph as Hancom accept/reject would."""

    output: list[str] = []
    delete_depth = 0
    insert_depth = 0
    for run in document.paragraphs[-1].runs:
        for span in run.to_model().text_spans:
            output.append(span.leading_text)
            for markup in span.marks:
                mark = markup.element
                if isinstance(mark, TrackChangeMark):
                    if mark.change_type == "delete":
                        delete_depth += 1 if mark.is_begin else -1
                    elif mark.change_type == "insert":
                        insert_depth += 1 if mark.is_begin else -1
                visible = delete_depth == 0 if accept else insert_depth == 0
                if visible:
                    output.append(markup.trailing_text)
    return "".join(output)


def test_tracked_insert_delete_replace_roundtrip_links_header_and_body() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("alpha beta gamma", char_pr_id_ref="0")

    # .change_id unwraps the 6.0 TrackedChange/TrackedReplacement objects
    # (design §2.6) right at the call site, so the rest of this test's
    # int-keyed logic is unchanged.
    insert_id = document.add_tracked_insert(paragraph, " INSERT", date=DATE).change_id
    delete_id = document.add_tracked_delete(paragraph, match="beta", date=DATE).change_id
    replacement = document.add_tracked_replace(
        paragraph,
        "gamma",
        " delta",
        date=DATE,
    )
    replace_delete_id, replace_insert_id = replacement.delete.change_id, replacement.insert.change_id

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
    assert " ".join(_project_tracked_text(reopened, accept=True).split()) == (
        "alpha delta INSERT"
    )
    assert " ".join(_project_tracked_text(reopened, accept=False).split()) == (
        "alpha beta gamma"
    )


def test_tracked_replace_keeps_new_text_at_the_deleted_position() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("before old after", char_pr_id_ref="0")

    replacement = document.add_tracked_replace(
        paragraph,
        "old",
        "new",
        date=DATE,
    )
    delete_id, insert_id = replacement.delete.change_id, replacement.insert.change_id
    reopened = HwpxDocument.open(document.to_bytes())
    relevant = [
        (mark.name, text)
        for _, mark, text in _paragraph_track_marks(reopened)
        if mark.tc_id in {delete_id, insert_id}
    ]

    assert relevant == [
        ("deleteBegin", "old"),
        ("deleteEnd", ""),
        ("insertBegin", "new"),
        ("insertEnd", " after"),
    ]
    assert _project_tracked_text(reopened, accept=True) == "before new after"
    assert _project_tracked_text(reopened, accept=False) == "before old after"


def test_tracked_replace_preserves_target_run_style_and_later_insert_order() -> None:
    document = HwpxDocument.new()
    target_style = document.ensure_run_style(bold=True)
    later_style = document.ensure_run_style(italic=True)
    paragraph = document.add_paragraph(
        "before old after",
        char_pr_id_ref=target_style,
    )
    paragraph.add_run(" tail", char_pr_id_ref=later_style)
    prior_insert_id = document.add_tracked_insert(
        paragraph,
        " prior",
        date=DATE,
        char_pr_id_ref=later_style,
    ).change_id

    replacement = document.add_tracked_replace(
        paragraph,
        "old",
        "new",
        date=DATE,
    )
    delete_id, replacement_insert_id = replacement.delete.change_id, replacement.insert.change_id
    reopened = HwpxDocument.open(document.to_bytes())
    reopened_paragraph = reopened.paragraphs[-1]

    assert [run.char_pr_id_ref for run in reopened_paragraph.runs] == [
        target_style,
        later_style,
    ]
    insert_begins = [
        (char_pr_id_ref, mark.tc_id, text)
        for char_pr_id_ref, mark, text in _paragraph_track_marks(reopened)
        if mark.name == "insertBegin"
    ]
    assert insert_begins == [
        (target_style, replacement_insert_id, "new"),
        (later_style, prior_insert_id, " prior"),
    ]
    assert {
        mark.tc_id
        for _, mark, _ in _paragraph_track_marks(reopened)
        if mark.name == "deleteBegin"
    } == {delete_id}
    assert _project_tracked_text(reopened, accept=True) == (
        "before new after tail prior"
    )
    assert _project_tracked_text(reopened, accept=False) == (
        "before old after tail"
    )


def test_tracked_replace_preflights_cross_inline_match_without_orphan_headers() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("before ", char_pr_id_ref="0")
    insert_id = document.add_tracked_insert(paragraph, "middle", date=DATE).change_id
    existing_change_ids = set(document.track_changes)

    with pytest.raises(
        ValueError,
        match="match crosses inline markup and cannot be wrapped safely",
    ):
        document.add_tracked_replace(
            paragraph,
            "before middle",
            "replacement",
            date=DATE,
        )

    assert set(document.track_changes) == existing_change_ids == {str(insert_id)}


_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _attach_line_layout_cache(paragraph) -> None:
    """Simulate a Hancom-saved paragraph: attach a cached ``<hp:linesegarray>``."""

    element = paragraph.element
    array = element.makeelement(f"{{{_HP_NS}}}linesegarray", {})
    seg = element.makeelement(
        f"{{{_HP_NS}}}lineseg",
        {"textpos": "0", "vertpos": "1000", "textheight": "1000"},
    )
    array.append(seg)
    element.append(array)


def _line_layout_cache_count(paragraph) -> int:
    return sum(
        1
        for child in paragraph.element
        if etree.QName(child).localname.lower() == "linesegarray"
    )


def test_tracked_edits_clear_stale_line_layout_cache() -> None:
    """줄겹침 회귀: 변경추적 편집은 편집 문단의 lineseg 캐시를 제거해야 한다.

    실한컴은 문단의 linesegarray를 그대로 신뢰해 줄배치를 재사용하므로,
    변경추적으로 텍스트가 자란 문단에 옛 캐시가 남으면 글자가 겹쳐 렌더된다.
    트랙마크가 있는 문단은 저장 시 stale 판정이 불가능해(byte-boundary sweep
    통과) 편집 시점에 반드시 지워야 한다.
    """

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("alpha beta gamma", char_pr_id_ref="0")

    _attach_line_layout_cache(paragraph)
    document.tracking.insert(paragraph, " INSERT", date=DATE)
    assert _line_layout_cache_count(paragraph) == 0

    _attach_line_layout_cache(paragraph)
    document.tracking.delete(paragraph, match="beta", date=DATE)
    assert _line_layout_cache_count(paragraph) == 0

    _attach_line_layout_cache(paragraph)
    document.tracking.replace(paragraph, "gamma", "delta", date=DATE)
    assert _line_layout_cache_count(paragraph) == 0


def test_tracked_insert_cache_stays_cleared_at_byte_boundary() -> None:
    """저장 스윕은 트랙마크 문단을 판정 못 하므로 편집 시점 제거가 바이트에 남아야 한다."""

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("alpha beta gamma", char_pr_id_ref="0")
    _attach_line_layout_cache(paragraph)
    document.tracking.insert(paragraph, " 추가된 내용", date=DATE)

    reopened = HwpxDocument.open(document.to_bytes())
    edited = next(p for p in reopened.paragraphs if "alpha" in (p.text or ""))
    assert _line_layout_cache_count(edited) == 0


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
