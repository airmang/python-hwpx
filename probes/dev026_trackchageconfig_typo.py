#!/usr/bin/env python3
"""DEV-026 -- ``hh:trackchangeConfig`` (correct spelling) is schema-only;
real documents and our own writer emit ``hh:trackchageConfig`` (the ``n``
dropped), the same typo-replication class as DEV-004/DEV-009/DEV-017 but
for a different subsystem (change-tracking configuration).

Schema claim: ``Header XML schema.xml`` declares ``<xs:element
name="trackchangeConfig">`` (correct spelling).

Real-document measurement: vendored-corpus grep across all 47 files finds
``trackchageConfig`` (typo) 47 times across 46 files, 0 occurrences of the
schema's correct spelling.

Our handling: ``header_part.py`` deliberately emits the typo
(``f"{_HH}trackchageConfig"``) for real-world compatibility, while
``header.py``/``header_part.py``'s readers defensively accept both
spellings (``name in {"trackchageConfig", "trackchangeConfig"}``) so a
hand-fixed or third-party document using the schema's correct spelling
still parses.

Run: ``python probes/dev026_trackchageconfig_typo.py``
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
    schema_file = SCHEMA_DIR / "Header XML schema.xml"
    if schema_file.exists():
        text = schema_file.read_text("utf-8")
        assert '<xs:element name="trackchangeConfig">' in text
        print("confirmed the schema declares the correctly-spelled trackchangeConfig")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    if CORPUS.exists() and any(CORPUS.glob("*.hwpx")):
        typo_hits = 0
        correct_hits = 0
        files_with_typo = set()
        for path in sorted(CORPUS.glob("*.hwpx")):
            try:
                with zipfile.ZipFile(path) as archive:
                    name = next((n for n in archive.namelist() if n.endswith("header.xml")), None)
                    if name is None:
                        continue
                    data = archive.read(name)
            except zipfile.BadZipFile:
                continue
            c = data.count(b"trackchageConfig")
            if c:
                typo_hits += c
                files_with_typo.add(path.name)
            correct_hits += data.count(b"trackchangeConfig")

        assert typo_hits > 0
        assert correct_hits == 0, f"expected zero correct-spelling occurrences, found {correct_hits}"
        print(f"confirmed {typo_hits} real trackchageConfig (typo) occurrences across "
              f"{len(files_with_typo)} vendored files, 0 correctly-spelled occurrences")
    else:
        print("SKIP: vendored hwpxlib corpus not found")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        header_xml = archive.read("Contents/header.xml").decode("utf-8")

    assert "trackchageConfig" in header_xml
    assert "trackchangeConfig" not in header_xml
    print("confirmed our own new-document writer emits the typo spelling, matching real "
          "Hancom output rather than the schema's correct spelling")

    print("PASS: DEV-026 reproduced (schema + vendored corpus + live writer evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
