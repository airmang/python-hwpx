#!/usr/bin/env python3
"""DEV-012 — ``startPt``/``endPt`` live in different namespaces on different
shapes, and the schema itself says so (this is not a schema-vs-reality gap
like DEV-004/007 — it is easy to miss because both fields visually mean the
same thing on both shapes).

Schema claim: ``ParaList XML schema.xml`` declares two different types for
what looks like the same pair of fields. ``LineType`` (``hp:line``, line
2376-2377) types ``startPt``/``endPt`` as ``hc:PointType`` — the plain core
coordinate pair every other geometry element (``hc:pt``, ``hc:center``,
``hc:ax1``...) also uses. ``ConnectLineType`` (``hp:connectLine``, line
2492-2493) types the *same-named* fields as ``hp:ConnectPointType`` — a
paragraph-namespace extension of ``hc:PointType`` that adds
``subjectIDRef``/``subjectIdx`` (which shape the endpoint is anchored to;
see DEV-013). The schema is internally consistent about this; a reader
skimming only the local names would not notice the type — and therefore
namespace — differs.

Real-document measurement: ``reader_writer__SimpleLine.hwpx`` (vendored)
writes ``hc:startPt``/``hc:endPt`` on its ``hp:line``, matching LineType
exactly. ``reader_writer__SimpleConnectLine.hwpx`` and
``error__20230818__test.hwpx`` (both vendored) write ``hp:startPt``/
``hp:endPt`` on their ``hp:connectLine`` elements, matching ConnectLineType
exactly — real Hancom output follows the schema's own type split here, it
just is not visually obvious without reading both declarations side by
side.

Our handling: ``hwpx.oxml.objects._create_line_element`` hard-codes the core
namespace (``_HC}startPt``/``_HC}endPt``) because that is the only shape
this package authors with that field pair — no code path exists that could
get this wrong for ``hp:line``. The generic *read*-side geometry scan
(``_SHAPE_POINT_LOCAL_NAMES`` in the same module, consumed by
``HwpxOxmlShape.resize()``) matches by **local name only** — "startPt"/
"endPt" regardless of namespace — so it already tolerates either shape's
real form without needing a namespace branch; this was true before this
cycle's connectLine investigation and stays true now that the investigation
is complete.

Run: ``python probes/dev012_startpt_endpt_namespace_duality.py``
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


def _first_child_namespace(root: etree._Element, parent_tag: str, child_local: str) -> str | None:
    for parent in root.iter(f"{{{HP_NS}}}{parent_tag}"):
        for child in parent:
            if etree.QName(child).localname == child_local:
                return etree.QName(child).namespace
    return None


def main() -> int:
    line_fixture = CORPUS / "reader_writer__SimpleLine.hwpx"
    connectline_fixtures = (
        CORPUS / "reader_writer__SimpleConnectLine.hwpx",
        CORPUS / "error__20230818__test.hwpx",
    )
    if not line_fixture.exists() or not any(f.exists() for f in connectline_fixtures):
        print("SKIP: vendored corpus fixtures not found")
        return 0

    with zipfile.ZipFile(line_fixture) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = etree.fromstring(archive.read(name))
    line_ns = _first_child_namespace(root, "line", "startPt")
    assert line_ns == HC_NS, f"expected hp:line startPt in hc: namespace, got {line_ns}"
    print(f"hp:line startPt namespace: {line_ns} (core, matches LineType)")

    for fixture in connectline_fixtures:
        if not fixture.exists():
            continue
        with zipfile.ZipFile(fixture) as archive:
            name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
            root = etree.fromstring(archive.read(name))
        connectline_ns = _first_child_namespace(root, "connectLine", "startPt")
        if connectline_ns is None:
            continue
        assert connectline_ns == HP_NS, (
            f"expected hp:connectLine startPt in hp: namespace, got {connectline_ns} ({fixture.name})"
        )
        print(f"hp:connectLine startPt namespace ({fixture.name}): {connectline_ns} (paragraph, matches ConnectLineType)")

    schema_files = sorted(SCHEMA_DIR.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        assert '<xs:element name="startPt" type="hc:PointType"/>' in schema_text
        assert '<xs:element name="startPt" type="hp:ConnectPointType"/>' in schema_text
        print("confirmed against the real OWPML schema: LineType and ConnectLineType declare different types for startPt")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.oxml.objects import _create_line_element, _SHAPE_POINT_LOCAL_NAMES

    # _create_line_element returns a stdlib ET.Element (not lxml) — its own
    # .tag string is the right way to inspect it, matching how the rest of
    # this codebase reads stdlib element tags (see e.g. paragraph.py).
    line_el = _create_line_element(0, 0, 14400, 7200)
    start_pt_tag = next(c.tag for c in line_el if c.tag.rsplit("}", 1)[-1] == "startPt")
    assert start_pt_tag == f"{{{HC_NS}}}startPt", start_pt_tag
    assert "startPt" in _SHAPE_POINT_LOCAL_NAMES and "endPt" in _SHAPE_POINT_LOCAL_NAMES
    print("our line authoring writes hc:startPt/hc:endPt; the generic resize() scan matches by local name only")

    print("PASS: DEV-012 reproduced (vendored evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
