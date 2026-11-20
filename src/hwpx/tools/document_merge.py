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
import itertools
from pathlib import Path
from typing import Any

from .._document.media import _find_binary_item, add_image
from ..document import HwpxDocument
from ..errors import HwpxValueError
from ..oxml.field_marks import field_type_id
from ..oxml._document_primitives import (
    IdSource,
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
#: Connectors and charts are carried since objlim: a chart part takes the first ``Chart/chartN.xml`` the target
#: does not use (Hancom 2024's 문서 끼워 넣기, evidence merge2), a connector stays attached to the shapes it joined,
#: which come along with their new instance ids (see :func:`_carry_connectors_and_charts`).
_REJECTED_LOCAL_TAGS: tuple[str, ...] = ()
_REJECTED_ATTRS = ("linkListIDRef", "linkListNextIDRef")
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
    used = set(_used_ids(paragraphs, "memoShapeIDRef"))
    # A memo kept in its MEMO field names its shape in the field's MemoShapeIDRef parameter
    # (element text, not an attribute); 65535 is "no shape" and names none.
    for paragraph in paragraphs:
        for param in paragraph.iter(f"{_HP}stringParam"):
            if param.get("name") == "MemoShapeIDRef" and param.text and param.text != "65535":
                used.add(param.text)
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
    source_header: Any, target_header: Any, para_pr_clones: list[Any],
    known: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Returns {"numbering": {old: new}, "bullet": {old: new}}.

    Scans *para_pr_clones* (the already-copied paraPr items, from
    :func:`_remap_para_properties` -- not the body paragraphs) for nested
    ``hh:heading`` children, since that is where the reference actually
    lives. A source definition *known* already maps to (an earlier copy from the same
    document brought it) is mapped there again instead of copied anew: Hancom counts a
    numbering per definition, so paragraphs copied one by one keep counting on as one list.
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
            earlier = (known or {}).get(space, {}).get(old_id)
            if earlier is not None and any(c.get("id") == earlier for c in target_container.findall(f"{_HH}{space}")):
                result[space][old_id] = earlier
                continue
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
    remap: dict[str, str] = {}
    for old_id in sorted(used):
        raw, fmt = _binary_item_data(source_doc, old_id)
        listed = next((item for item in source_doc._package._manifest_items() if item.get("id") == old_id), None)
        media_type = (listed.get("media-type") or "") if listed is not None else ""
        if not media_type or media_type.startswith("image/"):
            remap[old_id] = str(add_image(target_doc, raw, fmt))
            continue
        # Not a picture (an OLE object, as a chart keeps one): written as the source lists it -- its
        # media type and ``isEmbeded`` -- not as an embedded image.
        assert listed is not None
        listed_there = target_doc._package._manifest_items()
        taken = {item.get("id") for item in listed_there}
        stored = {str(item.get("href") or "") for item in listed_there} | set(target_doc._package.part_names())
        new_id = next(
            name for name in (f"BIN{number:04d}" for number in itertools.count(1))
            if name not in taken and f"BinData/{name}.{fmt}" not in stored
        )
        path = f"BinData/{new_id}.{fmt}"
        target_doc._package.write(path, raw)
        target_doc._package.add_manifest_item(
            new_id, path, media_type,
            extra_attrs={name: value for name, value in listed.attrib.items() if name not in ("id", "href", "media-type")},
        )
        remap[old_id] = new_id
    return remap


def _binary_item_data(source_doc: HwpxDocument, item_id: str) -> tuple[bytes, str]:
    """The data and format of the binary item *item_id* names in *source_doc*: listed in the header
    (``hh:binItem``) or, as Hancom saves a picture, in the package manifest alone. An item that cannot
    be read is refused (:func:`_reject_what_cannot_be_carried` does so before the target is touched):
    left in the copy under its old id, the reference named whatever item of that id the receiving
    document has -- another picture -- or nothing."""

    found = _find_binary_item(source_doc, item_id)
    path = found.bin_data_path if found is not None else None
    try:
        raw = source_doc.package.read(path) if path else None
    except KeyError:
        raw = None
    if not raw or path is None:
        raise HwpxValueError(
            f"the source document has no data for the binary item {item_id!r} its content points at",
            code="document-merge-unsupported-reference",
            context={"attribute": "binaryItemIDRef", "value": item_id},
            suggestion="Repair or remove the picture in the source document before copying from it.",
        )
    return raw, (Path(path).suffix.lstrip(".") or "png").lower()


_TRACK_MARKS = tuple(f"{_HP}{name}" for name in ("insertBegin", "insertEnd", "deleteBegin", "deleteEnd"))


def _tracked_change_ids(paragraphs: list[Any]) -> list[str]:
    """The change ids the tracked-change marks in *paragraphs* carry, in document order."""

    seen: dict[str, None] = {}
    for paragraph in paragraphs:
        for node in paragraph.iter(*_TRACK_MARKS):
            if node.get("TcId"):
                seen.setdefault(str(node.get("TcId")))
    return list(seen)


def _reject_what_cannot_be_carried(source: HwpxDocument, paragraphs: list[Any], target: HwpxDocument) -> None:
    """Refuse, before the receiving document is touched, content whose references cannot follow it:
    a picture the source has no data for, tracked changes without a definition in the source's
    header or of a kind that is not written (a character or paragraph shape change), and tracked
    changes whose author would be given a number the receiving document's changes already carry."""

    for item_id in sorted(_used_ids(paragraphs, "binaryItemIDRef")):
        _binary_item_data(source, item_id)
    definitions = source.oxml.track_changes
    if any(not node.get("TcId") for paragraph in paragraphs for node in paragraph.iter(*_TRACK_MARKS)):
        raise HwpxValueError(
            "a tracked-change mark in the copied content names no change",
            code="document-merge-unsupported-reference",
            context={"attribute": "TcId", "value": None},
            suggestion="Accept or reject that change in the source document first.",
        )
    for change_id in _tracked_change_ids(paragraphs):
        entry = definitions.get(change_id)
        if entry is None or str(getattr(entry, "change_type", None) or "").lower() not in ("insert", "delete"):
            raise HwpxValueError(
                f"the tracked change {change_id!r} in the copied content cannot be carried across",
                code="document-merge-unsupported-reference",
                context={"attribute": "TcId", "value": change_id},
                suggestion="Accept or reject that change in the source document first.",
            )
    _reject_an_author_number_already_carried(source, target, _tracked_change_ids(paragraphs))
    for attribute in ("charTcId", "paraTcId"):
        if _used_ids(paragraphs, attribute):
            raise HwpxValueError(
                f"document insert does not support {attribute!r} yet",
                code="document-merge-unsupported-reference",
                context={"attribute": attribute},
                suggestion="Accept or reject the shape changes in the source document first.",
            )


def _reject_an_author_number_already_carried(source: HwpxDocument, target: HwpxDocument, change_ids: list[str]) -> None:
    """Refuse changes whose author is new to *target* when the number that author would get is one
    its changes already carry without an author of that number.

    A document Hancom saved numbers its only author 0 and writes ``authorID="1"`` on that author's
    changes (``reader_writer__ChangeTrack``), and one that has been through an .hwp save carries numbers
    of its own. The next author added is given the number after the last author's; where changes carry
    that number already, they would read as the new author's from then on, and rejecting the new
    author's changes would reject theirs. Numbers a document already carries are not rewritten here
    (they only stay right across an .hwp save if left alone), so the content is not carried in."""

    from .._document.tracked import _resolved_author_name

    if not change_ids:
        return
    authors = target.oxml.track_change_authors
    known = {str(getattr(author, "name", "") or "") for author in authors.values()}
    definitions = source.oxml.track_changes
    joining = {
        name for name in (
            _resolved_author_name(source, definitions[change_id].author_id) or "AI Agent"
            for change_id in change_ids if change_id in definitions
        ) if name not in known
    }
    if not joining:
        return
    numbers = [int(key) for key in authors if str(key).isdigit()]
    first = max(numbers) + 1 if numbers else 1  # as the header numbers a new author
    carried = {
        int(change.author_id)
        for change in target.oxml.track_changes.values()
        if isinstance(change.author_id, int) and str(change.author_id) not in {str(key) for key in authors}
    }
    taken = sorted(carried & set(range(first, first + len(joining))))
    if taken:
        raise HwpxValueError(
            "the receiving document's tracked changes carry an author number "
            f"({taken[0]}) the incoming author would be given",
            code="document-merge-unsupported-reference",
            context={"attribute": "authorID", "value": taken[0]},
            suggestion="Accept or reject the tracked changes in one of the two documents first.",
        )


def _carry_tracked_changes(source: HwpxDocument, target: HwpxDocument, copies: list[Any]) -> int:
    """Give the tracked changes in *copies* definitions in *target*: each change the marks name is added
    to the receiving header under a new id, with its kind, author and date, and the marks follow it
    (``TcId``) with mark numbers of the receiving document (``Id``). Kept under the source's numbers, a
    mark named whatever change of that number the receiving document has -- so rejecting one's own
    change removed the text of somebody else's -- or none."""

    from .._document.tracked import _resolved_author_name

    change_ids = _tracked_change_ids(copies)
    if not change_ids:
        return 0
    definitions = source.oxml.track_changes
    renewed: dict[str, str] = {}
    for change_id in change_ids:
        entry = definitions[change_id]
        renewed[change_id] = str(
            target._root.add_track_change(
                str(entry.change_type),  # checked before the merge began: defined, and Insert or Delete
                author_name=_resolved_author_name(source, entry.author_id) or "AI Agent",
                date=entry.date,
                show=False,  # the receiving document keeps showing or hiding changes as it did
            )
        )
    next_mark = target._root.next_track_change_mark_id()
    marks: dict[tuple[str, str], str] = {}
    for copy in copies:
        for node in copy.iter(*_TRACK_MARKS):
            old_change = node.get("TcId")
            if old_change not in renewed:
                continue
            key = (str(old_change), node.get("Id") or "")
            if key not in marks:
                marks[key] = str(next_mark)
                next_mark += 1
            node.set("TcId", renewed[str(old_change)])
            if node.get("Id") is not None:
                node.set("Id", marks[key])
    return len(renewed)


def _follow_clones(copies: list[Any], clones: list[Any]) -> None:
    """Re-point the connectors in *clones* (the section's own copies of *copies*, made by
    ``insert_paragraphs`` with fresh instance ids) at the shapes' new ids there."""

    renewed: dict[str, str] = {}
    for copy, clone in zip(copies, clones):
        for before, after in zip(copy.iter(), clone.iter()):
            old = before.get("instid")
            if old not in (None, "", "0"):
                renewed[str(old)] = str(after.get("instid"))
    _reattach_connectors(clones, renewed)


def _reattach_connectors(paragraphs: list[Any], renewed: dict[str, str]) -> None:
    """Point every connector end in the copied *paragraphs* at the new instance id of the shape it joined
    (*renewed*: old id to new). Hancom 2024's own 문서 끼워 넣기 let the ends go (``subjectIDRef="0"``, objlim
    merge) and then drew no connector at all (its page image shows the two shapes without it); a connector
    attached to shapes is the form Hancom keeps when it saves a document (keepsrc), so the copy stays attached.
    An end whose shape did not come along lets go."""

    for paragraph in paragraphs:
        for node in paragraph.iter(f"{_HP}startPt", f"{_HP}endPt"):
            subject = node.get("subjectIDRef")
            if subject not in (None, "", "0"):
                node.set("subjectIDRef", renewed.get(subject, "0"))


def _carry_connectors_and_charts(source: HwpxDocument, target: HwpxDocument, paragraphs: list[Any]) -> None:
    """Carry the charts in the copied *paragraphs* as Hancom 2024's 문서 끼워 넣기 does (objlim evidence merge2):
    each chart's part is written to the first ``Chart/chartN.xml`` the target does not use, the chart pointing
    at it. (Connectors follow their shapes: :func:`_reattach_connectors`.)"""

    for paragraph in paragraphs:
        for node in paragraph.iter():
            chart = node.get("chartIDRef")
            if not chart or not source._package.has_part(chart):
                continue
            used = {name for name in target._package.part_names() if name.startswith("Chart/")}
            number = 1
            while f"Chart/chart{number}.xml" in used:
                number += 1
            name = f"Chart/chart{number}.xml"
            target._package.write(name, source._package.read(chart))
            node.set("chartIDRef", name)


def _deep_copy_element(element: Any) -> Any:
    return _copy.deepcopy(element)


# ================================================================================
# document-local structural id refresh (축 3) -- extends
# _refresh_copied_paragraph_subtree_ids (which already handles paragraph/
# object/instId) with the ids it deliberately leaves alone: memo, field
# begin/end pairing, bookmark name collisions.
# ================================================================================



def _pair_field_end(node: Any, begin_map: dict[str, tuple[str, str | None]],
                    begin_fieldid_map: dict[str, str]) -> bool:
    """Point the copied ``hp:fieldEnd`` *node* at the new id of the begin it names; False when no begin
    of that id has been seen (its ``fieldid`` alone follows then, when one is known)."""

    paired = begin_map.get(node.get("beginIDRef") or "")
    old_end_fieldid = node.get("fieldid")
    if paired is None:
        if old_end_fieldid and old_end_fieldid in begin_fieldid_map:
            node.set("fieldid", begin_fieldid_map[old_end_fieldid])
        return False
    new_id, new_fieldid = paired
    node.set("beginIDRef", new_id)
    if old_end_fieldid and new_fieldid is not None:
        node.set("fieldid", new_fieldid)
    return True


def _refresh_field_and_bookmark_ids(
    paragraphs: list[Any], existing_bookmark_names: set[str], *, ids: "IdSource | None"
) -> None:
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

    # The map spans every copied paragraph, not one: Hancom forms carry
    # click-here fields whose fieldEnd sits paragraphs after its fieldBegin
    # (a real public form: begin in paragraph 14, end in 18). Per-paragraph
    # maps renamed the begin but left the end pointing at the old id, and
    # Hancom drops such an unpaired fieldEnd when it saves.
    # A fieldEnd takes its new fieldid from the fieldBegin its beginIDRef
    # names: Hancom's own files give every field of a type the same fieldid
    # (CLICK_HERE 627272811, MEMO 623209829), so a map keyed by the old
    # fieldid would hand one field's value to another field's end.
    begin_map: dict[str, tuple[str, str | None]] = {}
    begin_fieldid_map: dict[str, str] = {}
    early_ends: list[Any] = []
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
        for node in paragraph.iter():
            if _local_name(node.tag) == "fieldBegin":
                old_id = node.get("id")
                new_id = _object_id(ids)
                node.set("id", new_id)
                new_fieldid = None
                old_fieldid = node.get("fieldid")
                if old_fieldid:
                    # Hancom's fieldid is the field type's control id, the same for
                    # every field of the type; a type without one gets a new id.
                    new_fieldid = field_type_id(node.get("type"), ids=ids)
                    begin_fieldid_map.setdefault(old_fieldid, new_fieldid)
                    node.set("fieldid", new_fieldid)
                if old_id:
                    begin_map[old_id] = (new_id, new_fieldid)
            elif _local_name(node.tag) == "fieldEnd":
                # In document order, with the begins: an end follows the begin before it. A source that
                # uses one id for two fields in a row (Hancom saves such files) had both ends pointed at
                # the second begin, since the ends were mapped after every begin had been.
                if not _pair_field_end(node, begin_map, begin_fieldid_map):
                    early_ends.append(node)
    for node in early_ends:  # an end in front of its begin: the begin is known now
        _pair_field_end(node, begin_map, begin_fieldid_map)

    for paragraph in paragraphs:
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
    ``hp:secPr`` and each ``hp:colPr`` specifically (never any other control
    sharing the same run) is removed individually, and the run itself is only
    dropped if that leaves it completely empty -- preserving the original
    single-element-run behavior exactly while no longer touching unrelated
    siblings. The same holds inside one ``hp:ctrl``: some Hancom files put a
    click-here ``hp:fieldBegin`` or a page-number restart in the ``hp:ctrl``
    that holds ``hp:colPr``, so only ``hp:colPr`` leaves it, and the
    ``hp:ctrl`` goes only when that empties it (dropping the whole ``hp:ctrl``
    left the field's ``hp:fieldEnd`` unpaired, and Hancom cannot open that).

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
                colpr = ctrl.find(f"{_HP}colPr")
                if colpr is None:
                    continue
                ctrl.remove(colpr)
                if len(ctrl) == 0:
                    run.remove(ctrl)
            if len(run) == 0:
                paragraph.remove(run)
    return removed


def _move_section_setup_to_first_paragraph(section: Any) -> bool:
    """Keep the target's ``hp:secPr`` in its section's first paragraph.

    ``insert_document(..., after_paragraph_index=-1)`` puts the copies in
    front of the paragraph that carries the section setup. Hancom reads a
    ``hp:secPr`` that is not in a section's first paragraph as the start of a
    new section: the inserted paragraphs become a section of their own with
    default page setup, and a page break appears before the old first
    paragraph. So the ``hp:secPr`` and the ``hp:colPr`` move, element by
    element as in :func:`_strip_embedded_section_properties`, into a new
    leading run of the first paragraph. An ``hp:ctrl`` that holds only
    ``hp:colPr`` moves whole; other controls in it stay where they are.
    Returns whether anything moved.
    """

    paragraphs = [p.element for p in section.paragraphs]
    if not paragraphs or paragraphs[0].find(f"{_HP}run/{_HP}secPr") is not None:
        return False
    first = paragraphs[0]
    for paragraph in paragraphs[1:]:
        for run in paragraph.findall(f"{_HP}run"):
            secpr = run.find(f"{_HP}secPr")
            if secpr is None:
                continue
            moving = [secpr]
            for ctrl in run.findall(f"{_HP}ctrl"):
                colpr = ctrl.find(f"{_HP}colPr")
                if colpr is None:
                    continue
                if len(ctrl) == 1:
                    moving.append(ctrl)
                else:
                    ctrl.remove(colpr)
                    own = ctrl.makeelement(f"{_HP}ctrl", {})
                    own.append(colpr)
                    moving.append(own)
            setup_run = first.makeelement(f"{_HP}run", {"charPrIDRef": run.get("charPrIDRef", "0")})
            for node in moving:
                if node.getparent() is run:
                    run.remove(node)
                setup_run.append(node)
            if len(run) == 0 and len(paragraph.findall(f"{_HP}run")) > 1:
                paragraph.remove(run)
            first.insert(0, setup_run)
            return True
    return False


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
    source: HwpxDocument, source_paragraphs: list[Any], *, ids: "IdSource | None"
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
            # A memo kept only in its MEMO field (Hancom's form, and python-hwpx's since 7.0) travels
            # with the copied field; it takes a new id like a memo-group memo does.
            memo_id_map[old_id] = _memo_id(ids)
            continue
        clone = _deep_copy_element(memo)
        new_id = _memo_id(ids)
        clone.set("id", new_id)
        memo_id_map[old_id] = new_id
        _refresh_copied_paragraph_subtree_ids(clone, ids=ids)
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

    # 7.0: Hancom keeps a memo only in its MEMO field (the field's hp:subList) and writes no
    # hp:memogroup, so each memo clone goes into the copied field that names it (already in
    # *target_section*), not into a memo group. A clone no copied field names is not written.
    if not memo_clones:
        return
    from ..oxml.memo import _fill_field_from_entry, memo_field_id, memo_fields_in

    fields = {memo_field_id(field): field for field in memo_fields_in(target_section.element)}
    for clone in memo_clones:
        field = fields.get(clone.get("id"))
        if field is not None:
            _fill_field_from_entry(field, clone)
    target_section.mark_dirty()


#: The header lists a copy reuses equal definitions from, in the order they are folded: fonts, border fills
#: and tab definitions first, since the character and paragraph shapes refer to them, and those before the
#: styles, which refer to them.
_REUSED_DEFINITIONS = (
    ("borderFills", "borderFill", "borderFillIDRef"),
    ("tabProperties", "tabPr", "tabPrIDRef"),
    ("charProperties", "charPr", "charPrIDRef"),
    ("paraProperties", "paraPr", "paraPrIDRef"),
    ("styles", "style", "styleIDRef"),
)


def _definition_list(header: Any, list_name: str) -> Any:
    root = header.element
    return next((node for node in root.iter() if isinstance(node.tag, str)
                 and _local_name(node.tag) == list_name), None)


def _children_named(holder: Any, name: str) -> list[Any]:
    return [node for node in holder if isinstance(node.tag, str) and _local_name(node.tag) == name]


def _definition_ids(header: Any) -> dict[str, set[str]]:
    """The ids each reused list of *header* holds now (fonts per language), before a copy adds to it."""

    ids: dict[str, set[str]] = {}
    for list_name, item_name, _ref in _REUSED_DEFINITIONS:
        holder = _definition_list(header, list_name)
        ids[item_name] = {str(node.get("id")) for node in _children_named(holder, item_name)} \
            if holder is not None else set()
    faces = _definition_list(header, "fontfaces")
    for face in _children_named(faces, "fontface") if faces is not None else ():
        ids["font:" + str(face.get("lang"))] = {str(node.get("id")) for node in _children_named(face, "font")}
    return ids


#: How definitions name each other: the attribute -> the ids it may hold, each read as the first id of the
#: header's definitions that are the same but for their ids (``"font:<LANG>"`` for an ``hh:fontRef``'s fonts).
_Aliases = dict[str, dict[str, str]]


def _definition_key(element: Any, aliases: "_Aliases | None" = None) -> bytes:
    """*element* as canonical XML without its ``id`` (a style's ``nextStyleIDRef`` to itself read as such):
    two definitions with the same key mean the same.

    With *aliases*, each reference to another definition is read as the first of the definitions equal to
    it: a header holding two equal fonts (Hancom writes 함초롬바탕 twice in the HANJA face of many documents,
    ids 0 and 6) has one character shape naming font 0 and another naming font 6 that mean the same."""

    from lxml import etree  # type: ignore[reportMissingImports]  # lxml has no complete bundled typing, as everywhere in hwpx

    clone = etree.fromstring(etree.tostring(element))
    own = clone.attrib.pop("id", None)
    if own is not None and clone.get("nextStyleIDRef") == own:
        clone.set("nextStyleIDRef", "itself")
    clone.tail = None
    if aliases:
        for node in clone.iter():
            if not isinstance(node.tag, str):
                continue
            fonts = _local_name(node.tag) == "fontRef"
            for name, value in list(node.attrib.items()):
                table = aliases.get("font:" + _FONT_REF_TO_FACE_LANG.get(name, "")) if fonts else aliases.get(name)
                if table and value in table:
                    node.set(name, table[value])
    return etree.tostring(clone, method="c14n")


def _equal_classes(items: list[Any], aliases: "_Aliases | None") -> dict[str, str]:
    """Each item's id -> the id of the first item the same as it (but for ids)."""

    first: dict[bytes, str] = {}
    classes: dict[str, str] = {}
    for node in items:
        own = str(node.get("id"))
        classes[own] = first.setdefault(_definition_key(node, aliases), own)
    return classes


def _fold(holder: Any, items: list[Any], before: set[str], aliases: "_Aliases | None" = None) -> dict[str, str]:
    """Fold the items of *holder* not in *before* into earlier equal ones, number the rest on from *before*;
    the id changes (old -> new). *aliases*: as :func:`_definition_key` reads references."""

    known: dict[bytes, str] = {}
    for node in items:
        if str(node.get("id")) in before:
            known.setdefault(_definition_key(node, aliases), str(node.get("id")))
    numbers = [int(i) for i in before if i.lstrip("-").isdigit()]
    next_id = max(numbers) + 1 if numbers else 0
    mapping: dict[str, str] = {}
    for node in items:
        old = str(node.get("id"))
        if old in before:
            continue
        key = _definition_key(node, aliases)
        same = known.get(key)
        if same is not None:
            mapping[old] = same
            holder.remove(node)
            continue
        known[key] = str(next_id)
        if old != str(next_id):
            mapping[old] = str(next_id)
            node.set("id", str(next_id))
        next_id += 1
    return mapping


def _reuse_equal_definitions(header: Any, before: dict[str, set[str]], scope: list[Any]) -> None:
    """Fold each definition this copy added to *header* (an id not in *before*) into one the header already
    had that is the same but for its id, pointing the references in *scope* (the copied paragraphs, memos
    and the definitions copied with them) at it; the definitions left are numbered on from the ones before,
    so the ids stay without gaps."""

    aliases: _Aliases = {}
    faces = _definition_list(header, "fontfaces")
    for face in _children_named(faces, "fontface") if faces is not None else ():
        lang = str(face.get("lang"))
        mapping = _fold(face, _children_named(face, "font"), before.get("font:" + lang, set()))
        aliases["font:" + lang] = _equal_classes(_children_named(face, "font"), None)
        if not mapping:
            continue
        attributes = [attr for attr, face_lang in _FONT_REF_TO_FACE_LANG.items() if face_lang == lang]
        for root in scope:
            for node in root.iter(f"{_HH}fontRef"):
                for attr in attributes:
                    if node.get(attr) in mapping:
                        node.set(attr, mapping[str(node.get(attr))])
        if face.get("fontCnt") is not None:
            face.set("fontCnt", str(len(_children_named(face, "font"))))
    for list_name, item_name, ref in _REUSED_DEFINITIONS:
        holder = _definition_list(header, list_name)
        if holder is None:
            continue
        mapping = _fold(holder, _children_named(holder, item_name), before[item_name], aliases)
        refs = (ref, "nextStyleIDRef", "charStyleIDRef") if item_name == "style" else (ref,)
        classes = _equal_classes(_children_named(holder, item_name), aliases)
        for name in refs:
            aliases[name] = classes
        if not mapping:
            continue
        for root in scope:
            for node in root.iter():
                if not isinstance(node.tag, str):
                    continue
                for name in refs:
                    value = node.get(name)
                    if value is not None and value in mapping:
                        node.set(name, mapping[value])
        if holder.get("itemCnt") is not None:
            holder.set("itemCnt", str(len(_children_named(holder, item_name))))


def _merge_paragraphs(
    target: HwpxDocument,
    source: HwpxDocument,
    *,
    source_section_index: int | None,
    paragraphs: list[Any] | None = None,
    known_headings: dict[str, dict[str, str]] | None = None,
) -> tuple[list[Any], list[Any], dict[str, Any]]:
    """Deep-copy source paragraphs (*paragraphs*, elements of *source*, or else those of its sections),
    remap every reference, return (paragraph elements, memo clones, report)."""

    if paragraphs is not None:
        source_paragraphs = list(paragraphs)
    else:
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
    # Checked on copies that draw no id from the receiving document: a refusal leaves it as it was,
    # the ids it will hand out next (with a seed) among that.
    _reject_what_cannot_be_carried(
        source, [*source_paragraphs, *_copy_referenced_memos(source, source_paragraphs, ids=None)[1]], target
    )
    ids = target._root._id_source  # new ids are the receiving document's
    memo_id_map, memo_clones = _copy_referenced_memos(source, source_paragraphs, ids=ids)

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
    # front, since a merge may add definitions (those not already there) and essentially every
    # non-empty merge touches the header (even a bare styleIDRef="0"
    # reference copies that default style under a fresh id).
    target_header.mark_dirty()
    before_merge = _definition_ids(target_header)

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
    _carry_tracked_changes(source, target, copies)
    _carry_connectors_and_charts(source, target, remap_scope)
    instance_ids = [(node, node.get("instid")) for copy in copies for node in copy.iter()
                    if node.get("instid") not in (None, "", "0")]
    # hh:heading (numbering/bullet's own polymorphic idRef) lives inside the
    # just-copied paraPr items, not the body paragraphs -- scan those.
    headings = _remap_headings(source_header, target_header, para_pr_clones, known_headings)
    if known_headings is not None:
        for space, mapping in headings.items():
            known_headings.setdefault(space, {}).update(mapping)
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
    # A definition copied over that the target already has, the same in every respect but its id, is not
    # kept twice: the copy uses the target's (what hwpx-school's run transplant did; a later copy of
    # another paragraph does the same).
    _reuse_equal_definitions(target_header, before_merge,
                             copies + memo_clones + para_pr_clones + char_pr_clones + style_clones)

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
        _refresh_copied_paragraph_subtree_ids(copy, ids=ids)
    _reattach_connectors(copies, {old: str(node.get("instid")) for node, old in instance_ids})
    # memo_clones already had _refresh_copied_paragraph_subtree_ids applied
    # to each individually inside _copy_referenced_memos (needed there, to
    # give each clone a fresh memo id + fresh nested paraList paragraph ids
    # before axis-1 scanning reads them) -- not repeated here.
    bookmark_names = _existing_bookmark_names(target)
    _refresh_field_and_bookmark_ids(copies, bookmark_names, ids=ids)
    # The field's OWN "ID"/"MemoShapeIDRef" hp:stringParam text values --
    # not attributes, so _apply_remaps never touches them -- get their own
    # pass, using the id map _copy_referenced_memos already built plus the
    # memoShapeIDRef remap dict computed above.
    _apply_memo_field_param_remaps(copies, memo_id=memo_id_map, memo_shape=memo_shape)

    report = {
        "paragraphsInserted": len(copies),
        "sectionPropertiesStripped": stripped_section_properties,
        # every memo the copied paragraphs anchor: in a memo group (6.x documents) or in its field
        "memosCopied": len(memo_id_map),
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
            inserted = target_section.insert_paragraphs(index, copies)
            _follow_clones(copies, [paragraph.element for paragraph in inserted])
        _insert_memos_into_target_section(target_section, memo_clones)
        report["position"] = "end"
        report["targetSectionIndex"] = target_section_index
        return report
    finally:
        if opened_here:
            source_doc.close()


def _facade_of(root: Any) -> HwpxDocument | None:
    """A document view over the ``HwpxOxmlDocument`` *root* and the package it was read from."""

    package = getattr(getattr(root, "_manifest_source", None), "__self__", None)
    return None if package is None else HwpxDocument(package, root)


def copy_paragraph(source: Any, anchor: Any, *, before: bool = False) -> Any:
    """``paragraph.copy_to(anchor, before=)``: put a copy of the paragraph object *source* right after
    (*before*: before) the paragraph object *anchor* and return it.

    *anchor* may belong to another document. The copy is made as :func:`insert_document` copies a
    paragraph: the definitions its text and objects name (character and paragraph shapes, styles,
    borders and fills, tabs, numberings and bullets, fonts, memo shapes) become new definitions of
    *anchor*'s document, pictures bring their images and charts their parts, fields, bookmarks, objects
    and paragraphs get fresh ids, a memo anchored in it comes along in its field, and section settings
    stay behind. What :func:`insert_document` refuses is refused the same way
    (``document-merge-unsupported-reference``). In the same document the copy is the one
    ``paragraph.insert_after()`` makes. No line layout cache comes along. The document's footnotes and
    endnotes are numbered again in document order, as ``note.copy_to`` numbers them.
    """

    from ..oxml._document_primitives import _clone_paragraph_element
    from ..oxml._paragraph_text_edit import (
        insert_paragraph_copy,
        renumber_copied_fields,
        resolve_paragraph_in,
        section_setting_runs,
    )
    from ..oxml.memo import renew_copied_memos
    from ..oxml.note_authoring import renumber_notes_holding
    from ..oxml.paragraph import HwpxOxmlParagraph

    if not isinstance(before, bool):
        raise HwpxValueError(f"before must be True or False; got {before!r}", code="paragraph-invalid-type",
                             suggestion="Pass before=True to put the copy in front of the paragraph.")
    source = resolve_paragraph_in(source, source, caller="copy_to")
    if not isinstance(anchor, HwpxOxmlParagraph):
        from ..errors import HwpxTypeError

        raise HwpxTypeError(
            f"paragraph must be a paragraph object; got {type(anchor).__name__}",
            code="paragraph-invalid-type",
            context={"caller": "copy_to", "type": type(anchor).__name__},
            suggestion="Pass the paragraph to copy next to, e.g. other_doc.paragraphs[i] or cell.paragraphs[i].",
        )
    anchor = resolve_paragraph_in(anchor, anchor, caller="copy_to")
    source_root, target_root = source.section.document, anchor.section.document
    if source_root is target_root:
        copy = _clone_paragraph_element(source.element, ids=anchor.section._ids)
        renumber_copied_fields(copy, ids=anchor.section._ids)
        for run, settings in section_setting_runs(copy):
            for child in settings:
                run.remove(child)
            if len(run) == 0:
                copy.remove(run)
        insert_paragraph_copy(copy, anchor, before=before)
        sections = list(target_root.sections) if target_root is not None else [anchor.section]
        renew_copied_memos(copy, sections, anchor.section)
        from ..oxml.shape_position import unique_object_ids

        unique_object_ids(anchor.section, (copy,))
        renumber_notes_holding(anchor.section, (copy,))
        return HwpxOxmlParagraph(copy, anchor.section)
    source_doc, target_doc = _facade_of(source_root), _facade_of(target_root)
    if source_doc is None or target_doc is None:
        raise HwpxValueError(
            "copying a paragraph into another document needs both documents opened or created as documents",
            code="paragraph-not-in-document",
            suggestion="Open both with HwpxDocument.open(...) or make them with HwpxDocument.new().",
        )
    # Paragraphs copied one by one from one document keep one numbering: a later copy maps the
    # source's numbering and bullet definitions to the ones an earlier copy brought.
    import weakref

    holder: Any = target_root
    registry = getattr(holder, "_copied_headings", None)
    if registry is None:
        registry = weakref.WeakKeyDictionary()
        holder._copied_headings = registry
    known: dict[str, dict[str, str]] = registry.setdefault(source_root, {})
    copies, memo_clones, _report = _merge_paragraphs(
        target_doc, source_doc, source_section_index=None, paragraphs=[source.element], known_headings=known
    )
    copy = copies[0]
    insert_paragraph_copy(copy, anchor, before=before)
    _insert_memos_into_target_section(anchor.section, memo_clones)
    from ..oxml.shape_position import unique_object_ids

    unique_object_ids(anchor.section, (copy,))
    renumber_notes_holding(anchor.section, (copy,))
    return HwpxOxmlParagraph(copy, anchor.section)


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
        # Where it goes, first: a place that is not there was refused after the source's styles and
        # images had been merged into the target, which then saved another document's image.
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
        copies, memo_clones, report = _merge_paragraphs(
            target, source_doc, source_section_index=source_section_index,
        )
        moved_by_insert = False
        if copies:
            had_settings = after_paragraph_index == -1 and (
                target_section.paragraphs[0].element.find(f"{_HP}run/{_HP}secPr") is not None)
            inserted = target_section.insert_paragraphs(after_paragraph_index + 1, copies)
            _follow_clones(copies, [paragraph.element for paragraph in inserted])
            # insert_paragraphs at index 0 moves the section settings to the first copy itself.
            moved_by_insert = had_settings and inserted[0].element.find(f"{_HP}run/{_HP}secPr") is not None
        relocated = after_paragraph_index == -1 and bool(copies) and (
            _move_section_setup_to_first_paragraph(target_section) or moved_by_insert)
        if relocated:
            target_section.mark_dirty()
        _insert_memos_into_target_section(target_section, memo_clones)
        report["sectionPropertiesRelocated"] = relocated
        report["position"] = "after_paragraph"
        report["afterParagraphIndex"] = after_paragraph_index
        report["targetSectionIndex"] = target_section_index
        return report
    finally:
        if opened_here:
            source_doc.close()
