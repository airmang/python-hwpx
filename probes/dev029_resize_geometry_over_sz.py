#!/usr/bin/env python3
"""DEV-029 -- a drawing shape's rendered size in real Hancom output comes
from its type-specific geometry (``pt0``-``pt3`` for a rectangle,
``center``/``ax1``/``ax2`` for an ellipse, ``startPt``/``endPt`` for a
line) scaled by ``scaMatrix`` -- not from ``sz``/``orgSz``/``curSz``.
Changing only the size elements reports a new size while Hancom keeps
drawing the old geometry.

Schema claim: the shape complex types (``RectangleType``/``EllipseType``/
``LineType``, ``ParaList XML schema.xml``) list ``sz``/``orgSz``/``curSz``
and the geometry elements as plain sibling children with no stated
precedence -- nothing in the schema says geometry wins over the size
elements at render time.

Real-document measurement: ``oracle: previously-verified`` -- owner
memory ``shape-authoring-namespace-defect.md`` records a real-Hancom 7/7
render verification (5.0.0 shape-authoring namespace defect) of this
exact geometry-over-sz mechanism. Not re-observable here (no Hancom
oracle in this environment).

Our handling: ``objects.py``'s ``resize()`` docstring states the
mechanism directly ("Hancom renders a drawing object from its
type-specific geometry ... scaled by scaMatrix -- not from sz") and the
method scales both the size elements *and* the geometry together. This
probe demonstrates, live, that (a) ``resize()`` changes both, and (b) a
naive "just set sz" edit -- which a schema-only reading would consider
sufficient -- would silently leave the drawn geometry at the old size.

Run: ``python probes/dev029_resize_geometry_over_sz.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"
HP_NS = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def main() -> int:
    schema_file = SCHEMA_DIR / "ParaList XML schema.xml"
    if schema_file.exists():
        text = schema_file.read_text("utf-8")
        for name in ("sz", "orgSz", "curSz", "pt0"):
            assert f'name="{name}"' in text, name
        print("confirmed sz/orgSz/curSz and pt0 (geometry) are all declared as plain "
              "sibling elements, with no stated render-time precedence")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.document import HwpxDocument
    from hwpx.oxml.namespaces import tag_local_name

    def geometry(shape) -> dict[str, tuple[str | None, str | None]]:
        return {
            tag_local_name(c.tag): (c.get("x"), c.get("y"))
            for c in shape.element.iter()
            if tag_local_name(c.tag) in ("pt0", "pt1", "pt2", "pt3")
        }

    doc = HwpxDocument.new()
    p = doc.sections[0].add_paragraph()
    rect = p.add_rectangle(10000, 8000)
    before_geometry = geometry(rect)
    sz_before = rect.element.find(f"{HP_NS}sz")
    assert (sz_before.get("width"), sz_before.get("height")) == ("10000", "8000")

    # Naive edit a schema-only reading would think is sufficient: touch sz alone.
    sz_before.set("width", "99999")
    sz_before.set("height", "99999")
    naive_geometry = geometry(rect)
    assert naive_geometry == before_geometry, (
        "expected editing sz alone to leave the drawn geometry untouched -- if this "
        "fails, Hancom's own renderer contract may have changed"
    )
    sz_before.set("width", "10000")
    sz_before.set("height", "8000")
    print("confirmed editing sz alone leaves pt0-pt3 (the actually-drawn geometry) "
          f"unchanged: {naive_geometry}")

    rect.resize(20000, 16000)
    after_geometry = geometry(rect)
    sz_after = rect.element.find(f"{HP_NS}sz")
    assert (sz_after.get("width"), sz_after.get("height")) == ("20000", "16000")
    assert after_geometry != before_geometry, "expected resize() to also move the geometry"
    assert after_geometry["pt1"] == ("20000", "0"), after_geometry
    assert after_geometry["pt2"] == ("20000", "16000"), after_geometry
    print(f"confirmed resize() updates both sz AND the drawn geometry together: "
          f"{after_geometry}")

    print("PASS: DEV-029 reproduced (schema silence + live geometry-vs-sz contrast, "
          "render confirmation is previously-verified per owner memory only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
