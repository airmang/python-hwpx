#!/usr/bin/env python3
"""DEV-022 -- ``hh:tabPr`` is also ``hp:switch``-wrapped (449 real
occurrences, DEV-018's third confirmed context alongside ``hh:paraPr`` and
DEV-021's ``hp:run``), but unlike DEV-018's margin/lineSpacing, the two
branches do **not** hold the same value: ``hp:case``'s ``hh:tabItem/@pos``
is exactly half of ``hp:default``'s, and only ``hp:case`` declares an
explicit ``unit="HWPUNIT"`` attribute.

Schema claim: none for the wrapper itself, same as DEV-018/DEV-021 --
``hp:switch``/``hp:case``/``hp:default`` are declared nowhere in the 7
vendored schema files (confirmed again here). ``hh:tabItem``'s own ``unit``
attribute is not declared by the schema at all either (only ``pos``/
``type``/``leader`` are) -- ``TabStop``'s own docstring already flagged
"실코퍼스가 이 자리에 unit 속성을 쓰는 문서를 드물게 관측했으나 원인
미확인" (real corpus rarely observed a unit attribute here, cause unknown)
before this probe -- this is that cause.

Real-document measurement: across the 47-file vendored corpus, every
``hp:case``/``hp:default`` pair with the same number of ``hh:tabItem``
children (34 pairs total) shows ``default.pos == case.pos * 2`` --
universal, no exceptions. ``hp:case``'s ``hh:tabItem`` carries
``unit="HWPUNIT"`` in 449/449 real occurrences; ``hp:default``'s and every
real *unwrapped* (non-switch) ``hh:tabItem`` (34 occurrences, 3 files)
never does (0/483 combined). ``error__20240626__no_manifest.hwpx``'s
unwrapped ``hh:tabPr`` entries settle which branch is the "real"/rendering
scale: their direct ``pos`` values (8064, 3216) match ``hp:default``'s
scale exactly, not ``hp:case``'s halved one.

Which branch is the position: Hancom 13.60 lays a stop out at ``hp:case``'s
position (HWPUNIT), reads an unwrapped ``hh:tabItem`` in HWPUNIT too, and
saves such an item as a switch of that position in ``hp:case`` and twice it
in ``hp:default`` (``tests/fixtures/hancom_saved/tab_bare_right_saved.hwpx``).
The unwrapped control document's values match ``hp:default``'s scale because
an older Hancom wrote the doubled scale there.

Our handling: ``TabDefinition.tab_stops`` reads ``hp:case`` (as DEV-018 does).
Hancom wraps each stop in its own ``hp:switch``; the read model gathers the
stops of every switch, and both branches stay readable via
``TabDefinition.version_switch``. ``ensure_tab_definition`` writes each stop
the same way and compares ``hp:case`` positions when it dedupes
(``_tab_definition_matches``, ``_document_primitives.py``), so a compatible
switch-wrapped definition is reused instead of duplicated.

Run: ``python probes/dev022_tabpr_switch_case_default_scale_mismatch.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SWITCH_WRAPPED_SAMPLE = CORPUS / "error__20230413__test.hwpx"
DIRECT_CHILD_SAMPLE = CORPUS / "error__20240626__no_manifest.hwpx"


def _header_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("header.xml"))
        return etree.fromstring(archive.read(name))


def main() -> int:
    if not SWITCH_WRAPPED_SAMPLE.exists() or not DIRECT_CHILD_SAMPLE.exists():
        print("SKIP: required vendored fixtures not found")
        return 0

    schema_dir = ROOT / "DevDoc" / "OWPML SCHEMA"
    schema_files = sorted(schema_dir.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        for name in ("switch", "case", "default"):
            assert f'name="{name}"' not in schema_text
        print("confirmed hp:switch/case/default declared nowhere in the vendored schema "
              "(same as DEV-018/DEV-021, reconfirmed in this third context)")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    # 34 case/default position pairs across the whole corpus, all ratio 2.0.
    ratio_pairs: list[tuple[int, int]] = []
    unit_case = 0
    unit_default = 0
    for path in sorted(CORPUS.glob("*.hwpx")):
        try:
            root = _header_root(path)
        except (zipfile.BadZipFile, KeyError, StopIteration):
            continue
        for switch in (s for tab_pr in root.iter(f"{{{HH_NS}}}tabPr") for s in tab_pr
                       if etree.QName(s).localname == "switch"):
            case = next((c for c in switch if etree.QName(c).localname == "case"), None)
            default = next((c for c in switch if etree.QName(c).localname == "default"), None)
            if case is None or default is None:
                continue
            case_items = [c for c in case if etree.QName(c).localname == "tabItem"]
            default_items = [c for c in default if etree.QName(c).localname == "tabItem"]
            for item in case_items:
                if item.get("unit"):
                    unit_case += 1
            for item in default_items:
                if item.get("unit"):
                    unit_default += 1
            if len(case_items) != len(default_items):
                continue
            for ci, di in zip(case_items, default_items):
                cp, dp = int(ci.get("pos") or 0), int(di.get("pos") or 0)
                if cp:
                    ratio_pairs.append((cp, dp))

    assert ratio_pairs, "expected at least one case/default tabItem position pair"
    assert all(dp == cp * 2 for cp, dp in ratio_pairs), (
        f"expected every default.pos == case.pos * 2, found violations in: "
        f"{[(cp, dp) for cp, dp in ratio_pairs if dp != cp * 2]}"
    )
    print(f"confirmed default.pos == case.pos * 2 across {len(ratio_pairs)} real position pairs "
          "(0 violations)")

    assert unit_case > 0, "expected hp:case tabItem entries to declare unit=\"HWPUNIT\""
    assert unit_default == 0, (
        f"expected hp:default tabItem entries to never declare unit, found {unit_default}"
    )
    print(f"confirmed unit=\"HWPUNIT\" appears on {unit_case} hp:case tabItem entries "
          "and 0 hp:default ones")

    direct_root = _header_root(DIRECT_CHILD_SAMPLE)
    direct_positions: set[int] = set()
    for tab_pr in direct_root.iter(f"{{{HH_NS}}}tabPr"):
        for item in tab_pr:
            if etree.QName(item).localname == "tabItem" and item.get("unit") is None:
                pos = item.get("pos")
                if pos:
                    direct_positions.add(int(pos))
    assert direct_positions, "expected at least one direct (non-switch) hh:tabItem in the control fixture"

    default_scale_positions = {dp for _cp, dp in ratio_pairs}
    overlap_default = direct_positions & default_scale_positions
    assert overlap_default, (
        f"expected the control fixture's direct positions {direct_positions} to overlap "
        f"hp:default's scale {default_scale_positions}"
    )
    print(f"confirmed unwrapped real tabItem positions {sorted(overlap_default)} match "
          "hp:default's doubled scale -- an older Hancom wrote that scale unwrapped")

    from hwpx.oxml.header import TabDefinitionVersionSwitch, parse_tab_definition

    root = _header_root(SWITCH_WRAPPED_SAMPLE)
    switch_wrapped_defs = [
        parse_tab_definition(tab_pr)
        for tab_pr in root.iter(f"{{{HH_NS}}}tabPr")
        if any(etree.QName(c).localname == "switch" for c in tab_pr)
    ]
    assert switch_wrapped_defs, "expected switch-wrapped hh:tabPr entries in the fixture"
    for definition in switch_wrapped_defs:
        assert definition.tab_stops, "tab_stops must not be empty for a switch-wrapped tabPr"
        switch = definition.version_switch
        assert isinstance(switch, TabDefinitionVersionSwitch)
        assert switch.case is not None
        assert [s.pos for s in definition.tab_stops] == [s.pos for s in switch.case.tab_stops]
    print(f"confirmed our TabDefinition.tab_stops reads hp:case (HWPUNIT) across "
          f"{len(switch_wrapped_defs)} real switch-wrapped tabPr entries, every switch gathered")

    import xml.etree.ElementTree as ET

    from hwpx.oxml.header_part import HwpxOxmlHeader

    header = HwpxOxmlHeader("header.xml", ET.Element(f"{{{HH_NS}}}head", {"version": "1.4", "secCnt": "1"}))
    tab_id = header.ensure_tab_definition(tab_stops=[{"pos": 42520, "type": "RIGHT", "leader": "DOT"}])
    authored = next(tp for tp in header.element.iter(f"{{{HH_NS}}}tabPr") if tp.get("id") == tab_id)
    case_items = authored.findall(f"{{{HP_NS}}}switch/{{{HP_NS}}}case/{{{HH_NS}}}tabItem")
    default_items = authored.findall(f"{{{HP_NS}}}switch/{{{HP_NS}}}default/{{{HH_NS}}}tabItem")
    assert [(i.get("pos"), i.get("unit")) for i in case_items] == [("42520", "HWPUNIT")]
    assert [i.get("pos") for i in default_items] == ["85040"]
    print("confirmed our authoring writes a stop as Hancom does: hp:case 42520 HWPUNIT, hp:default 85040")

    print("PASS: DEV-022 reproduced (vendored evidence; hp:case read and written as Hancom does)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
