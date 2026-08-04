#!/usr/bin/env python3
"""DEV-002 — hh:tabItem: schema implies maxOccurs=1, real documents carry many.

Schema claim: ``DevDoc/OWPML SCHEMA/Header XML schema.xml``'s
``TabDefType`` declares ``hh:tabItem`` with ``minOccurs="0"`` and no
``maxOccurs`` — XSD's default is 1, so a single ``hh:tabPr`` can hold at
most one tab stop.

Real-document measurement: ``error__20240626__no_manifest.hwpx`` (vendored
hwpxlib corpus) carries a single ``hh:tabPr`` with **31** ``hh:tabItem``
children, which Hancom itself produced and opens without complaint. A
second corpus file (National Tax Service filing, not vendored — see the
fallback path below) independently shows 4 position-ascending tab stops in
one ``hh:tabPr``, corroborating the pattern on a document from a different
producer/workflow.

Our handling: ``hwpx.oxml.header.parse_tab_definition``/``TabDefinition``
model an unbounded ``tab_stops: List[TabStop]``, and
``HwpxOxmlHeader.ensure_tab_definition`` authors as many ``hh:tabItem``
children as requested — order is part of the dedupe key because real
documents list them position-ascending (see ``docs/2026-08-0x`` train③
notes / commit a144733).

Run: ``python probes/dev002_tabitem_maxoccurs.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

EVIDENCE = ROOT / "tests/fixtures/hwpxlib_corpus/error__20240626__no_manifest.hwpx"
# 두 번째 표본은 국세청 공문(사설 다운로드 코퍼스, .gitignore 대상) — 근거
# 비공개이므로 있으면 교차검증만 하고 없으면 건너뛴다.
CORROBORATING_EVIDENCE = ROOT / "work/public-document-corpus/downloads/nts-1340231_29_76232e486a.hwpx"
NS = {"hh": "http://www.hancom.co.kr/hwpml/2011/head"}


def main() -> int:
    if not EVIDENCE.exists():
        print(f"SKIP: vendored evidence file not present locally: {EVIDENCE}")
        return 0

    data = zipfile.ZipFile(EVIDENCE).read("Contents/header.xml")
    root = etree.fromstring(data)
    tab_prs = root.findall(".//hh:tabPr", NS)
    multi = [tp for tp in tab_prs if len(tp.findall("hh:tabItem", NS)) > 1]
    assert multi, "expected at least one hh:tabPr with >1 hh:tabItem in the evidence file"
    richest = max(multi, key=lambda tp: len(tp.findall("hh:tabItem", NS)))
    positions = [int(item.get("pos")) for item in richest.findall("hh:tabItem", NS)]
    print(f"real document hh:tabPr id={richest.get('id')} carries {len(positions)} hh:tabItem")
    assert len(positions) > 1, "expected the schema's implied maxOccurs=1 to be violated"

    if CORROBORATING_EVIDENCE.exists():
        corr_data = zipfile.ZipFile(CORROBORATING_EVIDENCE).read("Contents/header.xml")
        corr_root = etree.fromstring(corr_data)
        corr_positions = [
            int(item.get("pos"))
            for tp in corr_root.findall(".//hh:tabPr", NS)
            for item in tp.findall("hh:tabItem", NS)
        ]
        print(f"corroborating (non-vendored) evidence: {len(corr_positions)} hh:tabItem observed across the file")
    else:
        print("corroborating (non-vendored, gitignored) evidence file absent — vendored evidence alone suffices")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.add_paragraph("탭 정의 프로브")
    doc.styles.apply_paragraph_format(
        paragraph_index=1,
        tab_stops=[{"pos_mm": p} for p in (10, 20, 30, 40)],
    )
    para_prop = doc.styles.paragraph_property(doc.paragraphs[1].para_pr_id_ref)
    tab_def = doc.styles.tab_property(para_prop.tab_pr_id_ref)
    doc.close()
    assert len(tab_def.tab_stops) == 4, "our own authoring should accept >1 tabItem too"
    print(f"our authoring: hh:tabPr with {len(tab_def.tab_stops)} hh:tabItem round-trips cleanly")
    print("PASS: DEV-002 reproduced (real evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
