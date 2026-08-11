# SPDX-License-Identifier: Apache-2.0
"""Document insertion/merge (문서 끼워 넣기, cycle 6.9 train 33, v2 cycle 6.10
train 38: merge-policy axes + MEMO support).

Copies another HWPX document's body content into an already-open
``HwpxDocument``, remapping every header-owned shared-resource reference
(``charPrIDRef``/``paraPrIDRef``/``styleIDRef``/``borderFillIDRef``/
``tabPrIDRef``/``memoShapeIDRef``/``binaryItemIDRef``/the paragraph-heading
``idRef``) so the copied content keeps pointing at the *same values* it did
in the source document -- just via freshly-minted ids in the target's own
header, never colliding with (or silently aliasing onto) whatever the
target document already had at those id numbers. As of v2, this also
covers a paragraph's referenced ``hp:memo`` content (copied from the
source's ``hp:memogroup`` and re-anchored, see ``_copy_referenced_memos``)
and exposes Hancom's own real-measured merge-policy axes (글자 모양 유지/
스타일 유지/쪽 모양 유지/문단 모양 유지, see ``_validate_merge_policy_axes``)
as named parameters -- though only the shipped default direction of each
axis has an implementation; the opposite ("흡수") is honestly deferred. See
``docs/2026-08-08-document-merge-contract.md`` for the full id-reference
catalog this module was designed against, the v1 scope decision (no style
deduplication -- every referenced item is copied under a fresh id, even if
it looks identical to something the target already has), and the specific
references this module still deliberately refuses to handle
(``hp:connectLine``'s ``subjectIDRef``, linked-textbox chains, chart binary
references) rather than risk a silent, wrong remap.

Two entry points, matching the contract's v1 scope:

* :func:`append_document` -- append another document's paragraphs to the
  end of the target's last section.
* :func:`insert_document` -- insert another document's paragraphs after a
  given paragraph in the target.

Both return a report dict (id counts remapped per reference space,
paragraphs inserted) rather than mutating silently -- matching this
library's general "report what happened" convention (``mutation_report``,
``merge_template_rows``'s own per-row report, etc).

The contract doc's gate #1 (referential-integrity sweep) is **not**
reimplemented here -- ``hwpx.tools.id_integrity.check_id_integrity`` already
does this, more thoroughly (per-lang fontfaces tables, orphaned-BinData
detection, sentinel/unset-id allowlisting) than a document-merge-local
version would. Call it on *target* after :func:`append_document`/
:func:`insert_document` to verify the merge.
"""

from __future__ import annotations

import copy as _copy
from pathlib import Path
from typing import Any

from .._document.media import _bin_data_stem, add_image
from ..document import HwpxDocument
from ..errors import HwpxValueError
from ..oxml._document_primitives import (
    _FONT_FACE_LANG_TO_REF,
    _FONT_REF_ATTRIBUTES,
    _HH,
    _HP,
    _allocate_font_id,
    _allocate_memo_shape_id,
    _allocate_tab_id,
    _memo_id,
    _object_id,
    _refresh_copied_paragraph_subtree_ids,
)

#: hh:fontRef's 7 lang attribute names ("hangul"/"latin"/...) -> the
#: hh:fontface/@lang value ("HANGUL"/"LATIN"/...) that attribute's id is
#: scoped to. Inverse of the codebase's existing lang->attr map
#: (``_FONT_FACE_LANG_TO_REF``) -- no ready-made inverse existed to import.
_FONT_REF_TO_FACE_LANG = {attr: lang for lang, attr in _FONT_FACE_LANG_TO_REF.items()}

#: Elements/attributes this v1 refuses to carry across documents rather than
#: risk a silent wrong remap -- see the contract doc's "보류" section for the
#: evidence behind each. Checked on the *source* content being copied, before
#: any mutation happens (fail before touching anything, not partway through).
_REJECTED_LOCAL_TAGS = (f"{_HP}connectLine",)
_REJECTED_ATTRS = ("linkListIDRef", "linkListNextIDRef", "chartIDRef")
#: Sentinel values for a rejected attribute that mean "not actually used,"
#: safe to pass through rather than reject. Found by team-lead's
#: independent verification (not assumed in advance): a census of the
#: vendored corpus shows linkListIDRef/linkListNextIDRef are 5,891/5,891
#: == "0" -- a boilerplate default every hp:subList carries (including our
#: own add_table's own output), never once a real linked-textbox chain
#: value. Rejecting on mere presence (as chartIDRef correctly still is --
#: the corpus's one real chartIDRef occurrence is a genuine path, never
#: "0") made every table-bearing document, including our own generator's
#: own output, unmergeable. chartIDRef has no such sentinel in this census
#: and is deliberately absent from this dict -- its presence alone stays
#: real usage.
_REJECTED_ATTR_SENTINELS: dict[str, frozenset[str]] = {
    "linkListIDRef": frozenset({"0", ""}),
    "linkListNextIDRef": frozenset({"0", ""}),
}
#: The 4 merge-policy axes Hancom's own "문서 끼워 넣기" dialog exposes as
#: checkboxes (글자 모양 유지/스타일 유지/쪽 모양 유지/문단 모양 유지), per
#: team-lead's real-GUI measurement (2026-08-07) -- see the contract doc's
#: 정책 4축 section for the exact dialog wording each axis name is drawn
#: from (never invented here). Hancom's own default is all 4 OFF (=="흡수":
#: copied content takes on the target's existing formatting rather than
#: keeping its own) -- the *opposite* of what this module's v1 already
#: shipped and had real-Hancom-verified (v13 batch): v1 always keeps every
#: axis's source formatting, unconditionally, with no parameter to turn it
#: off. These defaults preserve that exact shipped behavior for backward
#: compatibility -- only an explicit non-default value is rejected
#: (honest-defer, not guessed), since "흡수" requires mapping copied
#: content onto the target's *existing* formatting, and how Hancom
#: actually performs that mapping has no measured basis yet.
_MERGE_POLICY_AXIS_DEFAULTS: dict[str, bool] = {
    "keep_character_shape": True,
    "keep_style": True,
    "keep_paragraph_shape": True,
    "keep_page_shape": False,
}
#: Korean axis names exactly as measured from the real dialog.
_MERGE_POLICY_AXIS_KOREAN_NAMES: dict[str, str] = {
    "keep_character_shape": "글자 모양 유지",
    "keep_style": "스타일 유지",
    "keep_paragraph_shape": "문단 모양 유지",
    "keep_page_shape": "쪽 모양 유지",
}


def _validate_merge_policy_axes(
    *,
    keep_character_shape: bool,
    keep_style: bool,
    keep_paragraph_shape: bool,
    keep_page_shape: bool,
) -> None:
    """Reject any merge-policy axis value other than v1's shipped default.

    v2 exposes the 4 axes as named parameters (matching the real Hancom
    dialog's own checkbox names) so callers can *see* the policy this
    module has always applied -- but only the shipped, real-Hancom-verified
    direction of each axis actually has an implementation. Flipping an
    axis to its opposite ("흡수"/absorb, or -- for 쪽 모양 유지 -- replacing
    the target's page setup with the source's) needs target-formatting
    mapping semantics this module has no measured basis for yet; guessing
    risks exactly the silent-corruption failure mode this whole module
    exists to prevent. Called first, before any side effect, so a rejected
    request never opens/mutates anything.
    """

    requested = {
        "keep_character_shape": keep_character_shape,
        "keep_style": keep_style,
        "keep_paragraph_shape": keep_paragraph_shape,
        "keep_page_shape": keep_page_shape,
    }
    for axis, value in requested.items():
        default = _MERGE_POLICY_AXIS_DEFAULTS[axis]
        if value != default:
            raise HwpxValueError(
                f"{axis}={value!r} is not implemented yet -- only the "
                f"shipped default ({default!r}) is supported",
                code="document-merge-unsupported-policy-axis",
                context={
                    "axis": axis,
                    "koreanName": _MERGE_POLICY_AXIS_KOREAN_NAMES[axis],
                    "requested": value,
                    "supported": default,
                },
                suggestion=(
                    "See docs/2026-08-08-document-merge-contract.md's 정책 "
                    "4축 section -- the opposite direction of this axis "
                    "needs target-formatting mapping semantics this module "
                    "has no measured basis for yet."
                ),
            )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _reject_unsupported_references(paragraphs: list[Any]) -> None:
    for paragraph in paragraphs:
        for node in paragraph.iter():
            if node.tag in _REJECTED_LOCAL_TAGS:
                raise HwpxValueError(
                    f"document insert does not support {_local_name(node.tag)!r} yet",
                    code="document-merge-unsupported-reference",
                    context={"tag": _local_name(node.tag)},
                    suggestion=(
                        "See docs/2026-08-08-document-merge-contract.md's 보류 "
                        "section -- this reference's remap semantics are not "
                        "established with enough confidence to carry across "
                        "documents silently."
                    ),
                )
            for attr in _REJECTED_ATTRS:
                value = node.get(attr)
                if value is None:
                    continue
                sentinels = _REJECTED_ATTR_SENTINELS.get(attr)
                if sentinels is not None and value in sentinels:
                    continue
                raise HwpxValueError(
                    f"document insert does not support {attr!r} yet",
                    code="document-merge-unsupported-reference",
                    context={"attribute": attr, "tag": _local_name(node.tag)},
                    suggestion=(
                        "See docs/2026-08-08-document-merge-contract.md's "
                        "보류 section."
                    ),
                )


# ================================================================================
# header-owned shared-resource remapping (축 1) -- one function per id-space,
# each following the same shape: scan the copied content for every distinct
# value of *attr*, copy the referenced item from source's container into
# target's container under a freshly-allocated id, return {old_id: new_id}.
# Kept separate per space (not one generic loop) because each space's
# allocator has genuinely different, corpus-derived conventions (0-start vs
# 1-start, extra bookkeeping) that must not be reimplemented from scratch --
# see the contract doc's "재발명 안 함" note.
# ================================================================================


def _used_ids(paragraphs: list[Any], attr: str) -> set[str]:
    used: set[str] = set()
    for paragraph in paragraphs:
        for node in paragraph.iter():
            value = node.get(attr)
            if value:
                used.add(value)
    return used


def _extra_ids_from_style_bases(
    source_header: Any, style_ids_used: set[str]
) -> tuple[set[str], set[str]]:
    """Returns (extra charPr ids, extra paraPr ids) a copied ``hh:style``
    needs beyond whatever body content directly references.

    Discovered by live-testing an adversarial (not-coincidentally-default)
    style (not assumed in advance): every ``hh:style`` carries its own
    ``paraPrIDRef``/``charPrIDRef`` -- its base formatting -- and a
    paragraph can reference a style *only* via ``styleIDRef``, inheriting
    that base formatting implicitly without ever setting its own run/
    paragraph attribute to the same id. In this codebase's default
    skeleton every style happens to point at ``charPrIDRef="0"``, which
    also happens to be what a plain paragraph's own run defaults to -- a
    coincidence that masks the bug for trivial merges. A style with a
    genuinely custom base (built via ``ensure_style(...,
    para_pr_id_ref=..., char_pr_id_ref=...)``) exposes it: without this,
    the style's own base ids are never added to
    :func:`_remap_char_properties`/:func:`_remap_para_properties`'s
    ``used`` sets, so the copied style keeps pointing at source's raw
    numeric ids -- a dangling or silently-aliased reference on a header
    item now living in the target document, exactly the failure shape
    this whole module exists to prevent.
    """

    if not style_ids_used:
        return set(), set()
    source_container = source_header._styles_element()
    if source_container is None:
        return set(), set()
    extra_char: set[str] = set()
    extra_para: set[str] = set()
    for style_id in style_ids_used:
        item = next(
            (c for c in source_container.findall(f"{_HH}style") if c.get("id") == style_id), None
        )
        if item is None:
            continue
        char_ref = item.get("charPrIDRef")
        if char_ref:
            extra_char.add(char_ref)
        para_ref = item.get("paraPrIDRef")
        if para_ref:
            extra_para.add(para_ref)
    return extra_char, extra_para


def _remap_char_properties(
    source_header: Any, target_header: Any, paragraphs: list[Any], *, extra_ids: set[str] | None = None
) -> tuple[dict[str, str], list[Any]]:
    """Returns (old_id -> new_id, the newly-created charPr clones).

    The clones are returned (not just the remap dict) because ``hh:fontRef``
    -- whose 7 lang-scoped attributes each target a font id, see
    ``_remap_fonts`` -- lives *inside* a ``hh:charPr`` item, not in the body
    paragraphs this function scans for usage. *extra_ids* folds in ids a
    copied ``hh:style`` needs for its own base charPr (see
    :func:`_extra_ids_from_style_bases`) that body content alone would miss.
    """

    used = _used_ids(paragraphs, "charPrIDRef") | (extra_ids or set())
    if not used:
        return {}, []
    source_container = source_header._char_properties_element()
    target_container = target_header._char_properties_element(create=True)
    if source_container is None:
        return {}, []
    remap: dict[str, str] = {}
    clones: list[Any] = []
    for old_id in sorted(used):
        item = next(
            (c for c in source_container.findall(f"{_HH}charPr") if c.get("id") == old_id), None
        )
        if item is None:
            continue
        new_id = target_header._allocate_char_property_id(target_container)
        clone = _deep_copy_element(item)
        clone.set("id", new_id)
        target_container.append(clone)
        target_header._update_item_count(target_container, f"{_HH}charPr")
        remap[old_id] = new_id
        clones.append(clone)
    return remap, clones


def _remap_para_properties(
    source_header: Any, target_header: Any, paragraphs: list[Any], *, extra_ids: set[str] | None = None
) -> tuple[dict[str, str], list[Any]]:
    """Returns (old_id -> new_id, the newly-created paraPr clones).

    The clones are returned (not just the remap dict) because ``hh:heading``
    -- whose own ``idRef`` targets numbering/bullets, see
    ``_remap_headings`` -- lives *inside* a ``hh:paraPr`` item, not in the
    body paragraphs this function scans for usage. Body content only ever
    carries ``paraPrIDRef`` pointing *at* a paraPr; the heading reference is
    a paraPr-internal detail the caller must remap separately, on these
    same clones, after they exist. *extra_ids* folds in ids a copied
    ``hh:style`` needs for its own base paraPr (see
    :func:`_extra_ids_from_style_bases`) that body content alone would miss.
    """

    used = _used_ids(paragraphs, "paraPrIDRef") | (extra_ids or set())
    if not used:
        return {}, []
    source_container = source_header._para_properties_element()
    target_container = target_header._para_properties_element(create=True)
    if source_container is None:
        return {}, []
    remap: dict[str, str] = {}
    clones: list[Any] = []
    for old_id in sorted(used):
        item = next(
            (c for c in source_container.findall(f"{_HH}paraPr") if c.get("id") == old_id), None
        )
        if item is None:
            continue
        new_id = target_header._allocate_ref_id(target_container, f"{_HH}paraPr")
        clone = _deep_copy_element(item)
        clone.set("id", new_id)
        target_container.append(clone)
        target_header._update_item_count(target_container, f"{_HH}paraPr")
        remap[old_id] = new_id
        clones.append(clone)
    return remap, clones


def _remap_border_fills(
    source_header: Any, target_header: Any, paragraphs: list[Any], *, extra_ids: set[str] | None = None
) -> dict[str, str]:
    """*extra_ids* folds in refs living inside just-copied header items --
    ``hh:paraPr``'s own ``border/@borderFillIDRef`` and ``hh:charPr``'s
    글자-테두리 ``@borderFillIDRef`` -- that body content alone would miss
    (same shape as heading/fontRef; live-observed as borderless source
    paragraphs acquiring the target's SOLID table borders)."""

    used = _used_ids(paragraphs, "borderFillIDRef") | (extra_ids or set())
    if not used:
        return {}
    source_container = source_header._border_fills_element()
    target_container = target_header._border_fills_element(create=True)
    if source_container is None:
        return {}
    remap: dict[str, str] = {}
    for old_id in sorted(used):
        item = next(
            (c for c in source_container.findall(f"{_HH}borderFill") if c.get("id") == old_id), None
        )
        if item is None:
            continue
        new_id = target_header._allocate_border_fill_id(target_container)
        clone = _deep_copy_element(item)
        clone.set("id", new_id)
        target_container.append(clone)
        target_header._update_item_count(target_container, f"{_HH}borderFill")
        remap[old_id] = new_id
    return remap


def _remap_tab_properties(
    source_header: Any, target_header: Any, paragraphs: list[Any], *, extra_ids: set[str] | None = None
) -> dict[str, str]:
    """*extra_ids* folds in ``hh:paraPr``'s own ``@tabPrIDRef`` -- body
    content never carries it, so without the clone-scan a copied paraPr's
    tab definition silently aliases onto the target's same-numbered tabPr."""

    used = _used_ids(paragraphs, "tabPrIDRef") | (extra_ids or set())
    if not used:
        return {}
    source_container = source_header._tab_properties_element()
    target_container = target_header._tab_properties_element(create=True)
    if source_container is None:
        return {}
    remap: dict[str, str] = {}
    for old_id in sorted(used):
        item = next(
            (c for c in source_container.findall(f"{_HH}tabPr") if c.get("id") == old_id), None
        )
        if item is None:
            continue
        new_id = _allocate_tab_id(target_container)
        clone = _deep_copy_element(item)
        clone.set("id", new_id)
        target_container.append(clone)
        target_header._update_item_count(target_container, f"{_HH}tabPr")
        remap[old_id] = new_id
    return remap


def _remap_memo_properties(source_header: Any, target_header: Any, paragraphs: list[Any]) -> dict[str, str]:
    used = _used_ids(paragraphs, "memoShapeIDRef")
    if not used:
        return {}
    source_container = source_header._memo_properties_element()
    target_container = target_header._memo_properties_element(create=True)
    if source_container is None:
        return {}
    remap: dict[str, str] = {}
    for old_id in sorted(used):
        item = next(
            (c for c in source_container.findall(f"{_HH}memoPr") if c.get("id") == old_id), None
        )
        if item is None:
            continue
        new_id = _allocate_memo_shape_id(target_container)
        clone = _deep_copy_element(item)
        clone.set("id", new_id)
        target_container.append(clone)
        target_header._update_item_count(target_container, f"{_HH}memoPr")
        remap[old_id] = new_id
    return remap


#: hh:paraPr/hh:heading's own idRef is polymorphic -- the sibling `type`
#: attribute decides whether it targets the numberings or bullets id-space.
#: See the contract doc's id-reference catalog for the schema evidence.
_HEADING_TYPE_TO_CONTAINER_TAG = {"NUMBER": "numbering", "OUTLINE": "numbering", "BULLET": "bullet"}


def _remap_headings(
    source_header: Any, target_header: Any, para_pr_clones: list[Any]
) -> dict[str, dict[str, str]]:
    """Returns {"numbering": {old: new}, "bullet": {old: new}}.

    Scans *para_pr_clones* (the already-copied paraPr items, from
    :func:`_remap_para_properties` -- not the body paragraphs) for nested
    ``hh:heading`` children, since that is where the reference actually
    lives.
    """

    by_space: dict[str, set[str]] = {"numbering": set(), "bullet": set()}
    for clone in para_pr_clones:
        for node in clone.iter():
            if _local_name(node.tag) != "heading":
                continue
            space = _HEADING_TYPE_TO_CONTAINER_TAG.get(node.get("type", ""))
            id_ref = node.get("idRef")
            if space and id_ref:
                by_space[space].add(id_ref)

    result: dict[str, dict[str, str]] = {"numbering": {}, "bullet": {}}
    for space, used in by_space.items():
        if not used:
            continue
        getter = f"_{space}s_element"
        source_container = getattr(source_header, getter)()
        target_container = getattr(target_header, getter)(create=True)
        if source_container is None:
            continue
        for old_id in sorted(used):
            item = next(
                (c for c in source_container.findall(f"{_HH}{space}") if c.get("id") == old_id), None
            )
            if item is None:
                continue
            new_id = target_header._allocate_ref_id(target_container, f"{_HH}{space}")
            clone = _deep_copy_element(item)
            clone.set("id", new_id)
            target_container.append(clone)
            target_header._update_item_count(target_container, f"{_HH}{space}")
            result[space][old_id] = new_id
    return result


def _remap_fonts(
    source_header: Any, target_header: Any, char_pr_clones: list[Any]
) -> dict[str, dict[str, str]]:
    """Returns {lang_attr: {old_font_id: new_font_id}}, one map per
    ``hh:fontRef`` lang attribute (``hangul``/``latin``/``hanja``/
    ``japanese``/``other``/``symbol``/``user`` -- ``_FONT_REF_ATTRIBUTES``).

    Scans *char_pr_clones* (the already-copied charPr items, from
    :func:`_remap_char_properties` -- not the body paragraphs) for their
    nested ``hh:fontRef`` child. Confirmed by live testing (not assumed):
    each of fontRef's 7 lang attributes is a font id *independently scoped*
    to that lang's own ``hh:fontface[@lang=X]`` -- a HANGUL fontface can
    have font ids 0/1/2 while the LATIN fontface only goes up to 1, so the
    same numeric value means a *different* font depending which lang
    attribute it came from. Each lang therefore needs its own old->new map,
    keyed separately -- unlike every other id-space in this module, which
    is a single flat space.
    """

    by_lang: dict[str, set[str]] = {lang: set() for lang in _FONT_REF_ATTRIBUTES}
    for clone in char_pr_clones:
        font_ref = clone.find(f"{_HH}fontRef")
        if font_ref is None:
            continue
        for lang in _FONT_REF_ATTRIBUTES:
            value = font_ref.get(lang)
            if value:
                by_lang[lang].add(value)

    result: dict[str, dict[str, str]] = {lang: {} for lang in _FONT_REF_ATTRIBUTES}
    if not any(by_lang.values()):
        return result

    source_fontfaces = source_header._fontfaces_element()
    if source_fontfaces is None:
        return result
    target_fontfaces = target_header._fontfaces_element(create=True)

    for lang, used in by_lang.items():
        if not used:
            continue
        face_lang = _FONT_REF_TO_FACE_LANG[lang]
        source_fontface = source_header._fontface_element(source_fontfaces, face_lang, create=False)
        if source_fontface is None:
            continue
        target_fontface = target_header._fontface_element(target_fontfaces, face_lang, create=True)
        for old_id in sorted(used):
            item = next(
                (c for c in source_fontface.findall(f"{_HH}font") if c.get("id") == old_id), None
            )
            if item is None:
                continue
            new_id = _allocate_font_id(target_fontface)
            clone = _deep_copy_element(item)
            clone.set("id", new_id)
            target_fontface.append(clone)
            target_fontface.set("fontCnt", str(len(target_fontface.findall(f"{_HH}font"))))
            result[lang][old_id] = new_id
    return result


def _apply_font_remap(char_pr_clones: list[Any], fonts: dict[str, dict[str, str]]) -> None:
    """Substitute remapped font ids onto ``hh:fontRef``'s lang attributes.

    Separate from :func:`_apply_remaps` because font remaps are shaped
    differently (one dict per lang attribute, not one flat old->new dict)
    and only ever apply to a charPr's own ``fontRef`` child, never to a
    generic body-paragraph attribute scan.
    """

    for clone in char_pr_clones:
        font_ref = clone.find(f"{_HH}fontRef")
        if font_ref is None:
            continue
        for lang, remap in fonts.items():
            value = font_ref.get(lang)
            if value in remap:
                font_ref.set(lang, remap[value])


def _remap_binary_items(
    source_doc: HwpxDocument, target_doc: HwpxDocument, source_header: Any, target_header: Any,
    paragraphs: list[Any],
) -> dict[str, str]:
    """``binaryItemIDRef`` does NOT reference ``hh:binItem/@id`` (a plain
    numeric allocator id, "0"/"1"/...) -- it references the *stem* of the
    item's own ``BinData`` filename attribute (``"BIN0001.png"`` ->
    ``"BIN0001"``), confirmed against this codebase's own read-side lookup
    (``_document/media.py``'s ``_existing_image_item_ids``, which builds its
    id set from exactly this stem). Every other reference space in this
    module keys off ``@id`` -- this one is the deliberate exception, caught
    by testing an actual picture-carrying merge, not assumed.
    """

    used = _used_ids(paragraphs, "binaryItemIDRef")
    if not used:
        return {}
    source_container = source_header._bin_data_list_element()
    if source_container is None:
        return {}
    remap: dict[str, str] = {}
    for old_stem in sorted(used):
        item = next(
            (
                c for c in source_container.findall(f"{_HH}binItem")
                if _bin_data_stem(c.get("BinData")) == old_stem
            ),
            None,
        )
        if item is None:
            continue
        bin_data_name = item.get("BinData")
        fmt = (item.get("Format") or "").lower().lstrip(".")
        if not bin_data_name:
            continue
        # BinData files live at a fixed conventional path (BinData/<name>,
        # package-root not Contents/-relative -- confirmed against
        # add_image's own writer, _document/media.py's add_image).
        part_path = f"BinData/{bin_data_name}"
        try:
            raw = source_doc.package.read(part_path)
        except KeyError:
            continue
        if not fmt:
            fmt = Path(bin_data_name).suffix.lstrip(".") or "png"
        new_item = add_image(target_doc, raw, fmt)
        remap[old_stem] = str(new_item)
    return remap


def _deep_copy_element(element: Any) -> Any:
    return _copy.deepcopy(element)


# ================================================================================
# document-local structural id refresh (축 3) -- extends
# _refresh_copied_paragraph_subtree_ids (which already handles paragraph/
# object/instId) with the ids it deliberately leaves alone: memo, field
# begin/end pairing, bookmark name collisions.
# ================================================================================


def _refresh_field_and_bookmark_ids(paragraphs: list[Any], existing_bookmark_names: set[str]) -> None:
    """Refresh document-local ids that ``_refresh_copied_paragraph_subtree_ids``
    deliberately leaves alone (see its own docstring): field begin/end
    pairing and bookmark names. Applies uniformly to every fieldBegin type,
    including ``MEMO`` -- this function only ever touches the field
    control's *own* ``id``/``fieldid`` attributes, never its nested
    ``hp:parameters``, so it needs no special-casing for memo fields. The
    memo's own id (and the field's ``ID``/``MemoShapeIDRef``
    ``hp:stringParam`` text values that reference it) are handled
    separately by :func:`_copy_referenced_memos`/
    :func:`_apply_memo_field_param_remaps` -- real memo content lives in a
    sibling ``hp:memogroup``, not nested in this paragraph subtree at all.
    """

    for paragraph in paragraphs:
        # hp:fieldBegin/fieldEnd -- id/fieldid must both get fresh values,
        # and fieldEnd's beginIDRef/fieldid must follow its OWN fieldBegin's
        # new id/fieldid (pair integrity), not an independent fresh value.
        # fieldEnd's OWN fieldid starts out equal to its paired fieldBegin's
        # (both set to the same field_value at creation --
        # attach_memo_field, _document/memos.py:136,181) -- begin_fieldid_map
        # is keyed by that shared OLD value so the fieldEnd loop below can
        # look its new counterpart up the same way begin_id_map already does
        # for beginIDRef. Found live (not assumed in advance) via v14
        # openrate generator's own cross-run determinism check: leaving
        # fieldEnd's fieldid untouched meant it kept the SOURCE document's
        # raw uuid4().hex value (memos.py's own creation call, which does
        # NOT go through _document_primitives' patchable uuid4 binding and
        # so is not just non-deterministic across generator runs but also a
        # genuinely stale, unrefreshed value on copied content -- exactly
        # this module's own "silent corruption" failure shape, just on an
        # attribute nothing currently gates on).
        begin_id_map: dict[str, str] = {}
        begin_fieldid_map: dict[str, str] = {}
        for node in paragraph.iter():
            if _local_name(node.tag) == "fieldBegin":
                old_id = node.get("id")
                new_id = _object_id()
                if old_id:
                    begin_id_map[old_id] = new_id
                node.set("id", new_id)
                old_fieldid = node.get("fieldid")
                if old_fieldid:
                    new_fieldid = _object_id()
                    begin_fieldid_map[old_fieldid] = new_fieldid
                    node.set("fieldid", new_fieldid)
        for node in paragraph.iter():
            if _local_name(node.tag) == "fieldEnd":
                old_begin = node.get("beginIDRef")
                if old_begin and old_begin in begin_id_map:
                    node.set("beginIDRef", begin_id_map[old_begin])
                old_end_fieldid = node.get("fieldid")
                if old_end_fieldid and old_end_fieldid in begin_fieldid_map:
                    node.set("fieldid", begin_fieldid_map[old_end_fieldid])

        # hp:bookmark name -- not an id, a user-chosen string. Target
        # collision is avoided with a numeric suffix (v1 policy -- the
        # contract doc's own choice, simple over clever).
        for node in paragraph.iter():
            if _local_name(node.tag) == "bookmark":
                name = node.get("name")
                if not name:
                    continue
                candidate = name
                suffix = 1
                while candidate in existing_bookmark_names:
                    candidate = f"{name}_{suffix}"
                    suffix += 1
                node.set("name", candidate)
                existing_bookmark_names.add(candidate)


def _existing_bookmark_names(target: HwpxDocument) -> set[str]:
    names: set[str] = set()
    for section in target.sections:
        for node in section.element.iter():
            if _local_name(node.tag) == "bookmark":
                name = node.get("name")
                if name:
                    names.add(name)
    return names


# ================================================================================
# reference remap application
# ================================================================================


def _apply_remaps(
    paragraphs: list[Any],
    *,
    char_pr: dict[str, str],
    para_pr: dict[str, str],
    style: dict[str, str],
    border_fill: dict[str, str],
    tab_pr: dict[str, str],
    memo_shape: dict[str, str],
    binary_item: dict[str, str],
    headings: dict[str, dict[str, str]],
) -> None:
    for paragraph in paragraphs:
        for node in paragraph.iter():
            if node.get("charPrIDRef") in char_pr:
                node.set("charPrIDRef", char_pr[node.get("charPrIDRef")])
            if node.get("paraPrIDRef") in para_pr:
                node.set("paraPrIDRef", para_pr[node.get("paraPrIDRef")])
            if node.get("styleIDRef") in style:
                node.set("styleIDRef", style[node.get("styleIDRef")])
            if node.get("borderFillIDRef") in border_fill:
                node.set("borderFillIDRef", border_fill[node.get("borderFillIDRef")])
            if node.get("tabPrIDRef") in tab_pr:
                node.set("tabPrIDRef", tab_pr[node.get("tabPrIDRef")])
            if node.get("memoShapeIDRef") in memo_shape:
                node.set("memoShapeIDRef", memo_shape[node.get("memoShapeIDRef")])
            # hh:style's own internal references -- both target the SAME
            # `styles` id-space as styleIDRef itself (charStyleIDRef points at
            # another style entry flagged as a character style; nextStyleIDRef
            # at the style to apply after pressing Enter). Only remapped when
            # the target happens to already be in `style` (i.e. also directly
            # used by some body paragraph) -- v1 does not chase style chains
            # beyond that (see contract doc's v1 scope note).
            if node.get("nextStyleIDRef") in style:
                node.set("nextStyleIDRef", style[node.get("nextStyleIDRef")])
            if node.get("charStyleIDRef") in style:
                node.set("charStyleIDRef", style[node.get("charStyleIDRef")])
            if node.get("binaryItemIDRef") in binary_item:
                node.set("binaryItemIDRef", binary_item[node.get("binaryItemIDRef")])
            if _local_name(node.tag) == "heading":
                space = _HEADING_TYPE_TO_CONTAINER_TAG.get(node.get("type", ""))
                id_ref = node.get("idRef")
                if space and id_ref in headings.get(space, {}):
                    node.set("idRef", headings[space][id_ref])


def _strip_embedded_section_properties(paragraphs: list[Any]) -> int:
    """Remove any embedded ``hp:secPr``/column-layout ``hp:ctrl`` from the
    copied paragraphs, surgically -- element by element, not by discarding
    the whole run that happens to carry them.

    Discovered by live-testing a real merge (not assumed in advance): a
    section's *first* paragraph carries ``hp:secPr`` (the section's page
    setup -- margins, footnote/endnote policy, page border, etc) plus
    ``hp:ctrl/hp:colPr`` (column layout). On a *freshly-created* document
    these sit alone in their own text-less run, sibling to nothing --
    which was the only shape this function was originally tested against,
    and led to a real bug: it removed the *entire run* on sight of
    ``hp:secPr``. A real corpus fixture
    (``reader_writer__SimpleTable.hwpx``) exposed the gap -- that
    document's first paragraph packs ``secPr``/``ctrl``/``tbl``/``t`` all
    into *one* run, and the blunt whole-run removal silently deleted the
    table and text along with the section setup, passing every gate this
    module has (referential integrity has nothing to say about content
    that was never dangling because it no longer exists). Now each
    ``hp:secPr`` and each ``hp:ctrl`` that wraps ``hp:colPr`` specifically
    (never any other control type sharing the same run) is removed
    individually, and the run itself is only dropped if that leaves it
    completely empty -- preserving the original single-element-run
    behavior exactly while no longer touching unrelated siblings.

    v1's merge always inserts into an *already-existing* target section (it
    never creates a new one), so a copied source paragraph is never the
    destination section's first paragraph -- carrying its section-setup
    elements across would leave two ``hp:secPr`` in one ``hs:sec`` (a
    section should have exactly one) or, if inserted at index 0, silently
    replace the target's own page setup with the source's. ``hp:secPr``
    also carries its own id-references (``outlineShapeIDRef`` ->
    numberings, ``memoShapeIDRef`` -> memoProperties, nested
    ``pageBorderFill/@borderFillIDRef`` -> borderFills) that no remap
    function in this module touches -- carrying it across unremapped would
    silently produce dangling/wrong references on top of the structural
    problem. v1's answer: the target's own secPr stays sole authority for
    its section's page setup, unconditionally -- source's is dropped, not
    merged or chosen between. Returns the number of ``hp:secPr`` elements
    removed (surfaced in the report so callers can see it happened, not
    just infer it).
    """

    removed = 0
    for paragraph in paragraphs:
        for run in list(paragraph.findall(f"{_HP}run")):
            secpr = run.find(f"{_HP}secPr")
            if secpr is None:
                continue
            run.remove(secpr)
            removed += 1
            for ctrl in list(run.findall(f"{_HP}ctrl")):
                if ctrl.find(f"{_HP}colPr") is not None:
                    run.remove(ctrl)
            if len(run) == 0:
                paragraph.remove(run)
    return removed


# ================================================================================
# MEMO merge (hp:memogroup content) -- a memo's actual text lives in
# hp:memogroup, a *section-level sibling* of hp:p (DEV-042), never nested
# inside the anchoring paragraph. The anchoring paragraph only carries a
# fieldBegin/fieldEnd pair whose hp:parameters/hp:stringParam[name=ID]
# matches the memo's own @id -- so copying paragraphs alone (as every
# other reference space in this module operates on) would silently drop
# the memo's actual content while leaving a dangling-looking field marker
# behind. These functions find, clone, and re-anchor the referenced
# hp:memo elements; the clones are then folded into the SAME axis-1 remap
# scanning as the body paragraph copies (see _merge_paragraphs) so a
# memo's own charPr/paraPr/style/memoShapeIDRef usage gets remapped by the
# existing machinery, for free -- no separate remap pass needed for memo
# content itself.
# ================================================================================


def _find_memo_field_ids(paragraphs: list[Any]) -> set[str]:
    """Scan *paragraphs* for fieldBegin type=MEMO controls, returning the
    set of memo ids they reference (the "ID" stringParam value -- matches
    hp:memogroup/hp:memo/@id, per fieldBegin's own anchoring convention)."""

    memo_ids: set[str] = set()
    for paragraph in paragraphs:
        for node in paragraph.iter():
            if _local_name(node.tag) != "fieldBegin" or node.get("type") != "MEMO":
                continue
            params = node.find(f"{_HP}parameters")
            if params is None:
                continue
            for string_param in params.findall(f"{_HP}stringParam"):
                if string_param.get("name") == "ID" and string_param.text:
                    memo_ids.add(string_param.text)
    return memo_ids


def _copy_referenced_memos(
    source: HwpxDocument, source_paragraphs: list[Any]
) -> tuple[dict[str, str], list[Any]]:
    """Find every hp:memo the MEMO fields in *source_paragraphs* reference,
    clone them, and give each clone a fresh memo id plus fresh ids for its
    own nested paraList paragraph subtree.

    Searches across *all* of *source*'s sections (not just the ones the
    caller is copying paragraphs from) since hp:memogroup is a
    section-level sibling -- nothing in the schema guarantees a memo lives
    in the same section as every paragraph that could reference it, and
    this module would rather search a little wider than silently miss one.

    Returns (old_memo_id -> new_memo_id, the memo clones). Does NOT remap
    the clones' own charPrIDRef/paraPrIDRef/styleIDRef/memoShapeIDRef --
    the caller folds these clones into the same axis-1 scanning/
    application passes used for the body paragraph copies, so a memo's own
    formatting goes through the exact same remap machinery as everything
    else, rather than a separate reimplementation.
    """

    needed_ids = _find_memo_field_ids(source_paragraphs)
    if not needed_ids:
        return {}, []

    source_memos: dict[str, Any] = {}
    for section in source.sections:
        for memogroup in section.element.findall(f"{_HP}memogroup"):
            for memo in memogroup.findall(f"{_HP}memo"):
                memo_id = memo.get("id")
                if memo_id:
                    source_memos[memo_id] = memo

    memo_id_map: dict[str, str] = {}
    clones: list[Any] = []
    for old_id in sorted(needed_ids):
        memo = source_memos.get(old_id)
        if memo is None:
            continue
        clone = _deep_copy_element(memo)
        new_id = _memo_id()
        clone.set("id", new_id)
        memo_id_map[old_id] = new_id
        _refresh_copied_paragraph_subtree_ids(clone)
        clones.append(clone)
    return memo_id_map, clones


def _apply_memo_field_param_remaps(
    paragraphs: list[Any], *, memo_id: dict[str, str], memo_shape: dict[str, str]
) -> None:
    """Update fieldBegin type=MEMO's own hp:parameters/hp:stringParam text
    values ("ID" cross-references the memogroup entry; "MemoShapeIDRef"
    mirrors the memo's own memoShapeIDRef attribute for inline-render
    purposes) to match the id remaps applied elsewhere.

    These are element *text*, not attributes -- :func:`_apply_remaps` only
    ever substitutes attribute values, so this needs its own pass. Left
    untouched when a value isn't in the remap dict: "ID" always is (every
    surviving MEMO field references a memo that was found and cloned by
    :func:`_copy_referenced_memos`), but "MemoShapeIDRef" commonly stays at
    its "65535" sentinel (no shape override) -- which is never a
    remap-dict key, since a sentinel value never comes from a real
    memoShapeIDRef attribute on some hh:memoPr item in the first place.
    """

    for paragraph in paragraphs:
        for node in paragraph.iter():
            if _local_name(node.tag) != "fieldBegin" or node.get("type") != "MEMO":
                continue
            params = node.find(f"{_HP}parameters")
            if params is None:
                continue
            for string_param in params.findall(f"{_HP}stringParam"):
                name = string_param.get("name")
                if name == "ID" and string_param.text in memo_id:
                    string_param.text = memo_id[string_param.text]
                elif name == "MemoShapeIDRef" and string_param.text in memo_shape:
                    string_param.text = memo_shape[string_param.text]


def _insert_memos_into_target_section(target_section: Any, memo_clones: list[Any]) -> None:
    """Append *memo_clones* into *target_section*'s hp:memogroup, creating
    one if it doesn't already have one -- reusing the section's own
    find-or-create accessor (matching ``add_memo``'s own path, not a
    reimplementation) so a fresh memogroup lands wherever add_memo would
    put one.

    Explicitly marks the section dirty regardless of which branch ran: the
    accessor only does so itself when it *creates* a new memogroup -- the
    "already has one, just append more memo children" case would
    otherwise never reserialize on save, exactly the mark_dirty() omission
    class of bug this module already hit once for the header (see
    _merge_paragraphs's own docstring comment on that).
    """

    if not memo_clones:
        return
    memogroup = target_section._memo_group_element(create=True)
    for clone in memo_clones:
        memogroup.append(clone)
    target_section.mark_dirty()


def _merge_paragraphs(
    target: HwpxDocument,
    source: HwpxDocument,
    *,
    source_section_index: int | None,
) -> tuple[list[Any], list[Any], dict[str, Any]]:
    """Deep-copy source paragraphs, remap every reference, return
    (paragraph elements, memo clones, report)."""

    source_sections = (
        [source.sections[source_section_index]] if source_section_index is not None
        else list(source.sections)
    )
    source_paragraphs = [p.element for section in source_sections for p in section.paragraphs]
    if not source_paragraphs:
        return [], [], {"paragraphsInserted": 0}

    _reject_unsupported_references(source_paragraphs)

    # Found (via _find_memo_field_ids) and cloned from the ORIGINAL,
    # uncopied paragraphs -- fieldBegin's own "ID" stringParam values are
    # identical either way (deep-copying hasn't happened yet at this
    # point), and _copy_referenced_memos needs *source* itself (not just
    # source_paragraphs) to search its sections' hp:memogroup elements.
    memo_id_map, memo_clones = _copy_referenced_memos(source, source_paragraphs)

    copies = [_deep_copy_element(p) for p in source_paragraphs]
    # A copied paragraph is never the destination section's first paragraph
    # (v1 always merges into an existing section) -- so any embedded
    # section-setup run (hp:secPr + hp:ctrl/hp:colPr) it carries is dropped
    # rather than carried across unremapped. See the function's own
    # docstring for the full reasoning (structural + unremapped-reference).
    stripped_section_properties = _strip_embedded_section_properties(copies)

    source_header = source.parts.headers[0]
    target_header = target.parts.headers[0]
    # CRITICAL: every remap function below mutates target_header's element
    # tree directly (target_container.append(clone), etc) rather than going
    # through a facade method that already calls mark_dirty() itself (e.g.
    # HwpxOxmlHeader.ensure_char_property does). The OPC writer's save path
    # (HwpxOxmlDocument.to_bytes) only re-serializes a header from its live
    # tree when header.dirty is True -- otherwise it reuses the part's
    # original/cached bytes, silently dropping every element this module
    # just added. Found by live testing (not assumed in advance): a merge
    # that adds new charPr/paraPr/style items round-tripped CLEANLY whenever
    # the source also had a picture to copy (because _remap_binary_items's
    # add_image call happens to mark_dirty() the header as its own side
    # effect, masking the bug) but silently corrupted the saved document
    # (dangling *IDRef, invisible until reopened and checked) whenever it
    # did not. This single call is the fix -- do it unconditionally, up
    # front, since v1's own no-dedup policy means essentially every
    # non-empty merge touches the header (even a bare styleIDRef="0"
    # reference copies that default style under a fresh id).
    target_header.mark_dirty()

    # memo_clones fold into the SAME axis-1 scanning/application passes as
    # the body paragraph copies -- a memo's own paraList/hp:p carries
    # charPrIDRef/paraPrIDRef/styleIDRef exactly like body content, and
    # hp:memo's own memoShapeIDRef attribute is scanned identically too
    # (_used_ids's .iter() includes the top-level element itself, so a
    # bare hp:memo clone's own attribute is caught same as any nested
    # node's). No separate remap pass needed for memo content.
    remap_scope = copies + memo_clones

    # A style's own base paraPr/charPr may not be independently referenced
    # by any body paragraph (a paragraph can point only at the style and
    # inherit its formatting implicitly) -- computed *before* the char/para
    # remap calls so their `used` sets can fold these ids in. See
    # _extra_ids_from_style_bases's docstring for the live-tested evidence.
    style_ids_used = _used_ids(remap_scope, "styleIDRef")
    extra_char_ids, extra_para_ids = _extra_ids_from_style_bases(source_header, style_ids_used)

    char_pr, char_pr_clones = _remap_char_properties(
        source_header, target_header, remap_scope, extra_ids=extra_char_ids
    )
    para_pr, para_pr_clones = _remap_para_properties(
        source_header, target_header, remap_scope, extra_ids=extra_para_ids
    )
    style, style_clones = _remap_styles(source_header, target_header, remap_scope)
    # hh:paraPr's own border/@borderFillIDRef + @tabPrIDRef and hh:charPr's
    # 글자-테두리 @borderFillIDRef live inside the just-copied property items,
    # not the body paragraphs -- fold them into the import sets exactly like
    # heading/fontRef below. Missing them never dangles (the raw source id
    # aliases onto whatever the target header means by that number), which is
    # why gate #1 (check_id_integrity) stayed green while merged borderless
    # cover paragraphs rendered with the target's SOLID table borders.
    extra_border_ids = _used_ids(para_pr_clones, "borderFillIDRef") | _used_ids(
        char_pr_clones, "borderFillIDRef"
    )
    extra_tab_ids = _used_ids(para_pr_clones, "tabPrIDRef")
    border_fill = _remap_border_fills(
        source_header, target_header, remap_scope, extra_ids=extra_border_ids
    )
    tab_pr = _remap_tab_properties(
        source_header, target_header, remap_scope, extra_ids=extra_tab_ids
    )
    memo_shape = _remap_memo_properties(source_header, target_header, remap_scope)
    binary_item = _remap_binary_items(source, target, source_header, target_header, remap_scope)
    # hh:heading (numbering/bullet's own polymorphic idRef) lives inside the
    # just-copied paraPr items, not the body paragraphs -- scan those.
    headings = _remap_headings(source_header, target_header, para_pr_clones)
    # hh:fontRef (7 lang-scoped font ids) lives inside the just-copied
    # charPr items, not the body paragraphs -- scan those.
    fonts = _remap_fonts(source_header, target_header, char_pr_clones)

    remap_kwargs: dict[str, Any] = {
        "char_pr": char_pr, "para_pr": para_pr, "style": style, "border_fill": border_fill,
        "tab_pr": tab_pr, "memo_shape": memo_shape, "binary_item": binary_item, "headings": headings,
    }
    # Applied to the body paragraph copies (the normal case), the memo
    # clones (their own paraList content and hp:memo/@memoShapeIDRef, see
    # this function's memo_clones comment above), AND the header item
    # clones themselves -- a copied hh:paraPr can carry its own
    # tabPrIDRef/heading-idRef, and a copied hh:style can carry its own
    # paraPrIDRef/charPrIDRef/nextStyleIDRef/charStyleIDRef. Idempotent
    # dict-membership checks, so running it four times over disjoint
    # element sets is safe.
    _apply_remaps(copies, **remap_kwargs)
    _apply_remaps(memo_clones, **remap_kwargs)
    _apply_remaps(para_pr_clones, **remap_kwargs)
    # charPr clones carry their own 글자-테두리 borderFillIDRef attribute --
    # without this pass the imported definition exists but the ref still
    # points at the target's raw id.
    _apply_remaps(char_pr_clones, **remap_kwargs)
    _apply_remaps(style_clones, **remap_kwargs)
    # Font remap is shaped differently (per-lang dicts, not one flat dict)
    # and only ever touches a charPr's own fontRef child -- applied
    # separately, only to the charPr clones.
    _apply_font_remap(char_pr_clones, fonts)

    # HwpxOxmlDocument.char_properties is a lazily-built, explicitly-cached
    # dict (unlike every other header table this module touches, which is
    # computed fresh on every access) -- appending new hh:charPr elements
    # straight to the header's lxml tree (as every remap function here does)
    # does not itself invalidate it. Confirmed by live testing against
    # hwpx.tools.id_integrity.check_id_integrity, which reads through this
    # exact cache and (correctly) reported the newly-merged charPr ids as
    # dangling until this call was added -- the facade methods that
    # normally create charPr items (HwpxOxmlHeader.ensure_char_property)
    # already call this after mutating; this module must too.
    if char_pr:
        owning_document = target_header.document
        if owning_document is not None:
            owning_document.invalidate_char_property_cache()

    for copy in copies:
        _refresh_copied_paragraph_subtree_ids(copy)
    # memo_clones already had _refresh_copied_paragraph_subtree_ids applied
    # to each individually inside _copy_referenced_memos (needed there, to
    # give each clone a fresh memo id + fresh nested paraList paragraph ids
    # before axis-1 scanning reads them) -- not repeated here.
    bookmark_names = _existing_bookmark_names(target)
    _refresh_field_and_bookmark_ids(copies, bookmark_names)
    # The field's OWN "ID"/"MemoShapeIDRef" hp:stringParam text values --
    # not attributes, so _apply_remaps never touches them -- get their own
    # pass, using the id map _copy_referenced_memos already built plus the
    # memoShapeIDRef remap dict computed above.
    _apply_memo_field_param_remaps(copies, memo_id=memo_id_map, memo_shape=memo_shape)

    report = {
        "paragraphsInserted": len(copies),
        "sectionPropertiesStripped": stripped_section_properties,
        "memosCopied": len(memo_clones),
        "remapped": {
            "charPr": len(char_pr),
            "paraPr": len(para_pr),
            "style": len(style),
            "borderFill": len(border_fill),
            "tabPr": len(tab_pr),
            "memoShape": len(memo_shape),
            "binaryItem": len(binary_item),
            "numbering": len(headings.get("numbering", {})),
            "bullet": len(headings.get("bullet", {})),
            "font": sum(len(m) for m in fonts.values()),
        },
    }
    return copies, memo_clones, report


def _remap_styles(
    source_header: Any, target_header: Any, paragraphs: list[Any]
) -> tuple[dict[str, str], list[Any]]:
    """Returns (old_id -> new_id, the newly-created style clones).

    The clones are returned so the caller can also remap ``hh:style``'s own
    internal references (``nextStyleIDRef``/``charStyleIDRef``, both target
    the same ``styles`` space; ``paraPrIDRef``/``charPrIDRef``, which a
    style also carries directly) -- these live on the style item itself,
    not on any body paragraph.
    """

    used = _used_ids(paragraphs, "styleIDRef")
    if not used:
        return {}, []
    source_container = source_header._styles_element()
    target_container = target_header._styles_element(create=True)
    if source_container is None:
        return {}, []
    remap: dict[str, str] = {}
    clones: list[Any] = []
    for old_id in sorted(used):
        item = next(
            (c for c in source_container.findall(f"{_HH}style") if c.get("id") == old_id), None
        )
        if item is None:
            continue
        new_id = target_header._allocate_style_id(target_container)
        clone = _deep_copy_element(item)
        clone.set("id", new_id)
        target_container.append(clone)
        target_header._update_item_count(target_container, f"{_HH}style")
        remap[old_id] = new_id
        clones.append(clone)
    return remap, clones


# ================================================================================
# public entry points
# ================================================================================


def append_document(
    target: HwpxDocument,
    source: HwpxDocument | str | Path,
    *,
    target_section_index: int = -1,
    source_section_index: int | None = None,
    keep_character_shape: bool = True,
    keep_style: bool = True,
    keep_paragraph_shape: bool = True,
    keep_page_shape: bool = False,
) -> dict[str, Any]:
    """Append *source*'s paragraphs to the end of *target*'s section.

    *source* may be an already-open :class:`HwpxDocument` (not closed by
    this function -- caller's document, caller's lifecycle) or a path (opened
    and closed internally). *source_section_index* limits the copy to one
    source section; ``None`` (default) copies all of them, in order.

    *keep_character_shape*/*keep_style*/*keep_paragraph_shape*/
    *keep_page_shape* name the same 4 axes Hancom's own "문서 끼워 넣기"
    dialog exposes -- their defaults match this module's shipped, real-
    Hancom-verified behavior. Passing a non-default value raises
    ``HwpxValueError`` (code ``document-merge-unsupported-policy-axis``):
    see ``docs/2026-08-08-document-merge-contract.md``'s 정책 4축 section
    for why the opposite direction of each axis is honestly deferred
    rather than guessed.
    """

    _validate_merge_policy_axes(
        keep_character_shape=keep_character_shape,
        keep_style=keep_style,
        keep_paragraph_shape=keep_paragraph_shape,
        keep_page_shape=keep_page_shape,
    )
    if isinstance(source, HwpxDocument):
        opened_here = False
        source_doc = source
    else:
        opened_here = True
        source_doc = HwpxDocument.open(source)
    try:
        copies, memo_clones, report = _merge_paragraphs(
            target, source_doc, source_section_index=source_section_index,
        )
        target_section = target.sections[target_section_index]
        if copies:
            index = len(target_section.paragraphs)
            target_section.insert_paragraphs(index, copies)
        _insert_memos_into_target_section(target_section, memo_clones)
        report["position"] = "end"
        report["targetSectionIndex"] = target_section_index
        return report
    finally:
        if opened_here:
            source_doc.close()


def insert_document(
    target: HwpxDocument,
    source: HwpxDocument | str | Path,
    *,
    after_paragraph_index: int,
    target_section_index: int = 0,
    source_section_index: int | None = None,
    keep_character_shape: bool = True,
    keep_style: bool = True,
    keep_paragraph_shape: bool = True,
    keep_page_shape: bool = False,
) -> dict[str, Any]:
    """Insert *source*'s paragraphs into *target* after a given paragraph.

    ``after_paragraph_index`` is the index (within ``target.sections[
    target_section_index]``) of the paragraph the copied content is
    inserted after -- ``-1`` inserts before the first paragraph. See
    :func:`append_document` for *source*/*source_section_index*/the 4
    merge-policy axis parameters.
    """

    _validate_merge_policy_axes(
        keep_character_shape=keep_character_shape,
        keep_style=keep_style,
        keep_paragraph_shape=keep_paragraph_shape,
        keep_page_shape=keep_page_shape,
    )
    if isinstance(source, HwpxDocument):
        opened_here = False
        source_doc = source
    else:
        opened_here = True
        source_doc = HwpxDocument.open(source)
    try:
        copies, memo_clones, report = _merge_paragraphs(
            target, source_doc, source_section_index=source_section_index,
        )
        target_section = target.sections[target_section_index]
        total = len(target_section.paragraphs)
        if not -1 <= after_paragraph_index < total:
            raise HwpxValueError(
                f"after_paragraph_index {after_paragraph_index} out of range "
                f"(target section has {total} paragraphs)",
                code="document-merge-index-out-of-range",
                context={"afterParagraphIndex": after_paragraph_index, "paragraphCount": total},
                suggestion="Use -1 to insert before the first paragraph, or 0..N-1.",
            )
        if copies:
            target_section.insert_paragraphs(after_paragraph_index + 1, copies)
        _insert_memos_into_target_section(target_section, memo_clones)
        report["position"] = "after_paragraph"
        report["afterParagraphIndex"] = after_paragraph_index
        report["targetSectionIndex"] = target_section_index
        return report
    finally:
        if opened_here:
            source_doc.close()
