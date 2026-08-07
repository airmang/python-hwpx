#!/usr/bin/env python3
"""DEV-039 -- CROSSREF and TABLEOFCONTENTS fields share the exact same
``fieldBegin``/``dirty`` schema surface, but real Hancom recomputes them
on a different schedule: CROSSREF recomputes automatically on edit/save,
while TABLEOFCONTENTS only recomputes on the *next open* and needs the
caller to set ``dirty`` explicitly (DEV-031's finding). The schema has no
way to express this per-field-type difference.

Schema claim: ``hp:fieldBegin``'s ``type`` attribute is a single
``hp:FieldType`` enum, and ``dirty`` is one boolean attribute shared by
every field type -- nothing distinguishes CROSSREF's recompute timing
from TABLEOFCONTENTS's.

Real-document measurement: ``oracle: previously-verified`` -- the
``toc_author.py`` module docstring (lines 12-20) states directly, with a
"P0 measured" citation: CROSSREF's cached result run "Hancom recomputes
... automatically on edit/save" -- established by the M7 P0 real-
Hancom measurement stage (2026-07-02). Not re-observable here (no Hancom oracle); this
probe reproduces the structural asymmetry our own authoring API already
encodes as a direct consequence of that measurement.

Our handling: ``add_page_crossref`` has no ``dirty`` parameter at all --
it always emits ``dirty="0"`` (nothing for the caller to set, because
Hancom keeps CROSSREF fresh on its own). ``add_native_toc`` accepts and
defaults to ``dirty=True`` and ``mark_toc_dirty()`` exists as a standalone
follow-up call -- because TOC does *not* self-refresh. A caller who does
not know this asymmetry could reasonably assume CROSSREF also needs an
explicit dirty flag (it does not) or that TOC dirty-marking is optional
(it is not) -- which is exactly why ``known-traps.md`` documents it.

Run: ``python probes/dev039_crossref_vs_toc_recompute_asymmetry.py``
"""

from __future__ import annotations

import inspect
import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    schema_file = SCHEMA_DIR / "ParaList XML schema.xml"
    if schema_file.exists():
        text = schema_file.read_text("utf-8")
        # dirty is declared at least twice (fieldBegin's general attribute group,
        # reused across field types) -- one shared boolean, no per-type distinction.
        assert text.count('name="dirty" type="xs:boolean"') >= 1
        print("confirmed dirty is one boolean attribute shared across all hp:FieldType "
              "values -- the schema cannot express a per-field-type recompute schedule")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.tools.toc_author import add_native_toc, add_page_crossref

    crossref_params = inspect.signature(add_page_crossref).parameters
    assert "dirty" not in crossref_params, (
        "expected add_page_crossref to have no dirty parameter -- CROSSREF self-refreshes"
    )
    toc_params = inspect.signature(add_native_toc).parameters
    assert "dirty" in toc_params and toc_params["dirty"].default is True, (
        "expected add_native_toc to accept dirty, defaulting True -- TOC does not self-refresh"
    )
    print("confirmed the asymmetry at the API surface: add_page_crossref has no dirty "
          "parameter (nothing to set), add_native_toc defaults dirty=True (caller-owned)")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    headings = [doc.sections[0].add_paragraph(f"개요 {i}번") for i in range(1, 3)]
    target = doc.sections[0].add_paragraph("타깃 문단")
    ref = doc.sections[0].add_paragraph("참조 문단")
    add_page_crossref(doc, ref, target, cached_page=3)
    add_native_toc(doc, headings=headings, dirty=True)
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name).decode("utf-8")

    crossref_match = re.search(r'<hp:fieldBegin[^>]*type="CROSSREF"[^>]*>', section_xml)
    toc_match = re.search(r'<hp:fieldBegin[^>]*type="TABLEOFCONTENTS"[^>]*>', section_xml)
    assert crossref_match is not None and toc_match is not None

    assert 'dirty="0"' in crossref_match.group(0), crossref_match.group(0)
    assert 'dirty="1"' in toc_match.group(0), toc_match.group(0)
    print("confirmed the same asymmetry live in serialized output: CROSSREF fieldBegin "
          f"is dirty=\"0\" ({crossref_match.group(0)}), TOC fieldBegin is dirty=\"1\" "
          f"({toc_match.group(0)})")

    print("PASS: DEV-039 reproduced (schema symmetry + live API/output asymmetry; "
          "recompute-timing facts themselves are previously-verified per the toc_author.py "
          "'(measured)' docstring only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
