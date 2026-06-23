"""Synthesize a smoke-test fixture by injecting a <hp:lineSegArray> cache.

The repo ships no .hwpx that contains a layout cache (all are python-hwpx
outputs, already stripped), so the negative control has nothing to retain. This
helper injects a lineSegArray into the first paragraph of the first section at
the raw ZIP level, producing a document the harness can use to PROVE the ON/OFF
toggle works (ON strips it, OFF retains it).

This is a harness self-test only. It does NOT reproduce 글자 겹침 — that requires
genuine Hangul-saved documents and the Hancom render oracle.

Usage:
    uv run python scripts/visualcomplete-baseline/make_injected_fixture.py \
        <source.hwpx> <out.hwpx>
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

_SEG = (
    b"<hp:lineSegArray>"
    b'<hp:lineSeg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
    b'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/>'
    b"</hp:lineSegArray>"
)


def inject(src: Path, out: Path) -> int:
    with zipfile.ZipFile(src) as archive:
        names = archive.namelist()
        items = {name: archive.read(name) for name in names}

    sections = [n for n in names
                if "section" in n.lower() and n.lower().endswith(".xml")]
    if not sections:
        raise SystemExit(f"no section*.xml part found in {src}")
    target = sections[0]

    new_payload, count = re.subn(rb"</hp:p>", _SEG + b"</hp:p>", items[target], count=1)
    if count == 0:
        raise SystemExit(f"no <hp:p> paragraph found in {target}")
    items[target] = new_payload

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        # mimetype must be first and stored uncompressed in an OPC package.
        if "mimetype" in items:
            info = zipfile.ZipInfo("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            zout.writestr(info, items["mimetype"])
        for name in names:
            if name == "mimetype":
                continue
            zout.writestr(name, items[name])
    return len(re.findall(rb"<[^>/][^>]*linesegarray\b", new_payload, re.IGNORECASE))


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print(__doc__)
        return 2
    src, out = Path(args[0]), Path(args[1])
    injected = inject(src, out)
    print(f"injected {injected} lineSegArray element(s) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
