#!/usr/bin/env python3
"""Re-run the bounded M9 P0 Mac render and clip-detectability spike.

The input JSONL is a membership receipt only: each row must contain ``src``.
Outputs are fresh current-stack PDFs plus raw, hash-bound receipts.  This script
does not assign a visual pass; it only records render availability/timing and
whether PyMuPDF can discover table-cell clips for later differential checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from importlib import metadata
from pathlib import Path
from typing import Any

from hwpx.form_fit.wordbox import extract_cell_clips, extract_glyph_boxes
from hwpx.visual.oracle import MacHancomOracle


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_sources(path: Path) -> list[Path]:
    sources: list[Path] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        src = row.get("src") if isinstance(row, dict) else None
        if not isinstance(src, str) or not src:
            raise ValueError(f"{path}:{line_no}: missing src")
        source = Path(src).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        sources.append(source)
    if not sources:
        raise ValueError("membership receipt contained no sources")
    return sources


def _hancom_build(oracle: MacHancomOracle) -> dict[str, str | None]:
    app = oracle._app_path()  # bounded evidence helper; no source content is read
    version: str | None = None
    if app:
        try:
            proc = subprocess.run(
                ["mdls", "-raw", "-name", "kMDItemVersion", app],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            candidate = proc.stdout.strip().strip('"')
            if candidate and candidate != "(null)":
                version = candidate
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"app": app, "version": version}


def run(args: argparse.Namespace) -> int:
    membership = Path(args.membership_jsonl).resolve()
    out_dir = Path(args.out_dir).resolve()
    render_receipt = Path(args.render_receipt).resolve()
    clip_receipt = Path(args.clip_receipt).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    render_receipt.parent.mkdir(parents=True, exist_ok=True)
    clip_receipt.parent.mkdir(parents=True, exist_ok=True)

    sources = _load_sources(membership)
    oracle = MacHancomOracle(timeout=float(args.timeout))
    build = _hancom_build(oracle)
    version = metadata.version("python-hwpx")
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    rows: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        pdf = out_dir / f"{index:03d}_{source.stem}.pdf"
        started = time.monotonic()
        rendered_path = oracle.render_pdf(str(source), str(pdf))
        render_ms = round((time.monotonic() - started) * 1000)
        rendered = bool(rendered_path and pdf.is_file() and pdf.stat().st_size > 0)
        rows.append(
            {
                "index": index,
                "sourceId": source.name,
                "sourcePath": str(source),
                "sourceSha256": _sha256(source),
                "pdf": str(pdf),
                "pdfSha256": _sha256(pdf) if rendered else None,
                "pdfBytes": pdf.stat().st_size if rendered else 0,
                "rendered": rendered,
                "renderMs": render_ms,
                "oracle": "mac-gui",
                "error": None if rendered else "render produced no PDF",
            }
        )
        with render_receipt.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(rows[-1], ensure_ascii=False, sort_keys=True) + "\n")

    clip_rows: list[dict[str, Any]] = []
    for row in rows:
        pdf = Path(row["pdf"])
        if not row["rendered"]:
            clip_rows.append(
                {
                    "index": row["index"],
                    "sourceId": row["sourceId"],
                    "rendered": False,
                    "cellClips": 0,
                    "glyphs": 0,
                    "clipDetectable": False,
                    "error": "render unavailable",
                }
            )
            continue
        try:
            clips = extract_cell_clips(str(pdf))
            glyphs = extract_glyph_boxes(str(pdf))
            clip_rows.append(
                {
                    "index": row["index"],
                    "sourceId": row["sourceId"],
                    "rendered": True,
                    "cellClips": len(clips),
                    "glyphs": len(glyphs),
                    "clipDetectable": bool(clips),
                    "error": None,
                }
            )
        except Exception as exc:  # evidence records the honest unverified tier
            clip_rows.append(
                {
                    "index": row["index"],
                    "sourceId": row["sourceId"],
                    "rendered": True,
                    "cellClips": 0,
                    "glyphs": 0,
                    "clipDetectable": False,
                    "error": type(exc).__name__,
                }
            )

    rendered_count = sum(bool(row["rendered"]) for row in rows)
    detectable = sum(bool(row["clipDetectable"]) for row in clip_rows)
    successful_ms = [int(row["renderMs"]) for row in rows if row["rendered"]]
    report = {
        "schemaVersion": 1,
        "spike": "m9-p0-current-mac-render-clip",
        "generatedAt": generated_at,
        "membershipSha256": _sha256(membership),
        "toolVersions": {"python-hwpx": version, "hancom": build},
        "render": {
            "requested": len(rows),
            "rendered": rendered_count,
            "failed": len(rows) - rendered_count,
            "averageMs": round(sum(successful_ms) / len(successful_ms), 2) if successful_ms else None,
            "maxMs": max(successful_ms) if successful_ms else None,
        },
        "clip": {
            "judged": rendered_count,
            "detectable": detectable,
            "undetectable": rendered_count - detectable,
            "rate": detectable / rendered_count if rendered_count else None,
            "rule": "clipDetectable=false => overflow_checked=false (unverified), never pass",
        },
        "rows": clip_rows,
    }
    clip_receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if rendered_count == len(rows) else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--membership-jsonl", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--render-receipt", required=True)
    parser.add_argument("--clip-receipt", required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    render_receipt = Path(args.render_receipt)
    if render_receipt.exists():
        render_receipt.unlink()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
