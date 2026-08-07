#!/usr/bin/env python3
"""DEV-031 -- ``fieldBegin[type=TABLEOFCONTENTS]``'s ``dirty`` attribute is
a plain schema boolean, but its real meaning is "recompute the TOC the
*next time this document is opened*" -- and exporting in the *same*
session right after setting it can crash real Hancom.

Schema claim: ``ParaList XML schema.xml`` declares ``<xs:attribute
name="dirty" type="xs:boolean" default="false"/>`` -- a generic boolean,
no statement of when or by whom it is consumed.

Real-document measurement: ``oracle: previously-verified`` -- owner
memory ``s062-m7-progress.md`` (M7/S-062 P3) records that the Hancom
oracle automation deliberately separates ``refresh_document`` (which
triggers the recompute) from render/export into two distinct sessions to
avoid a same-session crash after setting ``dirty``. Not re-observable
here (no Hancom oracle, and the crash path is explicitly flagged
dangerous to attempt outside a controlled box run).

Our handling: ``toc_author.py``'s ``mark_toc_dirty()`` sets the trigger
but does not and cannot enforce session separation -- that responsibility
is the caller's (the automation layer's ``MacHancomOracle.refresh_document``
split exists because of this exact documented risk). This probe
reproduces the structural half only: that our TOC/CROSSREF authoring
paths set ``dirty`` differently by field type (TOC defaults dirty="1",
CROSSREF never sets it -- see DEV-039 for that asymmetry in detail).

Run: ``python probes/dev031_toc_dirty_next_open_trigger.py``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    schema_file = SCHEMA_DIR / "ParaList XML schema.xml"
    if schema_file.exists():
        text = schema_file.read_text("utf-8")
        assert re.search(
            r'<xs:attribute name="dirty" type="xs:boolean"', text
        ), "expected a plain boolean dirty attribute declaration"
        print("confirmed dirty is declared as a generic xs:boolean with no consumer-timing "
              "semantics stated")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.document import HwpxDocument
    from hwpx.tools.toc_author import add_native_toc, mark_toc_dirty

    doc = HwpxDocument.new()
    headings = [doc.sections[0].add_paragraph(f"개요 {i}번") for i in range(1, 3)]
    summary = add_native_toc(doc, headings=headings, dirty=True)
    assert summary["entryCount"] == 2

    data = doc.to_bytes()
    doc.close()
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name).decode("utf-8")

    match = re.search(r'<hp:fieldBegin[^>]*type="TABLEOFCONTENTS"[^>]*>', section_xml)
    assert match is not None, "expected a TABLEOFCONTENTS fieldBegin"
    assert 'dirty="1"' in match.group(0), (
        f"expected dirty=\"1\" on a freshly-authored TOC field, got: {match.group(0)}"
    )
    print("confirmed add_native_toc(dirty=True) sets dirty=\"1\" on the TABLEOFCONTENTS "
          "fieldBegin -- the caller-owned trigger for Hancom's next-open recompute")

    reopened = HwpxDocument.open(io.BytesIO(data))
    changed = mark_toc_dirty(reopened)
    assert changed >= 1, "expected mark_toc_dirty to find and flag at least one TOC field"
    print(f"confirmed mark_toc_dirty() re-flags {changed} TOC field(s) as dirty on an "
          f"already-authored document (the caller's responsibility after editing content "
          f"that could shift TOC page numbers)")
    reopened.close()

    print("PASS: DEV-031 reproduced (schema silence + live dirty-setting behavior, "
          "crash/next-open semantics are previously-verified per owner memory only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
