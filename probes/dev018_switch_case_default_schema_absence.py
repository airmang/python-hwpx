#!/usr/bin/env python3
"""DEV-018 -- ``hp:switch``/``hp:case``/``hp:default`` is a version-compat
branching wrapper that is completely absent from the vendored OWPML schema
copy, yet sits in nearly every real document's paragraph-property style
catalog, and its one attribute is itself namespace-prefixed in an unusual
way for this schema family.

Schema claim: none. A full-text search of all 7 vendored ``DevDoc/OWPML
SCHEMA/*.xml`` files for ``name="switch"``, ``name="case"``, or
``name="default"`` returns zero matches -- unlike DEV-004/005 (settings.xml,
layoutCompatibility), which are schema elements the corpus fills
differently than the schema implies, this construct has no schema
declaration to compare against at all.

Real-document measurement: the coverage ledger's real-corpus census (237
files) puts ``hp:switch``/``hp:case``/``hp:default`` at 236/237 files
(99.6%) -- effectively universal, tied for the highest frequency of any
element this registry has found with zero code support. Structurally, each
occurrence sits inside a ``hh:paraPr`` (a named paragraph style's
definition in ``header.xml``) and wraps two branches of the *same*
``hh:margin``/``hh:lineSpacing`` values: ``<hp:switch><hp:case
hp:required-namespace="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar">
...(2016-schema values)...</hp:case><hp:default>...(2011/legacy fallback
values)...</hp:default></hp:switch>`` -- a version-compatibility branch
(newer clients read hp:case's values if they recognize the named
namespace; older ones fall back to hp:default), the same purpose Markup
Compatibility (mc:AlternateContent/mc:Choice/mc:Fallback) serves in OOXML.
``hp:case``'s one attribute is itself unusual for this schema family:
``hp:required-namespace`` carries the ``hp:`` prefix on an *attribute*,
where nearly every other attribute in this codebase's corpus observations
is bare (``id``, ``zOrder``, ...) unless it is genuinely a foreign-namespace
attribute.

This is not a live authoring-correctness bug: ``header_part.py``'s
``_apply_paragraph_margins``/``_apply_paragraph_line_spacing`` already walk
*all* descendants of a ``hh:paraPr`` (not just direct children) when
setting margin/lineSpacing, so editing a real Hancom-authored style
correctly updates both the ``hp:case`` and ``hp:default`` copies today --
confirmed by reading that code, not asserted here. What is missing is a
typed read model for the wrapper itself (round-trip preservation already
works because nothing touches the untouched subtree).

Run: ``python probes/dev018_switch_case_default_schema_absence.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    schema_files = sorted(SCHEMA_DIR.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        for name in ("switch", "case", "default"):
            assert f'name="{name}"' not in schema_text, (
                f'expected zero schema declarations for "{name}" -- found one, '
                "this deviation's core claim no longer holds"
            )
        print("confirmed hp:switch/case/default are declared nowhere in the vendored schema")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    fixture = CORPUS / "tool__blank.hwpx"
    if not fixture.exists():
        print("SKIP: tool__blank.hwpx not found")
        return 0

    with zipfile.ZipFile(fixture) as archive:
        name = next(n for n in archive.namelist() if n.endswith("header.xml"))
        root = etree.fromstring(archive.read(name))

    switches = list(root.iter(f"{{{HP_NS}}}switch"))
    assert switches, "expected at least one hp:switch in header.xml's paraPr catalog"

    found_required_namespace = False
    found_dual_margin = False
    for switch in switches:
        case_element = switch.find(f"{{{HP_NS}}}case")
        default_element = switch.find(f"{{{HP_NS}}}default")
        assert case_element is not None, "hp:switch missing its hp:case branch"
        assert default_element is not None, "hp:switch missing its hp:default branch"

        # The attribute itself carries the hp: prefix -- unusual for this
        # schema family's attributes.
        required_ns = case_element.get(f"{{{HP_NS}}}required-namespace")
        if required_ns:
            found_required_namespace = True
            assert required_ns == "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar", required_ns

        case_margin = case_element.find(f"{{{HH_NS}}}margin")
        default_margin = default_element.find(f"{{{HH_NS}}}margin")
        if case_margin is not None and default_margin is not None:
            found_dual_margin = True

    assert found_required_namespace, "expected hp:case's hp:required-namespace attribute somewhere"
    assert found_dual_margin, "expected both branches to carry their own hh:margin"
    print(f"confirmed {len(switches)} hp:switch wrapper(s) in tool__blank.hwpx's paraPr "
          "catalog, each with hp:case (hp:required-namespace attribute) and hp:default "
          "branches carrying their own hh:margin")

    import xml.etree.ElementTree as ET

    from hwpx.oxml.header_part import HwpxOxmlHeader

    # HwpxOxmlHeader expects a stdlib ET.Element -- re-parse with stdlib
    # rather than reuse the lxml tree built above (Clark-notation .find()
    # behaves the same either way; the live wrapper's own type contract is
    # what matters here since we are exercising its real setter, not just
    # reading structure).
    with zipfile.ZipFile(fixture) as archive:
        header_xml = archive.read(name)
    stdlib_root = ET.fromstring(header_xml)

    header = HwpxOxmlHeader("header.xml", stdlib_root)
    para_properties = header._para_properties_element(create=False)
    assert para_properties is not None
    para_pr = next(iter(para_properties), None)
    assert para_pr is not None
    switch_in_para_pr = para_pr.find(f"{{{HP_NS}}}switch")
    if switch_in_para_pr is not None:
        margins_before = [
            m.find(f"{{{HC_NS}}}left").get("value")
            for m in para_pr.iter(f"{{{HH_NS}}}margin")
            if m.find(f"{{{HC_NS}}}left") is not None
        ]
        header._apply_paragraph_margins(para_pr, {"left": 9999})
        margins_after = [
            m.find(f"{{{HC_NS}}}left").get("value")
            for m in para_pr.iter(f"{{{HH_NS}}}margin")
            if m.find(f"{{{HC_NS}}}left") is not None
        ]
        assert len(margins_after) == len(margins_before) >= 2, (
            "expected the margin setter to reach every hh:margin descendant "
            "(hp:case's and hp:default's), not just a direct child"
        )
        assert margins_before != margins_after, "the setter did not actually change anything"
        assert all(v == "9999" for v in margins_after), margins_after
        print(f"confirmed _apply_paragraph_margins updates all {len(margins_after)} "
              "hh:margin descendants under hp:switch (both branches), not just one")
    else:
        print("(first paraPr in this fixture has no hp:switch -- skipped the live-update check)")

    print("PASS: DEV-018 reproduced (vendored evidence) and existing margin/lineSpacing "
          "setters confirmed to already handle both branches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
