#!/usr/bin/env python3
"""DEV-003 — AbstractDrawingObjectType child order: schema vs real output.

Schema claim: ``DevDoc/OWPML SCHEMA/ParaList XML schema.xml``'s
``AbstractDrawingObjectType`` declares its own sequence as
``lineShape, fillBrush, drawText, shadow`` (in that order).

Real-document measurement: Hancom's own output puts ``shadow`` *before*
``drawText`` — the exact opposite of the two elements' declared order.

Our handling: ``hwpx.oxml.objects._write_draw_text`` never assumes a fixed
predecessor. It anchors on the *next* thing instead — inserting the new
``hp:drawText`` immediately before the shape's first type-specific geometry
child (``pt0``/``pt``/``startPt``/``center``/``seg``, falling back to
``sz``) via ``_reposition_child_before_any`` — which is correct regardless
of whether ``lineShape``/``fillBrush``/``shadow`` are present, and matches
the real order without hard-coding "after shadow".

Run: ``python probes/dev003_drawtext_child_order.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

EVIDENCE = ROOT / "tests/fixtures/hwpxlib_corpus/reader_writer__SimpleRectangle.hwpx"
NS = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}


def _local_names(element) -> list[str]:
    return [etree.QName(child.tag).localname for child in element]


def main() -> int:
    if not EVIDENCE.exists():
        print(f"SKIP: evidence file not present locally: {EVIDENCE}")
        return 0

    data = zipfile.ZipFile(EVIDENCE).read("Contents/section0.xml")
    root = etree.fromstring(data)
    rect = root.find(".//hp:rect", NS)
    assert rect is not None, "expected a hp:rect in the evidence file"
    children = _local_names(rect)
    print(f"real document hp:rect children: {children}")
    assert "shadow" in children and "drawText" in children
    assert children.index("shadow") < children.index("drawText"), (
        "expected shadow before drawText (opposite of the schema's declared sequence)"
    )

    from hwpx.document import HwpxDocument
    from hwpx.oxml.namespaces import tag_local_name

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    new_rect = p.add_rectangle(10000, 8000, treat_as_char=True)
    new_rect.set_draw_text("프로브 텍스트")
    doc.close()
    our_children = [tag_local_name(c.tag) for c in new_rect.element]
    print(f"our authored hp:rect children: {our_children}")
    assert our_children.index("shadow") < our_children.index("drawText")
    assert our_children.index("drawText") < our_children.index("pt0")
    print("PASS: DEV-003 reproduced (real evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
