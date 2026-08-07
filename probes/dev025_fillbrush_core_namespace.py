#!/usr/bin/env python3
"""DEV-025 -- ``fillBrush`` follows the same pattern as DEV-024's point
family: declared locally in *two different* schema files (``hp``'s and
``hh``'s own), yet real output and our own writer always use ``hc:``.

Schema claim: ``fillBrush`` is declared independently in both
``ParaList XML schema.xml`` (lines 1037 and 2350, ``type="hc:FillBrushType"``)
and ``Header XML schema.xml`` (line 471, same type) -- so the formally
"correct" prefix per each declaring file would be ``hp:fillBrush`` or
``hh:fillBrush`` depending on context, never ``hc:fillBrush``.

Real-document measurement: vendored-corpus grep across all 47 files finds
1592 ``<hc:fillBrush`` occurrences in every single file (47/47), 0
occurrences of ``<hp:fillBrush`` or ``<hh:fillBrush``.

Our handling: ``_document_primitives.py``'s fill-brush writer already
appends ``hc:fillBrush`` regardless of the parent element's own namespace
(the same DEV-024-class local-name-driven design, applied here
independently before this probe existed).

Run: ``python probes/dev025_fillbrush_core_namespace.py``
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    para_schema = SCHEMA_DIR / "ParaList XML schema.xml"
    head_schema = SCHEMA_DIR / "Header XML schema.xml"
    if para_schema.exists() and head_schema.exists():
        para_text = para_schema.read_text("utf-8")
        head_text = head_schema.read_text("utf-8")
        assert para_text.count('name="fillBrush" type="hc:FillBrushType"') >= 2, (
            "expected fillBrush declared at least twice in ParaList XML schema.xml"
        )
        assert 'name="fillBrush" type="hc:FillBrushType"' in head_text, (
            "expected fillBrush also declared independently in Header XML schema.xml"
        )
        print("confirmed fillBrush is declared locally in both ParaList XML schema.xml "
              "(2+ places) and Header XML schema.xml, each with type=\"hc:FillBrushType\"")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    if not CORPUS.exists() or not any(CORPUS.glob("*.hwpx")):
        print("SKIP: vendored hwpxlib corpus not found")
        return 0

    hc_hits = 0
    files_with_hc = set()
    hp_hh_hits = 0
    for path in sorted(CORPUS.glob("*.hwpx")):
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith(".xml"):
                        continue
                    data = archive.read(name)
                    c = data.count(b"<hc:fillBrush")
                    if c:
                        hc_hits += c
                        files_with_hc.add(path.name)
                    hp_hh_hits += data.count(b"<hp:fillBrush") + data.count(b"<hh:fillBrush")
        except zipfile.BadZipFile:
            continue

    assert hc_hits > 0
    assert hp_hh_hits == 0, f"expected zero hp:/hh:fillBrush occurrences, found {hp_hh_hits}"
    print(f"confirmed {hc_hits} real <hc:fillBrush occurrences across {len(files_with_hc)}/"
          f"{len(list(CORPUS.glob('*.hwpx')))} vendored files, 0 hp:/hh: occurrences")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.shapes.add_rectangle(width=10000, height=8000, fill_color="#ff0000")
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name).decode("utf-8")

    assert "<hc:fillBrush" in section_xml
    assert "<hp:fillBrush" not in section_xml and "<hh:fillBrush" not in section_xml
    print("confirmed our own filled-rectangle writer emits hc:fillBrush, matching real "
          "Hancom output rather than either schema file's formal answer")

    print("PASS: DEV-025 reproduced (schema + vendored corpus + live writer evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
