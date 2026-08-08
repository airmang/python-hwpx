# SPDX-License-Identifier: Apache-2.0
"""``add_section()``'s renderable-layout carrier lookup (``document_parts.py``
overflow, cycle 6.11 train 44).

``document_parts.py`` had only 2 lines of headroom left under the
1600-line owner-file cap when the ``_renderable_section_carriers`` fix
(scanning every run of a section's first paragraph for the one carrying
``hp:secPr``, instead of assuming it's positionally first -- see that
function's own docstring for the real-corpus bug this fixes) needed a few
more lines than that. Rather than raise the cap, this module was born to
hold it -- matching the ``header_compat.py``/``dutmal_compose.py``
precedent (new small overflow module, not a cap increase).

These were ``HwpxOxmlDocument`` class/static methods; moved here as plain
functions since none of them actually used ``cls``/``self`` -- each is a
pure lookup over a passed-in ``section``. ``HwpxOxmlDocument.
_section_layout_for_insertion`` (still in ``document_parts.py``, since it
genuinely needs ``self._sections``) is the only caller.
"""

from __future__ import annotations

from copy import deepcopy
import xml.etree.ElementTree as ET

from ._document_primitives import _HP, _element_local_name, _object_id
from .section import HwpxOxmlSection


def has_positive_page_geometry(section_properties: ET.Element) -> bool:
    page_properties = section_properties.find(f"{_HP}pagePr")
    if page_properties is None or page_properties.find(f"{_HP}margin") is None:
        return False
    try:
        page_width = int(page_properties.get("width", "0"))
        page_height = int(page_properties.get("height", "0"))
    except (TypeError, ValueError):
        return False
    return page_width > 0 and page_height > 0


def renderable_section_carriers(
    section: HwpxOxmlSection,
) -> tuple[ET.Element, ET.Element, ET.Element] | None:
    """Locate a valid ``secPr`` and its ``colPr`` carrier.

    Scans every ``hp:run`` child of the section's first paragraph for
    the one carrying ``hp:secPr`` -- **not** just the paragraph's
    literal first run. Found live (cycle 6.11 train 44, carried over
    from train 38/㊱'s document-merge work): anchoring a memo (or any
    other field) onto a section's first paragraph prepends a new run
    (``attach_memo_field``'s own fieldBegin-only run) ahead of the
    secPr-bearing one, so the old "positionally first run" assumption
    silently stopped finding a real, present, valid secPr on such
    documents -- ``add_section``'s own contract ("no existing section
    has positive page geometry...") then failed on documents that
    plainly did have one, just not in the first slot. Iterating every
    run and matching on the presence of ``hp:secPr`` itself (rather
    than positional assumption) fixes this without weakening the
    actual invariant this function checks (a well-formed section still
    carries exactly one secPr in its first paragraph -- confirmed
    real-corpus precedent, see document_merge.py's own
    ``_strip_embedded_section_properties`` docstring for the sibling
    finding that a real document can pack unrelated content into that
    same run too).
    """
    first_paragraph = section.element.find(f"{_HP}p")
    if first_paragraph is None:
        return None

    section_properties = None
    carrier_run = None
    for run in first_paragraph.findall(f"{_HP}run"):
        candidate = run.find(f"{_HP}secPr")
        if candidate is not None:
            section_properties = candidate
            carrier_run = run
            break
    if section_properties is None or carrier_run is None:
        return None
    if not has_positive_page_geometry(section_properties):
        return None

    for control in carrier_run.findall(f"{_HP}ctrl"):
        column_properties = control.find(f"{_HP}colPr")
        if column_properties is not None:
            return section_properties, control, column_properties
    return None


def copy_renderable_section_layout(
    section: HwpxOxmlSection,
) -> tuple[ET.Element, ET.Element] | None:
    """Return story-free ``secPr`` and ``colPr`` carriers from *section*.

    Hancom requires every section part to carry positive page geometry and
    a column definition in its first paragraph's first run.  Header/footer
    stories are deliberately excluded because their object identifiers and
    content belong to the source section.
    """
    carriers = renderable_section_carriers(section)
    if carriers is None:
        return None
    section_properties, column_control, column_properties = carriers

    copied_properties = deepcopy(section_properties)
    story_children = {
        "header",
        "footer",
        "headerApply",
        "footerApply",
        "masterPage",
        "presentation",
    }
    for child in list(copied_properties):
        if _element_local_name(child) in story_children:
            copied_properties.remove(child)
    copied_properties.set("masterPageCnt", "0")
    if copied_properties.get("id") is None:
        copied_properties.set("id", "")

    copied_column_control = column_control.makeelement(
        column_control.tag,
        dict(column_control.attrib),
    )
    copied_column_properties = deepcopy(column_properties)
    column_id = copied_column_properties.get("id")
    if column_id:
        copied_column_properties.set("id", _object_id())
    elif column_id is None:
        copied_column_properties.set("id", "")
    copied_column_control.append(copied_column_properties)
    return copied_properties, copied_column_control
