# SPDX-License-Identifier: Apache-2.0
"""Authoring surface for document-level options/compatibility settings, plus
the one paragraph-style property ``header_part.py``'s existing setters never
covered -- ``hh:compatibleDocument`` (+``layoutCompatibility``)/
``hh:docOption`` (``linkinfo``)/``hh:paraPr``'s ``autoSpacing`` (cycle 6.6
train 23).

Cycle 6.5's ``c38bf07`` built the *read* side for these settings
(``LayoutCompatibility``/``CompatibleDocument`` in ``header.py``) and was
explicit that it stopped there: "no write API means the OPC layer's
untouched-bytes preservation applies." This module adds the write side,
locked against the real corpus rather than guessed:

* ``hh:compatibleDocument/@targetProgram`` -- 47/47 vendored files read
  ``"HWP201X"``, no other value ever observed.
* ``hh:compatibleDocument/hh:layoutCompatibility`` -- 47/47 vendored files
  have **zero** flag children, despite the schema declaring 48 possible
  flag names. Confirmed again here, independently of the read model's own
  finding (cycle 6.1 train 4/c38bf07).
* ``hh:docOption/hh:linkinfo`` -- ``path`` is always ``""`` and
  ``footnoteInherit`` is always ``"0"`` (47/47); ``pageInherit`` genuinely
  varies (8/47 ``"1"``, 39/47 ``"0"``) -- the one attribute here actually
  worth setting per-document.
* ``hh:paraPr/hh:autoSpacing`` -- sits in the exact schema position
  ``_apply_paragraph_margins``/``_apply_paragraph_line_spacing`` already
  handle, yet had no write path at all before this train, unlike its two
  siblings. Checked against the assumption that it would be
  ``hp:switch``-wrapped the same way margin/lineSpacing are (DEV-018,
  ``docs/owpml-deviations.md``) before writing this -- it is not: every
  real occurrence (1832/1832 across the vendored corpus) is a *direct*
  ``hh:paraPr`` child, never nested inside ``hp:case``/``hp:default``. The
  setter still walks descendants defensively (matching the sibling
  setters' idiom at zero cost, and correctly finding the direct child
  either way), but does not claim switch-wrapping evidence this element
  does not have.

All boolean attributes here use the ``"0"``/``"1"`` convention
(``_zero_one_bool_str``), not ``"true"``/``"false"`` -- confirmed against
the vendored corpus for every attribute this module writes (0 ``"true"``/
``"false"`` occurrences), matching DEV-006's already-established convention
for this schema family.

Why this lives outside ``header_part.py``: ``HwpxOxmlHeader``'s owner file
sits at its 1600-line modularization cap (1599/1600 measured by ``wc -l``
before a line of this module was written -- zero headroom, exactly as the
``c38bf07`` commit message already flagged for whoever picked this up
next). So this capability is free functions operating on the class's
already-public surface (``.element``, ``.mark_dirty()``) plus its private
``@staticmethod`` tree helpers (``_direct_child_by_local`` et al -- already
``self``-independent, so calling them via the class rather than an
instance is safe, not a hack) -- the same drift-avoiding reuse this
session already used for ``oxml.objects._REQUIRED_SHAPE_CHILD_NAMES``. Zero
new lines land in ``header_part.py``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Iterable

from ..errors import HwpxValueError
from ._document_primitives import _HH, _zero_one_bool_str
from .header_part import HwpxOxmlHeader

if TYPE_CHECKING:
    pass

__all__ = [
    "apply_paragraph_auto_spacing",
    "set_compatible_document_target_program",
    "set_doc_option_link_info",
    "set_layout_compatibility_flags",
]


def _compatible_document_element(header: HwpxOxmlHeader, *, create: bool) -> ET.Element | None:
    root = header.element
    element = HwpxOxmlHeader._direct_child_by_local(root, "compatibleDocument")
    if element is not None or not create:
        return element
    element = root.makeelement(f"{_HH}compatibleDocument", {})
    HwpxOxmlHeader._insert_child_after(
        root, element, {"beginNum", "refList", "forbiddenWordList"}
    )
    return element


def set_compatible_document_target_program(header: HwpxOxmlHeader, target_program: str) -> None:
    """Set ``hh:compatibleDocument/@targetProgram``.

    Does not restrict *target_program* to the corpus-observed ``"HWP201X"``
    -- there is no evidence of what else real Hancom itself would ever
    write, so this lets a caller building a document from scratch, or
    correcting one missing the attribute, set it explicitly rather than
    guessing at an enumeration this repo has only ever seen one member of.
    """

    if not target_program:
        raise HwpxValueError(
            "target_program must be a non-empty string",
            code="header-compat-empty-target-program",
            context={"target_program": target_program},
            suggestion='Pass the observed real-corpus value, e.g. "HWP201X".',
        )
    element = _compatible_document_element(header, create=True)
    assert element is not None
    element.set("targetProgram", target_program)
    header.mark_dirty()


def set_layout_compatibility_flags(header: HwpxOxmlHeader, flags: Iterable[str]) -> None:
    """Replace ``hh:compatibleDocument/hh:layoutCompatibility``'s flag-marker
    children with exactly *flags*.

    Real-corpus contract (47/47 vendored files): every observed real
    document has zero flags -- the 48 names the schema declares
    (``applyFontWeightToBold`` etc.) are never emitted by Hancom itself
    (cycle 6.1 train 4/c38bf07's own finding, reconfirmed independently
    here). This setter exists for completeness/symmetry with the read
    model (``LayoutCompatibility.flags``, which preserves whatever's
    observed instead of hardcoding the 48-name enumeration) -- passing real
    flag names produces output with **no real-Hancom precedent to compare
    against**; passing an empty iterable (the corpus-typical case) clears
    any existing flags.
    """

    compatible_document = _compatible_document_element(header, create=True)
    assert compatible_document is not None
    layout_compatibility = HwpxOxmlHeader._direct_child_by_local(
        compatible_document, "layoutCompatibility"
    )
    if layout_compatibility is None:
        layout_compatibility = compatible_document.makeelement(
            f"{_HH}layoutCompatibility", {}
        )
        compatible_document.append(layout_compatibility)
    for child in list(layout_compatibility):
        layout_compatibility.remove(child)
    for flag in flags:
        if not flag:
            raise HwpxValueError(
                "layout compatibility flag names must be non-empty strings",
                code="header-compat-empty-flag-name",
                suggestion="Drop the empty entry, or omit it to clear all flags.",
            )
        layout_compatibility.append(layout_compatibility.makeelement(f"{_HH}{flag}", {}))
    header.mark_dirty()


def set_doc_option_link_info(
    header: HwpxOxmlHeader,
    *,
    path: str | None = None,
    page_inherit: bool | None = None,
    footnote_inherit: bool | None = None,
) -> None:
    """Set ``hh:docOption/hh:linkinfo``'s ``path``/``pageInherit``/
    ``footnoteInherit`` attributes. ``None`` leaves an attribute unchanged
    (or defaults it to the corpus-majority value on first creation)."""

    root = header.element
    doc_option = HwpxOxmlHeader._direct_child_by_local(root, "docOption")
    if doc_option is None:
        doc_option = root.makeelement(f"{_HH}docOption", {})
        HwpxOxmlHeader._insert_child_after(
            root,
            doc_option,
            {"beginNum", "refList", "forbiddenWordList", "compatibleDocument"},
        )
    link_info = HwpxOxmlHeader._direct_child_by_local(doc_option, "linkinfo")
    if link_info is None:
        link_info = doc_option.makeelement(
            f"{_HH}linkinfo",
            {"path": "", "pageInherit": "0", "footnoteInherit": "0"},
        )
        doc_option.append(link_info)
    if path is not None:
        link_info.set("path", path)
    if page_inherit is not None:
        link_info.set("pageInherit", _zero_one_bool_str(page_inherit))
    if footnote_inherit is not None:
        link_info.set("footnoteInherit", _zero_one_bool_str(footnote_inherit))
    header.mark_dirty()


def apply_paragraph_auto_spacing(
    header: HwpxOxmlHeader,
    para_pr: ET.Element,
    *,
    e_asian_eng: bool | None = None,
    e_asian_num: bool | None = None,
) -> None:
    """Set a ``hh:paraPr``'s ``hh:autoSpacing`` (``eAsianEng``/
    ``eAsianNum``).

    Reuses the descendant-walk pattern ``_apply_paragraph_margins``/
    ``_apply_paragraph_line_spacing`` already use (matching their idiom at
    zero cost), but unlike those two, real autoSpacing is never
    ``hp:switch``-wrapped -- checked directly (1832/1832 real occurrences
    are a direct ``hh:paraPr`` child, 0 nested inside ``hp:case``/
    ``hp:default``), so in practice this always finds and updates exactly
    one element. Both attributes are schema-``required`` (``ParaList XML
    schema.xml``'s ``autoSpacing`` declaration) -- creating a fresh element
    without an explicit value for one defaults it to ``"0"`` (the
    corpus-majority value, 1694/1832 real occurrences) rather than leaving
    a required attribute unset.
    """

    auto_spacing_elements = HwpxOxmlHeader._descendants_by_local(para_pr, "autoSpacing")
    if not auto_spacing_elements:
        auto_spacing = para_pr.makeelement(
            f"{_HH}autoSpacing", {"eAsianEng": "0", "eAsianNum": "0"}
        )
        HwpxOxmlHeader._insert_child_after(
            para_pr, auto_spacing, {"breakSetting", "heading", "align"}
        )
        auto_spacing_elements = [auto_spacing]

    for auto_spacing in auto_spacing_elements:
        if e_asian_eng is not None:
            auto_spacing.set("eAsianEng", _zero_one_bool_str(e_asian_eng))
        elif "eAsianEng" not in auto_spacing.attrib:
            auto_spacing.set("eAsianEng", "0")
        if e_asian_num is not None:
            auto_spacing.set("eAsianNum", _zero_one_bool_str(e_asian_num))
        elif "eAsianNum" not in auto_spacing.attrib:
            auto_spacing.set("eAsianNum", "0")

    header.mark_dirty()
