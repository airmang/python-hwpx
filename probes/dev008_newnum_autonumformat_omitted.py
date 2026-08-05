#!/usr/bin/env python3
"""DEV-008 — ``hp:newNum`` ships without its schema-required ``autoNumFormat``
child.

Schema claim: ``hp:newNum`` (and its sibling ``hp:autoNum``) share
``AutoNumNewNumType`` (``ParaList XML schema.xml:2741-2759``), whose
``xs:sequence`` declares a required ``autoNumFormat`` child
(``minOccurs`` not overridden — the XSD default is 1, so exactly one is
mandatory).

Real-document measurement: every ``hp:newNum`` reachable in the vendored
fixture tree (``reader_writer__PageFunctions.hwpx`` plus several
``error__*`` regression fixtures — see the probe's own live count) self-
closes with only ``num``/``numType`` — none carry an ``autoNumFormat``
child, and ``numType`` is always ``PAGE``.

Our handling: ``HwpxOxmlParagraph.add_new_num`` (``oxml/paragraph.py``)
emits the self-closing real-corpus shape and never synthesizes an
``autoNumFormat`` child — matching real Hancom output over the schema's
nominal requirement (cycle-6.2 train 9).

Run: ``python probes/dev008_newnum_autonumformat_omitted.py``
"""

from __future__ import annotations

import glob
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def main() -> int:
    fixtures = sorted(glob.glob(str(ROOT / "tests/fixtures/*/*.hwpx")))
    if not fixtures:
        print("SKIP: no vendored corpus files found")
        return 0

    total = 0
    with_children = 0
    num_types: set[str | None] = set()
    files_with_newnum: set[str] = set()

    for path in fixtures:
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith(".xml") or "section" not in name.lower():
                        continue
                    try:
                        root = etree.fromstring(archive.read(name))
                    except etree.XMLSyntaxError:
                        continue
                    for element in root.iter(f"{{{HP_NS}}}newNum"):
                        total += 1
                        files_with_newnum.add(path)
                        num_types.add(element.get("numType"))
                        if len(element) > 0:
                            with_children += 1
        except (zipfile.BadZipFile, KeyError):
            continue

    print(f"hp:newNum found in {len(files_with_newnum)} file(s), {total} element(s) total")
    print(f"elements with a child (e.g. autoNumFormat): {with_children}/{total}")
    print(f"numType values observed: {num_types}")
    if total == 0:
        print("SKIP: no hp:newNum instances in the local vendored corpus")
        return 0
    assert with_children == 0, "expected every real hp:newNum to self-close"
    assert num_types <= {"PAGE"}, "expected numType to be PAGE-only in real corpus"

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.restart_page_number(paragraph, number=23)
    ctrl = paragraph.element.find(f".//{{{HP_NS}}}ctrl/{{{HP_NS}}}newNum").getparent()
    new_num = ctrl.find(f"{{{HP_NS}}}newNum")
    assert len(new_num) == 0, "our authoring must not add an autoNumFormat child either"
    assert new_num.get("num") == "23"
    assert new_num.get("numType") == "PAGE"
    doc.close()
    print("our authoring matches: self-closing hp:newNum, no autoNumFormat child")
    print("PASS: DEV-008 reproduced (vendored evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
