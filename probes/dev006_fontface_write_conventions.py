#!/usr/bin/env python3
"""DEV-006 — fontface/tab boolean spelling and substFont shape diverge from
the rest of OWPML.

Schema claim: ``hh:font/@isEmbedded``, ``hh:tabPr/@autoTabLeft``/
``@autoTabRight`` are ``xs:boolean`` — XSD's boolean lexical space allows
both ``"true"``/``"false"`` and ``"1"``/``"0"``, and most other OWPML
boolean attributes in this codebase (``_bool_str``) use ``"true"``/
``"false"``.

Real-document measurement: ``isEmbedded``/``autoTabLeft``/``autoTabRight``
use **only** ``"0"``/``"1"`` across the full reachable corpus (6741
``hh:font``/``hh:substFont`` occurrences, 142 ``hh:tabPr`` occurrences) —
"true"/"false" is never observed for these three attributes. Separately, a
non-embedded ``hh:font`` never carries a ``binaryItemIDRef`` attribute at
all (1682/1682), while ``hh:substFont`` always carries one, empty-string
when there is no binary item (284/284) — the two elements are asymmetric.

Our handling: ``hwpx.oxml._document_primitives._zero_one_bool_str`` (used
by both ``_build_font_element`` and ``_build_tab_definition_element``)
emits ``"0"``/``"1"`` instead of the codebase's general-purpose
``_bool_str``. ``_build_font_element`` omits ``binaryItemIDRef`` for a
non-embedded ``hh:font`` but always sets it (possibly to ``""``) on
``hh:substFont``.

Run: ``python probes/dev006_fontface_write_conventions.py``
"""

from __future__ import annotations

import sys
import zipfile
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"


def main() -> int:
    fixtures = sorted(glob.glob(str(ROOT / "tests/fixtures/hwpxlib_corpus/*.hwpx")))
    if not fixtures:
        print("SKIP: no vendored corpus files found")
        return 0

    is_embedded_values: set[str] = set()
    auto_tab_values: set[str] = set()
    font_binary_ref_present = 0
    subst_binary_ref_present = 0
    font_count = 0
    subst_count = 0

    for path in fixtures:
        try:
            header = zipfile.ZipFile(path).read("Contents/header.xml")
        except KeyError:
            continue
        root = etree.fromstring(header)
        for font in root.iter(f"{{{HH_NS}}}font"):
            font_count += 1
            is_embedded_values.add(font.get("isEmbedded"))
            if "binaryItemIDRef" in font.attrib:
                font_binary_ref_present += 1
        for subst in root.iter(f"{{{HH_NS}}}substFont"):
            subst_count += 1
            is_embedded_values.add(subst.get("isEmbedded"))
            if "binaryItemIDRef" in subst.attrib:
                subst_binary_ref_present += 1
        for tab_pr in root.iter(f"{{{HH_NS}}}tabPr"):
            auto_tab_values.add(tab_pr.get("autoTabLeft"))
            auto_tab_values.add(tab_pr.get("autoTabRight"))

    print(f"hh:font/hh:substFont isEmbedded values observed: {is_embedded_values} ({font_count + subst_count} elements)")
    print(f"hh:tabPr autoTabLeft/autoTabRight values observed: {auto_tab_values}")
    print(f"hh:font with binaryItemIDRef: {font_binary_ref_present}/{font_count}")
    print(f"hh:substFont with binaryItemIDRef: {subst_binary_ref_present}/{subst_count}")
    assert is_embedded_values <= {"0", "1"}, "expected only 0/1, never true/false"
    assert auto_tab_values <= {"0", "1", None}
    assert font_binary_ref_present == 0, "expected non-embedded hh:font to never carry binaryItemIDRef"
    assert subst_count == 0 or subst_binary_ref_present == subst_count, (
        "expected hh:substFont to always carry binaryItemIDRef"
    )

    from hwpx.document import HwpxDocument
    from hwpx.oxml.namespaces import HH

    doc = HwpxDocument.new()
    doc.styles.ensure_font("프로브글꼴", lang="HANGUL", subst_face="함초롬바탕")
    header_el = doc.oxml.headers[0].element
    font_el = header_el.find(f".//{HH}fontfaces/{HH}fontface/{HH}font[@face='프로브글꼴']")
    assert "binaryItemIDRef" not in font_el.attrib
    assert font_el.get("isEmbedded") == "0"
    subst_el = font_el.find(f"{HH}substFont")
    assert subst_el.get("binaryItemIDRef") == ""
    doc.close()
    print("our authoring matches: no binaryItemIDRef on font, empty-string on substFont, isEmbedded='0'")
    print("PASS: DEV-006 reproduced (real evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
