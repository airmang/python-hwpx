# SPDX-License-Identifier: Apache-2.0
"""Content-level read-fidelity harness for HWPX (M6 / S-060).

Where :mod:`hwpx.tools.roundtrip_diff` measures *element-count* preservation,
this module measures *content* fidelity:

* :func:`resolve_run_spans` — the canonical per-run resolved formatting
  (bold / italic / underline / strikeout / color / size / font). This is the
  single source of truth the installed MCP surface is verified against.
* :func:`collect_notes` — footnote / endnote instances with their body text and
  body run formatting (the reading surfaces drop these today).
* :func:`roundtrip_fidelity` / :func:`corpus_fidelity` — open->save->reopen
  agreement, the lossless guard.
* :func:`spans_fidelity` / :func:`notes_fidelity` — general comparators reused
  to score a candidate extraction (e.g. an MCP tool payload) against the
  canonical one.

Purely structural — no Hancom oracle required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from hwpx.document import HwpxDocument

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
#: Values that mean "attribute is present but inactive".
_OFF = {None, "", "NONE"}


@dataclass(frozen=True)
class RunSpan:
    """Resolved inline formatting of a single ``<hp:run>``."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: str | None = None  # underline TYPE (BOTTOM/CENTER/TOP...) or None when off
    strikeout: bool = False
    color: str | None = None
    size_pt: float | None = None
    font: str | None = None
    superscript: bool = False
    subscript: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "strikeout": self.strikeout,
            "color": self.color,
            "sizePt": self.size_pt,
            "font": self.font,
            "superscript": self.superscript,
            "subscript": self.subscript,
        }


@dataclass(frozen=True)
class NoteSpan:
    """A footnote / endnote instance and its resolved body."""

    kind: str  # "footNote" | "endNote"
    inst_id: str | None
    anchor_para_index: int
    body_text: str
    body_spans: tuple[RunSpan, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "instId": self.inst_id,
            "anchorParaIndex": self.anchor_para_index,
            "bodyText": self.body_text,
            "bodySpans": [s.to_dict() for s in self.body_spans],
        }


# ── resolution ───────────────────────────────────────────────────────
def _fontface_maps(doc: HwpxDocument) -> dict[str, dict[str, str]]:
    """Return ``{lang: {font_id: face_name}}`` from every header's fontfaces."""
    maps: dict[str, dict[str, str]] = {}
    for header in getattr(doc.oxml, "headers", []) or []:
        element = getattr(header, "element", None)
        if element is None:
            continue
        for fontface in element.iter(f"{_HH}fontface"):
            lang = (fontface.get("lang") or "").lower()
            bucket = maps.setdefault(lang, {})
            for font in fontface.findall(f"{_HH}font"):
                fid, face = font.get("id"), font.get("face")
                if fid is not None and face is not None:
                    bucket.setdefault(fid, face)
    return maps


def _resolve_font(style: Any, fontfaces: dict[str, dict[str, str]]) -> str | None:
    font_ref = (style.child_attributes.get("fontRef") if style else None) or {}
    fid = font_ref.get("hangul")
    if fid is None:
        fid = next(iter(font_ref.values()), None)
    if fid is None:
        return None
    return fontfaces.get("hangul", {}).get(fid) or None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _style_to_span(text: str, style: Any, fontfaces: dict[str, dict[str, str]]) -> RunSpan:
    if style is None:
        return RunSpan(text=text)
    child = style.child_attributes or {}

    underline_type = (child.get("underline") or {}).get("type")
    if underline_type in _OFF:
        underline_type = None

    strike_shape = (child.get("strikeout") or {}).get("shape")
    strikeout = strike_shape not in _OFF

    height = style.attributes.get("height")
    size_pt = round(_int(height) / 100.0, 2) if height and _int(height) > 0 else None

    offset_h = _int((child.get("offset") or {}).get("hangul"))

    return RunSpan(
        text=text,
        bold="bold" in child,
        italic="italic" in child,
        underline=underline_type,
        strikeout=strikeout,
        color=style.attributes.get("textColor"),
        size_pt=size_pt,
        font=_resolve_font(style, fontfaces),
        superscript=offset_h > 0,
        subscript=offset_h < 0,
    )


def resolve_run_spans(doc: HwpxDocument) -> list[RunSpan]:
    """Return the resolved inline formatting for every body run, in order."""
    fontfaces = _fontface_maps(doc)
    spans: list[RunSpan] = []
    for section in doc.sections:
        for paragraph in section.paragraphs:
            for run in paragraph.runs:
                spans.append(_style_to_span(run.text or "", run.style, fontfaces))
    return spans


def collect_notes(doc: HwpxDocument) -> list[NoteSpan]:
    """Return every footnote / endnote with body text and body formatting."""
    fontfaces = _fontface_maps(doc)
    notes: list[NoteSpan] = []
    para_index = 0
    for section in doc.sections:
        for paragraph in section.paragraphs:
            for note in list(paragraph.footnotes) + list(paragraph.endnotes):
                body_spans: tuple[RunSpan, ...] = ()
                try:
                    body = note.body_paragraph
                    body_spans = tuple(
                        _style_to_span(r.text or "", r.style, fontfaces) for r in body.runs
                    )
                except Exception:  # pragma: no cover - defensive
                    body_spans = ()
                notes.append(
                    NoteSpan(
                        kind=note.kind,
                        inst_id=note.inst_id,
                        anchor_para_index=para_index,
                        body_text=note.text,
                        body_spans=body_spans,
                    )
                )
            para_index += 1
    return notes


# ── comparators ──────────────────────────────────────────────────────
def _first_mismatch(ref: Sequence[Any], cand: Sequence[Any]) -> dict[str, Any] | None:
    for i, a in enumerate(ref):
        b = cand[i] if i < len(cand) else None
        if a != b:
            return {"index": i, "ref": a.to_dict() if a is not None else None,
                    "cand": b.to_dict() if b is not None else None}
    if len(cand) > len(ref):
        return {"index": len(ref), "ref": None, "cand": cand[len(ref)].to_dict()}
    return None


def spans_fidelity(ref: Sequence[RunSpan], cand: Sequence[RunSpan]) -> dict[str, Any]:
    """Fraction of reference run-spans reproduced identically by ``cand``."""
    denom = max(len(ref), 1)
    same = sum(1 for i, a in enumerate(ref) if i < len(cand) and a == cand[i])
    return {
        "count_ref": len(ref),
        "count_cand": len(cand),
        "same": same,
        "fidelity": same / denom,
        "count_match": len(ref) == len(cand),
        "first_mismatch": _first_mismatch(ref, cand),
    }


def notes_fidelity(ref: Sequence[NoteSpan], cand: Sequence[NoteSpan]) -> dict[str, Any]:
    """Fraction of reference notes reproduced identically by ``cand``."""
    denom = max(len(ref), 1)
    same = sum(1 for i, a in enumerate(ref) if i < len(cand) and a == cand[i])
    return {
        "count_ref": len(ref),
        "count_cand": len(cand),
        "same": same,
        "fidelity": same / denom,
        "count_match": len(ref) == len(cand),
        "first_mismatch": _first_mismatch(ref, cand),
    }


# ── round-trip ───────────────────────────────────────────────────────
def roundtrip_fidelity(source: str | Path | bytes) -> dict[str, Any]:
    """Open->serialize->reopen and score run-format + note preservation."""
    before = HwpxDocument.open(source)
    runs_before = resolve_run_spans(before)
    notes_before = collect_notes(before)

    after = HwpxDocument.open(before.to_bytes())
    runs_after = resolve_run_spans(after)
    notes_after = collect_notes(after)

    return {
        "run_format": spans_fidelity(runs_before, runs_after),
        "notes": notes_fidelity(notes_before, notes_after),
    }


def corpus_fidelity(paths: Sequence[str | Path]) -> dict[str, Any]:
    """Aggregate run-format round-trip fidelity across a corpus."""
    per_file: dict[str, Any] = {}
    total_runs = same_runs = 0
    below: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for path in paths:
        key = str(path)
        try:
            report = roundtrip_fidelity(path)["run_format"]
        except Exception as exc:  # pragma: no cover - defensive
            errors[key] = repr(exc)[:200]
            continue
        per_file[key] = report
        total_runs += report["count_ref"]
        same_runs += report["same"]
        if report["fidelity"] < 1.0 or not report["count_match"]:
            below.append({"file": key, "fidelity": report["fidelity"], "runs": report["count_ref"]})
    return {
        "files": len(per_file),
        "total_runs": total_runs,
        "run_format_fidelity": (same_runs / total_runs) if total_runs else 1.0,
        "files_below_100pct": below,
        "errors": errors,
        "per_file": per_file,
    }
