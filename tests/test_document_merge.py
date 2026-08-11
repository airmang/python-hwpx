# SPDX-License-Identifier: Apache-2.0
"""Document insertion/merge (cycle 6.9 train 33, v2 cycle 6.10 train 38) --
id-remap correctness, MEMO merge support, and merge-policy axis validation.

See ``docs/2026-08-08-document-merge-contract.md`` for the id-reference
catalog this module was designed against. Referential integrity is checked
via the existing ``hwpx.tools.id_integrity.check_id_integrity`` (not a
document-merge-local reimplementation -- see the contract doc's gate #1 note
for why an earlier local version was discarded in favor of it).
"""

from __future__ import annotations

import base64
from pathlib import Path

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


def test_merge_allocates_new_ids_in_a_deterministic_order() -> None:
    """Regression: found live while building the v13 openrate generator
    (cycle 6.9 cleanup train) -- every remap function iterated
    ``_used_ids()``'s return value (a plain ``set[str]``) directly when
    calling a sequential ("max existing + 1") allocator. Set iteration
    order for string keys depends on hash randomization, which is fixed
    per-process but varies *across* separate process runs -- so the same
    merge, re-run in a fresh process, could assign a *different* new id to
    the *same* old id, producing byte-different (though still internally
    self-consistent and referentially sound) output. Confirmed concretely:
    the v13 generator's own determinism check (comparing sha256 across two
    independent runs) failed on 8/10 authored-docmerge records before this
    fix, 0/10 after. Fix: iterate ``sorted(used)`` everywhere an allocator
    is called. This test locks in the *mechanism* directly (ascending
    lexicographic old-id order -> ascending new-id order) rather than
    relying on hash-seed luck to reproduce the original symptom."""

    source = HwpxDocument.new()
    old_ids: list[str] = []
    for i in range(6):
        # each size is distinct so ensure_run's own dedup never reuses an
        # id -- six new entries, on top of whatever the skeleton already
        # has, necessarily crosses a single-digit -> double-digit id
        # boundary, where lexicographic order diverges from numeric order
        # ("10" < "9" as strings, 9 < 10 as numbers) regardless of exactly
        # where the skeleton's own count happens to start.
        old_ids.append(source.styles.ensure_run(bold=True, size=8 + i))
    assert len({int(value) for value in old_ids}) == len(old_ids), old_ids  # all distinct
    assert len({len(value) for value in old_ids}) > 1, (
        f"old ids {old_ids} do not span a digit-length boundary -- this "
        "test needs lexicographic and numeric order to actually diverge"
    )

    for old_id in old_ids:
        source.add_paragraph(f"uses {old_id}", char_pr_id_ref=old_id)

    target = HwpxDocument.new()
    report = append_document(target, source)
    # >= not == -- source's own default (empty) first paragraph carries its
    # own charPrIDRef="0", also remapped, but it is not one of old_ids and
    # sits before them in merge order (see the tail slice below).
    assert report["remapped"]["charPr"] >= len(old_ids)

    merged_paragraphs = target.sections[0].paragraphs[-len(old_ids):]
    new_id_for: dict[str, int] = {}
    for p, old_id in zip(merged_paragraphs, old_ids, strict=True):
        run = p.element.find(f"{_HP}run")
        new_id_for[old_id] = int(run.get("charPrIDRef"))

    # sorted(used) processes old ids in ascending *lexicographic* order --
    # that order must land on ascending new-id order (the allocator is a
    # plain "max existing + 1" sequence, called in that order).
    lexicographic_order = sorted(old_ids)
    new_ids_in_lexicographic_order = [new_id_for[old] for old in lexicographic_order]
    assert new_ids_in_lexicographic_order == sorted(new_ids_in_lexicographic_order), new_id_for

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
# linkListIDRef/linkListNextIDRef sentinel passthrough (team-lead's
# independent-verification finding: these are 5,891/5,891 == "0" in the
# vendored corpus -- a boilerplate default every hp:subList carries,
# including our own add_table's own output -- never a real linked-textbox
# chain. Rejecting on mere presence made every table-bearing document
# unmergeable, including documents this library's own add_table produces.)
# ============================================================================


def test_merge_accepts_a_document_containing_a_table_from_add_table() -> None:
    source = HwpxDocument.new()
    source.add_table(rows=2, cols=2)

    target = HwpxDocument.new()
    report = append_document(target, source)  # must not raise

    section = target.sections[0]
    tables = section.element.findall(f".//{_HP}tbl")
    assert len(tables) == 1

    after = check_id_integrity(target)
    assert after.ok, after.dangling

    # the save-path dirty-tracking bug (found while fixing this) would let
    # this pass in-memory but corrupt the saved file -- always check via a
    # real round-trip here, not just the in-memory object.
    data = target.to_bytes()
    reopened = HwpxDocument.open(data)
    reopened_tables = reopened.sections[0].element.findall(f".//{_HP}tbl")
    assert len(reopened_tables) == 1
    after_rt = check_id_integrity(reopened)
    assert after_rt.ok, after_rt.dangling
    assert report["remapped"]["borderFill"] >= 1


def test_merge_accepts_a_real_corpus_document_containing_a_table() -> None:
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "hwpxlib_corpus"
        / "reader_writer__SimpleTable.hwpx"
    )
    source = HwpxDocument.open(fixture)
    # sanity: this fixture is the real evidence the linkListIDRef sentinel
    # claim is built on -- confirm it actually carries the "0" boilerplate
    # before relying on it to exercise the fix.
    sub_lists = source.sections[0].element.findall(f".//{_HP}subList")
    assert sub_lists, "fixture has no hp:subList -- not exercising the fix"
    assert all(sl.get("linkListIDRef") == "0" for sl in sub_lists)

    target = HwpxDocument.new()
    append_document(target, source)  # must not raise
    source.close()

    after = check_id_integrity(target)
    assert after.ok, after.dangling
    data = target.to_bytes()
    reopened = HwpxDocument.open(data)
    after_rt = check_id_integrity(reopened)
    assert after_rt.ok, after_rt.dangling
    assert reopened.sections[0].element.findall(f".//{_HP}tbl")


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


def _memo_field_string_param(paragraph_element, name: str) -> str | None:
    for node in paragraph_element.iter():
        if node.tag == f"{_HP}fieldBegin" and node.get("type") == "MEMO":
            params = node.find(f"{_HP}parameters")
            if params is None:
                continue
            for string_param in params.findall(f"{_HP}stringParam"):
                if string_param.get("name") == name:
                    return string_param.text
    return None


def _memogroup_memo_ids(doc: HwpxDocument, section_index: int = 0) -> list[str]:
    section = doc.sections[section_index]
    ids: list[str] = []
    for memogroup in section.element.findall(f"{_HP}memogroup"):
        for memo in memogroup.findall(f"{_HP}memo"):
            ids.append(memo.get("id"))
    return ids


# ============================================================================
# MEMO merge (hp:memogroup content, section-level sibling per DEV-042) --
# "결함-부활": these were fail-closed rejection tests (v1's explicit 보류
# scope) until train 38/cycle 6.10 added real memo support; they are now
# converted to positive support tests rather than deleted, per the same
# defect-resurrection discipline this module's other bug fixes followed.
# ============================================================================


def test_merge_copies_referenced_memo_content() -> None:
    source = HwpxDocument.new()
    shape_id = source.styles.ensure_memo_shape(fill_color="#F0FFE9")
    p = source.add_paragraph("annotated text")
    source.notes.add_memo("a comment", anchor=p, memo_shape_id_ref=shape_id)

    # target already owns a memo shape at the SAME id (both allocators
    # start at "1" on a fresh document) -- an adversarial, not
    # coincidentally-matching setup, so a coincidental id match can't mask
    # a remap that silently never ran (see this codebase's own
    # _extra_ids_from_style_bases precedent for why coincidental defaults
    # are treated as untrustworthy test setups).
    target = HwpxDocument.new()
    target.styles.ensure_memo_shape(fill_color="#FFFFFF")
    assert shape_id == "1"

    report = append_document(target, source)
    assert report["memosCopied"] == 1

    merged = target.sections[0].paragraphs[-1]
    field_id = _memo_field_string_param(merged.element, "ID")
    field_shape_ref = _memo_field_string_param(merged.element, "MemoShapeIDRef")
    assert field_id is not None

    memo_ids = _memogroup_memo_ids(target)
    assert memo_ids == [field_id]

    memo_element = next(
        m
        for mg in target.sections[0].element.findall(f"{_HP}memogroup")
        for m in mg.findall(f"{_HP}memo")
    )
    assert memo_element.get("id") == field_id
    assert memo_element.get("memoShapeIDRef") == field_shape_ref
    # A remapped memoShapeIDRef must differ from the source's raw id -- an
    # unchanged value here would mean the remap silently no-op'd (a
    # dangling/aliased reference), not a genuine "no override" sentinel.
    assert field_shape_ref != shape_id
    memo_text = "".join(t.text or "" for t in memo_element.iter(f"{_HP}t"))
    assert "a comment" in memo_text

    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_merge_memo_default_shape_ref_stays_the_65535_sentinel() -> None:
    """No memo_shape_id_ref passed -- Hancom's own "no shape override"
    sentinel ("65535") on both the field's own stringParam and (its
    absence on) hp:memo's own attribute, unchanged by the merge."""

    source = HwpxDocument.new()
    p = source.add_paragraph("plain comment")
    source.notes.add_memo("no shape override", anchor=p)

    target = HwpxDocument.new()
    append_document(target, source)

    merged = target.sections[0].paragraphs[-1]
    assert _memo_field_string_param(merged.element, "MemoShapeIDRef") == "65535"
    memo_element = next(
        m
        for mg in target.sections[0].element.findall(f"{_HP}memogroup")
        for m in mg.findall(f"{_HP}memo")
    )
    assert memo_element.get("memoShapeIDRef") is None

    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_merge_with_narrowed_source_section_still_copies_referenced_memo() -> None:
    """Narrowing source_section_index to the very section the memo's field
    lives in must still resolve and copy the memo -- narrowing the scan
    scope must never accidentally also narrow away content that *is*
    being copied."""

    source = HwpxDocument.new()
    p0 = source.sections[0].paragraphs[0]
    source.notes.add_memo("in section 0", anchor=p0)
    source.add_paragraph("plain text, still section 0")

    target = HwpxDocument.new()
    report = append_document(target, source, source_section_index=0)
    assert report["memosCopied"] == 1
    assert len(_memogroup_memo_ids(target)) == 1


def test_merge_excludes_memo_anchored_in_a_source_section_not_being_copied() -> None:
    """A memo anchored in a source section that source_section_index
    excludes must not be copied -- _find_memo_field_ids only sees the
    fieldBegin controls actually present in the paragraphs being copied,
    so a memo nobody references in-scope is correctly left behind.

    Section 1 is added *before* the memo is anchored, though it no longer
    strictly needs to be: anchoring a memo onto a section's very first
    paragraph used to break add_section() entirely (a real, separate
    fragility in add_section() unrelated to document_merge, routed around
    here rather than fixed when this test was written, out of that
    train's scope). Fixed in cycle 6.11 train 44 --
    tests/test_paragraph_section_management.py::TestSectionManagement::
    test_add_section_succeeds_when_first_paragraph_has_an_anchored_memo
    is the dedicated regression test; this test's own ordering is kept as
    written since reordering it isn't this test's job."""

    source = HwpxDocument.new()
    source.add_section()
    p0 = source.sections[0].paragraphs[0]
    source.notes.add_memo("only in section 0", anchor=p0)
    source.sections[1].add_paragraph("section 1, no memo reference")

    target = HwpxDocument.new()
    report = append_document(target, source, source_section_index=1)
    assert report["memosCopied"] == 0
    assert _memogroup_memo_ids(target) == []

    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_merge_appends_into_an_existing_target_memogroup_not_a_duplicate() -> None:
    """Target already has its own memo (its own memogroup) -- merging a
    second, source-provided memo must land in the SAME memogroup, not a
    second sibling one."""

    target = HwpxDocument.new()
    target_p = target.add_paragraph("target's own annotated text")
    target.notes.add_memo("target's own comment", anchor=target_p)
    assert len(target.sections[0].element.findall(f"{_HP}memogroup")) == 1

    source = HwpxDocument.new()
    source_p = source.add_paragraph("source's annotated text")
    source.notes.add_memo("source's comment", anchor=source_p)

    report = append_document(target, source)
    assert report["memosCopied"] == 1
    assert len(target.sections[0].element.findall(f"{_HP}memogroup")) == 1
    assert len(_memogroup_memo_ids(target)) == 2

    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_merge_memo_survives_real_save_and_reopen() -> None:
    """Save-path dirty-tracking regression for memogroup mutation -- the
    same failure shape train 33's header fix caught (in-memory checks pass
    cleanly but the saved bytes silently omit the mutation because nothing
    marked the owning part dirty). Appending hp:memo directly into
    hp:memogroup mutates the SECTION's element tree, not the header's --
    this needs target_section.mark_dirty(), a fully independent code path
    from the header fix, so it gets its own dedicated round-trip test
    rather than relying on other tests' incidental save/reopen coverage."""

    source = HwpxDocument.new()
    shape_id = source.styles.ensure_memo_shape(fill_color="#FFE9CC")
    p = source.add_paragraph("annotated text")
    source.notes.add_memo("survives a real save", anchor=p, memo_shape_id_ref=shape_id)

    target = HwpxDocument.new()
    append_document(target, source)

    data = target.to_bytes()
    reopened = HwpxDocument.open(data)

    memo_ids = _memogroup_memo_ids(reopened)
    assert len(memo_ids) == 1
    merged = reopened.sections[0].paragraphs[-1]
    assert _memo_field_string_param(merged.element, "ID") == memo_ids[0]
    memo_element = next(
        m
        for mg in reopened.sections[0].element.findall(f"{_HP}memogroup")
        for m in mg.findall(f"{_HP}memo")
    )
    memo_text = "".join(t.text or "" for t in memo_element.iter(f"{_HP}t"))
    assert "survives a real save" in memo_text

    after = check_id_integrity(reopened)
    assert after.ok, after.dangling


def test_merge_refreshes_field_end_fieldid_to_match_its_paired_field_begin() -> None:
    """Found via the v14 openrate generator's own cross-run determinism
    check (not assumed in advance): hp:fieldBegin and hp:fieldEnd both get
    their fieldid attribute set to the SAME field_value at creation
    (attach_memo_field, _document/memos.py:136,181). The merge refresh
    always regenerates fieldBegin's own id/fieldid, and fieldEnd's
    beginIDRef follows fieldBegin's new id -- but fieldEnd's OWN fieldid
    was left completely untouched, keeping the SOURCE document's raw
    uuid4().hex value on copied content. That value comes from
    uuid.uuid4() directly (memos.py's own creation call), not through
    _document_primitives' patchable uuid4 binding -- so it isn't just
    non-deterministic across generator runs, it's a genuinely stale,
    unrefreshed value on copied content: this module's own "silent
    corruption" failure shape, on an attribute nothing currently gates on
    (check_id_integrity doesn't track fieldid at all -- this needs a
    dedicated assertion, not a byproduct of the referential-integrity
    gate)."""

    source = HwpxDocument.new()
    p = source.add_paragraph("annotated text")
    source.notes.add_memo("field pairing test", anchor=p)

    target = HwpxDocument.new()
    append_document(target, source)

    merged = target.sections[0].paragraphs[-1]
    field_begin = next(
        node for node in merged.element.iter() if node.tag == f"{_HP}fieldBegin"
    )
    field_end = next(
        node for node in merged.element.iter() if node.tag == f"{_HP}fieldEnd"
    )
    assert field_end.get("beginIDRef") == field_begin.get("id")
    assert field_end.get("fieldid") == field_begin.get("fieldid")
    # Neither should retain the source document's original 32-hex-char
    # uuid4().hex value (attach_memo_field's own format) -- both fieldBegin
    # and fieldEnd's fieldid must be the merge's own freshly-allocated
    # value, not a leftover.
    assert len(field_begin.get("fieldid")) != 32
    assert len(field_end.get("fieldid")) != 32


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


def test_merge_round_trips_when_no_picture_is_involved() -> None:
    """Regression for a real bug found while fixing the linkListIDRef
    over-rejection: every remap function mutates target's header element
    tree directly, but none of them called target_header.mark_dirty() --
    the save path only re-serializes a header from its live tree when
    header.dirty is True, otherwise it silently reuses the part's
    original/cached bytes. A merge that adds new charPr/paraPr/style items
    passed check_id_integrity cleanly *in memory* but produced a
    genuinely corrupted file (the newly-added header items never actually
    written) -- invisible until the file was reopened and checked fresh.
    This slipped past the original test suite because the one test that
    did check a real round-trip
    (test_merge_result_round_trips_through_save_and_reopen) also happened
    to copy a picture, and add_image's own mark_dirty() call masked the
    bug as a side effect. This test deliberately excludes any picture."""

    source = HwpxDocument.new()
    source.styles.ensure_font("맑은 고딕", lang="HANGUL")
    cid = source.styles.ensure_run(font="맑은 고딕", bold=True)
    source.add_paragraph("no picture here", char_pr_id_ref=cid)

    target = HwpxDocument.new()
    target.add_paragraph("existing target para")

    insert_document(target, source, after_paragraph_index=0)

    header = target.parts.headers[0]
    assert header.dirty, "target_header.mark_dirty() was not called"

    data = target.to_bytes()
    reopened = HwpxDocument.open(data)
    assert "no picture here" in _texts(reopened)

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


# ============================================================================
# merge-policy axes (정책 4축) -- Hancom's own real-measured "문서 끼워 넣기"
# dialog checkboxes (글자 모양 유지/스타일 유지/쪽 모양 유지/문단 모양 유지).
# Only the shipped default direction of each axis has an implementation;
# the opposite ("흡수") is honestly deferred with a typed error rather than
# guessed -- see docs/2026-08-08-document-merge-contract.md's 정책 4축
# section.
# ============================================================================

_MERGE_POLICY_AXES = (
    "keep_character_shape",
    "keep_style",
    "keep_paragraph_shape",
    "keep_page_shape",
)


def test_append_document_default_policy_axes_are_accepted() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("default axes")
    target = HwpxDocument.new()

    report = append_document(
        target,
        source,
        keep_character_shape=True,
        keep_style=True,
        keep_paragraph_shape=True,
        keep_page_shape=False,
    )
    assert "default axes" in _texts(target)
    after = check_id_integrity(target)
    assert after.ok, after.dangling
    # HwpxDocument.new() ships with its own default empty-text paragraph --
    # source_section_index=None (the default) copies every source
    # paragraph, including that pre-existing empty one, not just the one
    # explicitly added above.
    assert report["paragraphsInserted"] == 2


def test_insert_document_default_policy_axes_are_accepted() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("default axes")
    target = HwpxDocument.new()
    target.add_paragraph("existing")

    report = insert_document(
        target,
        source,
        after_paragraph_index=0,
        keep_character_shape=True,
        keep_style=True,
        keep_paragraph_shape=True,
        keep_page_shape=False,
    )
    assert "default axes" in _texts(target)
    assert report["paragraphsInserted"] == 2


_MERGE_POLICY_DEFAULTS = {
    "keep_character_shape": True,
    "keep_style": True,
    "keep_paragraph_shape": True,
    "keep_page_shape": False,
}


def test_append_document_rejects_every_non_default_policy_axis() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("text")
    target = HwpxDocument.new()

    for axis in _MERGE_POLICY_AXES:
        kwargs = dict(_MERGE_POLICY_DEFAULTS)
        kwargs[axis] = not kwargs[axis]

        with pytest.raises(HwpxValueError) as excinfo:
            append_document(target, source, **kwargs)
        assert excinfo.value.code == "document-merge-unsupported-policy-axis"
        assert excinfo.value.context.get("axis") == axis
        assert excinfo.value.context.get("koreanName")
        # rejected before any side effect -- target must stay untouched
        # (a fresh HwpxDocument.new() ships with one default empty paragraph)
        assert _texts(target) == [""]


def test_insert_document_rejects_every_non_default_policy_axis() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("text")
    target = HwpxDocument.new()
    target.add_paragraph("existing")

    for axis in _MERGE_POLICY_AXES:
        kwargs = dict(_MERGE_POLICY_DEFAULTS)
        kwargs[axis] = not kwargs[axis]

        with pytest.raises(HwpxValueError) as excinfo:
            insert_document(target, source, after_paragraph_index=0, **kwargs)
        assert excinfo.value.code == "document-merge-unsupported-policy-axis"
        assert excinfo.value.context.get("axis") == axis
        # rejected before any side effect -- target must stay untouched
        assert _texts(target) == ["", "existing"]


# ============================================================================
# property-clone nested refs into shared id-spaces (borderFill / tabPr)
#
# A copied hh:paraPr carries its own border/@borderFillIDRef and
# @tabPrIDRef, and a copied hh:charPr its own 글자-테두리 @borderFillIDRef.
# Those live inside the just-copied header items, not the body paragraphs
# the import scans -- exactly like hh:heading/hh:fontRef, which already get
# the clone-scan treatment. Missing them does not dangle (check_id_integrity
# stays green): the raw source id silently aliases onto whatever the target
# header means by that id. Live-observed: mfds admin notice의 무테두리 표지
# 문단들이 서울시 시행문에 병합되자 타깃 borderFill[3](표 SOLID 테두리)을
# 물려받아 전부 박스로 렌더됐다.
# ============================================================================

_GOLD = Path(__file__).parent / "fixtures" / "m3_gongmun_gold"


def _border_edges_for_paragraph(doc: HwpxDocument, snippet: str) -> dict[str, str]:
    """Resolve paragraph -> paraPr -> border/@borderFillIDRef -> edge types."""

    paragraph = next(
        p for section in doc.sections for p in section.paragraphs if snippet in (p.text or "")
    )
    para_ref = paragraph.element.get("paraPrIDRef")
    header = doc.parts.headers[0]
    para_pr = next(
        c for c in header._para_properties_element() if c.get("id") == para_ref
    )
    border_ref = None
    for node in para_pr.iter():
        if node.tag == f"{_HH}border":
            border_ref = node.get("borderFillIDRef")
    assert border_ref is not None, "paraPr has no border reference"
    border_fill = next(
        c for c in header._border_fills_element() if c.get("id") == border_ref
    )
    edges = {}
    for child in border_fill:
        name = child.tag.rsplit("}", 1)[-1]
        if name in {"leftBorder", "rightBorder", "topBorder", "bottomBorder"}:
            edges[name] = child.get("type")
    return edges


def test_merge_imports_parapr_border_fill_instead_of_aliasing_real_corpus() -> None:
    target = HwpxDocument.open(_GOLD / "seoul_sihaengmun.hwpx")
    report = append_document(target, _GOLD / "mfds_admin_notice.hwpx")
    assert report["paragraphsInserted"] > 0

    # 소스에서 이 표지 문단의 borderFill은 4변 전부 NONE — 병합 후에도
    # 같은 의미로 해석돼야 한다 (타깃 borderFill[3]=SOLID로 앨리어싱 금지).
    edges = _border_edges_for_paragraph(target, "생산·수입 중단")
    assert set(edges.values()) == {"NONE"}, edges

    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_merge_imports_parapr_tab_definition_instead_of_aliasing() -> None:
    source = HwpxDocument.new()
    source.add_paragraph("tabbed line")
    # HwpxDocument.new()는 기본 빈 문단 1개를 갖고 시작 — "tabbed line"은 index 1.
    source.styles.apply_paragraph_format(paragraph_index=1, tab_stops=[{"pos_mm": 30.0}])

    target = HwpxDocument.new()
    # 소스의 raw tabPr id가 타깃에서 "다른 정의"를 가리키도록 선점.
    target.parts.headers[0].ensure_tab_definition(
        tab_stops=[{"pos": 999}], auto_tab_left=True, auto_tab_right=False
    )
    target.parts.headers[0].ensure_tab_definition(
        tab_stops=[{"pos": 555}], auto_tab_left=False, auto_tab_right=True
    )

    def _tab_positions(doc: HwpxDocument, snippet: str) -> list[str]:
        paragraph = next(
            p for section in doc.sections for p in section.paragraphs if snippet in (p.text or "")
        )
        para_ref = paragraph.element.get("paraPrIDRef")
        header = doc.parts.headers[0]
        para_pr = next(
            c for c in header._para_properties_element() if c.get("id") == para_ref
        )
        tab_ref = para_pr.get("tabPrIDRef")
        assert tab_ref is not None, "paraPr has no tabPrIDRef"
        tab_pr = next(
            c for c in header._tab_properties_element() if c.get("id") == tab_ref
        )
        return sorted(
            item.get("pos") for item in tab_pr if item.tag.rsplit("}", 1)[-1] == "tabItem"
        )

    expected = _tab_positions(source, "tabbed line")
    append_document(target, source)
    assert _tab_positions(target, "tabbed line") == expected

    after = check_id_integrity(target)
    assert after.ok, after.dangling


def test_merge_imports_charpr_character_border_instead_of_aliasing() -> None:
    source = HwpxDocument.new()
    char_id = source.styles.ensure_run(bold=True)
    dash_fill = source.parts.headers[0].ensure_border_fill(
        active_borders=("left",), border_type="DASH"
    )
    source_char_pr = next(
        c
        for c in source.parts.headers[0]._char_properties_element()
        if c.get("id") == str(char_id)
    )
    source_char_pr.set("borderFillIDRef", dash_fill)
    source.add_paragraph("char border", char_pr_id_ref=char_id)

    target = HwpxDocument.new()
    # 소스 raw id가 4변 SOLID 정의로 앨리어싱되도록 타깃 공간 선점
    # (색상을 다르게 해 dedupe가 패딩을 접지 않게 한다).
    for color in ("#000000", "#111111", "#222222", "#333333"):
        target.parts.headers[0].ensure_border_fill(
            active_borders=("left", "right", "top", "bottom"),
            border_type="SOLID",
            border_color=color,
        )

    append_document(target, source)

    paragraph = next(
        p
        for section in target.sections
        for p in section.paragraphs
        if "char border" in (p.text or "")
    )
    run_ref = paragraph.element.find(f"{_HP}run").get("charPrIDRef")
    header = target.parts.headers[0]
    char_pr = next(
        c for c in header._char_properties_element() if c.get("id") == run_ref
    )
    border_ref = char_pr.get("borderFillIDRef")
    assert border_ref is not None
    border_fill = next(
        c for c in header._border_fills_element() if c.get("id") == border_ref
    )
    edges = {
        child.tag.rsplit("}", 1)[-1]: child.get("type")
        for child in border_fill
        if child.tag.rsplit("}", 1)[-1]
        in {"leftBorder", "rightBorder", "topBorder", "bottomBorder"}
    }
    assert edges["leftBorder"] == "DASH", edges
    assert edges["rightBorder"] == "NONE", edges

    after = check_id_integrity(target)
    assert after.ok, after.dangling


# ============================================================================
# clone layout-cache hygiene -- a copied paragraph is always new content at a
# new position, so the source's absolute hp:linesegarray never holds for it.
# ============================================================================


def _lineseg_count(paragraph) -> int:
    return sum(
        1
        for node in paragraph.element.iter()
        if node.tag.rsplit("}", 1)[-1].lower() == "linesegarray"
    )


def test_inserted_paragraph_clones_drop_source_layout_cache() -> None:
    doc = HwpxDocument.open(_GOLD / "seoul_sihaengmun.hwpx")
    section = doc.sections[0]
    cached_body = section.paragraphs[2]
    assert _lineseg_count(cached_body) > 0, "fixture paragraph should carry a cache"

    inserted = section.insert_paragraphs(3, [cached_body, cached_body])

    for clone in inserted:
        assert _lineseg_count(clone) == 0
    # 원본 문단(무편집)의 캐시는 그대로 보존 — 터치 범위 한정 원칙.
    assert _lineseg_count(cached_body) > 0


def test_merged_copies_carry_no_source_layout_cache() -> None:
    target = HwpxDocument.open(_GOLD / "seoul_sihaengmun.hwpx")
    existing = len(target.sections[0].paragraphs)
    append_document(target, _GOLD / "mfds_admin_notice.hwpx")

    for paragraph in target.sections[0].paragraphs[existing:]:
        assert _lineseg_count(paragraph) == 0
