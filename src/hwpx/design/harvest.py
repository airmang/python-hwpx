# SPDX-License-Identifier: Apache-2.0
"""Harvest a profile from a real Hancom-saved document (plan §2 Phase E, task 1).

Given a genuine ``.hwpx`` it writes, under ``profiles/<id>/``:

* ``template.hwpx`` — a **body-stripped skeleton**: the real document with its
  section body reduced to a single ``secPr``-carrying paragraph. ``header.xml``
  (every style/font/borderFill) and the page setup survive untouched, so the
  committed artifact is small and carries no document content (no PII), yet is
  genuinely Hancom-derived — never imagined XML.
* ``fragments/{title,heading,body,info_table}.xml`` — real ``<hp:p>`` / ``<hp:tbl>``
  elements harvested from the source, with their text **sanitised to placeholders**
  (the style is kept, the content dropped).
* ``profile.json`` — the manifest the loader reads.

This is an authoring-time tool (run once per profile); the committed artifacts are
what production uses.
"""
from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from lxml import etree

from hwpx.document import HwpxDocument

from . import _support as S

PROFILE_SCHEMA = "hwpx.design.profile.v1"

_PLACEHOLDER = {
    "title": "{{title}}",
    "heading": "{{heading}}",
    "body": "{{body}}",
}


def _font_height(doc, ref) -> int:
    style = doc.char_property(ref)
    if style is None:
        return 0
    try:
        return int(style.attributes.get("height") or 0)
    except ValueError:
        return 0


def _text_paragraphs(doc):
    out = []
    for index, para in enumerate(doc.sections[0].paragraphs):
        if getattr(para, "tables", []):
            continue
        text = (para.text or "").strip()
        if not text:
            continue
        runs = para.runs
        cref = runs[0].char_pr_id_ref if runs else "0"
        out.append(
            {
                "index": index,
                "para": para.element.get("paraPrIDRef"),
                "char": cref,
                "h": _font_height(doc, cref),
                "len": len(text),
                "element": para.element,
            }
        )
    return out


def _pick_fragments(doc) -> dict[str, etree._Element]:
    tps = _text_paragraphs(doc)
    if not tps:
        raise ValueError("no text paragraphs to harvest")
    prose = [t for t in tps if t["len"] >= 8] or tps

    title = max(tps, key=lambda t: t["h"])
    combo = Counter((t["para"], t["char"]) for t in prose)
    body_key = combo.most_common(1)[0][0]
    body = next(t for t in prose if (t["para"], t["char"]) == body_key)
    head_pool = [
        t for t in tps
        if (t["para"], t["char"]) != body_key
        and Counter((x["para"], x["char"]) for x in tps)[(t["para"], t["char"])] >= 2
        and t["h"] >= body["h"]
    ]
    heading = max(head_pool, key=lambda t: t["h"], default=title)

    picks = {"title": title, "heading": heading, "body": body}
    fragments = {role: deepcopy(p["element"]) for role, p in picks.items()}
    for role, frag in fragments.items():
        S.set_paragraph_text(frag, _PLACEHOLDER[role])

    info = _pick_info_table(doc)
    if info is not None:
        fragments["info_table"] = info
    return fragments


def _references_binary(element: etree._Element) -> bool:
    """True if *element* embeds an image / binary (so harvesting would dangle)."""

    for node in element.iter():
        if S.ln(node.tag).lower() in ("pic", "img", "image", "ole", "drawing"):
            return True
        for key in node.attrib:
            if "binaryitemidref" in S.ln(key).lower() or "bindata" in S.ln(key).lower():
                return True
    return False


def _is_simple_grid(table_element: etree._Element) -> bool:
    """True if every cell is 1×1 (no row/col merges) — safe to row-clone."""

    for tc in S.iter_local(table_element, "tc"):
        span = next((c for c in tc if S.ln(c.tag) == "cellSpan"), None)
        if span is not None:
            if int(span.get("rowSpan", "1")) > 1 or int(span.get("colSpan", "1")) > 1:
                return False
    return True


def _pick_info_table(doc) -> etree._Element | None:
    best = None
    for para in doc.sections[0].paragraphs:
        for table in getattr(para, "tables", []):
            rows, cols = table.row_count, table.column_count
            if not (2 <= cols <= 4 and 2 <= rows <= 12):
                continue
            if _references_binary(table.element):
                continue  # text-only key-value tables, never image grids
            if not _is_simple_grid(table.element):
                continue  # merge-free grids only — the composer row-clones them
            score = rows * cols
            if best is None or score < best[0]:
                best = (score, table)
    if best is None:
        return None
    # Harvest the *paragraph* that wraps the table — a table is not a valid
    # section child on its own; it must ride inside an <hp:p>.
    frag = deepcopy(best[1].paragraph.element)
    # Sanitise every cell to a neutral placeholder; structure is what we keep.
    for tc in S.iter_local(frag, "tc"):
        sublist = _subList(tc)
        for para in S.children_local(sublist if sublist is not None else tc, "p"):
            S.set_paragraph_text(para, "{{cell}}")
    S.strip_lineseg(frag)
    return frag


def _subList(tc: etree._Element):
    for child in tc:
        if S.ln(child.tag) == "subList":
            return child
    return None


def _build_skeleton(source: Path, out_path: Path) -> dict:
    doc = HwpxDocument.open(source)
    section = doc.sections[0]
    secpr = S.find_secpr(section.element)
    if secpr is None:
        doc.close()
        raise ValueError("template has no secPr (page setup)")
    secpr = deepcopy(secpr)

    empty = etree.SubElement(section.element, S.hp(section.element, "p"))
    run = etree.SubElement(empty, S.hp(section.element, "run"), {"charPrIDRef": "0"})
    etree.SubElement(run, S.hp(section.element, "t")).text = ""
    section.element.remove(empty)  # detach; replace_section_body re-inserts
    S.replace_section_body(section.element, [empty])
    S.move_secpr_into(empty, secpr)
    section.mark_dirty()

    stripped = _strip_binaries(doc)
    _scrub_metadata(doc)

    page = {}
    try:
        ps, pm = section.properties.page_size, section.properties.page_margins
        page = {
            "width": ps.width, "height": ps.height, "orientation": ps.orientation,
            "margins": {"left": pm.left, "right": pm.right, "top": pm.top, "bottom": pm.bottom},
        }
    except Exception:  # pragma: no cover - diagnostics only
        page = {}

    report = doc.save_report(out_path)
    style_count = len(doc.char_properties)
    doc.close()
    return {
        "page": page,
        "char_pr_count": style_count,
        "open_safe": report.open_safety.ok,
        "stripped_parts": stripped,
    }


def _strip_binaries(doc) -> list[str]:
    """Drop embedded images + the source preview (size + PII) from the skeleton.

    The body is already reduced to one empty paragraph, so nothing references
    these parts; removing them (and their manifest items) keeps the committed
    skeleton small and content-free while leaving every style in header.xml.
    """

    package = doc._package
    removed: list[str] = []

    for item in list(package._manifest_items()):
        href = item.get("href", "") or ""
        media = item.get("media-type", "") or ""
        base = href.rsplit("/", 1)[-1]
        if (
            "BinData/" in href
            or base.startswith("PrvImage")
            or media.lower().startswith("image/")
        ):
            item_id = item.get("id")
            if item_id:
                package.remove_manifest_item(item_id)

    for name in list(package.part_names()):
        if name.startswith("BinData/") or name.startswith("Preview/PrvImage"):
            try:
                package.delete(name)
                removed.append(name)
            except Exception:  # pragma: no cover - defensive
                pass

    if package.has_part("Preview/PrvText.txt"):
        package.set_part("Preview/PrvText.txt", b"")  # clear source text (PII)
    return removed


# Manifest (content.hpf) metadata that carries source PII — author, the person who
# last saved, the source title, and timestamps. Cleared so generated docs inherit
# nothing identifying.
_SCRUB_META_NAMES = {
    "creator", "lastsaveby", "subject", "description", "keyword",
    "date", "CreatedDate", "ModifiedDate",
}


def _scrub_metadata(doc) -> None:
    """Blank source-identifying OPF metadata in Contents/content.hpf (PII)."""

    package = doc._package
    try:
        tree = package.manifest_tree()
    except Exception:  # pragma: no cover - defensive
        return
    for element in tree.iter():
        name = S.ln(element.tag)
        if name == "title":
            element.text = ""
        elif name == "meta" and element.get("name") in _SCRUB_META_NAMES:
            element.text = ""
    package.set_part(package.main_content.full_path, tree)


def harvest_profile(source: str | Path, profile_id: str, out_root: str | Path) -> dict:
    """Harvest *source* into ``<out_root>/<profile_id>/`` and return the manifest."""

    source = Path(source)
    out_dir = Path(out_root) / profile_id
    (out_dir / "fragments").mkdir(parents=True, exist_ok=True)

    # Fragments first (reads the full source), then the skeleton (rewrites body).
    doc = HwpxDocument.open(source)
    fragments = _pick_fragments(doc)
    doc.close()

    roles = []
    for role, frag in fragments.items():
        path = out_dir / "fragments" / f"{role}.xml"
        path.write_bytes(etree.tostring(frag, encoding="UTF-8"))
        roles.append(role)

    skel = _build_skeleton(source, out_dir / "template.hwpx")

    manifest = {
        "schemaVersion": PROFILE_SCHEMA,
        "id": profile_id,
        "template": "template.hwpx",
        "fragments": {role: f"fragments/{role}.xml" for role in roles},
        "page": skel["page"],
        "char_pr_count": skel["char_pr_count"],
        "style_coverage_threshold": 0.98,
        "source_basename": source.name,
    }
    (out_dir / "profile.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        **manifest,
        "skeleton_open_safe": skel["open_safe"],
        "stripped_parts": skel.get("stripped_parts", []),
    }


__all__ = ["harvest_profile", "PROFILE_SCHEMA"]
