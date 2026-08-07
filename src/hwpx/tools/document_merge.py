# SPDX-License-Identifier: Apache-2.0
"""Document insertion/merge (문서 끼워 넣기, cycle 6.9 train 33).

Copies another HWPX document's body content into an already-open
``HwpxDocument``, remapping every header-owned shared-resource reference
(``charPrIDRef``/``paraPrIDRef``/``styleIDRef``/``borderFillIDRef``/
``tabPrIDRef``/``memoShapeIDRef``/``binaryItemIDRef``/the paragraph-heading
``idRef``) so the copied content keeps pointing at the *same values* it did
in the source document -- just via freshly-minted ids in the target's own
header, never colliding with (or silently aliasing onto) whatever the
target document already had at those id numbers. See
``docs/2026-08-08-document-merge-contract.md`` for the full id-reference
catalog this module was designed against, the v1 scope decision (no style
deduplication -- every referenced item is copied under a fresh id, even if
it looks identical to something the target already has), and the specific
references this v1 deliberately refuses to handle (``hp:connectLine``'s
``subjectIDRef``, linked-textbox chains, chart binary references) rather
than risk a silent, wrong remap.

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
#: hp:fieldBegin type values this v1 refuses to carry across documents.
#: MEMO was added after live testing (not assumed in advance) surfaced that
#: a memo's actual text lives in <hp:memogroup>, a *sibling* of the
#: paragraphs at the section level -- not nested inside the anchoring
#: paragraph at all (the paragraph only carries a fieldBegin/fieldEnd pair
#: whose "ID" stringParam matches hp:memogroup/hp:memo/@id). Copying only
#: the paragraphs this module operates on would silently drop the memo's
#: actual content while leaving a dangling-looking field marker behind --
#: exactly the silent-corruption shape this module exists to prevent.
#: Full memo support (copying the referenced memogroup entries, remapping
#: both the field's ID param and the memo's own id consistently) is real
#: but out of v1's explicit scope -- reported as a v13+ candidate.
_REJECTED_FIELD_TYPES = ("MEMO",)


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
            if _local_name(node.tag) == "fieldBegin" and node.get("type") in _REJECTED_FIELD_TYPES:
                raise HwpxValueError(
                    f"document insert does not support fieldBegin type={node.get('type')!r} yet",
                    code="document-merge-unsupported-reference",
                    context={"fieldType": node.get("type")},
                    suggestion=(
                        "See docs/2026-08-08-document-merge-contract.md's 보류 "
                        "section -- this field type's actual content lives "
                        "outside the paragraphs this module copies (e.g. memo "
                        "text lives in a sibling hp:memogroup), so copying the "
                        "paragraph alone would silently drop it."
                    ),
                )
            for attr in _REJECTED_ATTRS:
                if node.get(attr) is not None:
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
    for old_id in used:
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
    for old_id in used:
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


def _remap_border_fills(source_header: Any, target_header: Any, paragraphs: list[Any]) -> dict[str, str]:
    used = _used_ids(paragraphs, "borderFillIDRef")
    if not used:
        return {}
    source_container = source_header._border_fills_element()
    target_container = target_header._border_fills_element(create=True)
    if source_container is None:
        return {}
    remap: dict[str, str] = {}
    for old_id in used:
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


def _remap_tab_properties(source_header: Any, target_header: Any, paragraphs: list[Any]) -> dict[str, str]:
    used = _used_ids(paragraphs, "tabPrIDRef")
    if not used:
        return {}
    source_container = source_header._tab_properties_element()
    target_container = target_header._tab_properties_element(create=True)
    if source_container is None:
        return {}
    remap: dict[str, str] = {}
    for old_id in used:
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
    for old_id in used:
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
        for old_id in used:
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
        for old_id in used:
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
    for old_stem in used:
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
    pairing and bookmark names. Does NOT handle ``hp:memo`` -- real memo
    content never nests inside a paragraph at all (it lives in a sibling
    ``hp:memogroup``, see ``_REJECTED_FIELD_TYPES``'s docstring), so
    ``fieldBegin type="MEMO"`` is rejected upstream in
    :func:`_reject_unsupported_references` before this function ever runs.
    """

    for paragraph in paragraphs:
        # hp:fieldBegin/fieldEnd -- id/fieldid must both get fresh values,
        # and fieldEnd's beginIDRef must follow its OWN fieldBegin's new id
        # (pair integrity), not an independent fresh value.
        begin_id_map: dict[str, str] = {}
        for node in paragraph.iter():
            if _local_name(node.tag) == "fieldBegin":
                old_id = node.get("id")
                new_id = _object_id()
                if old_id:
                    begin_id_map[old_id] = new_id
                node.set("id", new_id)
                if node.get("fieldid"):
                    node.set("fieldid", _object_id())
        for node in paragraph.iter():
            if _local_name(node.tag) == "fieldEnd":
                old_begin = node.get("beginIDRef")
                if old_begin and old_begin in begin_id_map:
                    node.set("beginIDRef", begin_id_map[old_begin])

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
    """Remove any embedded section-setup run from the copied paragraphs.

    Discovered by live-testing a real merge (not assumed in advance): a
    section's *first* paragraph carries a dedicated, text-less ``hp:run``
    holding ``hp:secPr`` (the section's page setup -- margins, footnote/
    endnote policy, page border, etc) plus ``hp:ctrl/hp:colPr`` (column
    layout) as siblings; every other paragraph's runs carry only ``hp:t``.
    v1's merge always inserts into an *already-existing* target section (it
    never creates a new one), so a copied source paragraph is never the
    destination section's first paragraph -- carrying its section-setup run
    across would leave two ``hp:secPr`` in one ``hs:sec`` (a section should
    have exactly one) or, if inserted at index 0, silently replace the
    target's own page setup with the source's. ``hp:secPr`` also carries its
    own id-references (``outlineShapeIDRef`` -> numberings,
    ``memoShapeIDRef`` -> memoProperties, nested ``pageBorderFill/
    @borderFillIDRef`` -> borderFills) that no remap function in this module
    touches -- carrying it across unremapped would silently produce
    dangling/wrong references on top of the structural problem. v1's answer:
    the target's own secPr stays sole authority for its section's page
    setup, unconditionally -- source's is dropped, not merged or chosen
    between. Returns the number of section-setup runs removed (surfaced in
    the report so callers can see it happened, not just infer it).
    """

    removed = 0
    for paragraph in paragraphs:
        for run in list(paragraph.findall(f"{_HP}run")):
            if run.find(f"{_HP}secPr") is not None:
                paragraph.remove(run)
                removed += 1
    return removed


def _merge_paragraphs(
    target: HwpxDocument,
    source: HwpxDocument,
    *,
    source_section_index: int | None,
) -> tuple[list[Any], dict[str, Any]]:
    """Deep-copy source paragraphs, remap every reference, return (elements, report)."""

    source_sections = (
        [source.sections[source_section_index]] if source_section_index is not None
        else list(source.sections)
    )
    source_paragraphs = [p.element for section in source_sections for p in section.paragraphs]
    if not source_paragraphs:
        return [], {"paragraphsInserted": 0}

    _reject_unsupported_references(source_paragraphs)

    copies = [_deep_copy_element(p) for p in source_paragraphs]
    # A copied paragraph is never the destination section's first paragraph
    # (v1 always merges into an existing section) -- so any embedded
    # section-setup run (hp:secPr + hp:ctrl/hp:colPr) it carries is dropped
    # rather than carried across unremapped. See the function's own
    # docstring for the full reasoning (structural + unremapped-reference).
    stripped_section_properties = _strip_embedded_section_properties(copies)

    source_header = source.parts.headers[0]
    target_header = target.parts.headers[0]

    # A style's own base paraPr/charPr may not be independently referenced
    # by any body paragraph (a paragraph can point only at the style and
    # inherit its formatting implicitly) -- computed *before* the char/para
    # remap calls so their `used` sets can fold these ids in. See
    # _extra_ids_from_style_bases's docstring for the live-tested evidence.
    style_ids_used = _used_ids(copies, "styleIDRef")
    extra_char_ids, extra_para_ids = _extra_ids_from_style_bases(source_header, style_ids_used)

    char_pr, char_pr_clones = _remap_char_properties(
        source_header, target_header, copies, extra_ids=extra_char_ids
    )
    para_pr, para_pr_clones = _remap_para_properties(
        source_header, target_header, copies, extra_ids=extra_para_ids
    )
    style, style_clones = _remap_styles(source_header, target_header, copies)
    border_fill = _remap_border_fills(source_header, target_header, copies)
    tab_pr = _remap_tab_properties(source_header, target_header, copies)
    memo_shape = _remap_memo_properties(source_header, target_header, copies)
    binary_item = _remap_binary_items(source, target, source_header, target_header, copies)
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
    # Applied to the body paragraph copies (the normal case) AND to the
    # header item clones themselves -- a copied hh:paraPr can carry its own
    # tabPrIDRef/heading-idRef, and a copied hh:style can carry its own
    # paraPrIDRef/charPrIDRef/nextStyleIDRef/charStyleIDRef. Idempotent
    # dict-membership checks, so running it three times over disjoint
    # element sets is safe.
    _apply_remaps(copies, **remap_kwargs)
    _apply_remaps(para_pr_clones, **remap_kwargs)
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
    bookmark_names = _existing_bookmark_names(target)
    _refresh_field_and_bookmark_ids(copies, bookmark_names)

    report = {
        "paragraphsInserted": len(copies),
        "sectionPropertiesStripped": stripped_section_properties,
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
    return copies, report


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
    for old_id in used:
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
) -> dict[str, Any]:
    """Append *source*'s paragraphs to the end of *target*'s section.

    *source* may be an already-open :class:`HwpxDocument` (not closed by
    this function -- caller's document, caller's lifecycle) or a path (opened
    and closed internally). *source_section_index* limits the copy to one
    source section; ``None`` (default) copies all of them, in order.
    """

    if isinstance(source, HwpxDocument):
        opened_here = False
        source_doc = source
    else:
        opened_here = True
        source_doc = HwpxDocument.open(source)
    try:
        copies, report = _merge_paragraphs(
            target, source_doc, source_section_index=source_section_index,
        )
        target_section = target.sections[target_section_index]
        if copies:
            index = len(target_section.paragraphs)
            target_section.insert_paragraphs(index, copies)
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
) -> dict[str, Any]:
    """Insert *source*'s paragraphs into *target* after a given paragraph.

    ``after_paragraph_index`` is the index (within ``target.sections[
    target_section_index]``) of the paragraph the copied content is
    inserted after -- ``-1`` inserts before the first paragraph. See
    :func:`append_document` for *source*/*source_section_index*.
    """

    if isinstance(source, HwpxDocument):
        opened_here = False
        source_doc = source
    else:
        opened_here = True
        source_doc = HwpxDocument.open(source)
    try:
        copies, report = _merge_paragraphs(
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
        report["position"] = "after_paragraph"
        report["afterParagraphIndex"] = after_paragraph_index
        report["targetSectionIndex"] = target_section_index
        return report
    finally:
        if opened_here:
            source_doc.close()
