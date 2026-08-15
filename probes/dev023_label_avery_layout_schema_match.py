#!/usr/bin/env python3
"""DEV-023 -- ``hp:label`` (Avery-style label-sheet/nameplate print
layout) is the last code-blind high-frequency element this registry's
completeness ledger found (64/237 real files in the census population,
27% -- the only remaining ``read=False`` element above corpus 10 files,
gap-map v2 section B.2). Unlike most elements this registry has reverse-
engineered, the schema and real output agree completely -- there is no
"schema says X, real output does Y" divergence to register here, just a
genuine zero-code-support gap that is now closed.

Schema claim: ``ParaList XML schema.xml``'s ``TableType`` sequence
declares ``hp:label`` (``minOccurs="0"``) as the *last* element, after all
``hp:tr`` rows -- 11 attributes total, all ``xs:nonNegativeInteger`` except
``landscape`` (enum ``WIDELY``/``NARROWLY``).

Real-document measurement: this repo's completeness program reverse-
engineers structure from the maintainer's private real-world Hancom
documents when the vendored 47-file corpus has no examples (documented
practice, see ``docs/_extra/element-census.json``'s populationNote -- the
private corpus's path is deliberately not recorded anywhere, including
here, for privacy). That reverse-engineering (75 files, 436 real
``hp:label`` occurrences) found: (a) the parent is always ``hp:tbl``
(436/436), always as the table's *last* child (spot-checked across
several files, matching the schema's own sequence position); (b) all 11
schema-declared attributes appear, no others, no exceptions; (c) real
output collapses to exactly 2 distinct attribute-value combinations across
75 files -- a small 2-columns-by-9-rows label sheet (325 occurrences) and
a large 1-column-by-2-rows square nameplate/placard layout (111
occurrences, ``boxwidth == boxlength``); (d) ``landscape="WIDELY"`` in
100% of real occurrences (``"NARROWLY"`` is schema-legal but unconfirmed
against real output). None of this private-corpus evidence is
independently reproducible by this probe (by design -- see above); what
follows tests only what is: the vendored schema declaration, and our own
round-trip/authoring implementation against synthetic (not real) values.

Our handling: ``hwpx.oxml.body.Label``/``parse_label_element``/
``_label_to_xml`` (a typed ``PreservedElement``, wired into
``parse_preserved_element``'s dispatch the same way DEV-011's
``ParameterList`` and DEV-018/019's version-switch types were).
``HwpxOxmlTable.label``/``.set_label()``/``.remove_label()`` provide the
authoring surface, appending as the table's last child (matching the
schema/real-corpus position) without restricting attribute values to the
two combinations actually observed -- there is no real-corpus evidence for
what other combinations Hancom accepts or rejects, so no invented
validation rule is added beyond the schema's own types.

Run: ``python probes/dev023_label_avery_layout_schema_match.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    schema_dir = ROOT / "DevDoc" / "OWPML SCHEMA"
    schema_files = sorted(schema_dir.glob("*.xml"))
    if not schema_files:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout")
        return 0

    schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
    assert 'name="label"' in schema_text, "expected hp:label declared in the schema"
    for attr in (
        "topmargin", "leftmargin", "boxwidth", "boxlength", "boxmarginhor",
        "boxmarginver", "labelcols", "labelrows", "landscape", "pagewidth",
        "pageheight",
    ):
        assert f'name="{attr}"' in schema_text, f"expected hp:label attribute {attr!r} declared"
    assert "WIDELY" in schema_text and "NARROWLY" in schema_text
    print("confirmed hp:label declared with all 11 real-corpus-observed attributes "
          "(topmargin/leftmargin/boxwidth/boxlength/boxmarginhor/boxmarginver/"
          "labelcols/labelrows/landscape/pagewidth/pageheight) plus the landscape "
          "enum (WIDELY/NARROWLY)")

    from lxml import etree

    from hwpx.oxml.body import Label, parse_preserved_element

    HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    # Synthetic values -- not copied from any real document.
    xml = (
        f'<hp:label xmlns:hp="{HP_NS}" topmargin="2500" leftmargin="900" '
        'boxwidth="18000" boxlength="7500" boxmarginhor="450" boxmarginver="0" '
        'labelcols="3" labelrows="8" landscape="WIDELY" pagewidth="59528" '
        'pageheight="84188"/>'
    )
    node = etree.fromstring(xml)

    dispatched = parse_preserved_element(node)
    assert isinstance(dispatched, Label), (
        f"expected parse_preserved_element to dispatch hp:label to Label, got "
        f"{type(dispatched).__name__}"
    )
    assert dispatched.labelcols == 3 and dispatched.labelrows == 8
    assert dispatched.landscape == "WIDELY"
    print("confirmed parse_preserved_element dispatches hp:label to a typed Label, "
          "not a generic fallback")

    from hwpx.document import HwpxDocument

    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=2, section=0)
    assert table.label is None

    written = table.set_label(
        topmargin=2500, leftmargin=900, boxwidth=18000, boxlength=7500,
        boxmarginhor=450, boxmarginver=0, labelcols=3, labelrows=8,
        landscape="WIDELY", pagewidth=59528, pageheight=84188,
    )
    assert written.labelcols == 3
    children_tags = [child.tag.rsplit("}", 1)[-1] for child in table.element]
    assert children_tags[-1] == "label", (
        f"expected hp:label to be the table's last child, got order {children_tags}"
    )
    print("confirmed set_label() places hp:label as the table's last child, "
          "matching the schema sequence and real-corpus position")

    data = document.to_bytes()
    reopened = HwpxDocument.open(data)
    reopened_table = next(
        t for p in reopened.oxml.sections[0].paragraphs for t in p.tables
    )
    reopened_label = reopened_table.label
    assert reopened_label is not None
    assert reopened_label.labelcols == 3 and reopened_label.labelrows == 8
    assert reopened_label.boxwidth == 18000 and reopened_label.boxlength == 7500
    print("confirmed hp:label round-trips through a real open/save cycle intact")

    removed = reopened_table.remove_label()
    assert removed is True
    assert reopened_table.label is None
    print("confirmed remove_label() removes it cleanly")

    print("PASS: DEV-023 reproduced (schema evidence + our implementation verified; "
          "private-corpus evidence is asserted, not re-derived here, by design)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
