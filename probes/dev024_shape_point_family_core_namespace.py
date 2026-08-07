#!/usr/bin/env python3
"""DEV-024 -- the whole shape-coordinate family (``pt0``-``pt3``, ``center``/
``ax1``/``ax2``, ``start1``/``end1``/``start2``/``end2``) is locally declared
inside the ``hp:``-targeted schema file but always serializes as ``hc:`` in
real output and in our own writer -- DEV-012 already registered this split
for ``startPt``/``endPt`` specifically (``hp:line`` vs ``hp:connectLine``);
this entry generalizes it to the rest of the coordinate family that DEV-012
does not cover (rectangle corners, ellipse/arc centers and sweep points).

Schema claim: ``ParaList XML schema.xml`` declares its own
``targetNamespace`` as the 2024 paragraph (``hp``) namespace (line 5), yet
``pt0``/``pt1``/``pt2``/``pt3`` (rectangle corners, e.g. lines 2275/2387),
``center``/``ax1``/``ax2`` (ellipse/arc, e.g. lines 2400-2401/2426-2427) are
all declared with ``type="hc:PointType"`` -- borrowing the *type* from the
core (``hc``) namespace while the *element declaration* itself lives in the
``hp``-targeted schema file. XML Schema element/type namespaces are
independent: a locally-declared element takes its own file's target
namespace regardless of which namespace its type comes from, so the
formally correct serialization per the schema is ``hp:pt0`` etc.

Real-document measurement: real output uses ``hc:`` for this whole family,
not ``hp:``. Vendored-corpus grep across all 47 files: ``hc:pt0`` appears
195 times across 17 files, 0 occurrences of ``hp:pt0``.

Our handling: ``objects.py``'s ``_SHAPE_POINT_LOCAL_NAMES`` frozenset and
the geometry writers that use it already match by local name only
(namespace-agnostic), so this schema/reality split was already absorbed
before this probe existed -- this entry documents *why* that design choice
is correct, and extends the write-side confirmation to shapes beyond line/
connectLine (rectangle, ellipse).

Run: ``python probes/dev024_shape_point_family_core_namespace.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    schema_file = SCHEMA_DIR / "ParaList XML schema.xml"
    if schema_file.exists():
        text = schema_file.read_text("utf-8")
        assert 'targetNamespace="http://www.owpml.org/owpml/2024/paragraph"' in text
        for local_name in ("pt0", "pt1", "pt2", "pt3", "center", "ax1", "ax2"):
            assert f'name="{local_name}" type="hc:PointType"' in text, local_name
        print("confirmed pt0/pt1/pt2/pt3/center/ax1/ax2 are all declared locally in the "
              "hp-targeted schema file with type=\"hc:PointType\" (type borrowed from core, "
              "declaration itself scoped to hp)")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    if not CORPUS.exists() or not any(CORPUS.glob("*.hwpx")):
        print("SKIP: vendored hwpxlib corpus not found")
        return 0

    hc_hits = 0
    hp_hits = 0
    files_with_hc = set()
    for path in sorted(CORPUS.glob("*.hwpx")):
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith(".xml"):
                        continue
                    data = archive.read(name)
                    c = data.count(b"<hc:pt0")
                    if c:
                        hc_hits += c
                        files_with_hc.add(path.name)
                    hp_hits += data.count(b"<hp:pt0")
        except zipfile.BadZipFile:
            continue

    assert hc_hits > 0, "expected at least one real <hc:pt0 occurrence"
    assert hp_hits == 0, f"expected zero <hp:pt0 occurrences, found {hp_hits}"
    print(f"confirmed {hc_hits} real <hc:pt0 occurrences across {len(files_with_hc)} vendored "
          f"files, 0 <hp:pt0 occurrences")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.shapes.add_rectangle(width=10000, height=8000)
    doc.shapes.add_ellipse(width=10000, height=8000)
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name)

    for literal in (b"<hc:pt0", b"<hc:center", b"<hc:ax1"):
        assert literal in section_xml, f"expected {literal!r} in our own serialized output"
    for literal in (b"<hp:pt0", b"<hp:center", b"<hp:ax1"):
        assert literal not in section_xml, f"did not expect {literal!r} in our serialized output"
    print("confirmed our own rectangle/ellipse writer emits hc: for pt0/center/ax1 "
          "(matches real Hancom output, not the schema's formal hp: answer)")

    print("PASS: DEV-024 reproduced (schema + vendored corpus + live writer evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
