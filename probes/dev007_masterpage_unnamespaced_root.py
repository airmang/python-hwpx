#!/usr/bin/env python3
"""DEV-007 — masterPage part root ships without its own namespace prefix.

Schema claim: ``DevDoc/OWPML SCHEMA/MasterPage XML schema.xml`` declares
the part root as ``hm:masterPage`` (``hm`` = the master-page namespace,
``http://www.hancom.co.kr/hwpml/2011/master-page``) — matching how
``Contents/header.xml``'s root is ``hh:head`` and a section's root is
``hs:sec``.

Real-document measurement: a real Hancom-produced masterpage part
(``Contents/masterpage0.xml``) declares ``xmlns:hm="..."`` on its root
element but never applies that (or any) prefix to the root itself — the
root tag is bare ``masterPage``, entirely unnamespaced, while its own
children (``hp:subList``/``hp:p``/…) correctly carry the ``hp:`` prefix.
Confirmed against the *vendored* corpus (this is not a private-corpus-only
finding), independently corroborating the completeness audit's census
note that ``corpusUnnamespacedElements`` records exactly this element.
Cycle 6.4 train 15 cross-validated this against 110 additional real
masterpage parts from a second, independent real-world document collection
(a separate research-paper document family, not this repo's own fixtures)
— every one of them also has the bare, unprefixed ``masterPage`` root.

Our handling: promoted from a bare element wrapper (train 15, cycle 6.4,
commit 1e9c0c8) to a real structured read model —
``hwpx.oxml.master_page.parse_master_page``/``MasterPage`` — reachable via
``HwpxOxmlMasterPage.to_model()``. The parser validates the root by local
name only (``local_name(node) == "masterPage"``, namespace-agnostic by
construction), so this quirk needed no special-casing once the parser was
namespace-indifferent to begin with; the DEV-007 status moves from
"observed, no code" to "implemented, and the observation is exactly why the
parser is written the way it is."

Run: ``python probes/dev007_masterpage_unnamespaced_root.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EVIDENCE = (
    ROOT
    / "tests/fixtures/hwpxlib_corpus"
    / "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
)


def main() -> int:
    if not EVIDENCE.exists():
        print(f"SKIP: evidence file not present locally: {EVIDENCE}")
        return 0

    from lxml import etree

    data = zipfile.ZipFile(EVIDENCE).read("Contents/masterpage0.xml")
    root = etree.fromstring(data)
    print(f"real masterpage0.xml root tag: {root.tag!r}")
    assert root.tag == "masterPage", "expected a bare, unprefixed root tag"
    assert "hm" in root.nsmap, "expected xmlns:hm to still be declared (just unused on the root)"
    subject = root.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}subList")
    assert subject is not None, "expected the root's own children to carry their proper hp: prefix"
    print("root has xmlns:hm declared but unused on itself; hp:subList child is correctly prefixed")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.open(str(EVIDENCE))
    master_pages = doc.parts.master_pages
    assert master_pages, "expected our library to still discover the master page part"
    print(f"our library discovers {len(master_pages)} master page part(s) despite the bare root")

    model = master_pages[0].to_model()
    from hwpx.oxml.master_page import MasterPage

    assert isinstance(model, MasterPage)
    assert model.id == "masterpage0"
    assert model.type == "OPTIONAL_PAGE"
    print(f"to_model() reads it structurally despite the bare root: {model!r}")
    doc.close()
    print("PASS: DEV-007 reproduced (vendored evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
