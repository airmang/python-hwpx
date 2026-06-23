"""Cross-platform driver: produce lineseg ON/OFF .hwpx pairs for measurement.

Runs anywhere python-hwpx imports (including macOS); does NOT need Hancom.
For each input document and each mutation kind it writes::

    <outdir>/<stem>__<kind>__ON.hwpx     # engine default: layout cache stripped
    <outdir>/<stem>__<kind>__OFF.hwpx    # control: layout cache retained

plus a manifest.json describing every pair and a SELF-CHECK (``control_valid``)
confirming that OFF actually retains more lineSegArray than ON. If
``control_valid`` is false, the negative control is broken (e.g. a strip path was
not neutralized, or Hancom-independent stripping happened anyway) and the
downstream render comparison would be meaningless.

Usage::

    uv run python work/visualcomplete-baseline/run_pairs.py \
        --out /tmp/vc-pairs doc1.hwpx doc2.hwpx
    uv run python work/visualcomplete-baseline/run_pairs.py \
        --out /tmp/vc-pairs --mutations short_to_long doc.hwpx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

# Make sibling modules importable regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hwpx.document import HwpxDocument  # noqa: E402
from lineseg_toggle import lineseg_invalidation  # noqa: E402
from mutate import MUTATIONS  # noqa: E402

# Count only opening <...lineSegArray ...> elements (exclude </...> closers).
_LINESEG_RE = re.compile(rb"<[^>/][^>]*[lL]ineSegArray\b")


def _count_linesegarray(hwpx_path: Path) -> int:
    total = 0
    with zipfile.ZipFile(hwpx_path) as archive:
        for name in archive.namelist():
            lower = name.lower()
            if "section" in lower and lower.endswith(".xml"):
                total += len(_LINESEG_RE.findall(archive.read(name)))
    return total


def _produce(src: Path, kind: str, enabled: bool, out_path: Path) -> dict:
    with lineseg_invalidation(enabled=enabled) as state:
        doc = HwpxDocument.open(str(src))
        result = MUTATIONS[kind](doc)
        doc.save(str(out_path))
    return {"mode": state["mode"], "patched": state["patched"],
            "mutation": result.__dict__}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="input .hwpx files")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--mutations", default=",".join(MUTATIONS),
                        help=f"comma-separated subset of {list(MUTATIONS)}")
    args = parser.parse_args(argv)
    mutation_kinds = [m.strip() for m in args.mutations.split(",") if m.strip()]

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    pairs = []
    for raw in args.inputs:
        src = Path(raw)
        stem = src.stem
        for kind in mutation_kinds:
            if kind not in MUTATIONS:
                print(f"skip unknown mutation: {kind}", file=sys.stderr)
                continue
            on_path = outdir / f"{stem}__{kind}__ON.hwpx"
            off_path = outdir / f"{stem}__{kind}__OFF.hwpx"
            try:
                on_meta = _produce(src, kind, True, on_path)
                off_meta = _produce(src, kind, False, off_path)
            except Exception as exc:  # noqa: BLE001 - report, keep going
                pairs.append({"source": str(src), "mutation": kind,
                              "error": repr(exc)})
                print(f"  ERROR {src.name} [{kind}]: {exc!r}", file=sys.stderr)
                continue
            on_ls = _count_linesegarray(on_path)
            off_ls = _count_linesegarray(off_path)
            pairs.append({
                "source": str(src),
                "mutation": kind,
                "on": {"path": str(on_path), "linesegarray_count": on_ls, **on_meta},
                "off": {"path": str(off_path), "linesegarray_count": off_ls, **off_meta},
                # OFF must retain strictly MORE lineSegArray than ON for the
                # control to be meaningful.
                "control_valid": off_ls > on_ls,
            })

    manifest = {"pairs": pairs}
    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    ok_pairs = [p for p in pairs if "error" not in p]
    valid = sum(1 for p in ok_pairs if p.get("control_valid"))
    print(f"wrote {len(ok_pairs)} pair(s) to {outdir}")
    print(f"control_valid (OFF retains more lineseg than ON): {valid}/{len(ok_pairs)}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
