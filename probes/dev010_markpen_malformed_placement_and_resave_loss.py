#!/usr/bin/env python3
"""DEV-010 — one real fixture's ``markpenBegin`` lives outside ``hp:t``, and
its own resave drops the ``color`` attribute.

Schema claim: ``ParaList XML schema.xml:228-237`` declares
``markpenBegin``/``markpenEnd`` as children of the mixed-content ``hp:t``
element only — never siblings of ``hp:ctrl`` directly under ``hp:run``.

Real-document measurement: **this is evidence from an hwpxlib *error*
regression fixture, not an ordinary Hancom-authored document** —
``hwpxlib_corpus/error__20251107__test.hwpx`` is one of hwpxlib's own
named error/edge-case test cases, so it demonstrates a malformed shape
hwpxlib itself flags, not typical output. In that file, ``hp:markpenBegin``
sits as a direct child of ``hp:run`` (a sibling of ``hp:ctrl``), outside
any ``hp:t`` — schema-nonconformant. Its own resaved companion,
``error__20251107__test_re.hwpx``, keeps the malformed *position* but
drops the ``color`` attribute from that same ``markpenBegin`` entirely —
this pair is the same source Hancom/hwpxlib re-saved lossily, corroborated
by DEV-009's independent finding that the same ``_re`` file also drops
``memoType`` from its ``hh:memoPr`` entries.

Our handling: ``hwpx._document.highlight._span_highlights`` only pairs
``markpenBegin``/``markpenEnd`` when both live inside the same ``hp:t``
(the schema-conformant shape our own writer always produces) — reading
this malformed file therefore reports **zero** highlights rather than
fabricating one from the orphaned mark, an explicit, tested choice
(cycle-6.2 train 6; pinned by
``tests/test_highlight_authoring.py::test_real_corpus_malformed_pair_reads_as_empty_not_fabricated``).

Run: ``python probes/dev010_markpen_malformed_placement_and_resave_loss.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

ORIGINAL = ROOT / "tests/fixtures/hwpxlib_corpus/error__20251107__test.hwpx"
RESAVED = ROOT / "tests/fixtures/hwpxlib_corpus/error__20251107__test_re.hwpx"


def main() -> int:
    if not ORIGINAL.exists() or not RESAVED.exists():
        print(f"SKIP: evidence files not present locally: {ORIGINAL}, {RESAVED}")
        return 0

    from lxml import etree

    HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"

    original_xml = zipfile.ZipFile(ORIGINAL).read("Contents/section1.xml")
    resaved_xml = zipfile.ZipFile(RESAVED).read("Contents/section1.xml")

    original_root = etree.fromstring(original_xml)
    original_mark = next(original_root.iter(f"{{{HP_NS}}}markpenBegin"))
    assert original_mark.getparent().tag == f"{{{HP_NS}}}run", (
        "expected the original file's markpenBegin to sit directly under hp:run"
    )
    assert original_mark.get("color") == "#CBFF99", "expected the original mark to carry its color"
    print(f"original markpenBegin parent: {etree.QName(original_mark.getparent()).localname!r}, "
          f"color={original_mark.get('color')!r}")

    resaved_root = etree.fromstring(resaved_xml)
    resaved_mark = next(resaved_root.iter(f"{{{HP_NS}}}markpenBegin"))
    assert resaved_mark.getparent().tag == f"{{{HP_NS}}}run", (
        "expected the resaved file to keep the same malformed placement"
    )
    assert resaved_mark.get("color") is None, "expected the resave to have dropped the color attribute"
    print(f"resaved markpenBegin parent: {etree.QName(resaved_mark.getparent()).localname!r}, "
          f"color={resaved_mark.get('color')!r} (lost on resave)")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.open(str(ORIGINAL))
    found = doc.text.highlights()
    assert found == (), f"expected zero fabricated highlights from the malformed pair, got {found!r}"
    doc.close()
    print("our reader reports zero highlights for the malformed pair (honest, not fabricated)")
    print("PASS: DEV-010 reproduced (vendored hwpxlib-error evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
