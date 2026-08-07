# SPDX-License-Identifier: Apache-2.0
"""Document insertion/merge (cycle 6.9 train 33) -- id-remap correctness.

See ``docs/2026-08-08-document-merge-contract.md`` for the id-reference
catalog this module was designed against. Referential integrity is checked
via the existing ``hwpx.tools.id_integrity.check_id_integrity`` (not a
document-merge-local reimplementation -- see the contract doc's gate #1 note
for why an earlier local version was discarded in favor of it).
"""

from __future__ import annotations

import base64

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.document_merge import append_document, insert_document
from hwpx.tools.id_integrity import check_id_integrity

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

# A minimal valid 1x1 PNG (same fixture bytes as test_image_object_workflow.py).
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)


def _texts(doc: HwpxDocument) -> list[str]:
    return [p.text for p in doc.sections[0].paragraphs]


def _inject_attr(paragraph_element, attr: str, value: str) -> None:
    paragraph_element.set(attr, value)


# ============================================================================
# basic append / insert
# ============================================================================


def test_append_document_adds_source_paragraphs_at_section_end() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("first")
    source.add_paragraph("second")

    target = HwpxDocument.new()
    target.add_paragraph("existing")

    report = append_document(target, source)

    assert report["position"] == "end"
    texts = _texts(target)
    assert texts[-2:] == ["first", "second"]
    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_insert_document_places_content_after_given_paragraph() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("inserted")

    target = HwpxDocument.new()
    target.add_paragraph("para 0")
    target.add_paragraph("para 1")

    report = insert_document(target, source, after_paragraph_index=1)

    assert report["position"] == "after_paragraph"
    # target starts as [default empty, "para 0", "para 1"] (HwpxDocument.new()
    # always seeds one empty paragraph); after_paragraph_index=1 is "para 0",
    # so source's own [default empty, "inserted"] lands between it and "para 1".
    assert _texts(target) == ["", "para 0", "", "inserted", "para 1"]
    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_insert_document_out_of_range_index_is_a_typed_error() -> None:
    source = HwpxDocument.new()
    target = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        insert_document(target, source, after_paragraph_index=99)
    assert excinfo.value.code == "document-merge-index-out-of-range"


def test_append_document_accepts_a_path_and_closes_it_itself(tmp_path) -> None:
    source = HwpxDocument.new()
    source.add_paragraph("from disk")
    path = tmp_path / "source.hwpx"
    source.save_to_path(path)

    target = HwpxDocument.new()
    append_document(target, path)
    assert "from disk" in _texts(target)


def test_append_document_does_not_close_an_already_open_source() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("still usable after merge")

    target = HwpxDocument.new()
    append_document(target, source)

    # If append_document had closed *source* (opened_here misdetected),
    # this would raise -- proving caller-owned lifecycle is respected.
    assert source.sections[0].paragraphs[-1].text == "still usable after merge"


# ============================================================================
# hp:secPr stripping (section-setup run never carried into a mid-section
# position -- see the function's own docstring in document_merge.py)
# ============================================================================


def test_insert_before_first_paragraph_preserves_targets_own_section_properties() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("top")

    target = HwpxDocument.new()
    target.add_paragraph("existing")
    target_first_id = target.sections[0].paragraphs[0].element.get("id")

    report = insert_document(target, source, after_paragraph_index=-1)

    assert report["sectionPropertiesStripped"] == 1
    section = target.sections[0]
    secpr_bearing = [
        p for p in section.paragraphs if p.element.find(f"{_HP}run/{_HP}secPr") is not None
    ]
    assert len(secpr_bearing) == 1
    assert secpr_bearing[0].element.get("id") == target_first_id


def test_append_document_strips_a_second_documents_section_setup_run() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("body")

    target = HwpxDocument.new()
    target.add_paragraph("existing")

    report = append_document(target, source)

    assert report["sectionPropertiesStripped"] == 1
    section = target.sections[0]
    secpr_count = sum(
        1 for p in section.paragraphs if p.element.find(f"{_HP}run/{_HP}secPr") is not None
    )
    assert secpr_count == 1


# ============================================================================
# id-collision non-aliasing -- the highest-frequency reference spaces per the
# contract's own catalog (charPr 51 hits, paraPr 19, style 16)
# ============================================================================


def test_merge_copies_a_custom_styles_own_base_charpr_and_parapr() -> None:
    """Adversarial case that found a real bug: a style's own base charPr/
    paraPr (not directly referenced by any body paragraph, only inherited
    via styleIDRef) must still be remapped -- the default skeleton's every
    style happens to point at charPr "0" (the same id a plain paragraph's
    run defaults to), which coincidentally masks this unless the style's
    base is genuinely custom.
    """

    source = HwpxDocument.new()
    style_cid = source.styles.ensure_run(bold=True)
    style_pids = source.styles.ensure_numbering(kind="number")
    sid = source.parts.headers[0].ensure_style(
        "Body Custom", para_pr_id_ref=style_pids[0], char_pr_id_ref=style_cid
    )
    source.add_paragraph("via style only", style_id_ref=sid)

    target = HwpxDocument.new()
    # pre-populate target's own spaces so a naive remap could plausibly
    # alias onto them if it silently skipped the style's own base ids.
    target.styles.ensure_run(italic=True)
    target.styles.ensure_numbering(kind="number")

    report = append_document(target, source)

    assert report["remapped"]["charPr"] >= 2  # default run + style's own base
    assert report["remapped"]["paraPr"] >= 2
    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_merge_never_aliases_onto_targets_preexisting_char_and_para_ids() -> None:
    source = HwpxDocument.new()
    cid = source.styles.ensure_run(bold=True, color="#FF0000")
    source.add_paragraph("red bold", char_pr_id_ref=cid)

    target = HwpxDocument.new()
    for i in range(4):
        target.styles.ensure_run(italic=True, size=9 + i)

    before_ids = {c.get("id") for c in target.parts.headers[0]._char_properties_element()}

    report = append_document(target, source)
    assert report["remapped"]["charPr"] >= 1

    header = target.parts.headers[0]
    char_props = header._char_properties_element()
    new_ids = {c.get("id") for c in char_props} - before_ids
    assert new_ids, "expected at least one freshly-allocated charPr id"
    for new_id in new_ids:
        item = char_props.find(f"{_HH}charPr[@id='{new_id}']")
        assert item is not None

    after = check_id_integrity(target)
    assert after.ok, after.dangling


# ============================================================================
# heading (numbering/bullet's polymorphic idRef, lives inside paraPr)
# ============================================================================


def test_merge_remaps_heading_numbering_reference() -> None:
    source = HwpxDocument.new()
    para_pr_ids = source.styles.ensure_numbering(kind="number")
    source.add_paragraph("1. numbered item", para_pr_id_ref=para_pr_ids[0])

    target = HwpxDocument.new()
    # populate target's own numbering space first to force a real remap,
    # not a coincidental id match.
    target.styles.ensure_numbering(kind="number")

    report = append_document(target, source)
    assert report["remapped"]["numbering"] == 1

    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_merge_remaps_bullet_heading_reference() -> None:
    source = HwpxDocument.new()
    para_pr_ids = source.styles.ensure_numbering(kind="bullet")
    source.add_paragraph("• bulleted item", para_pr_id_ref=para_pr_ids[0])

    target = HwpxDocument.new()

    report = append_document(target, source)
    assert report["remapped"]["bullet"] == 1

    after = check_id_integrity(target)
    assert after.ok, after.dangling


# ============================================================================
# fonts (hh:fontRef's 7 lang-scoped, independently-numbered id-spaces)
# ============================================================================


def test_merge_remaps_font_reference_without_aliasing_onto_targets_own_font() -> None:
    source = HwpxDocument.new()
    source.styles.ensure_font("맑은 고딕", lang="HANGUL")
    cid = source.styles.ensure_run(font="맑은 고딕")
    source.add_paragraph("font test", char_pr_id_ref=cid)

    target = HwpxDocument.new()
    # pre-populate target's HANGUL fontface block so the merged font's id
    # cannot coincidentally reuse a value that already means something else.
    target.styles.ensure_font("바탕", lang="HANGUL")
    target.styles.ensure_font("굴림", lang="HANGUL")

    report = append_document(target, source)
    assert report["remapped"]["font"] > 0

    header = target.parts.headers[0]
    char_props = header._char_properties_element()
    merged_run = target.sections[0].paragraphs[-1].element.find(f"{_HP}run")
    new_char_id = merged_run.get("charPrIDRef")
    char_pr = char_props.find(f"{_HH}charPr[@id='{new_char_id}']")
    font_ref = char_pr.find(f"{_HH}fontRef")
    new_font_id = font_ref.get("hangul")

    fontfaces = header._fontfaces_element()
    hangul_face = header._fontface_element(fontfaces, "HANGUL", create=False)
    matching = [f for f in hangul_face.findall(f"{_HH}font") if f.get("id") == new_font_id]
    assert len(matching) == 1
    assert matching[0].get("face") == "맑은 고딕"

    after = check_id_integrity(target)
    assert after.ok, after.dangling


# ============================================================================
# binary items (binaryItemIDRef keys off BinData filename stem, not @id)
# ============================================================================


def test_merge_copies_binary_image_bytes_and_remaps_binary_item_id_ref() -> None:
    source = HwpxDocument.new()
    source.add_picture(PNG_1X1, "png")

    target = HwpxDocument.new()
    report = append_document(target, source)
    assert report["remapped"]["binaryItem"] == 1

    header = target.parts.headers[0]
    bin_items = header._bin_data_list_element().findall(f"{_HH}binItem")
    assert len(bin_items) == 1
    bin_name = bin_items[0].get("BinData")
    assert target.package.read(f"BinData/{bin_name}") == PNG_1X1

    after = check_id_integrity(target)
    assert after.ok, after.dangling
    assert not after.orphan_bin_data


# ============================================================================
# fail-closed rejections (v1's explicit "보류" scope)
# ============================================================================


def test_merge_rejects_connect_line_content() -> None:
    source = HwpxDocument.new()
    p = source.add_paragraph("has a smart connector")
    run = p.element.find(f"{_HP}run")
    run.append(run.makeelement(f"{_HP}connectLine", {"subjectIDRef": "123"}))

    target = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        append_document(target, source)
    assert excinfo.value.code == "document-merge-unsupported-reference"
    assert excinfo.value.context.get("tag") == "connectLine"


def test_merge_rejects_link_list_reference() -> None:
    source = HwpxDocument.new()
    p = source.add_paragraph("linked textbox")
    _inject_attr(p.element, "linkListIDRef", "1")

    target = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        append_document(target, source)
    assert excinfo.value.code == "document-merge-unsupported-reference"
    assert excinfo.value.context.get("attribute") == "linkListIDRef"


def test_merge_rejects_chart_id_ref() -> None:
    source = HwpxDocument.new()
    p = source.add_paragraph("chart placeholder")
    _inject_attr(p.element, "chartIDRef", "1")

    target = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        append_document(target, source)
    assert excinfo.value.code == "document-merge-unsupported-reference"


def test_merge_rejects_documents_containing_memos() -> None:
    source = HwpxDocument.new()
    p = source.add_paragraph("annotated text")
    source.notes.add_memo("a comment", anchor=p)

    target = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        append_document(target, source)
    assert excinfo.value.code == "document-merge-unsupported-reference"
    assert excinfo.value.context.get("fieldType") == "MEMO"


def test_merge_still_rejects_memo_when_source_section_index_narrows_scope() -> None:
    """The reject-scan runs on whatever content is actually being copied --
    confirms a memo in an *excluded* section does not block the merge
    (narrowing scope is a real way to route around unsupported content, not
    a bypass of the check on content that *is* copied)."""

    source = HwpxDocument.new()
    p0 = source.sections[0].paragraphs[0]
    source.notes.add_memo("in section 0", anchor=p0)
    source.add_paragraph("plain text, still section 0")

    target = HwpxDocument.new()
    with pytest.raises(HwpxValueError):
        append_document(target, source, source_section_index=0)


# ============================================================================
# nested style references (nextStyleIDRef / charStyleIDRef)
# ============================================================================


def test_merge_remaps_styles_next_style_reference_when_both_styles_are_copied() -> None:
    source = HwpxDocument.new()
    header = source.parts.headers[0]
    first_cid = source.styles.ensure_run(bold=True)
    second_cid = source.styles.ensure_run(italic=True)
    second_sid = header.ensure_style("Second", char_pr_id_ref=second_cid)
    first_sid = header.ensure_style(
        "First", char_pr_id_ref=first_cid, next_style_id_ref=second_sid
    )
    source.add_paragraph("first para", style_id_ref=first_sid)
    source.add_paragraph("second para", style_id_ref=second_sid)

    target = HwpxDocument.new()
    report = append_document(target, source)
    assert report["remapped"]["style"] >= 2

    after = check_id_integrity(target)
    assert after.ok, after.dangling


# ============================================================================
# round-trip preservation (contract gate #2) + byte-level: untouched target
# content is unaffected (contract gate #3, structural variant)
# ============================================================================


def test_merge_result_round_trips_through_save_and_reopen() -> None:
    source = HwpxDocument.new()
    source.styles.ensure_font("맑은 고딕", lang="HANGUL")
    cid = source.styles.ensure_run(font="맑은 고딕", bold=True)
    source.add_paragraph("roundtrip para 1", char_pr_id_ref=cid)
    source.add_paragraph("roundtrip para 2", char_pr_id_ref=cid)
    source.add_picture(PNG_1X1, "png")

    target = HwpxDocument.new()
    target.add_paragraph("existing target para")

    insert_document(target, source, after_paragraph_index=0)

    data = target.to_bytes()
    reopened = HwpxDocument.open(data)
    texts = _texts(reopened)
    assert "roundtrip para 1" in texts
    assert "roundtrip para 2" in texts
    assert "existing target para" in texts

    after = check_id_integrity(reopened)
    assert after.ok, after.dangling


def test_untouched_target_paragraphs_are_structurally_unaffected_by_merge() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("incoming")

    target = HwpxDocument.new()
    target.add_paragraph("untouched paragraph one")
    target.add_paragraph("untouched paragraph two")
    untouched_ids_before = [
        p.element.get("id") for p in target.sections[0].paragraphs
    ]
    untouched_text_before = _texts(target)

    append_document(target, source)

    # the original (pre-merge) paragraphs are still present, in order, with
    # their own ids unchanged -- the merge only ever appends, never mutates
    # target's existing elements.
    remaining = target.sections[0].paragraphs[: len(untouched_ids_before)]
    assert [p.element.get("id") for p in remaining] == untouched_ids_before
    assert [p.text for p in remaining] == untouched_text_before


# ============================================================================
# referential integrity gate (contract gate #1) -- sanity on a clean baseline
# ============================================================================


def test_fresh_document_passes_the_referential_integrity_gate() -> None:
    doc = HwpxDocument.new()
    report = check_id_integrity(doc)
    assert report.ok, report.dangling
