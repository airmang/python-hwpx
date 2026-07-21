#!/usr/bin/env python3
"""rhwp_triage.py — internal, fail-closed triage wrapper around the rhwp CLI.

**Not a public API. Not a visual oracle. Internal dev tool only.**

Context (do not skip before touching this file):
  - specs/033-rhwp-spike/go-no-go.md — S-090 go/no-go: rhwp is a conditional,
    narrow, read-side/triage tool. Its exit code is UNRELIABLE (0 even on
    parse failure / missing file / unknown subcommand — verified by the
    spike's own root re-check). Hancom Office remains the only visual oracle,
    permanently. rhwp may never become a mutation path or a trusted producer.
  - specs/035-formfill-round2/evidence/p0/rhwp-divergence-audit.md — rhwp
    ignores landscape orientation, multi-column flow, and 2-up pagination, so
    its ABSOLUTE page count is not comparable to Hancom's on such documents.
    However, a blank-vs-filled DELTA computed with the *same* rhwp render is
    self-consistent (the same approximation error applies to both renders and
    mostly cancels), which is what makes it useful as a cheap, offline,
    Hancom-free ripple screen. This module exists to test that hypothesis, not
    to assert it.

Design rules enforced by this module (do not relax these without re-reading
go-no-go.md):
  1. Exact-pin binary. Every invocation re-hashes RHWP_BIN and compares it to
     the sha256 recorded in the S-090 spike receipt
     (python-hwpx-s090/work/rhwp-spike/receipts/capability_probe.md). A
     mismatch or missing binary is a typed error, never a silent skip.
  2. Exit code is IGNORED for pass/fail judgment. A verdict is "ok" iff the
     expected output file exists, has nonzero size, AND PyMuPDF can open it.
     This is required because rhwp returns exit 0 on parse failure, on a
     missing input file, and even on an unknown subcommand (measured in the
     S-090 spike; see receipts/failure_modes.json / capability_probe.md).
  3. Fail-closed. Every failure path returns a typed `reason` string. Nothing
     is silently coerced to a boolean "False" without saying why, and a
     verdict that cannot be determined (e.g. one side of a pair failed to
     render) is reported as `None`/"undetermined", never guessed at.
  4. Non-authoritative. Nothing in this module's output should be read as
     "the document renders correctly" — only as "rhwp did/didn't produce a
     plausible screening signal". Hancom render_checked remains the only
     correctness oracle anywhere in this codebase.

CLI usage:
    python scripts/rhwp_triage.py check-binary
    python scripts/rhwp_triage.py probe FILE.hwpx [FILE2.hwpx ...]
    python scripts/rhwp_triage.py validate-p0 [--out work/rhwp-triage]
    python scripts/rhwp_triage.py demo-failclosed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# Exact-pin binary reference. Values come from the S-090 spike receipt
# (python-hwpx-s090/work/rhwp-spike/receipts/capability_probe.md) — do not
# update RHWP_BIN_SHA256 without re-verifying against a fresh spike receipt.
# ---------------------------------------------------------------------------
RHWP_BIN = Path(
    "/Users/wilycastle/Code/projects/hwpx/python-hwpx-s090/work/rhwp-spike/"
    "rhwp-bin/rhwp/rhwp"
)
RHWP_VERSION = "v0.7.19"
RHWP_BIN_SHA256 = "4ef5b3928f2f628a5711472f187d3910b6ccdee015ce2ff2fbb0f71fc5f5d9b6"

# Spike's own tail latency was 12.5s (mpm-law-1285_10, a 27/54-page document).
# 30s gives a >2x margin without letting a hang stall a batch run.
DEFAULT_TIMEOUT_S = 30.0


class RhwpTriageError(RuntimeError):
    """Typed, fail-closed error raised for conditions that must never be
    silently swallowed (missing/mismatched binary). Distinct from a per-doc
    DocVerdict, which records a failure as data rather than raising.
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def verify_binary(
    expected_sha256: str = RHWP_BIN_SHA256, binary: Path = RHWP_BIN
) -> str:
    """Exact-pin check against the S-090 spike receipt.

    Raises RhwpTriageError if the binary is missing or its sha256 does not
    match. Called before every subprocess invocation in this module — a path
    on disk named "rhwp" is not trusted just because it exists.
    """
    if not binary.exists():
        raise RhwpTriageError("BINARY_NOT_FOUND", str(binary))
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise RhwpTriageError(
            "BINARY_SHA256_MISMATCH",
            f"{binary} sha256={digest} expected={expected_sha256}",
        )
    return digest


# ---------------------------------------------------------------------------
# Subprocess wrapper — exit code ignored by design (see module docstring §2).
# ---------------------------------------------------------------------------

_TIME_RSS_RE = re.compile(r"^\s*(\d+)\s+maximum resident set size", re.M)


@dataclass
class RunResult:
    argv: list
    returncode: Optional[int]
    wall_s: float
    stdout: str
    stderr: str
    timed_out: bool = False
    rss_bytes: Optional[int] = None


def _decode(x) -> str:
    if isinstance(x, bytes):
        return x.decode(errors="replace")
    return x or ""


def _run(argv: list[str], timeout: float = DEFAULT_TIMEOUT_S) -> RunResult:
    """Run under /usr/bin/time -l (macOS) to also capture peak RSS."""
    wrapped = ["/usr/bin/time", "-l", *argv]
    t0 = time.monotonic()
    try:
        cp = subprocess.run(wrapped, capture_output=True, text=True, timeout=timeout)
        wall = round(time.monotonic() - t0, 4)
        res = RunResult(argv, cp.returncode, wall, cp.stdout, cp.stderr)
    except subprocess.TimeoutExpired as e:
        wall = round(time.monotonic() - t0, 4)
        res = RunResult(
            argv, None, wall, _decode(e.stdout), _decode(e.stderr), timed_out=True
        )
    m = _TIME_RSS_RE.search(res.stderr)
    if m:
        res.rss_bytes = int(m.group(1))
    return res


def _stderr_head(text: str, n: int = 400) -> str:
    """First N chars of stderr.

    Deliberately the HEAD, not the tail: stderr is wrapped with
    `/usr/bin/time -l`, which appends its own resource-usage block AFTER the
    wrapped program's output. rhwp's own typed Korean error text (the thing
    a caller actually needs to see) is always at the head; the tail is time's
    noise.
    """
    text = (text or "").strip()
    return text[:n]


# ---------------------------------------------------------------------------
# Per-document verdict
# ---------------------------------------------------------------------------


@dataclass
class DocVerdict:
    docId: str
    sourcePath: str
    rhwpOk: bool
    pages: Optional[int]
    textChars: Optional[int]
    reason: Optional[str]  # typed reason; present iff not rhwpOk
    wallS: float
    timedOut: bool
    rssBytes: Optional[int]
    stderrHead: str
    pdfPath: Optional[str]


def export_pdf_verdict(
    doc_id: str,
    src: Path,
    out_dir: Path,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> DocVerdict:
    """Render `src` via `rhwp export-pdf` and judge the result.

    Judgment is output-existence + size + fitz-openability. The rhwp exit
    code is read into the record for debugging but never used to decide ok/
    not-ok (see module docstring §2 — it is 0 on failure in this CLI).
    """
    src = Path(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = out_dir / f"{doc_id}.rhwp.pdf"

    if not src.exists():
        return DocVerdict(
            doc_id, str(src), False, None, None, "SOURCE_NOT_FOUND",
            0.0, False, None, "", None,
        )

    verify_binary()  # raises RhwpTriageError on pin mismatch — never proceeds silently

    if out_pdf.exists():
        out_pdf.unlink()
    argv = [str(RHWP_BIN), "export-pdf", str(src), "-o", str(out_pdf)]
    res = _run(argv, timeout=timeout)

    if res.timed_out:
        return DocVerdict(
            doc_id, str(src), False, None, None, "TIMEOUT",
            res.wall_s, True, res.rss_bytes, _stderr_head(res.stderr), None,
        )

    if not out_pdf.exists() or out_pdf.stat().st_size == 0:
        return DocVerdict(
            doc_id, str(src), False, None, None, "NO_OUTPUT_WRITTEN",
            res.wall_s, False, res.rss_bytes, _stderr_head(res.stderr), None,
        )

    try:
        d = fitz.open(str(out_pdf))
        pages = d.page_count
        chars = sum(len(pg.get_text("text")) for pg in d)
        d.close()
    except Exception as exc:  # noqa: BLE001 - typed into the record, not raised
        return DocVerdict(
            doc_id, str(src), False, None, None,
            f"FITZ_OPEN_FAILED: {type(exc).__name__}: {exc}",
            res.wall_s, False, res.rss_bytes, _stderr_head(res.stderr), str(out_pdf),
        )

    return DocVerdict(
        doc_id, str(src), True, pages, chars, None,
        res.wall_s, False, res.rss_bytes, _stderr_head(res.stderr), str(out_pdf),
    )


# ---------------------------------------------------------------------------
# Layout caveats — landscape / multi-column detection on the SOURCE hwpx.
#
# Rationale (rhwp-divergence-audit.md): rhwp ignores landscape orientation,
# multi-column flow, and 2-up pagination, so a document with any of these
# properties has an ABSOLUTE rhwp page count that is not comparable to
# Hancom's. This does not invalidate the blank-vs-filled DELTA signal (same
# renderer both sides), but it is reported so a human reading triage output
# knows which documents that caveat applies to.
#
# KNOWN LIMITATION (found while building this tool, documented honestly):
# the <hp:colPr colCount="N"> control is NOT a reliable multi-column detector
# on this corpus. mfds-44182_20 — the divergence audit's own example of a
# real 2-column Hancom render — has colCount="1" on every <hp:colPr> in every
# section. Its 다단 (multi-column) layout is evidently achieved by some other
# authoring mechanism (table-simulated columns are a plausible guess, not
# verified here), not the native HWP column-definition control. Treat
# `multiColumn: false` in this report as "no *native* column control found",
# not as "definitely single-column". `landscape` detection (pagePr/@landscape
# == "WIDELY") was verified directly against 4 of the audit's landscape
# exemplars and is considered reliable.
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^Contents/section\d+\.xml$")
_LANDSCAPE_RE = re.compile(rb'<hp:pagePr\b[^>]*\blandscape="([A-Z]+)"')
_COLPR_RE = re.compile(rb'<hp:colPr\b[^>]*\bcolCount="(\d+)"')


def layout_caveats(src: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(src) as z:
            names = [n for n in z.namelist() if _SECTION_RE.match(n)]
            landscape = False
            max_cols = 1
            for n in names:
                raw = z.read(n)
                if any(v == b"WIDELY" for v in _LANDSCAPE_RE.findall(raw)):
                    landscape = True
                for c in _COLPR_RE.findall(raw):
                    max_cols = max(max_cols, int(c))
            return {
                "landscape": landscape,
                "multiColumn": max_cols > 1,
                "colCountMax": max_cols,
                "sectionsScanned": len(names),
            }
    except Exception as exc:  # noqa: BLE001 - typed into the record
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Pair triage — the actual "ripple screen" this wrapper exists to run.
# ---------------------------------------------------------------------------


def triage_pair(
    pair_id: str,
    blank_path: Path,
    filled_path: Path,
    out_dir: Path,
    blank_cache: dict[str, DocVerdict],
) -> dict[str, Any]:
    bkey = str(blank_path)
    if bkey not in blank_cache:
        blank_cache[bkey] = export_pdf_verdict(Path(blank_path).stem, blank_path, out_dir)
    blank_v = blank_cache[bkey]
    filled_v = export_pdf_verdict(pair_id, filled_path, out_dir)
    caveats = layout_caveats(blank_path)

    rec: dict[str, Any] = {
        "pairId": pair_id,
        "blank": asdict(blank_v),
        "filled": asdict(filled_v),
        "layoutCaveats": caveats,
    }
    if blank_v.rhwpOk and filled_v.rhwpOk:
        rec["pageDelta"] = filled_v.pages - blank_v.pages
        rec["charDelta"] = filled_v.textChars - blank_v.textChars
        rec["rippleFlag"] = rec["pageDelta"] != 0
    else:
        # Fail-closed: undetermined is reported as None, never as False.
        rec["pageDelta"] = None
        rec["charDelta"] = None
        rec["rippleFlag"] = None
    return rec


# ---------------------------------------------------------------------------
# P0 baseline corpus resolution + ground truth (specs/035-formfill-round2/
# evidence/p0/baseline-4.0.0.md, cross-checked against differential-4.0.0.json)
# ---------------------------------------------------------------------------

S085 = Path("/Users/wilycastle/Code/projects/hwpx/python-hwpx-s085")
S094 = Path(__file__).resolve().parents[1]
FILLED_DIR = S085 / "work" / "m9-fitspike" / "fills"
DOWNLOADS_DIR = S085 / "work" / "public-document-corpus" / "downloads"
M2_FIXTURES = S094 / "tests" / "fixtures" / "m2_corpus"
DIFFERENTIAL_JSON = Path(
    "/Users/wilycastle/Code/projects/hwpx/specs/035-formfill-round2/"
    "evidence/p0/differential-4.0.0.json"
)

# The 5 ripple pairs (baseline-4.0.0.md §2 "② 리플 5건") with Hancom-verified
# blank->filled page counts. All 5 are a +1 page shift.
RIPPLE_GROUND_TRUTH: dict[str, dict[str, int]] = {
    "fiton-m2_gov_donation_report_form-short": {"blankPages": 30, "filledPages": 31},
    "fiton-corpus_moel-20250100168_22_4f8faba5c0-short": {"blankPages": 18, "filledPages": 19},
    "fiton-corpus_sen-20260114092512329_25_60b8f2fc82-overflow": {"blankPages": 8, "filledPages": 9},
    "fiton-corpus_mpm-notice-1669_17_10d8a016a7-short": {"blankPages": 2, "filledPages": 3},
    "fiton-corpus_moel-20250100168_23_66168394e2-overflow": {"blankPages": 1, "filledPages": 2},
}

# The 6 table-shape-only pairs (baseline-4.0.0.md §2 "③ 표-shape-only 6건") —
# Hancom page count is UNCHANGED for these; only the table shape vector
# differs. Not expected to produce a page-delta signal; observed, not scored.
SHAPE_ONLY_IDS: set[str] = {
    "fiton-corpus_nts-1340231_28_baf896bb72-short",
    "fiton-corpus_nts-1340231_28_baf896bb72-medium",
    "fiton-corpus_nts-1340231_29_76232e486a-medium",
    "fiton-corpus_sen-20260114092512329_24_a3b170ac87-short",
    "fiton-corpus_sen-20260114092512329_24_a3b170ac87-medium",
    "fiton-corpus_sen-20260114092512329_24_a3b170ac87-overflow",
}


def resolve_blank_path(blank_name: str) -> Path:
    if blank_name == "gov_donation_report_form.hwpx":
        return M2_FIXTURES / blank_name
    return DOWNLOADS_DIR / blank_name


def load_31_pairs() -> list[dict]:
    data = json.loads(DIFFERENTIAL_JSON.read_text())
    return [p for p in data["pairs"] if p["status"] != "skipped"]


def classify_ground_truth(pair_id: str) -> str:
    if pair_id in RIPPLE_GROUND_TRUTH:
        return "ripple"
    if pair_id in SHAPE_ONLY_IDS:
        return "shape_only"
    return "stable"


def run_validation(out_dir: Path) -> dict[str, Any]:
    verify_binary()
    pairs = load_31_pairs()
    if len(pairs) != 31:
        raise RhwpTriageError(
            "UNEXPECTED_CORPUS_SIZE", f"expected 31 verified pairs, got {len(pairs)}"
        )

    blank_cache: dict[str, DocVerdict] = {}
    records = []
    for p in pairs:
        pid = p["id"]
        blank_path = resolve_blank_path(p["blank"])
        filled_path = FILLED_DIR / f"{pid}.hwpx"
        rec = triage_pair(pid, blank_path, filled_path, out_dir, blank_cache)
        rec["groundTruth"] = classify_ground_truth(pid)
        records.append(rec)

    return score(records)


def score(records: list[dict]) -> dict[str, Any]:
    tp = fp = fn = tn = undetermined = 0
    shape_obs = []
    rows = []
    for r in records:
        gt = r["groundTruth"]
        actual_ripple = gt == "ripple"
        predicted = r["rippleFlag"]
        rows.append(
            {
                "pairId": r["pairId"],
                "groundTruth": gt,
                "rhwpBlankPages": r["blank"]["pages"],
                "rhwpFilledPages": r["filled"]["pages"],
                "pageDelta": r["pageDelta"],
                "predictedRipple": predicted,
                "blankOk": r["blank"]["rhwpOk"],
                "filledOk": r["filled"]["rhwpOk"],
            }
        )
        if predicted is None:
            undetermined += 1
            continue
        if actual_ripple and predicted:
            tp += 1
        elif actual_ripple and not predicted:
            fn += 1
        elif not actual_ripple and predicted:
            fp += 1
        else:
            tn += 1
        if gt == "shape_only":
            shape_obs.append({"pairId": r["pairId"], "pageDelta": r["pageDelta"], "predictedRipple": predicted})

    determined = tp + fp + fn + tn
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None

    return {
        "n": len(records),
        "determined": determined,
        "undetermined": undetermined,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": precision,
        "recall": recall,
        "shapeOnlyObservations": shape_obs,
        "rows": rows,
        "records": records,
    }


# ---------------------------------------------------------------------------
# Fail-closed demonstration cases
# ---------------------------------------------------------------------------


def demo_failclosed(out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}

    # 1. Wrong pinned hash -> must raise, not silently proceed.
    try:
        verify_binary(expected_sha256="0" * 64)
        results["sha256_mismatch_case"] = {"raised": False, "BUG": "did not raise"}
    except RhwpTriageError as exc:
        results["sha256_mismatch_case"] = {"raised": True, "code": exc.code, "message": str(exc)}

    # 2. Nonexistent source file -> typed error, no subprocess call needed.
    missing = out_dir / "does-not-exist-6f3a91.hwpx"
    v = export_pdf_verdict("demo-missing-file", missing, out_dir)
    results["missing_file_case"] = asdict(v)

    # 3. Corrupt zip (bit-flipped copy of a small real corpus file, built here
    #    in scratch space only — no corpus original is ever touched).
    seed = next(iter(load_31_pairs()))
    seed_blank = resolve_blank_path(seed["blank"])
    raw = bytearray(seed_blank.read_bytes())
    for i in range(64, min(len(raw), 4096)):
        raw[i] ^= 0xFF
    corrupt_path = out_dir / "demo-corrupt.hwpx"
    corrupt_path.write_bytes(bytes(raw))
    v2 = export_pdf_verdict("demo-corrupt-zip", corrupt_path, out_dir)
    results["corrupt_zip_case"] = asdict(v2)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-binary", help="verify the exact-pin sha256 and print it")

    p_probe = sub.add_parser("probe", help="triage arbitrary hwpx file(s)")
    p_probe.add_argument("files", nargs="+", type=Path)
    p_probe.add_argument("--out", type=Path, default=S094 / "work" / "rhwp-triage" / "probe")

    p_val = sub.add_parser("validate-p0", help="run the 31-pair P0 baseline ripple validation")
    p_val.add_argument("--out", type=Path, default=S094 / "work" / "rhwp-triage" / "validate-p0")

    p_demo = sub.add_parser("demo-failclosed", help="run the fail-closed demonstration cases")
    p_demo.add_argument("--out", type=Path, default=S094 / "work" / "rhwp-triage" / "demo")

    args = parser.parse_args(argv)

    if args.cmd == "check-binary":
        digest = verify_binary()
        _print_json({"ok": True, "sha256": digest, "version": RHWP_VERSION, "binary": str(RHWP_BIN)})
        return 0

    if args.cmd == "probe":
        args.out.mkdir(parents=True, exist_ok=True)
        for f in args.files:
            v = export_pdf_verdict(f.stem, f, args.out)
            caveats = layout_caveats(f)
            _print_json({"verdict": asdict(v), "layoutCaveats": caveats})
        return 0

    if args.cmd == "validate-p0":
        result = run_validation(args.out)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "validation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str)
        )
        summary = {k: v for k, v in result.items() if k not in ("records", "rows")}
        _print_json(summary)
        return 0

    if args.cmd == "demo-failclosed":
        result = demo_failclosed(args.out)
        _print_json(result)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
