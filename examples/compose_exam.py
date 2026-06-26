"""Compose an authored exam (Markdown) into a school form .hwpx.

    python examples/compose_exam.py FORM.hwpx EXAM.md OUT.hwpx

Without a Hancom oracle the result is composed (keepWithNext) but reported
render_checked=false / needs_review=true (no silent true). On macOS with
Hancom + HWPX_MAC_ORACLE_SMOKE=1 the convergence loop verifies splits=0."""
from __future__ import annotations

import sys
from pathlib import Path

from hwpx.exam import compose_exam_into_form


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    form, md_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    result = compose_exam_into_form(form, Path(md_path).read_text(encoding="utf-8"), out)
    print(f"out={result.out_path} render_checked={result.render_checked} "
          f"splits={result.splits} overflow={result.overflow} "
          f"placeholders_ok={result.placeholders_ok} needs_review={result.needs_review}")
    for note in result.notes:
        print(f"  - {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
