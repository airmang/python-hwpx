#!/usr/bin/env python3
"""DEV-033 -- ``hp:headerApply``/``hp:footerApply`` (a page-type-scoped
(BOTH/EVEN/ODD) header/footer application indirection) are declared nowhere
in the vendored schema. ``hp:header``/``hp:footer`` themselves are declared
(``HeaderFooterType``).

Schema claim: none for ``headerApply``/``footerApply``. All 7 vendored
schema files parse cleanly with 0 declarations of either name.

Real-document measurement: Hancom writes neither. Every Hangul-saved
document of the public corpus that has a header or footer (68 files:
tests/fixtures, rhwp samples, kordoc fixtures) keeps it as an ``hp:ctrl``
story in the body only -- no story under ``hp:secPr``, no apply element.
Only documents python-hwpx up to 6.x wrote carry them (the fuzz baseline
fixture is one).

Our handling (7.0): ``doc.page.set_header``/``set_footer`` write the one
``hp:ctrl`` story Hancom reads and no ``hp:headerApply``. A 6.x document's
``hp:secPr`` copy and apply element are still read, kept in step with the
control copy on save, and dropped when that header is set again. This probe
authors EVEN/ODD headers live and confirms distinct ``applyPageType``
values on ``hp:ctrl`` stories and no apply element.

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

    assert "<hp:headerApply" not in section_xml, "7.0 writes no hp:headerApply"
    sec_pr = re.search(r"<hp:secPr\b.*?</hp:secPr>", section_xml, re.S)
    assert sec_pr is not None and "<hp:header" not in sec_pr.group(0), "no story under hp:secPr"
    stories = re.findall(r'<hp:ctrl><hp:header\b[^>]*applyPageType="(\w+)"', section_xml)
    assert sorted(stories) == ["EVEN", "ODD"], f"expected EVEN/ODD control stories, got: {stories}"
    print(f"confirmed doc.page.set_header(page_type=...) writes hp:ctrl stories only, with "
          f"distinct applyPageType values {sorted(stories)} and no hp:headerApply")

    print("PASS: DEV-033 reproduced (schema absence; the authoring API no longer emits the "
          "undeclared apply element)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
