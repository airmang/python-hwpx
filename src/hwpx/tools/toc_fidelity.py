# SPDX-License-Identifier: Apache-2.0
"""Native TOC / cross-reference fidelity harness (M7 / S-062).

Parses the Hancom-native field contract captured in
``specs/009-native-toc-xrefs/evidence/p0-native-toc-xml-contract.md``:

* ``<hp:fieldBegin type="TABLEOFCONTENTS">`` region whose generated entries are
  HYPERLINK fields wrapping a single ``<hp:t>`` of the form
  ``제목텍스트<hp:tab leader=".."/>쪽번호`` (page number lives in the *tail* of
  the nested ``hp:tab``),
* ``<hp:fieldBegin type="CROSSREF">`` whose cached result is the plain ``hp:t``
  run between its fieldBegin and fieldEnd,
* anchors that are plain paragraph ``id`` attributes (``?#<para-id>``).

Measured semantics (P0, owner-confirmed): CROSSREF caches recompute
automatically on edit/save; the TOC block only recomputes after an explicit
차례 새로 고침 — so ``dirty`` is NOT a reliable staleness marker and the only
honest verdict comes from comparing cached page numbers against rendered ones
(Hancom render -> fitz words). Without an oracle the report degrades to a
structural verdict with ``render_checked=False`` (Constitution V/IX).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from hwpx.document import HwpxDocument

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_TARGET_RE = re.compile(r"\?#(\d+)")
#: Generated paragraphs share this constant id — useless as an anchor.
NON_UNIQUE_PARA_ID = "2147483648"


@dataclass(frozen=True)
class TocEntry:
    target_id: str | None
    title: str
    cached_page: int | None

    def to_dict(self) -> dict[str, Any]:
        return {"targetId": self.target_id, "title": self.title, "cachedPage": self.cached_page}


@dataclass(frozen=True)
class CrossRef:
    target_id: str | None
    cached_page: int | None
    ref_content_type: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetId": self.target_id,
            "cachedPage": self.cached_page,
            "refContentType": self.ref_content_type,
        }


@dataclass
class TocModel:
    """Everything the harness reads out of one document's XML."""

    toc_field_id: str | None = None
    toc_command: str | None = None
    entries: list[TocEntry] = field(default_factory=list)
    crossrefs: list[CrossRef] = field(default_factory=list)
    paragraph_texts: dict[str, str] = field(default_factory=dict)  # para id -> text


# ── XML parsing ──────────────────────────────────────────────────────
def _open(source: str | Path | bytes | HwpxDocument) -> HwpxDocument:
    if isinstance(source, HwpxDocument):
        return source
    return HwpxDocument.open(source)


def _para_text(p_el: Any) -> str:
    parts: list[str] = []
    for t in p_el.iter(f"{_HP}t"):
        if t.text:
            parts.append(t.text)
        for child in t:
            if child.tail:
                parts.append(child.tail)
    return "".join(parts)


def _field_type(ctrl_el: Any) -> tuple[Any, str] | None:
    begin = ctrl_el.find(f"{_HP}fieldBegin")
    if begin is None:
        return None
    return begin, begin.get("type", "")


def _string_params(begin_el: Any) -> dict[str, str]:
    params: dict[str, str] = {}
    parameters = begin_el.find(f"{_HP}parameters")
    if parameters is None:
        return params
    for child in parameters:
        name = child.get("name")
        if name:
            params[name] = child.text or ""
    return params


def _target_of(params: dict[str, str]) -> str | None:
    for key in ("RefPath", "Command"):
        value = params.get(key) or ""
        match = _TARGET_RE.search(value)
        if match:
            return match.group(1)
    return None


def parse_toc_model(source: str | Path | bytes | HwpxDocument) -> TocModel:
    """Parse the native TOC field region, CROSSREF fields, and paragraph ids."""
    doc = _open(source)
    model = TocModel()

    for section in doc.oxml.sections:
        root = section.element
        inside_toc = False  # region state spans paragraphs (fieldBegin..fieldEnd)
        for p_el in root.iter(f"{_HP}p"):
            pid = p_el.get("id")
            if pid and pid not in model.paragraph_texts:
                model.paragraph_texts[pid] = _para_text(p_el)

            # walk runs/ctrls in document order with a tiny state machine
            hyperlink_target: str | None = None
            crossref: dict[str, Any] | None = None
            for run in p_el.findall(f"{_HP}run"):
                for child in run:
                    tag = child.tag
                    if tag == f"{_HP}ctrl":
                        info = _field_type(child)
                        if info is None:
                            end = child.find(f"{_HP}fieldEnd")
                            if end is not None:
                                # closes an open crossref…
                                if crossref is not None:
                                    model.crossrefs.append(
                                        CrossRef(
                                            target_id=crossref["target"],
                                            cached_page=crossref["page"],
                                            ref_content_type=crossref["content_type"],
                                        )
                                    )
                                    crossref = None
                                # …or the TOC region itself
                                if inside_toc and end.get("beginIDRef") == model.toc_field_id:
                                    inside_toc = False
                            continue
                        begin, ftype = info
                        params = _string_params(begin)
                        if ftype == "TABLEOFCONTENTS":
                            model.toc_field_id = begin.get("id")
                            model.toc_command = params.get("Command")
                            inside_toc = True
                        elif ftype == "CROSSREF":
                            crossref = {
                                "target": _target_of(params),
                                "page": None,
                                "content_type": params.get("RefContentType"),
                            }
                        elif ftype == "HYPERLINK":
                            hyperlink_target = _target_of(params)
                    elif tag == f"{_HP}t":
                        if crossref is not None:
                            digits = (child.text or "").strip()
                            if digits.isdigit():
                                crossref["page"] = int(digits)
                            continue
                        tab = child.find(f"{_HP}tab")
                        if tab is not None and (hyperlink_target is not None or inside_toc):
                            # Hyperlinked entry (ContentsHyperlink:1, gold) or the
                            # PLAIN entry Hancom regenerates with ContentsHyperlink:0
                            # (measured on a refreshed save): same t+tab+page shape,
                            # no target reference — identity resolves by title.
                            title = (child.text or "").strip()
                            page_text = (tab.tail or "").strip()
                            model.entries.append(
                                TocEntry(
                                    target_id=hyperlink_target,
                                    title=title,
                                    cached_page=int(page_text) if page_text.isdigit() else None,
                                )
                            )
                            hyperlink_target = None
    return model


# ── structural verdict (oracle-free) ─────────────────────────────────
def structural_report(source: str | Path | bytes | HwpxDocument) -> dict[str, Any]:
    """Oracle-free checks: fields present, anchors resolve, internal consistency.

    ``internal_conflicts`` cross-checks CROSSREF caches (auto-recomputed by
    Hancom) against TOC entry caches (explicit-refresh only) for shared
    targets — a disagreement proves the TOC block is stale without any render.
    """
    model = parse_toc_model(source)
    targets = [e.target_id for e in model.entries] + [c.target_id for c in model.crossrefs]
    unresolved = [t for t in targets if t and t not in model.paragraph_texts]

    conflicts: list[dict[str, Any]] = []
    entry_pages = {e.target_id: e.cached_page for e in model.entries if e.target_id}
    for ref in model.crossrefs:
        if ref.target_id in entry_pages and ref.cached_page is not None:
            toc_page = entry_pages[ref.target_id]
            if toc_page is not None and toc_page != ref.cached_page:
                conflicts.append(
                    {
                        "targetId": ref.target_id,
                        "tocCachedPage": toc_page,
                        "crossrefCachedPage": ref.cached_page,
                    }
                )

    return {
        "hasNativeToc": model.toc_field_id is not None,
        "tocCommand": model.toc_command,
        "entryCount": len(model.entries),
        "crossrefCount": len(model.crossrefs),
        "entries": [e.to_dict() for e in model.entries],
        "crossrefs": [c.to_dict() for c in model.crossrefs],
        "unresolvedTargets": unresolved,
        "targetsResolve": not unresolved,
        "internal_conflicts": conflicts,
        "internally_consistent": not conflicts,
    }


# ── repagination trigger ─────────────────────────────────────────────
def grow_paragraph(doc: HwpxDocument, *, contains: str, added_chars: int = 2000) -> bool:
    """Lengthen the first body paragraph containing ``contains`` to force a
    page shift on the next Hancom re-layout. Returns True when applied."""
    filler = " 재배열을 유발하기 위한 채움 문장입니다." * (added_chars // 24 + 1)
    for section in doc.sections:
        for paragraph in section.paragraphs:
            text = paragraph.text or ""
            if contains in text:
                paragraph.text = text + filler[:added_chars]
                return True
    return False


# ── oracle leg ───────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


_OUTLINE_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*\.?")


def heading_rendered_pages(pdf_path: str, headings: dict[str, str]) -> dict[str, int | None]:
    """Locate each heading's rendered page (1-based) via the PDF text layer.

    Line-exact matching (measured discipline — a page-substring heuristic
    misfires two ways against a real Hancom render: body echoes of the title
    match later pages, and excluding the TOC's page hides a heading that
    shares it). A rendered heading is a *whole line* equal to the title,
    optionally prefixed by its outline number ("1." / "2.1"). TOC entry lines
    never match (they carry a trailing leader + page digits) and body echoes
    never match (the line continues past the title). Wrapped multi-line
    headings are a known limitation — keep demo headings single-line.
    """
    from hwpx.form_fit.wordbox import extract_word_boxes

    boxes = extract_word_boxes(pdf_path)
    grouped: dict[tuple[int, int, int], list[Any]] = {}
    for box in boxes:
        grouped.setdefault((box.page, box.block, box.line), []).append(box)
    lines: list[tuple[int, str]] = []
    for (page, _block, _line), words in sorted(grouped.items()):
        text = _normalize("".join(w.text for w in sorted(words, key=lambda w: w.word_no)))
        if text:
            lines.append((page, text))

    result: dict[str, int | None] = {}
    for para_id, title in headings.items():
        needle = _normalize(title)
        found: int | None = None
        if needle:
            for page, line_text in lines:
                if line_text == needle or _OUTLINE_PREFIX_RE.sub("", line_text) == needle:
                    # LAST match wins: the TOC region precedes the body, and a
                    # TOC entry whose page digit wraps to its own line (no
                    # right tab stop) is indistinguishable from a numbered
                    # heading line — measured against a real render of our own
                    # emission. The real heading always follows the TOC.
                    found = page + 1  # fitz 0-based -> Hancom 1-based
        result[para_id] = found
    return result


def toc_verify(
    source: str | Path | bytes,
    *,
    oracle: Any | None = None,
    pdf_path: str | None = None,
) -> dict[str, Any]:
    """Full verdict: structural report + (when a render is available) cached
    page numbers checked against rendered heading pages.

    Pass ``pdf_path`` to reuse an existing render; else ``oracle.render_pdf``
    is used when the oracle reports available. Otherwise degrades honestly.
    """
    structural = structural_report(source)
    report: dict[str, Any] = {
        "structural": structural,
        "render_checked": False,
        "toc_correctness_ratio": None,
        "stale_entries": [],
        "crossref_correctness_ratio": None,
        "verdict": "unverified",
    }

    model = parse_toc_model(source)

    def _entry_key(entry: TocEntry) -> str | None:
        """Lookup key for an entry: its anchor id, or (plain regenerated
        entries carry no target reference) a title-derived key."""
        if entry.target_id:
            return entry.target_id
        stripped = _OUTLINE_PREFIX_RE.sub("", _normalize(entry.title))
        return f"title::{stripped}" if stripped else None

    headings: dict[str, str] = {}
    for t in {e.target_id for e in model.entries} | {c.target_id for c in model.crossrefs}:
        if t and t in model.paragraph_texts and model.paragraph_texts[t].strip():
            headings[t] = model.paragraph_texts[t]
    for entry in model.entries:
        key = _entry_key(entry)
        if key and key.startswith("title::"):
            # identity by title: the rendered heading line equals the entry
            # title minus its numbering prefix
            title = _OUTLINE_PREFIX_RE.sub("", entry.title.strip()).strip()
            if title:
                headings[key] = title

    rendered_pdf = pdf_path
    if rendered_pdf is None and oracle is not None:
        try:
            if getattr(oracle, "available", lambda: False)():
                src = source if isinstance(source, (str, Path)) else None
                if src is None:
                    import tempfile

                    handle, tmp = tempfile.mkstemp(suffix=".hwpx")
                    Path(tmp).write_bytes(source)  # type: ignore[arg-type]
                    src = tmp
                rendered_pdf = oracle.render_pdf(str(src))
        except Exception:  # pragma: no cover - defensive: degrade, never crash
            rendered_pdf = None

    if not rendered_pdf:
        if not structural["internally_consistent"]:
            report["verdict"] = "stale_detected_structurally"
        return report

    try:
        actual = heading_rendered_pages(rendered_pdf, headings)
    except Exception:  # pragma: no cover - fitz/pdf failure -> honest degrade
        return report

    report["render_checked"] = True
    report["rendered_pdf"] = rendered_pdf
    report["heading_pages"] = actual

    stale: list[dict[str, Any]] = []
    scored = 0
    correct = 0
    entry_rows: list[dict[str, Any]] = []
    for entry in model.entries:
        actual_page = actual.get(_entry_key(entry) or "")
        row = entry.to_dict() | {"actualPage": actual_page}
        if entry.cached_page is not None and actual_page is not None:
            scored += 1
            if entry.cached_page == actual_page:
                correct += 1
            else:
                stale.append(row)
        entry_rows.append(row)
    report["toc_entries"] = entry_rows
    report["toc_correctness_ratio"] = (correct / scored) if scored else None
    report["stale_entries"] = stale

    xr_scored = xr_correct = 0
    xr_rows: list[dict[str, Any]] = []
    for ref in model.crossrefs:
        actual_page = actual.get(ref.target_id or "")
        row = ref.to_dict() | {"actualPage": actual_page}
        if ref.cached_page is not None and actual_page is not None:
            xr_scored += 1
            if ref.cached_page == actual_page:
                xr_correct += 1
        xr_rows.append(row)
    report["crossrefs"] = xr_rows
    report["crossref_correctness_ratio"] = (xr_correct / xr_scored) if xr_scored else None

    ratios = [r for r in (report["toc_correctness_ratio"], report["crossref_correctness_ratio"]) if r is not None]
    if not ratios:
        report["verdict"] = "unverified"
    elif all(r == 1.0 for r in ratios):
        report["verdict"] = "verified"
    else:
        report["verdict"] = "stale"
    return report
