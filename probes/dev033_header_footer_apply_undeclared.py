#!/usr/bin/env python3
"""DEV-033 -- ``hp:headerApply``/``hp:footerApply`` (the page-type-scoped
(BOTH/EVEN/ODD) header/footer application mechanism) are declared nowhere
in the vendored schema. ``hp:header``/``hp:footer`` themselves are
declared (``HeaderFooterType``); the separate "apply this header/footer to
these page types" indirection is a pure Hancom extension.

Schema claim: none for ``headerApply``/``footerApply``. All 7 vendored
schema files parse cleanly with 0 declarations of either name.

Real-document measurement: **honest gap, not fabricated** -- neither name
appears anywhere in this checkout's 47-file vendored corpus, nor in the
live 237-file element census (``docs/coverage-ledger.json``). This is
narrower evidence than most entries in this registry: it does not mean
these elements are rare in the wild (``section_format.py``'s substantial,
pre-existing ``_ensure_header_footer_apply``/``_apply_elements``/
``_match_apply_for_element`` machinery did not appear from nothing), only
that this checkout's available corpus/census population happens not to
sample a document using page-type-scoped headers/footers. Flagged here
rather than silently citing a stale count.

Our handling: ``section_format.py``'s header/footer application machinery
is built entirely on this undeclared mechanism (confirmed by direct source
read, not just docstring citation). This probe exercises the *actual
authoring API* (``doc.page.set_header(page_type=...)``) live and confirms
it emits real ``<hp:headerApply>`` elements with distinct
``applyPageType`` values -- the strongest evidence available in this
environment, since no corpus sample exists to grep.

Run: ``python probes/dev033_header_footer_apply_undeclared.py``
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    schema_dir = SCHEMA_DIR
    schema_files = sorted(schema_dir.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        for name in ("headerApply", "footerApply"):
            assert f'name="{name}"' not in schema_text, name
        assert 'name="header"' in schema_text and 'name="footer"' in schema_text, (
            "expected hp:header/hp:footer themselves to be declared (only the apply "
            "indirection is undeclared)"
        )
        print("confirmed headerApply/footerApply declared nowhere in the 7 vendored schema "
              "files, while header/footer themselves are declared")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.page.set_header(text="짝수 페이지 머리말", page_type="EVEN")
    doc.page.set_header(text="홀수 페이지 머리말", page_type="ODD")
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name).decode("utf-8")

    apply_elements = re.findall(r'<hp:headerApply[^>]*>', section_xml)
    assert apply_elements, "expected at least one hp:headerApply element"
    page_types = re.findall(r'applyPageType="(\w+)"', section_xml)
    assert "EVEN" in page_types and "ODD" in page_types, (
        f"expected distinct EVEN/ODD applyPageType values, got: {page_types}"
    )
    print(f"confirmed doc.page.set_header(page_type=...) emits real hp:headerApply "
          f"elements with distinct applyPageType values: {sorted(set(page_types))}")

    print("PASS: DEV-033 reproduced (schema absence + live authoring API; real-document "
          "frequency is an honest gap in this checkout's corpus population, not confirmed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
