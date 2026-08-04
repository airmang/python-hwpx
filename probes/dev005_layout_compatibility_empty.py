#!/usr/bin/env python3
"""DEV-005 — hh:layoutCompatibility: schema declares 48 flags, real corpus
never sets any of them.

Schema claim: ``DevDoc/OWPML SCHEMA/Header XML schema.xml``'s
``CompatibleDocumentType`` declares ``hh:layoutCompatibility`` as a
sequence of 48 optional marker children (``applyFontWeightToBold``,
``useInnerUnderline``, … each ``minOccurs="0"``, presence-only — no
attribute value).

Real-document measurement: every reachable corpus file emits
``<hh:layoutCompatibility/>`` completely empty — 0 flags set, 100% of the
time. This was one of the completeness audit's two "genuinely code-blind"
findings (§4-R1): the element existed in 166/166 real files but no code
anywhere referenced its name.

Our handling: ``hwpx.oxml.header.LayoutCompatibility`` stores whatever
child names *are* present as a ``flags: frozenset[str]`` rather than
hard-coding the 48-name enum — a document with any combination of flags
(even ones absent from our corpus sample) round-trips losslessly.

Run: ``python probes/dev005_layout_compatibility_empty.py``
"""

from __future__ import annotations

import sys
import zipfile
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

NS = {"hh": "http://www.hancom.co.kr/hwpml/2011/head"}


def main() -> int:
    fixtures = sorted(glob.glob(str(ROOT / "tests/fixtures/hwpxlib_corpus/*.hwpx")))
    if not fixtures:
        print("SKIP: no vendored corpus files found")
        return 0

    scanned = 0
    flagged = 0
    for path in fixtures:
        try:
            data = zipfile.ZipFile(path).read("Contents/header.xml")
        except KeyError:
            continue
        root = etree.fromstring(data)
        layout = root.find(".//hh:layoutCompatibility", NS)
        if layout is None:
            continue
        scanned += 1
        if len(layout) > 0:
            flagged += 1
    print(f"scanned {scanned} vendored files with hh:layoutCompatibility, {flagged} had any flag set")
    assert scanned > 0
    assert flagged == 0, "expected 0 real files with a set layoutCompatibility flag"

    from hwpx.oxml.header import parse_compatible_document
    import xml.etree.ElementTree as ET

    HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
    node = ET.Element(f"{HH}compatibleDocument", {"targetProgram": "HWP201X"})
    layout = ET.SubElement(node, f"{HH}layoutCompatibility")
    ET.SubElement(layout, f"{HH}applyFontWeightToBold")
    ET.SubElement(layout, f"{HH}unknownFutureFlag123")
    compatible = parse_compatible_document(node)
    assert compatible.layout_compatibility.flags == {"applyFontWeightToBold", "unknownFutureFlag123"}
    print(f"our model preserves unknown-to-schema flags too: {compatible.layout_compatibility.flags}")
    print("PASS: DEV-005 reproduced (real evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
