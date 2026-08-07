#!/usr/bin/env python3
"""DEV-032 -- Hancom's TOC paragraph collection is not driven by an
"outline level" schema concept at all; it is keyed by ``styleIDRef`` and
the actual decision lives in a schema-opaque ``ContentsStyles:wstring:0:``
command parameter embedded in the TOC field's own parameter list.

Schema claim: ``hp:p`` carries both ``paraPrIDRef`` and ``styleIDRef`` as
plain attributes; ``hh:style`` merely references a ``paraPrIDRef``. Which
paragraphs a TOC "collects" on regeneration is not connected to any of
this by the schema -- and the parameter that actually encodes the answer
lives inside ``hp:parameters`` (``hp:ParameterList`` -- the same generic
name-value bag as DEV-016/DEV-037's CLICKHERE ``Command``), whose
individual parameter names and string-payload grammar are entirely
outside the schema's vocabulary.

Real-document measurement: ``oracle: previously-verified`` -- the "(measured)"
tagged docstring in ``toc_author.py``'s ``add_native_toc`` records that
Hancom collects outline-styled paragraphs *and*, via the
``ContentsStyles:wstring:0:`` command parameter, style-0 (바탕글/body
text) paragraphs too on regeneration -- unless the caller gives body text
a non-collected style. Whether style-0 paragraphs actually get pulled
into the TOC on a real regeneration is not re-observable here (no Hancom
oracle); this probe confirms the structural half -- that our own
authoring path emits exactly this command parameter.

Our handling: ``add_native_toc`` embeds the literal
``ContentsStyles:wstring:0:`` command segment in the TOC field's
``Command`` parameter (see also DEV-010's ``dirty``/recompute-timing
finding, which governs the same regeneration event this decision fires
inside of).

Run: ``python probes/dev032_toc_contentsstyles_collection_command.py``
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from hwpx.document import HwpxDocument
    from hwpx.tools.toc_author import add_native_toc

    doc = HwpxDocument.new()
    headings = [doc.sections[0].add_paragraph(f"개요 {i}번") for i in range(1, 3)]
    add_native_toc(doc, headings=headings)

    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name).decode("utf-8")

    assert "ContentsStyles:wstring:0:" in section_xml, (
        "expected the ContentsStyles:wstring:0: command segment in the TOC field's "
        "Command parameter"
    )
    match = re.search(r'name="Command"[^>]*>([^<]*ContentsStyles:wstring:0:[^<]*)<', section_xml)
    assert match is not None
    print(f"confirmed our TOC field's Command parameter carries the schema-opaque "
          f"ContentsStyles:wstring:0: collection directive: ...{match.group(1)[-60:]!r}")

    print("PASS: DEV-032 reproduced (live authoring output; regeneration-time collection "
          "behavior is previously-verified per the toc_author.py '(measured)' docstring only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
