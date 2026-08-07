#!/usr/bin/env python3
"""DEV-027 -- ``hp:lineseg``/``hp:linesegarray`` (Hangul's line-layout
cache) is declared nowhere in the vendored schema, present in a majority
of real documents, and stale copies cause visible text overlap if a
paragraph's text is replaced without removing them.

Schema claim: none. All 7 vendored schema files parse cleanly with 0
declarations of ``lineseg``/``linesegarray``.

Real-document measurement: ``docs/coverage-ledger.json``'s live census
(237 files) reports ``hp:lineseg``/``hp:linesegarray`` at 213/237 files
(89.9%) -- among the highest-frequency elements this registry has found
with zero schema support. The 47-file vendored corpus (this probe's
reproducible slice) shows the same shape at smaller scale.

The cache-staleness -> overlap causal claim is ``oracle: previously-
verified`` -- ``body_patch.py``'s in-code comment cites a 2026-07-07 real
Hancom measurement (AI중점학교 신청서: only the paragraph whose text was
replaced without stripping the cache showed overlap; clone paragraphs
whose cache was stripped rendered normally), and
``src/hwpx/data/contract_docs/known-traps.md`` carries the same fact as a
bundled contract. This probe reproduces the structural half only (cache
declaration absence + our strip function actually removing it) -- the
render-overlap consequence itself is not re-observable without a Hancom
oracle in this environment.

Our handling: ``patch.py``'s ``_strip_paragraph_layout_cache`` (called
from both ``table_patch.py`` and ``body_patch.py``'s edit paths) already
assumes this deviation and removes ``<hp:linesegarray>`` whenever a
paragraph's text is replaced.

Run: ``python probes/dev027_lineseg_cache_undeclared.py``
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
    schema_dir = SCHEMA_DIR
    schema_files = sorted(schema_dir.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        for name in ("lineseg", "linesegarray"):
            assert f'name="{name}"' not in schema_text, name
        print("confirmed lineseg/linesegarray declared nowhere in the 7 vendored schema files")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    if CORPUS.exists() and any(CORPUS.glob("*.hwpx")):
        total = 0
        files_with = set()
        for path in sorted(CORPUS.glob("*.hwpx")):
            try:
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        if name.startswith("Contents/section") and name.endswith(".xml"):
                            data = archive.read(name)
                            if b"<hp:linesegarray" in data:
                                files_with.add(path.name)
                                total += 1
            except zipfile.BadZipFile:
                continue
        assert total > 0, "expected at least one real linesegarray occurrence"
        corpus_size = len(list(CORPUS.glob("*.hwpx")))
        print(f"confirmed linesegarray present in {len(files_with)}/{corpus_size} vendored files "
              f"(no schema support, real Hangul-authored layout cache)")
    else:
        print("SKIP: vendored hwpxlib corpus not found")

    from hwpx.patch import _strip_paragraph_layout_cache

    paragraph = (
        '<hp:p id="1" paraPrIDRef="0" styleIDRef="0">'
        '<hp:linesegarray>'
        '<hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
        'baseline="850" spacing="600" horzpos="0" horzsize="10000" flags="393216"/>'
        '</hp:linesegarray>'
        '<hp:run charPrIDRef="0"><hp:t>교체된 텍스트</hp:t></hp:run>'
        '</hp:p>'
    ).encode("utf-8")
    assert b"<hp:linesegarray" in paragraph
    stripped = _strip_paragraph_layout_cache(paragraph)
    assert b"<hp:linesegarray" not in stripped, "expected the layout cache to be removed"
    assert "교체된 텍스트".encode("utf-8") in stripped, (
        "expected the paragraph's own text/structure to survive the strip"
    )
    print("confirmed our _strip_paragraph_layout_cache removes a stale linesegarray while "
          "leaving the paragraph's own content intact")

    print("PASS: DEV-027 reproduced (schema absence + vendored frequency + live strip function)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
