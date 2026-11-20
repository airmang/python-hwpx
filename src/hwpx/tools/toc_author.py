# SPDX-License-Identifier: Apache-2.0
"""Author Hancom-native TOC and page cross-reference fields.

Emits the exact field contract inferred from an owner-authored
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
from hwpx.errors import HwpxValueError
from hwpx.oxml.field_marks import field_type_id
# The outline style names (개요 N / Outline N) are the engine's: hwpx.oxml.paragraph_heading.outline_style_level.
from hwpx.oxml.paragraph_heading import _OUTLINE_STYLE_NAME as _OUTLINE_NAME_RE

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_NON_UNIQUE_PARA_ID = "2147483648"
#: Measured TOC Command (gold contract). ``ContentsMake`` says which lists Hangul
#: builds when it regenerates the TOC: Hangul 2024 rebuilt a dirty TOC with 31 as
#: 제목·표·그림·수식 차례, with 17 as 제목 차례 only (entries, links and page
#: numbers filled), and dropped the 표/그림/수식 list for 29/27/23 (bits 2/4/8);
#: without 16 it made no title entries. We write a title TOC, so 17.
_TOC_COMMAND = (
    "TableOfContents:set:140:ContentsMake:uint:17 ContentsStyles:wstring:0: "
    "ContentsLevel:int:{level} ContentsAutoTabRight:int:0 "
    "ContentsLeader:int:{leader} ContentsHyperlink:bool:{hyperlink}  "
)

#: ``hh:tabItem/@leader`` names indexed by the leader code the TOC Command
#: (``ContentsLeader``) and the inline ``hp:tab/@leader`` use. Hancom draws
#: ``DASH`` (code 3, the default) as the fine dotted leader of its own TOC.
_TAB_LEADER_NAMES = (
    "NONE", "SOLID", "DOT", "DASH", "DASH_DOT", "DASH_DOT_DOT", "LONG_DASH",
    "CIRCLE", "DOUBLE_SLIM", "SLIM_THICK", "THICK_SLIM", "SLIM_THICK_SLIM",
)


#: ``hp:ctrl`` children that set up the section from its first paragraph on.
_SECTION_START_CONTROLS = frozenset(
    {"colPr", "header", "footer", "pageNum", "pageNumCtrl", "pageHiding", "newNum"}
)


def _rand_id() -> str:
    return str(uuid4().int & 0x7FFFFFFF)


def _keep_section_setup_first(section: Any) -> bool:
    """Move the section setup back into the section's first paragraph.

    Paragraphs inserted in front of the one that carries ``hp:secPr`` leave the
    setup in the middle of the section, and Hancom reads a ``hp:secPr`` that is
    not in a section's first paragraph as the start of a new section: a TOC
    put at index 0 became a section of its own, followed by a page break.
    ``hp:secPr`` and the controls that
    apply from the section start (columns, header, footer, page numbering) move,
    in order, into a new leading run of the first paragraph -- where Hancom
    keeps them when it inserts a TOC at the start of a document itself.
    Returns whether anything moved.
    """
    paragraphs = [p.element for p in section.paragraphs]
    if not paragraphs or paragraphs[0].find(f"{_HP}run/{_HP}secPr") is not None:
        return False
    holder = next((p for p in paragraphs[1:] if p.find(f"{_HP}run/{_HP}secPr") is not None), None)
    if holder is None:
        return False
    first = paragraphs[0]
    setup_run = first.makeelement(f"{_HP}run", {"charPrIDRef": "0"})
    for run in holder.findall(f"{_HP}run"):
        for node in list(run):
            name = ET.QName(node).localname
            if name == "secPr" or (
                name == "ctrl" and any(ET.QName(c).localname in _SECTION_START_CONTROLS for c in node)
            ):
                if name == "secPr":
                    setup_run.set("charPrIDRef", run.get("charPrIDRef", "0"))
                run.remove(node)
                setup_run.append(node)
        if len(run) == 0 and len(holder.findall(f"{_HP}run")) > 1:
            holder.remove(run)
    first.insert(0, setup_run)
    section.mark_dirty()
    return True


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
    carry the shared ``2147483648`` constant). Hancom's own anchors are positive
    numbers, so an id ``0`` (a new document's first paragraph) gets one too."""
    element = paragraph.element
    pid = element.get("id")
    ids = _existing_paragraph_ids(doc)
    duplicated = pid and sum(1 for section in doc.oxml.sections
                             for p in section.element.iter(f"{_HP}p")
                             if p.get("id") == pid) > 1
    if not pid or pid in (_NON_UNIQUE_PARA_ID, "0") or not pid.isdigit() or duplicated:
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
            "fieldid": field_type_id(ftype, ids=None),  # HYPERLINK/CROSSREF: their control ids, no new id
            "metaTag": "",
        },
    )
    return begin


def _field_end(run: ET.Element, begin: ET.Element) -> None:
    """The end of field *begin*: its id and, as Hancom writes it, its ``fieldid``."""
    ctrl = ET.SubElement(run, f"{_HP}ctrl")
    ET.SubElement(ctrl, f"{_HP}fieldEnd", {"beginIDRef": begin.get("id", ""), "fieldid": begin.get("fieldid", "")})


def _entry_para_pr(doc: HwpxDocument, leader: int) -> str:
    """Paragraph property for TOC entries: a right tab stop at the text edge.

    Hancom lays a tab out from the paragraph's tab stops; the ``hp:tab``
    attributes are only a cache of that layout. Without a right tab stop the
    page number lands at the next default tab, right after the title.
    """
    properties = doc.oxml.sections[0].properties
    size, margins = properties.page_size, properties.page_margins
    sizes = (size.drawn_width, margins.left, margins.right, margins.gutter)
    width = 0 if None in sizes else sizes[0] - sizes[1] - sizes[2] - sizes[3]  # type: ignore[operator]
    if width <= 0:
        return "0"
    header = doc.oxml.headers[0]
    tab_pr_id = header.ensure_tab_definition(
        tab_stops=[{"pos": width, "type": "RIGHT", "leader": _TAB_LEADER_NAMES[leader]}],
        auto_tab_left=True,
    )
    return header.ensure_paragraph_format(base_para_pr_id="0", tab_pr_id_ref=tab_pr_id)


def _entry_paragraph(
    numbered_title: str,
    page: int,
    target_id: str,
    char_pr: str = "0",
    *,
    para_pr: str = "0",
    leader: int = 3,
) -> ET.Element:
    """One generated TOC entry: HYPERLINK field wrapping ``title<tab/>page``."""
    p = ET.Element(f"{_HP}p", {
        "id": _rand_id(), "paraPrIDRef": para_pr, "styleIDRef": "0",
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
    tab = ET.SubElement(t, f"{_HP}tab", {"width": "34032", "leader": str(leader), "type": "2"})
    tab.tail = str(page)

    run3 = ET.SubElement(p, f"{_HP}run", {"charPrIDRef": char_pr})
    _field_end(run3, begin)
    return p


_COLLECTED_STYLE_ID = "0"


def _paragraph_own_text(p_el: ET.Element) -> str:
    """Text carried by the paragraph's direct runs (nested table text excluded)."""
    parts: list[str] = []
    for run in p_el.findall(f"{_HP}run"):
        for t in run.findall(f"{_HP}t"):
            parts.append("".join(t.itertext()))
    return "".join(parts)


def _inside_header_footer(p_el: ET.Element, stop: ET.Element) -> bool:
    current = p_el.getparent()
    while current is not None and current is not stop:
        if current.tag in (f"{_HP}header", f"{_HP}footer"):
            return True
        current = current.getparent()
    return False


def ensure_body_styles_not_collected(doc: HwpxDocument) -> int:
    """Route non-empty 바탕글(style 0) paragraphs onto the 본문/Body style.

    Measured ContentsStyles trap (M7): the emitted TOC Command pins
    ``ContentsStyles:wstring:0:``, so on regeneration Hancom collects every
    non-empty style-0 paragraph as a TOC entry — body text must not sit on
    style 0 while a native TOC is present (the M7 demo authored body on
    본문/style 1). Only ``styleIDRef`` is rewritten; a missing ``paraPrIDRef``
    is pinned to the 바탕글 paraPr first so the effective formatting cannot
    change. Header/footer paragraphs and empty paragraphs are left alone
    (the M7 demo's empty style-0 skeleton paragraph was measured as not
    collected). Call this BEFORE :func:`add_native_toc` so the TOC region's
    own style-0 paragraphs (gold contract) are not rerouted.

    Returns the number of rerouted paragraphs. Raises :class:`ValueError`
    when the document has no 본문/Body style to route onto, refusing to
    silently produce a TOC that would swallow the body text as entries.
    """
    body_style_id: str | None = None
    collected_para_pr = "0"
    for style_id, style in (doc.styles or {}).items():
        name = (getattr(style, "name", "") or "").strip()
        eng_name = (getattr(style, "eng_name", "") or "").strip()
        raw = getattr(style, "raw_id", None)
        resolved = str(raw if raw is not None else style_id)
        if resolved == _COLLECTED_STYLE_ID:
            para_ref = getattr(style, "para_pr_id_ref", None)
            if para_ref is not None:
                collected_para_pr = str(para_ref)
            continue
        if body_style_id is None and (name == "본문" or eng_name == "Body"):
            body_style_id = resolved
    if body_style_id is None:
        raise ValueError(
            "native TOC requires a non-collected body style: this document has "
            "no 본문/Body style to route 바탕글(style 0) body text onto, and "
            "Hancom's ContentsStyles:0 regeneration would collect that text as "
            "TOC entries (measured M7 trap)"
        )
    rerouted = 0
    for section in doc.oxml.sections:
        section_rerouted = 0
        sec_el = section.element
        for p_el in sec_el.iter(f"{_HP}p"):
            if p_el.get("styleIDRef", _COLLECTED_STYLE_ID) != _COLLECTED_STYLE_ID:
                continue
            if not _paragraph_own_text(p_el).strip():
                continue
            if _inside_header_footer(p_el, sec_el):
                continue
            if p_el.get("paraPrIDRef") is None:
                p_el.set("paraPrIDRef", collected_para_pr)
            p_el.set("styleIDRef", body_style_id)
            section_rerouted += 1
        if section_rerouted:
            section.mark_dirty()
        rerouted += section_rerouted
    return rerouted


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
    dirty: bool | None = None,
    headings: Sequence[Any] | None = None,
    section: int = 0,
) -> dict[str, Any]:
    """Insert a Hancom-native TABLEOFCONTENTS field region at ``at_index`` of section *section*.

    Entries are generated from ``headings`` (paragraph wrappers) or, when
    omitted, auto-detected 개요/Outline-styled paragraphs. Emitted entry page
    numbers are naive estimates; with ``dirty=True`` Hancom regenerates the
    whole region — correct entries, styles, and page numbers — on its next
    open, so the first thing a user sees is a TOC Hancom itself computed.
    Hancom regenerates it from the paragraphs it collects (see below), so a
    TOC built from explicit ``headings`` that are not outline paragraphs would
    lose its entries and links. ``dirty`` therefore defaults to ``True`` for
    auto-detected headings and to ``False`` when ``headings`` is given; pass
    it explicitly to choose. Returns a summary dict.

    Collection note (measured): Hancom collects outline-styled paragraphs and
    — via the ``ContentsStyles:wstring:0:`` command — style-0 (바탕글)
    paragraphs too; give body text a non-collected style (e.g. 본문, style 1)
    or it will appear as TOC entries after regeneration.

    Entry paragraphs get a right tab stop at the text edge of the first
    section with the ``leader`` fill (a code from 0 to 11: 0 none, 3 the
    dotted leader of Hancom's own TOC), so page numbers line up on the right.
    """
    if isinstance(leader, bool) or not 0 <= leader < len(_TAB_LEADER_NAMES):
        raise HwpxValueError(
            f"leader must be a tab leader code from 0 to {len(_TAB_LEADER_NAMES) - 1}, got {leader!r}",
            code="paragraph-tab-leader-invalid",
            context={"requested": leader, "available": f"0-{len(_TAB_LEADER_NAMES) - 1}"},
            suggestion="0 은 채움 없음, 3 은 한컴 차례의 점선이다.",
        )
    if headings is None:
        detected = outline_heading_paragraphs(doc)
    else:
        detected = [(p, 1, (p.text or "").strip()) for p in headings]
    if not detected:
        raise ValueError("no outline headings found to build a TOC from")
    if dirty is None:
        dirty = headings is None

    anchors: list[tuple[str, int, str]] = []
    for paragraph, lvl, text in detected:
        anchor = ensure_paragraph_anchor_id(doc, paragraph)
        anchors.append((anchor, lvl, text))

    target_section = doc.oxml.sections[section]
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

    entry_para_pr = _entry_para_pr(doc, leader)
    entry_elements = [
        _entry_paragraph(f"{i}. {text}", 1, anchor, para_pr=entry_para_pr, leader=leader)
        for i, (anchor, _lvl, text) in enumerate(anchors, start=1)
    ]

    # closing paragraph: [ctrl fieldEnd]
    close_p = ET.Element(f"{_HP}p", {
        "id": _rand_id(), "paraPrIDRef": "0", "styleIDRef": "0",
        "pageBreak": "0", "columnBreak": "0", "merged": "0",
    })
    close_run = ET.SubElement(close_p, f"{_HP}run", {"charPrIDRef": "0"})
    _field_end(close_run, begin)

    placed = target_section.insert_paragraphs(at_index, [open_p, *entry_elements, close_p])
    # The paragraphs go in as copies with ids of their own: the table's field, which begins in the first
    # and ends in the last, has the id the copy was given.
    for node in placed[0].element.iter(f"{_HP}fieldBegin"):
        if node.get("type") == "TABLEOFCONTENTS":
            toc_field_id = str(node.get("id"))
            break
    if at_index == 0:
        _keep_section_setup_first(target_section)
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
    _field_end(run3, begin)

    paragraph.section.mark_dirty()
    return {"fieldId": field_id, "targetId": target_id, "cachedPage": cached_page}


# ── reading, rebuilding and removing a table of contents (hwpx.objects.TableOfContents) ──
#
# What a TOC region holds, as Hancom saves it (m7_toc_gold A/B, gui_probes/title_mark_*): the
# paragraph with the TABLEOFCONTENTS fieldBegin and the title ("<제목 차례>", style 차례 제목);
# one paragraph per entry, styled 차례 N for its level, whose text is ``<number> <heading>`` and a
# tab, then the page number in the tab's tail, wrapped in a HYPERLINK field to ``?#<heading id>``
# (``ContentsHyperlink:1``) or plain (``ContentsHyperlink:0``, measured on a refreshed save); then,
# for a TOC that collects tables, pictures and equations too, a 차례 제목 paragraph per kind
# ("<표 차례>" …) with its own entries; the fieldEnd in the last paragraph. ``dirty="1"`` on the
# fieldBegin makes Hancom build the whole region again -- entries, styles and page numbers -- the
# next time it opens the document (docs/internals/toc-dirty.md): that is how a page number nobody
# but Hancom can know gets filled in.

_TOC_ENTRY_STYLE = re.compile(r"^(?:차례|TOC)\s*(\d+)$")
_TOC_HEADING_STYLES = ("차례 제목", "TOC Heading")
_SET_HEAD = re.compile(r"^\s*[A-Za-z]+:set:\d+:")
_SET_ITEM = re.compile(r"\s*([A-Za-z]+):([A-Za-z]+):")
_SET_LENGTH = re.compile(r"(\d+):")
_SET_VALUE = re.compile(r"(\S*)")
_LINK_TARGET = re.compile(r"^\?(#?[^;]*);")


def toc_command_values(command: str) -> dict[str, str]:
    """The items of a ``TableOfContents:set:…`` command, ``name -> value`` (a ``wstring`` by its length)."""

    head = _SET_HEAD.match(command or "")
    rest, at, values = (command or "")[head.end() if head else 0:], 0, {}
    while (item := _SET_ITEM.match(rest, at)) is not None:
        name, kind, at = item.group(1), item.group(2), item.end()
        if kind == "wstring":
            length = _SET_LENGTH.match(rest, at)
            if length is None:
                break
            at = length.end()
            values[name] = rest[at : at + int(length.group(1))]
            at += int(length.group(1))
        else:
            value = _SET_VALUE.match(rest, at)
            values[name] = value.group(1) if value else ""
            at = value.end() if value else at
    return values


def _local(node: Any) -> str:
    tag = getattr(node, "tag", None)
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _param_text(begin: Any, name: str) -> str:
    for holder in begin:
        if _local(holder) == "parameters":
            for param in holder:
                if param.get("name") == name:
                    return param.text or ""
    return ""


def _style_name(doc: HwpxDocument, element: Any) -> tuple[str, str]:
    style = doc.oxml.style(element.get("styleIDRef"))
    return ((style.name or "").strip(), (style.eng_name or "").strip()) if style is not None else ("", "")


def _entry_level(doc: HwpxDocument, element: Any) -> int | None:
    for name in _style_name(doc, element):
        found = _TOC_ENTRY_STYLE.match(name)
        if found:
            return int(found.group(1))
    return None


def _is_toc_heading(doc: HwpxDocument, element: Any) -> bool:
    return any(name in _TOC_HEADING_STYLES for name in _style_name(doc, element))


def _entry_text(element: Any) -> tuple[str, str] | None:
    """(the text before the tab, the text after it) of a TOC entry paragraph, ``None`` without a tab."""

    before: list[str] = []
    after: list[str] = []
    into, found = before, False
    for run in element:
        if _local(run) != "run":
            continue
        for node in run:
            if _local(node) != "t":
                continue
            into.append(node.text or "")
            for child in node:
                if _local(child) == "tab" and not found:
                    found, into = True, after
                into.append(child.tail or "")
    return ("".join(before), "".join(after)) if found else None


def _entry_link(element: Any) -> Any:
    for begin in element.iter(f"{_HP}fieldBegin"):
        if begin.get("type") == "HYPERLINK":
            return begin
    return None


def _entry_target(element: Any) -> str:
    begin = _entry_link(element)
    if begin is None:
        return ""
    found = _LINK_TARGET.match(_param_text(begin, "Command"))
    return found.group(1) if found else ""


def _region(doc: HwpxDocument, begin: Any) -> tuple[Any, Any, list[Any]]:
    """(the begin's paragraph view, the end's paragraph or ``None``, the paragraphs between)."""

    from hwpx._document.fields import _match_for_begin

    match = _match_for_begin(doc, begin)
    span = match.get("_span")
    if span is None:
        return match["_paragraph"], None, []
    return match["_paragraph"], span[0], list(span[4])


def toc_entries(doc: HwpxDocument, begin: Any) -> tuple[Any, ...]:
    """The entries of the TOC opened by *begin*, as :class:`hwpx.objects.TocEntry` values."""

    from hwpx.objects.form_field import TocEntry
    from hwpx.oxml import HwpxOxmlParagraph

    paragraph, end, middle = _region(doc, begin)
    entries = []
    for element in [*middle, *([end] if end is not None else [])]:
        parts = _entry_text(element)
        if parts is None:
            continue
        entries.append(TocEntry(
            text=parts[0],
            level=_entry_level(doc, element),
            page=parts[1],
            target=_entry_target(element),
            paragraph=HwpxOxmlParagraph(element, paragraph.section),
        ))
    return tuple(entries)


def toc_title(doc: HwpxDocument, begin: Any) -> str:
    """The text after *begin* in its paragraph, up to the next field."""

    paragraph, _end, _middle = _region(doc, begin)
    parts: list[str] = []
    started = False
    for run in paragraph.element:
        if _local(run) != "run":
            continue
        for node in run:
            if _local(node) == "ctrl":
                if any(child is begin for child in node):
                    started = True
                elif started and node.find(f"{_HP}fieldBegin") is not None:
                    return "".join(parts)
            elif started and _local(node) == "t":
                parts.append("".join(node.itertext()))
    return "".join(parts)


def _hidden_from_toc(element: Any) -> bool:
    """Whether the paragraph carries Hancom's 차례 숨기기 mark (``hp:titleMark ignore="0"``, DEV-044)."""

    for run in element:
        if _local(run) != "run":
            continue
        for node in run:
            if _local(node) == "t":
                for child in node:
                    if _local(child) == "titleMark" and (child.get("ignore") or "false").lower() in ("0", "false"):
                        return True
    return False


def _outline_labels(doc: HwpxDocument) -> dict[Any, str]:
    """The number Hancom shows before each numbered body paragraph (``1.``, ``가.``), by element."""

    from hwpx.tools.exporter import _ListLabels

    header = doc.oxml.headers[0].element if doc.oxml.headers else None
    labels = _ListLabels(header)
    found: dict[Any, str] = {}
    for section in doc.oxml.sections:
        labels.start_section(section.element)
        for paragraph in section.paragraphs:
            label = labels.label(paragraph.element)
            if label:
                found[paragraph.element] = label
            for run in paragraph.element.findall(f"{_HP}run"):
                for node in run:
                    if _local(node) == "tbl":
                        labels.count(node)
    return found


def _clean(text: str) -> str:
    return " ".join(text.replace("\t", " ").replace("\n", " ").split())


def toc_headings(doc: HwpxDocument, levels: int, *, exclude: Sequence[Any] = ()) -> list[tuple[Any, int, str]]:
    """``(paragraph, level, entry text)`` for the body paragraphs a TOC of *levels* collects: outline
    paragraphs of level 1 to *levels* that are not marked 차례 숨기기 and hold text. The entry text is
    the paragraph's number and its text, as Hancom writes an entry (``1. 개요 첫 번째``)."""

    skip = {id(element) for element in exclude}
    labels = _outline_labels(doc)
    found = []
    for paragraph in doc.paragraphs:
        element = paragraph.element
        level = paragraph.outline_level
        if id(element) in skip or not 1 <= level <= levels or _hidden_from_toc(element):
            continue
        text = _clean(paragraph.text)
        if not text:
            continue
        label = labels.get(element, "")
        found.append((paragraph, level, f"{label} {text}" if label else text))
    return found


def _toc_refuse(message: str, code: str, suggestion: str, **context: Any) -> HwpxValueError:
    return HwpxValueError(message, code=code, context=context or None, suggestion=suggestion)


def _level_style(doc: HwpxDocument, level: int) -> Any:
    for style in doc.oxml.styles.values():
        for name in ((style.name or "").strip(), (style.eng_name or "").strip()):
            found = _TOC_ENTRY_STYLE.match(name)
            if found and int(found.group(1)) == level and (style.type or "PARA").upper() == "PARA":
                return style
    return None


def _run_char_pr(element: Any, predicate: Any) -> str | None:
    for run in element:
        if _local(run) == "run" and any(predicate(node) for node in run):
            return run.get("charPrIDRef")
    return None


def _build_entry(
    doc: HwpxDocument,
    *,
    text: str,
    level: int,
    anchor: str,
    hyperlink: bool,
    template: Any,
    leader: int,
) -> Any:
    """One entry paragraph: Hancom's shape, the template entry's look, the level's 차례 N style."""

    style = _level_style(doc, level)
    if template is not None:
        style_ref = str(style.raw_id if style is not None and style.raw_id is not None else template.get("styleIDRef", "0"))
        para_ref = (str(style.para_pr_id_ref) if style is not None and style.para_pr_id_ref is not None
                    else template.get("paraPrIDRef", "0"))
        tab_t = next((t for t in template.iter(f"{_HP}t") if t.find(f"{_HP}tab") is not None), None)
        tab_attrs = dict(tab_t.find(f"{_HP}tab").attrib) if tab_t is not None else {}
        text_char = _run_char_pr(template, lambda node: _local(node) == "t" and node.find(f"{_HP}tab") is not None)
        link_char = _run_char_pr(template, lambda node: _local(node) == "ctrl" and node.find(f"{_HP}fieldBegin") is not None)
    else:
        style_ref = str(style.raw_id) if style is not None and style.raw_id is not None else "0"
        para_ref = (str(style.para_pr_id_ref) if style is not None and style.para_pr_id_ref is not None
                    else _entry_para_pr(doc, leader))
        tab_attrs, text_char, link_char = {}, None, None
    style_char = str(style.char_pr_id_ref) if style is not None and style.char_pr_id_ref is not None else "0"
    text_char = text_char or style_char
    link_char = link_char or text_char
    if not tab_attrs:
        tab_attrs = {"width": "34032", "leader": str(leader), "type": "2"}
    paragraph = ET.Element(f"{_HP}p", {
        "id": _NON_UNIQUE_PARA_ID, "paraPrIDRef": para_ref, "styleIDRef": style_ref,
        "pageBreak": "0", "columnBreak": "0", "merged": "0",
    })
    begin = None
    if hyperlink:
        run = ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": link_char})
        begin = _field_begin(run, ftype="HYPERLINK", field_id=_rand_id(), editable="0", dirty="1")
        params = ET.SubElement(begin, f"{_HP}parameters", {"cnt": "5", "name": ""})
        _param(params, "integerParam", "Prop", "0")
        _param(params, "stringParam", "Command", f"?#{anchor};0;1;0;")
        _param(params, "stringParam", "Category", "HWPHYPERLINK_TYPE_HWP")
        _param(params, "stringParam", "TargetType", "HWPHYPERLINK_TARGET_OUTLINE")
        _param(params, "stringParam", "DocOpenType", "HWPHYPERLINK_JUMP_CURRENTTAB")
    run = ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": text_char})
    node = ET.SubElement(run, f"{_HP}t")
    node.text = text
    ET.SubElement(node, f"{_HP}tab", tab_attrs).tail = ""  # the page: Hancom fills it in
    if begin is not None:
        _field_end(ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": link_char}), begin)
        ET.SubElement(ET.SubElement(paragraph, f"{_HP}run", {"charPrIDRef": link_char}), f"{_HP}t")
    return paragraph


def rebuild_toc(doc: HwpxDocument, begin: Any) -> None:
    """Rewrite the heading entries of the TOC opened by *begin* from the document's outline paragraphs.

    The entries of its first block (up to the next 차례 제목 paragraph: "<표 차례>" …) are replaced by one
    entry per outline paragraph of level 1 to its ``ContentsLevel`` (not marked 차례 숨기기), in
    document order, with the paragraph's number and text, its level's 차례 N style and the look of
    the entries it had; linked to the heading when the TOC links (``ContentsHyperlink``). Page numbers
    are left empty and the field is marked ``dirty``: Hancom fills them in -- and builds the region
    again by its own rules -- the next time it opens the document. Other blocks stay as they are.
    """

    values = toc_command_values(_param_text(begin, "Command"))
    level_text = values.get("ContentsLevel", "")
    if not level_text.isdigit():
        raise _toc_refuse(
            "the table of contents does not say how many outline levels it collects (ContentsLevel)",
            "toc-command-unknown",
            "Mark it for Hancom to rebuild (toc.refresh_on_open = True) instead.",
            command=_param_text(begin, "Command"),
        )
    paragraph, end, middle = _region(doc, begin)
    if end is None:
        raise _toc_refuse(
            "the table of contents begins and ends in one paragraph: there is no place for its entries",
            "toc-region-unsupported",
            "Remove it (toc.remove()) and add a new one (doc.refs.add_table_of_contents()).",
        )
    block: list[Any] = []
    for element in middle:
        if _is_toc_heading(doc, element):
            break
        block.append(element)
    old_entries = [element for element in block if _entry_text(element) is not None]
    template = old_entries[0] if old_entries else None
    region = [paragraph.element, *middle, end]
    hyperlink = values.get("ContentsHyperlink", "1") not in ("0", "false")
    leader_text = values.get("ContentsLeader", "3")
    leader = int(leader_text) if leader_text.isdigit() and int(leader_text) < len(_TAB_LEADER_NAMES) else 3
    new_entries = []
    for heading, level, text in toc_headings(doc, int(level_text), exclude=region):
        anchor = ""
        if hyperlink:
            before = heading.element.get("id")
            anchor = ensure_paragraph_anchor_id(doc, heading)  # Hancom finds a heading by a unique id
            if anchor != before:
                heading.section.mark_dirty()
        new_entries.append(_build_entry(doc, text=text, level=level, anchor=anchor, hyperlink=hyperlink,
                                        template=template, leader=leader))
    container = paragraph.element.getparent()
    position = (container.index(old_entries[0]) if old_entries
                else container.index(middle[0] if middle else end))
    for element in old_entries:
        container.remove(element)
    for offset, element in enumerate(new_entries):
        container.insert(position + offset, element)
    begin.set("dirty", "1")
    paragraph.section.mark_dirty()


def remove_toc(doc: HwpxDocument, begin: Any) -> None:
    """Take the TOC opened by *begin* out: everything between its begin and end, paragraphs and all,
    as a field's content goes; what follows the end in its paragraph joins the begin's paragraph."""

    from hwpx._document.fields import remove_form_field

    remove_form_field(doc, begin, keep_text=False)


def list_tables_of_contents(doc: HwpxDocument) -> tuple[Any, ...]:
    """The document's tables of contents (``fieldBegin type="TABLEOFCONTENTS"``), in document order."""

    from hwpx._document.fields import _field_type_is, _iter_field_matches
    from hwpx.objects.form_field import TableOfContents

    return tuple(
        TableOfContents(doc, match["_field_begin"])
        for match in _iter_field_matches(doc, _field_type_is("TABLEOFCONTENTS"))
    )


def add_table_of_contents(
    doc: HwpxDocument,
    *,
    index: int = 0,
    section: int = 0,
    title: str = "<제목 차례>",
    levels: int = 2,
    leader: str = "DASH",
    hyperlink: bool = True,
) -> Any:
    """Put a TOC of the document's outline paragraphs of level 1 to *levels* at paragraph *index* of
    *section*, written as Hancom writes one, and return it (``refresh_on_open`` on, page numbers empty)."""

    if isinstance(levels, bool) or not isinstance(levels, int) or not 1 <= levels <= 10:
        raise _toc_refuse(f"levels must be an int from 1 to 10; got {levels!r}", "toc-levels-value",
                          "Pass how many outline levels the table collects (Hancom's default is 2).",
                          requested=repr(levels))
    if leader not in _TAB_LEADER_NAMES:
        raise _toc_refuse(f"leader must be one of {', '.join(_TAB_LEADER_NAMES)}; got {leader!r}",
                          "toc-leader-value", "Pass 'DASH' for Hancom's dotted leader, 'NONE' for none.",
                          requested=repr(leader))
    if not isinstance(title, str) or not isinstance(hyperlink, bool):
        raise _toc_refuse("title must be a str and hyperlink True or False", "toc-levels-value",
                          "Pass the title shown over the entries, e.g. '<제목 차례>'.")
    # Where it goes, before anything is written: an index past the section's paragraphs was refused
    # by the insertion (a bare IndexError), after the headings had been given their anchor ids.
    sections = doc.oxml.sections
    if isinstance(section, bool) or not isinstance(section, int) or not -len(sections) <= section < len(sections):
        raise _toc_refuse(f"section must be the index of a section (0 to {len(sections) - 1}); got {section!r}",
                          "toc-place-value", "Pass the section the table goes into, e.g. section=0.",
                          requested=repr(section))
    count = len(sections[section].paragraphs)
    from ..oxml.table_sizes import whole_number

    place = whole_number(index, floats=True)  # a whole number of any kind, as before (1, 1.0, Decimal("1"))
    if place is None or not 0 <= place <= count:
        raise _toc_refuse(f"index must be a paragraph position from 0 to {count}; got {index!r}",
                          "toc-place-value", "Pass where the table goes among the section's paragraphs (0: first).",
                          requested=repr(index), count=count)
    index = place
    headings = toc_headings(doc, levels)
    if not headings:
        raise _toc_refuse(
            f"the document has no outline paragraph of level 1 to {levels} to list",
            "toc-no-headings",
            "Add headings first (doc.add_heading), or give a paragraph an outline level.",
            levels=levels,
        )
    summary = add_native_toc(doc, at_index=index, title=title, level=levels,
                             leader=_TAB_LEADER_NAMES.index(leader), hyperlink=hyperlink, dirty=True,
                             headings=[heading for heading, _level, _text in headings], section=section)
    toc = next(toc for toc in list_tables_of_contents(doc) if toc.element.get("id") == summary["tocFieldId"])
    toc.rebuild()
    return toc
