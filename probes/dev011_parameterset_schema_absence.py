#!/usr/bin/env python3
"""DEV-011 — ``hp:parameterset`` root element and ``hp:unsignedintegerParam``
leaf type are not declared anywhere in the vendored schema copy.

Schema claim: ``ParaList XML schema.xml:2764`` declares a reusable
``ParameterList`` complex type (``booleanParam``/``integerParam``/
``floatParam``/``stringParam``/``listParam`` leaves, ``cnt``/``name``
attributes) but never binds it to a root element literally named
``parameterset`` — the only reachable declaration is the field-click-action
usage as ``hp:parameters`` (plural) inside ``hp:fieldBegin``, which this
repo's ``toc_author.py`` already authors (booleanParam/integerParam/
stringParam, render-verified for TOC/CROSSREF/HYPERLINK fields). Nothing in
any of the 7 vendored schema files declares ``unsignedintegerParam`` as a
``ParameterList`` choice member either — only ``integerParam`` (signed) is.

Real-document measurement: ``error__20230809__test.hwpx`` (vendored,
neolord0/hwpxlib error-regression fixture — a real, non-synthetic Hancom
document) has an ``hp:rect`` shape whose last child is
``<hp:parameterset cnt="1" name="539"><hp:listParam cnt="1" name="12291">
<hp:unsignedintegerParam name="28673">2</hp:unsignedintegerParam>
</hp:listParam></hp:parameterset>`` — the *same* ``ParameterList`` shape
(cnt/name attributes, nested listParam), just attached to a shape's
extended-property slot under a different root tag and with a leaf type our
local schema copy does not know about. This is the only occurrence of
either ``parameterset`` or ``unsignedintegerParam`` in the 47-file vendored
corpus (cycle-6.3 train 11 scan, single file, single occurrence each).

Our handling: ``hwpx.oxml.body.ParameterList``/``Parameter`` model the
shape structurally (not the field-only ``hp:parameters`` alias) and
``parse_parameter_list_element``/``parameter_list_to_xml`` round-trip
*either* root tag verbatim (``model.tag`` preserves which one was read) —
``unsignedintegerParam`` is included in ``_PARAM_LEAF_KINDS`` alongside the
schema's 4 declared leaf kinds, keyed to observation rather than the local
schema copy (cycle-6.3 train 11). **Wiring correction (2026-08 cycle 6.6
train 20)**: cycle 6.5 train 17's re-verification found this class was
unit-tested but never reached through the real document-open dispatch
(``parse_preserved_element``, ``body.py``) -- opening a real document with
this shape produced ``GenericElement`` (byte-preserved but opaque), not
``ParameterList``. Both the read dispatch (``parse_preserved_element``) and
the write dispatch (``_preserved_element_to_xml``) now have a branch for
``parameterset``/``parameters`` -- verified against all 306 real
occurrences of parameterset/parameters/listParam in the vendored corpus
(0 attribute loss, 0 cnt/child-count mismatches) before wiring, so this is
not a blind flip.

Run: ``python probes/dev011_parameterset_schema_absence.py``
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
#: 실제 Hancom OWPML 전문(7종) — src/hwpx/tools/_schemas/*.xsd는 검증용
#: 스텁(14/12줄)이라 이 확인엔 못 쓴다.
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    fixtures = sorted(CORPUS.glob("*.hwpx"))
    if not fixtures:
        print("SKIP: no vendored hwpxlib corpus files found")
        return 0

    hits: dict[str, int] = {}
    for path in fixtures:
        try:
            with zipfile.ZipFile(path) as archive:
                names = [n for n in archive.namelist() if n.startswith("Contents/section")]
                for name in names:
                    root = etree.fromstring(archive.read(name))
                    count = len(root.findall(f".//{{{HP_NS}}}parameterset"))
                    if count:
                        hits[path.name] = hits.get(path.name, 0) + count
        except (zipfile.BadZipFile, KeyError):
            continue

    print(f"hp:parameterset found in {len(hits)} file(s): {hits}")
    if not hits:
        print("SKIP: no hp:parameterset in the local vendored corpus")
        return 0
    assert hits == {"error__20230809__test.hwpx": 1}, (
        f"expected exactly the one known occurrence, got {hits}"
    )

    with zipfile.ZipFile(CORPUS / "error__20230809__test.hwpx") as archive:
        root = etree.fromstring(archive.read("Contents/section0.xml"))
    (node,) = root.iter(f"{{{HP_NS}}}parameterset")
    assert node.get("cnt") == "1" and node.get("name") == "539"
    (list_param,) = node.iter(f"{{{HP_NS}}}listParam")
    assert list_param.get("cnt") == "1" and list_param.get("name") == "12291"
    (leaf,) = list_param.iter(f"{{{HP_NS}}}unsignedintegerParam")
    assert leaf.get("name") == "28673" and leaf.text == "2"
    print("real-document structure confirmed: parameterset > listParam > unsignedintegerParam")

    from hwpx.oxml.body import parameter_list_to_xml, parse_parameter_list_element

    model = parse_parameter_list_element(node)
    assert model.name == "539"
    assert model.params[0].kind == "list" and model.params[0].name == "12291"
    inner = model.params[0].items[0]
    assert inner.kind == "unsignedinteger" and inner.name == "28673" and inner.value == 2

    rebuilt = parameter_list_to_xml(model)
    assert rebuilt.get("cnt") == "1" and rebuilt.get("name") == "539"
    rebuilt_list_param = list(rebuilt)[0]
    assert rebuilt_list_param.get("cnt") == "1" and rebuilt_list_param.get("name") == "12291"
    rebuilt_leaf = list(rebuilt_list_param)[0]
    assert etree.QName(rebuilt_leaf).localname == "unsignedintegerParam"
    assert rebuilt_leaf.get("name") == "28673" and rebuilt_leaf.text == "2"
    print("our model round-trips the schema-absent element + leaf type structurally")

    # Real dispatch, not the direct function call above -- proves the 2026-08
    # cycle 6.6 train 20 wiring fix (opening the actual document now yields
    # ParameterList, not GenericElement passthrough).
    from hwpx.oxml import GenericElement, parse_section_xml

    with zipfile.ZipFile(CORPUS / "error__20230809__test.hwpx") as archive:
        section_xml = archive.read("Contents/section0.xml")
    section_model = parse_section_xml(section_xml)

    def _walk(value):
        if isinstance(value, (str, bytes, bytearray, dict)) or value is None:
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                yield from _walk(item)
            return
        yield value
        for f in getattr(value, "__dataclass_fields__", {}):
            yield from _walk(getattr(value, f))

    from hwpx.oxml.body import ParameterList

    dispatched = [n for n in _walk(section_model) if isinstance(n, ParameterList)]
    leftover_generic = [
        n
        for n in _walk(section_model)
        if isinstance(n, GenericElement) and n.name in {"parameters", "parameterset"}
    ]
    assert dispatched, "real dispatch (parse_section_xml) never produced a ParameterList"
    assert leftover_generic == [], (
        f"parameterset/parameters still falling through to GenericElement: {leftover_generic}"
    )
    print("confirmed real dispatch (parse_section_xml -> parse_preserved_element) now "
          "reaches ParameterList, not GenericElement passthrough")

    schema_files = sorted(SCHEMA_DIR.glob("*.xml"))
    if not schema_files:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-absence step skipped")
    else:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        assert "parameterset" not in schema_text.lower()
        assert "unsignedintegerparam" not in schema_text.lower()
        assert "ParameterList" in schema_text  # sanity: the reusable type itself IS declared
        print(f"confirmed against {len(schema_files)} real OWPML schema files: neither name appears")

    print("PASS: DEV-011 reproduced (vendored evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
