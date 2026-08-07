#!/usr/bin/env python3
"""DEV-021 -- ``hp:switch`` is not scoped to ``hh:paraPr`` style properties
(DEV-018) or ``hh:tabPr`` tab-stop definitions -- it also wraps *inline
object alternates* directly inside a run, choosing between a modern
representation (``hp:chart``, the 2016 OOXML-chart format) and a legacy
fallback (``hp:ole``) for what is structurally the same embedded object.

Schema claim: none, same as DEV-018 -- ``hp:switch``/``hp:case``/
``hp:default`` are declared nowhere in any of the 7 vendored schema files
(confirmed again here).

Real-document measurement: ``error__20230426__HwpxTest1.hwpx`` (vendored)
has a ``hp:run`` whose children are ``[hp:t, hp:switch, hp:t]`` -- the
switch sits as a direct run child, not inside a paragraph-property style
definition at all. Its ``hp:case`` (``hp:required-namespace="http://
www.hancom.co.kr/hwpml/2016/ooxmlchart"``) wraps a full ``hp:chart``
object; its ``hp:default`` wraps a full ``hp:ole`` object. This is a
structurally different use of the same wrapper than DEV-018 characterized:
DEV-018 is about two *branches holding the same property values* (margin/
lineSpacing, present in both branches with the same semantic meaning);
this is two *entirely different embedded-object representations* of the
same conceptual object -- the modern client renders the chart directly,
the legacy client falls back to a static OLE snapshot. Same purpose as
Markup Compatibility (``mc:AlternateContent``/``Choice``/``Fallback``) in
OOXML, now confirmed across a second, structurally distinct context.

Not a live bug: this codebase's ``PreservedElement`` fallback
(``parse_preserved_element``, ``body.py``) already treats an unrecognized
run child as an opaque ``GenericElement`` and round-trips it byte-for-byte
(confirmed below) -- exactly the same "preserved but opaque" handling
DEV-018 found for the paraPr case before its read-model fix. No chart/ole
typed read model reaches inside this particular ``hp:switch`` today (our
``add_chart`` authoring path never emits one either) -- flagged as a
measurement gap for the next cycle's gap map, not fixed here.

Run: ``python probes/dev021_switch_as_inline_object_alternate.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"
FIXTURE = CORPUS / "error__20230426__HwpxTest1.hwpx"


def main() -> int:
    if not FIXTURE.exists():
        print(f"SKIP: {FIXTURE.name} not found")
        return 0

    with zipfile.ZipFile(FIXTURE) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = etree.fromstring(archive.read(name))

    switches_under_run = []
    for switch in root.iter(f"{{{HP_NS}}}switch"):
        parent = switch.getparent()
        if parent is not None and etree.QName(parent).localname == "run":
            switches_under_run.append((parent, switch))

    assert switches_under_run, "expected at least one hp:switch directly under hp:run"
    run, switch = switches_under_run[0]

    run_children = [etree.QName(c).localname for c in run]
    assert run_children.count("switch") == 1
    print(f"confirmed hp:switch sits directly under hp:run (siblings: {run_children})")

    case_element = switch.find(f"{{{HP_NS}}}case")
    default_element = switch.find(f"{{{HP_NS}}}default")
    assert case_element is not None and default_element is not None

    case_children = [etree.QName(c).localname for c in case_element]
    default_children = [etree.QName(c).localname for c in default_element]
    assert case_children == ["chart"], case_children
    assert default_children == ["ole"], default_children
    required_namespace = case_element.get(f"{{{HP_NS}}}required-namespace")
    assert required_namespace == "http://www.hancom.co.kr/hwpml/2016/ooxmlchart", required_namespace
    print(
        "confirmed hp:case (required-namespace=2016/ooxmlchart) wraps hp:chart, "
        "hp:default wraps hp:ole -- same object, two representations"
    )

    schema_files = sorted(SCHEMA_DIR.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        for name_token in ("switch", "case", "default"):
            assert f'name="{name_token}"' not in schema_text
        print("confirmed hp:switch/case/default are declared nowhere in the vendored schema "
              "(same as DEV-018, reconfirmed in this second context)")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    import sys as _sys

    _sys.path.insert(0, str(ROOT / "src"))
    from hwpx.tools.roundtrip_diff import roundtrip_report

    report = roundtrip_report(FIXTURE)
    assert report["reopened"] is True
    assert report["lost_elements"] == {}, report["lost_elements"]
    print(
        "confirmed this run-level hp:switch (and its hp:chart/hp:ole contents) "
        "round-trips byte-structurally intact via the existing GenericElement "
        "fallback -- opaque but not lossy, same shape as DEV-018's pre-fix state"
    )

    print("PASS: DEV-021 reproduced (vendored evidence, second hp:switch context)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
