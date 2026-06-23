"""Rasterize Hancom-exported PDFs and score the lineseg ON/OFF comparison.

Pipeline (run after run_pairs.py + hancom_render.ps1):

    manifest.json (ON/OFF .hwpx pairs)
      + <pdf-dir>/<stem>.pdf  (one per .hwpx, from hancom_render.ps1)
      -> rasterize each PDF page (pymupdf)
      -> per pair: diff_ratio(ON, OFF) + overlap_score(OFF) vs overlap_score(ON)
      -> verdict + report.json + report.md

Verdicts:
    hancom_relayouts : ON and OFF render ~identically (max diff_ratio < --diff-eps).
                       Stale lineSegArray is HARMLESS; the engine's blanket strip
                       is belt-and-braces, not load-bearing. => P1 can be a
                       'keep + prove' note, not new scoped-invalidation work.
    lineseg_matters  : OFF differs from ON beyond --diff-eps, and/or OFF shows a
                       collapsed-band overlap signature ON does not. Stripping
                       lineseg is load-bearing for visual correctness.
    inconclusive     : a render is missing (pdf not produced / not opened).

Requires pymupdf + Pillow + numpy. Run wherever the PDFs live (the Windows box,
or copy PDFs back to macOS):
    uv run --with pymupdf --with pillow --with numpy python rasterize_score.py \
        --manifest /vc-pairs/manifest.json --pdf-dir /vc-pdfs --out /vc-report
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fitz  # pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from overlap_detect import diff_ratio, overlap_score  # noqa: E402


def _render_pdf(pdf_path: Path, dpi: int = 150) -> list[Image.Image]:
    pages: list[Image.Image] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return pages


def _pdf_for(hwpx_path: str, pdf_dir: Path) -> Path:
    return pdf_dir / (Path(hwpx_path).stem + ".pdf")


def _score_pair(pair: dict, pdf_dir: Path, diff_eps: float) -> dict:
    on_pdf = _pdf_for(pair["on"]["path"], pdf_dir)
    off_pdf = _pdf_for(pair["off"]["path"], pdf_dir)
    out = {"source": pair["source"], "mutation": pair["mutation"],
           "on_pdf": str(on_pdf), "off_pdf": str(off_pdf)}

    if not on_pdf.exists() or not off_pdf.exists():
        out.update(verdict="inconclusive",
                   reason=f"missing pdf (on={on_pdf.exists()}, off={off_pdf.exists()})")
        return out

    on_pages = _render_pdf(on_pdf)
    off_pages = _render_pdf(off_pdf)
    page_count = min(len(on_pages), len(off_pages))
    if page_count == 0:
        out.update(verdict="inconclusive", reason="zero rendered pages")
        return out

    page_results = []
    max_diff = 0.0
    overlap_flag = False
    for i in range(page_count):
        dr = diff_ratio(on_pages[i], off_pages[i])
        on_ov = overlap_score(on_pages[i])
        off_ov = overlap_score(off_pages[i])
        # OFF shows a tall collapsed band that ON does not -> overlap signature.
        page_overlap = (off_ov["tall_band_ratio"] >= 3.0 and
                        off_ov["tall_band_ratio"] > on_ov["tall_band_ratio"] + 1.0)
        overlap_flag = overlap_flag or page_overlap
        max_diff = max(max_diff, dr)
        page_results.append({"page": i, "diff_ratio": round(dr, 5),
                             "on_overlap": on_ov, "off_overlap": off_ov,
                             "page_overlap": page_overlap})

    out["pages"] = page_results
    out["page_count_on"] = len(on_pages)
    out["page_count_off"] = len(off_pages)
    out["max_diff_ratio"] = round(max_diff, 5)
    out["page_count_changed"] = len(on_pages) != len(off_pages)

    if max_diff < diff_eps and not overlap_flag and not out["page_count_changed"]:
        out["verdict"] = "hancom_relayouts"
        out["reason"] = f"max diff {max_diff:.4f} < eps {diff_eps}; no overlap signature"
    else:
        out["verdict"] = "lineseg_matters"
        reasons = []
        if max_diff >= diff_eps:
            reasons.append(f"diff {max_diff:.4f} >= eps {diff_eps}")
        if overlap_flag:
            reasons.append("OFF overlap signature")
        if out["page_count_changed"]:
            reasons.append("page count changed")
        out["reason"] = "; ".join(reasons)
    return out


def _write_markdown(report: dict, path: Path) -> None:
    lines = ["# lineSegArray baseline — Hancom render comparison", ""]
    tally: dict[str, int] = {}
    for r in report["results"]:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    lines.append("## Summary")
    for verdict, count in sorted(tally.items()):
        lines.append(f"- **{verdict}**: {count}")
    lines.append("")
    lines.append("Interpretation:")
    lines.append("- all `hancom_relayouts` -> stale lineseg is harmless; "
                 "P1 scoped-invalidation is NOT needed (keep blanket strip as guard).")
    lines.append("- any `lineseg_matters` -> stripping lineseg IS load-bearing; "
                 "the blanket strip is correct and the byte-patch path must also strip.")
    lines.append("")
    lines.append("## Per-pair")
    lines.append("")
    lines.append("| source | mutation | verdict | max_diff | reason |")
    lines.append("|---|---|---|---|---|")
    for r in report["results"]:
        lines.append(
            f"| {Path(r['source']).name} | {r['mutation']} | {r['verdict']} | "
            f"{r.get('max_diff_ratio', '—')} | {r.get('reason', '')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="run_pairs.py manifest.json")
    parser.add_argument("--pdf-dir", required=True, help="dir with Hancom-exported PDFs")
    parser.add_argument("--out", required=True, help="output dir for report.{json,md}")
    parser.add_argument("--diff-eps", type=float, default=0.005,
                        help="ink-diff fraction below which ON==OFF (default 0.005)")
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text())
    pdf_dir = Path(args.pdf_dir)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    results = []
    for pair in manifest.get("pairs", []):
        if "error" in pair:
            results.append({"source": pair["source"], "mutation": pair.get("mutation"),
                            "verdict": "inconclusive", "reason": "pair errored in run_pairs"})
            continue
        results.append(_score_pair(pair, pdf_dir, args.diff_eps))

    report = {"diff_eps": args.diff_eps, "dpi": args.dpi, "results": results}
    (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    _write_markdown(report, outdir / "report.md")

    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print("verdict tally:", tally)
    print("report:", outdir / "report.json", "and report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
