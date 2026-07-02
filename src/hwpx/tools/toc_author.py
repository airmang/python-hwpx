# SPDX-License-Identifier: Apache-2.0
"""Author Hancom-native TOC and page cross-reference fields (M7 / S-062 P2).

Emits the exact field contract reverse-engineered from an owner-authored
Hancom document (``specs/009-native-toc-xrefs/evidence/
p0-native-toc-xml-contract.md``; gold pair vendored in
``tests/fixtures/m7_toc_gold/``):

* ``<hp:fieldBegin type="TABLEOFCONTENTS">`` + ``TableOfContents:set`` Command
  DSL wrapping generated entry paragraphs (HYPERLINK fields whose single
  ``<hp:t>`` nests the dot-leader ``hp:tab``; page number in the tab's tail),
* ``<hp:fieldBegin type="CROSSREF">`` page references whose cached result is
  the plain ``hp:t`` run between fieldBegin and fieldEnd (Hancom recomputes
  these automatically on edit/save — P0 measured),
* anchors that are plain paragraph ``id`` attributes; TOC-targeted headings
  therefore need document-unique ids (:func:`ensure_paragraph_anchor_id`).

Honest semantics (measured): entry page numbers emitted here are ESTIMATES —
Hancom only recomputes the TOC block on an explicit 차례 새로 고침, which the
P3 oracle triggers and verifies. CROSSREF caches self-heal on edit/save.
The parameter spelling ``Fiexde`` replicates Hancom's own output verbatim.
"""
from __future__ import annotations

import re
from typing import Any, Sequence
from uuid import uuid4

# live section paragraphs are lxml elements — new nodes must match
from lxml import etree as ET

from hwpx.document import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_NON_UNIQUE_PARA_ID = "2147483648"
_OUTLINE_NAME_RE = re.compile(r"^(?:개요|Outline)\s*(\d+)$")
#: Measured TOC Command (gold contract). ContentsMake:uint:31 = the bitmask the
#: Hancom dialog emitted (title+table+figure+equation blocks); other values are
#: unmeasured, so v1 replicates the captured value verbatim.
_TOC_COMMAND = (
    "TableOfContents:set:140:ContentsMake:uint:31 ContentsStyles:wstring:0: "
    "ContentsLevel:int:{level} ContentsAutoTabRight:int:0 "
    "ContentsLeader:int:{leader} ContentsHyperlink:bool:{hyperlink}  "
)


def _rand_id() -> str:
    return str(uuid4().int & 0x7FFFFFFF)


def _existing_paragraph_ids(doc: HwpxDocument) -> set[str]:
    ids: set[str] = set()
    for section in doc.oxml.sections:
        for p_el in section.element.iter(f"{_HP}p"):
            pid = p_el.get("id")
            if pid:
                ids.add(pid)
    return ids


def ensure_paragraph_anchor_id(doc: HwpxDocument, paragraph: Any) -> str:
    """Make ``paragraph`` addressable as a field anchor (``?#<id>``).

    Hancom resolves TOC/CROSSREF targets by the paragraph ``id`` attribute, so
    an anchor id must be unique in the document (generated paragraphs may all
    carry the shared ``2147483648`` constant)."""
    element = paragraph.element
    pid = element.get("id")
    ids = _existing_paragraph_ids(doc)
    duplicated = pid and sum(1 for section in doc.oxml.sections
                             for p in section.element.iter(f"{_HP}p")
                             if p.get("id") == pid) > 1
    if not pid or pid == _NON_UNIQUE_PARA_ID or duplicated:
        new_id = _rand_id()
        while new_id in ids:
            new_id = _rand_id()
        element.set("id", new_id)
        pid = new_id
    return pid


def outline_heading_paragraphs(doc: HwpxDocument) -> list[tuple[Any, int, str]]:
    """Return ``(paragraph, level, text)`` for 개요/Outline-styled paragraphs."""
    levels: dict[str, int] = {}
    for style_id, style in (doc.styles or {}).items():
        name = getattr(style, "name", "") or ""
        match = _OUTLINE_NAME_RE.match(name.strip())
        if match:
            levels[str(style_id)] = int(match.group(1))
    result: list[tuple[Any, int, str]] = []
    for section in doc.sections:
        for paragraph in section.paragraphs:
            style_ref = paragraph.element.get("styleIDRef")
            if style_ref in levels and (paragraph.text or "").strip():
                result.append((paragraph, levels[style_ref], paragraph.text.strip()))
    return result


# ── low-level field emission ─────────────────────────────────────────
def _param(parent: ET.Element, kind: str, name: str, value: str, *, preserve: bool = False) -> None:
    el = ET.SubElement(parent, f"{_HP}{kind}", {"name": name})
    if preserve:
        el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    el.text = value


def _field_begin(run: ET.Element, *, ftype: str, field_id: str, editable: str, dirty: str) -> ET.Element:
    ctrl = ET.SubElement(run, f"{_HP}ctrl")
    begin = ET.SubElement(
        ctrl,
        f"{_HP}fieldBegin",
        {
            "id": field_id,
            "type": ftype,
            "name": "",
            "editable": editable,
            "dirty": dirty,
            "zorder": "-1",
            "fieldid": _rand_id(),
            "metaTag": "",
        },
    )
    return begin


def _field_end(run: ET.Element, field_id: str) -> None:
    ctrl = ET.SubElement(run, f"{_HP}ctrl")
    ET.SubElement(ctrl, f"{_HP}fieldEnd", {"beginIDRef": field_id})


def _entry_paragraph(numbered_title: str, page: int, target_id: str, char_pr: str = "0") -> ET.Element:
    """One generated TOC entry: HYPERLINK field wrapping ``title<tab/>page``."""
    p = ET.Element(f"{_HP}p", {
        "id": _rand_id(), "paraPrIDRef": "0", "styleIDRef": "0",
        "pageBreak": "0", "columnBreak": "0", "merged": "0",
    })
    field_id = _rand_id()
    run1 = ET.SubElement(p, f"{_HP}run", {"charPrIDRef": char_pr})
    begin = _field_begin(run1, ftype="HYPERLINK", field_id=field_id, editable="0", dirty="1")
    params = ET.SubElement(begin, f"{_HP}parameters", {"cnt": "5", "name": ""})
    _param(params, "integerParam", "Prop", "0")
    _param(params, "stringParam", "Command", f"?#{target_id};0;1;0;")
    _param(params, "stringParam", "Category", "HWPHYPERLINK_TYPE_HWP")
    _param(params, "stringParam", "TargetType", "HWPHYPERLINK_TARGET_OUTLINE")
    _param(params, "stringParam", "DocOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB")

    run2 = ET.SubElement(p, f"{_HP}run", {"charPrIDRef": char_pr})
    t = ET.SubElement(run2, f"{_HP}t")
    t.text = numbered_title
    tab = ET.SubElement(t, f"{_HP}tab", {"width": "34032", "leader": "3", "type": "2"})
    tab.tail = str(page)

    run3 = ET.SubElement(p, f"{_HP}run", {"charPrIDRef": char_pr})
    _field_end(run3, field_id)
    return p


def mark_toc_dirty(doc: HwpxDocument) -> int:
    """Set ``dirty="1"`` on every TABLEOFCONTENTS field — the measured
    re-number trigger: Hancom regenerates a dirty TOC (entries, styles, page
    numbers) when it next opens the document. Call after edits that shift
    pagination. Returns the number of fields marked."""
    count = 0
    for section in doc.oxml.sections:
        for begin in section.element.iter(f"{_HP}fieldBegin"):
            if begin.get("type") == "TABLEOFCONTENTS":
                begin.set("dirty", "1")
                count += 1
        if count:
            section.mark_dirty()
    return count


def add_native_toc(
    doc: HwpxDocument,
    *,
    at_index: int = 0,
    title: str = "<제목 차례>",
    level: int = 2,
    leader: int = 3,
    hyperlink: bool = True,
    dirty: bool = True,
    headings: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Insert a Hancom-native TABLEOFCONTENTS field region at ``at_index``.

    Entries are generated from ``headings`` (paragraph wrappers) or, when
    omitted, auto-detected 개요/Outline-styled paragraphs. Emitted entry page
    numbers are naive estimates; with ``dirty=True`` (default, measured
    semantics) Hancom regenerates the whole region — correct entries, styles,
    and page numbers — on its next open, so the first thing a user sees is a
    TOC Hancom itself computed. Returns a summary dict.

    Collection note (measured): Hancom collects outline-styled paragraphs and
    — via the ``ContentsStyles:wstring:0:`` command — style-0 (바탕글)
    paragraphs too; give body text a non-collected style (e.g. 본문, style 1)
    or it will appear as TOC entries after regeneration.
    """
    if headings is None:
        detected = outline_heading_paragraphs(doc)
    else:
        detected = [(p, 1, (p.text or "").strip()) for p in headings]
    if not detected:
        raise ValueError("no outline headings found to build a TOC from")

    anchors: list[tuple[str, int, str]] = []
    for paragraph, lvl, text in detected:
        anchor = ensure_paragraph_anchor_id(doc, paragraph)
        anchors.append((anchor, lvl, text))

    section = doc.oxml.sections[0]
    toc_field_id = _rand_id()

    # opening paragraph: [ctrl fieldBegin TABLEOFCONTENTS][t title]
    open_p = ET.Element(f"{_HP}p", {
        "id": _rand_id(), "paraPrIDRef": "0", "styleIDRef": "0",
        "pageBreak": "0", "columnBreak": "0", "merged": "0",
    })
    run = ET.SubElement(open_p, f"{_HP}run", {"charPrIDRef": "0"})
    begin = _field_begin(
        run, ftype="TABLEOFCONTENTS", field_id=toc_field_id,
        editable="1", dirty="1" if dirty else "0",
    )
    params = ET.SubElement(begin, f"{_HP}parameters", {"cnt": "2", "name": ""})
    _param(params, "integerParam", "Prop", "8")
    _param(
        params, "stringParam", "Command",
        _TOC_COMMAND.format(level=level, leader=leader, hyperlink=1 if hyperlink else 0),
        preserve=True,
    )
    t = ET.SubElement(run, f"{_HP}t")
    t.text = title

    entry_elements = [
        _entry_paragraph(f"{i}. {text}", 1, anchor)
        for i, (anchor, _lvl, text) in enumerate(anchors, start=1)
    ]

    # closing paragraph: [ctrl fieldEnd]
    close_p = ET.Element(f"{_HP}p", {
        "id": _rand_id(), "paraPrIDRef": "0", "styleIDRef": "0",
        "pageBreak": "0", "columnBreak": "0", "merged": "0",
    })
    close_run = ET.SubElement(close_p, f"{_HP}run", {"charPrIDRef": "0"})
    _field_end(close_run, toc_field_id)

    section.insert_paragraphs(at_index, [open_p, *entry_elements, close_p])
    return {
        "tocFieldId": toc_field_id,
        "entryCount": len(anchors),
        "anchors": [a for a, _l, _t in anchors],
        "cachedPagesAreEstimates": True,
    }


def add_page_crossref(
    doc: HwpxDocument,
    paragraph: Any,
    target_paragraph: Any,
    *,
    cached_page: int = 1,
) -> dict[str, Any]:
    """Append a Hancom-native page CROSSREF (상호참조 → 쪽 번호) to ``paragraph``.

    The cached result run is a best-effort estimate; Hancom recomputes CROSSREF
    caches automatically on edit/save (P0 measured on the gold pair: 2→3)."""
    target_id = ensure_paragraph_anchor_id(doc, target_paragraph)
    field_id = _rand_id()
    p_el = paragraph.element

    run1 = ET.SubElement(p_el, f"{_HP}run", {"charPrIDRef": "0"})
    begin = _field_begin(run1, ftype="CROSSREF", field_id=field_id, editable="0", dirty="0")
    params = ET.SubElement(begin, f"{_HP}parameters", {"cnt": "8", "name": ""})
    _param(params, "booleanParam", "Fiexde", "1")  # sic — Hancom's own spelling
    _param(params, "integerParam", "Prop", "0")
    _param(params, "stringParam", "Command", f"?#{target_id};5;0;0;0;")
    _param(params, "stringParam", "RefPath", f"?#{target_id};")
    _param(params, "stringParam", "RefType", "TARGET_OUTLINE")
    _param(params, "stringParam", "RefContentType", "OBJECT_TYPE_PAGE")
    _param(params, "booleanParam", "RefHyperLink", "false")
    _param(params, "stringParam", "RefOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB")

    run2 = ET.SubElement(p_el, f"{_HP}run", {"charPrIDRef": "0"})
    t = ET.SubElement(run2, f"{_HP}t")
    t.text = str(cached_page)

    run3 = ET.SubElement(p_el, f"{_HP}run", {"charPrIDRef": "0"})
    _field_end(run3, field_id)

    paragraph.section.mark_dirty()
    return {"fieldId": field_id, "targetId": target_id, "cachedPage": cached_page}
