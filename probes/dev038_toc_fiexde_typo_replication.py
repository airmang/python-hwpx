#!/usr/bin/env python3
"""DEV-038 -- a CROSSREF field's boolean parameter named ``Fiexde``
replicates Hancom's own spelling verbatim -- the same typo-replication
class as DEV-004/DEV-009/DEV-026 but in a third subsystem (page
cross-reference field parameters, discovered via a different path --
the M7 native-TOC train's gold-corpus reverse engineering rather than a general census
sweep). Despite the module-level docstring's phrasing ("TOC field
parameter spelling"), the parameter itself is emitted by
``add_page_crossref`` (CROSSREF), not ``add_native_toc``.

Schema claim: same as DEV-016/DEV-032/DEV-037 -- ``hp:parameters``
(``hp:ParameterList``) is a generic name-value bag, so there is no
schema-declared "correct" spelling for a parameter name to typo *from* in
the first place; the only source of truth is real Hancom output.

Real-document measurement: ``oracle: not-applicable`` -- the real-Hancom
gold TOC fixture pair (``tests/fixtures/m7_toc_gold/``) already carries
this spelling verbatim, and our own docstring records it directly.

Our handling: ``toc_author.py``'s module docstring states outright: "The
parameter spelling ``Fiexde`` replicates Hancom's own output verbatim."
This probe confirms it appears, unmodified, in our own live
``add_page_crossref`` output (line ``_param(params, "booleanParam",
"Fiexde", "1")  # sic -- Hancom's own spelling``).

Run: ``python probes/dev038_toc_fiexde_typo_replication.py``
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

GOLD_DIR = ROOT / "tests" / "fixtures" / "m7_toc_gold"


def main() -> int:
    if GOLD_DIR.exists() and any(GOLD_DIR.glob("*.hwpx")):
        hits = 0
        for path in sorted(GOLD_DIR.glob("*.hwpx")):
            try:
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        if name.startswith("Contents/section") and name.endswith(".xml"):
                            if b"Fiexde" in archive.read(name):
                                hits += 1
            except zipfile.BadZipFile:
                continue
        assert hits > 0, "expected the Fiexde literal in the real-Hancom gold TOC fixture"
        print(f"confirmed the Fiexde literal appears in {hits} gold-fixture section part(s) "
              f"(real Hancom output, m7_toc_gold)")
    else:
        print("SKIP: tests/fixtures/m7_toc_gold/ not present in this checkout")

    from hwpx.document import HwpxDocument
    from hwpx.tools.toc_author import add_page_crossref

    doc = HwpxDocument.new()
    target = doc.sections[0].add_paragraph("타깃 문단")
    ref = doc.sections[0].add_paragraph("참조 문단")
    add_page_crossref(doc, ref, target, cached_page=5)
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name).decode("utf-8")

    assert 'name="Fiexde"' in section_xml, "expected the Fiexde parameter name verbatim"
    print("confirmed our own add_page_crossref() output carries the Fiexde parameter name, "
          "matching real Hancom output's own typo rather than a 'corrected' spelling")

    print("PASS: DEV-038 reproduced (gold fixture + live authoring output)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
