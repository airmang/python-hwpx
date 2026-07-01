# SPDX-License-Identifier: Apache-2.0
"""Stage the negative-control set for the M9 open-rate harness (specs/007, P0/FR-005).

The published headline is PARSED = opened AND real content loaded (textLength>0)
— box finding 2026-07-01: Hancom's COM Open() returns true even for blank/garbage
(opened-blank), so 'opened' alone is not the number. A negative "leaks" only if it
reaches the PARSED tier (yields real content from a file that is not a valid doc).

Two tiers, and the threat model matters (box run 2026-07-01 taught us this):

* tier ``must_refuse`` — CORRUPT-HWPX: a valid .hwpx OPC container whose INTERNAL
  content is corrupt/missing. This is the threat model ADJACENT to our real files
  (all valid HWPX): could Hancom fabricate/repair content from a broken HWPX and
  wrongly inflate parsed_rate? A leak (parsed) HARD-invalidates the run.
    - ``corrupt_section``  : Contents/section0.xml body is non-OWPML garbage.
    - ``corrupt_header``   : Contents/header.xml (shape/font defs) is garbage.
    - ``missing_section``  : Contents/section0.xml removed entirely (no body).
    - ``empty_file``       : 0 bytes; nothing to parse.
  On the .161 build, corrupt_section + the IRB pair REFUSED (opened=false) — the
  auto-repair threat is refuted; these variants broaden that check.

* tier ``expected_refuse`` — DOCUMENTED Hancom general-opener leniency. Not
  corrupt-HWPX; a leak here is recorded (SOFT) but does NOT invalidate. The box run
  showed Hancom is a lenient general opener, which is orthogonal to HWPX acceptance:
    - ``leniency_not_zip``        : not an archive → Hancom opens it AS PLAIN TEXT.
    - ``leniency_truncated_zip``  : first 60% of a real .hwpx → Hancom RECOVERS
                                    partial text (tolerant reader).
    - ``leniency_missing_mimetype``: valid zip, only the OPC mimetype hint removed →
                                    Hancom reads the real content anyway.
    - IRB pair                    : real Hancom-authored gov forms, non-standard OPF,
                                    OBSERVED (and confirmed on-box) to refuse.

NOTE — the two stale-lineseg gov docs (aikorea-64, mpm-law-1285) were removed as
negatives (structurally-intact real docs Hancom opens cleanly).

Writes work/openrate-corpus/_negatives/ + negatives.json (schema v3, sha256-frozen).
Deterministic: synthetic files are byte-manipulations of a frozen authored output.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # python-hwpx/
OUT = ROOT / "work" / "openrate-corpus" / "_negatives"
RR = ROOT / "tests" / "fixtures" / "reader_robustness"

_GARBAGE = b"\x00\x01CORRUPT-NOT-OWPML\xff\xfe</not-xml" + b"A" * 2048

# Files from earlier builds that this schema no longer emits — removed on run so a
# stale invalid control can't linger.
_OBSOLETE = (
    "aikorea-64_09_6364efbc0f.hwpx", "mpm-law-1285_10_6656eeb313.hwpx",
    "synthetic_not_zip.hwpx", "synthetic_empty_file.hwpx", "synthetic_truncated_zip.hwpx",
    "synthetic_corrupt_section.hwpx", "synthetic_missing_mimetype.hwpx",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rezip(source: Path, dest: Path, overrides: dict[str, bytes | None]) -> None:
    """Copy source .hwpx to dest, replacing (bytes) or dropping (None) named parts.

    Keeps the package structurally valid (mimetype first + stored) so Hancom reaches
    the internal-parse decision rather than rejecting at the zip layer.
    """
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename in overrides and overrides[info.filename] is None:
                continue  # drop this part
            data = overrides.get(info.filename)
            if data is None:
                data = zin.read(info.filename)
            if info.filename == "mimetype":
                zout.writestr(info, data, compress_type=zipfile.ZIP_STORED)
            else:
                zout.writestr(info.filename, data)


def _synthesize(source: Path) -> list[dict[str, object]]:
    made: list[dict[str, object]] = []
    raw = source.read_bytes()

    # ---- must_refuse: CORRUPT-HWPX (the threat model adjacent to our real files) --
    corrupt = [
        ("corrupt_section.hwpx", "corrupt_hwpx:section", {"Contents/section0.xml": _GARBAGE},
         "valid OPC package, Contents/section0.xml body is non-OWPML garbage"),
        ("corrupt_header.hwpx", "corrupt_hwpx:header", {"Contents/header.xml": _GARBAGE},
         "valid OPC package, Contents/header.xml (shape/font defs) is non-OWPML garbage"),
        ("missing_section.hwpx", "corrupt_hwpx:missing_section", {"Contents/section0.xml": None},
         "valid OPC package with the body section removed entirely"),
    ]
    for name, kind, overrides, why in corrupt:
        dst = OUT / name
        _rezip(source, dst, overrides)
        made.append({"name": name, "kind": kind, "tier": "must_refuse", "rationale": why})

    empty = OUT / "empty_file.hwpx"
    empty.write_bytes(b"")
    made.append({"name": empty.name, "kind": "corrupt_hwpx:empty", "tier": "must_refuse",
                 "rationale": "0 bytes; nothing to parse"})

    # ---- expected_refuse: documented Hancom general-opener leniency ---------------
    notzip = OUT / "leniency_not_zip.hwpx"
    notzip.write_bytes(b"NOT A HWPX / NOT A ZIP \x00\x01\x02 corrupt sentinel\n")
    made.append({"name": notzip.name, "kind": "leniency:not_zip", "tier": "expected_refuse",
                 "rationale": "not an archive; Hancom's auto-detect opens it as a plain text file"})

    trunc = OUT / "leniency_truncated_zip.hwpx"
    trunc.write_bytes(raw[: max(1, int(len(raw) * 0.6))])
    made.append({"name": trunc.name, "kind": "leniency:truncated_zip", "tier": "expected_refuse",
                 "rationale": "first 60% of a real .hwpx; Hancom's tolerant reader recovers partial text"})

    nomime = OUT / "leniency_missing_mimetype.hwpx"
    _rezip(source, nomime, {"mimetype": None})
    made.append({"name": nomime.name, "kind": "leniency:missing_mimetype", "tier": "expected_refuse",
                 "rationale": "valid zip, only the OPC mimetype hint removed; Hancom reads the content anyway"})
    return made


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in _OBSOLETE:
        p = OUT / name
        if p.exists():
            p.unlink()

    seed_candidates = sorted((ROOT / "work" / "openrate-corpus" / "authored").glob("*.hwpx"))
    if not seed_candidates:
        seed_candidates = sorted((ROOT / "tests" / "fixtures" / "m2_corpus").glob("*.hwpx"))
    if not seed_candidates:
        raise SystemExit("no seed .hwpx found to synthesize negatives from")
    seed = seed_candidates[0]

    records: list[dict[str, object]] = []
    for meta in _synthesize(seed):
        dst = OUT / str(meta["name"])
        records.append({
            "path": str(dst), "name": meta["name"], "kind": meta["kind"], "tier": meta["tier"],
            "sha256": _sha256(dst), "source": str(seed), "expected": "not parsed",
            "rationale": meta["rationale"],
        })

    for name in ("irb_form_blank.hwpx", "irb_form_filled.hwpx"):
        src = RR / name
        if not src.exists():
            continue
        dst = OUT / name
        shutil.copy2(src, dst)
        records.append({
            "path": str(dst), "name": name, "kind": "documented_hancom_reject",
            "tier": "expected_refuse", "sha256": _sha256(dst), "source": str(src),
            "expected": "not parsed",
            "rationale": "real Hancom-authored gov form, non-standard OPF; confirmed to refuse on-box",
        })

    hard = sum(1 for r in records if r["tier"] == "must_refuse")
    soft = sum(1 for r in records if r["tier"] == "expected_refuse")
    manifest = {
        "schemaVersion": "hwpx.openrate.negatives.v3",
        "generatedAt": None,
        "note": "Leak = a negative reaching the PARSED tier (opened AND real content). must_refuse "
                "(corrupt-HWPX) leak -> harness_valid=false; expected_refuse (documented Hancom "
                "general-opener leniency) leak -> soft warning only. Open negatives FIRST on the box.",
        "count": len(records),
        "counts_by_tier": {"must_refuse": hard, "expected_refuse": soft},
        "negatives": records,
    }
    (OUT / "negatives.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"staged {len(records)} negative controls ({hard} must_refuse / {soft} expected_refuse) -> {OUT}")
    for r in records:
        print(f"  [{r['tier']:15}] {r['kind']:30} {r['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
