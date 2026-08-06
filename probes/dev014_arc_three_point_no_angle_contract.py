#!/usr/bin/env python3
"""DEV-014 — ``hp:arc`` declares only three points and no angle/sweep field
at all; the one real example shows those three points are the *entire*
geometry (a quarter-ellipse), which is why train 14 (cycle 6.4) could author
exactly that one verified quadrant and nothing beyond it with confidence.

Schema claim: ``ArcType`` (``ParaList XML schema.xml``) extends
``AbstractDrawingObjectType`` with a sequence of exactly three points
(``center``/``ax1``/``ax2``, all ``hc:PointType``) and a ``type`` attribute
(``NORMAL``/``PIE``/``CHORD``, default ``NORMAL``) — nothing else. There is
no start-angle, end-angle, or sweep field anywhere in ``ArcType``, unlike
what "arc" usually implies (a partial ellipse boundary needs *some* way to
say where it starts and stops). Compare ``EllipseType`` (this same package's
existing ``add_ellipse``), which the same schema gives *seven* points
(``center``/``ax1``/``ax2``/``start1``/``end1``/``start2``/``end2``) — the
extra four exist specifically to carry a cut/sweep when ``hasArcPr="1"``.
``ArcType`` has no such extras.

Real-document measurement: ``reader_writer__SimpleArc.hwpx`` (vendored) is
the one arc example in this corpus (schema-declared as PARSE-only before
this cycle — census: 1 file). Its three points are ``center=(0,0)``,
``ax1=(0,11225)`` (straight down from center), ``ax2=(12450,0)`` (straight
right from center) with ``type="PIE"``. The arc's own bounding box
(``orgSz``) is exactly ``12450x11225`` — precisely the box a quarter-ellipse
swept between those two axis endpoints would occupy. With only three points
and no angle data anywhere in the element, this is not a coincidence: the
three points *are* the sweep. A more general ``hp:arc`` (arbitrary, non-90-
degree start/end angles) is not ruled out by the schema's grammar, but this
package has exactly one real sample and it is a quarter-ellipse — there is
no second example to check whether ``ax1``/``ax2`` can validly sit anywhere
else on the ellipse boundary.

Our handling: ``hwpx.oxml.objects._create_arc_element`` authors precisely
the verified pattern (``center`` at one corner of the requested bounding
box, ``ax1`` straight down, ``ax2`` straight right) for
``corner="TOP_LEFT"``, and reaches the other three corners by mirroring that
same point pattern with ``hp:flip`` — the identical mechanism
line/rect/ellipse/polygon already use here — rather than inventing new,
unverified point math for other sweep angles. ``type`` is passed through as
the schema's own enum.

Run: ``python probes/dev014_arc_three_point_no_angle_contract.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    fixture = CORPUS / "reader_writer__SimpleArc.hwpx"
    if not fixture.exists():
        print("SKIP: reader_writer__SimpleArc.hwpx not found in vendored corpus")
        return 0

    with zipfile.ZipFile(fixture) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = etree.fromstring(archive.read(name))
    (arc,) = root.iter(f"{{{HP_NS}}}arc")

    geometry_children = [
        c for c in arc if c.tag.split("}")[-1] in ("center", "ax1", "ax2")
    ]
    assert len(geometry_children) == 3, f"expected exactly 3 geometry points, got {len(geometry_children)}"
    assert all(c.tag == f"{{{HC_NS}}}{c.tag.split('}')[-1]}" for c in geometry_children)
    print(f"hp:arc geometry: exactly 3 points ({[c.tag.split('}')[-1] for c in geometry_children]}), all hc: namespace")

    points = {c.tag.split("}")[-1]: (int(c.get("x", "0")), int(c.get("y", "0"))) for c in geometry_children}
    center, ax1, ax2 = points["center"], points["ax1"], points["ax2"]
    assert center == (0, 0)
    assert ax1[0] == center[0] and ax1[1] > center[1], "expected ax1 straight below center"
    assert ax2[1] == center[1] and ax2[0] > center[0], "expected ax2 straight right of center"
    print(f"center={center} ax1={ax1} (straight down) ax2={ax2} (straight right) -- quarter-ellipse pairing")

    org_sz = arc.find(f"{{{HP_NS}}}orgSz")
    assert org_sz is not None
    width, height = ax2[0] - center[0], ax1[1] - center[1]
    assert (int(org_sz.get("width", "0")), int(org_sz.get("height", "0"))) == (width, height)
    print(f"orgSz={dict(org_sz.attrib)} matches the quarter-ellipse's own bounding box exactly ({width}x{height})")

    assert arc.get("type") == "PIE"
    print("type=PIE (schema enum, no angle field present anywhere on the element)")

    schema_files = sorted(SCHEMA_DIR.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        arc_start = schema_text.find('name="ArcType"')
        assert arc_start != -1
        arc_block = schema_text[arc_start:arc_start + 800]
        for angle_word in ("startAngle", "endAngle", "sweep", "angle1", "angle2"):
            assert angle_word not in arc_block, f"unexpected angle field {angle_word!r} found in ArcType"
        assert arc_block.count('type="hc:PointType"') == 3
        print("confirmed against the real OWPML schema: ArcType has exactly 3 hc:PointType children and no angle field")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.oxml.objects import _ARC_CORNER_FLIPS, _create_arc_element

    generated = _create_arc_element(width, height, corner="TOP_LEFT", arc_type="PIE")
    gen_points = {
        c.tag.split("}")[-1]: (int(c.get("x", "0")), int(c.get("y", "0")))
        for c in generated if c.tag.split("}")[-1] in ("center", "ax1", "ax2")
    }
    assert gen_points == points, f"generated geometry {gen_points} != real geometry {points}"
    assert set(_ARC_CORNER_FLIPS) == {"TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT"}
    assert _ARC_CORNER_FLIPS["TOP_LEFT"] == (False, False), "the corpus-verified corner must be the unflipped one"
    print("our add_arc reproduces the real geometry exactly for the verified corner; the other 3 corners are hp:flip-mirrored, not independently derived")

    print("PASS: DEV-014 reproduced (vendored evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
