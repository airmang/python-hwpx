#!/usr/bin/env python3
"""DEV-034 -- the comment/memo subsystem (``hp:memo``/``hp:memogroup``/
``hp:paraList``) is declared nowhere in the vendored schema, despite being
a well-attested real feature (Hancom's margin-comment "메모" tool).

Schema claim: none. All 7 vendored schema files parse cleanly with 0
declarations of ``memo``/``memogroup``/``paraList`` as element names
(``ParaListType`` -- the *type* -- does exist in the schema, but the
lowercase element name ``paraList`` that actually appears inside a real
memo body is never declared under that name).

Real-document measurement: the live 237-file element census
(``docs/coverage-ledger.json``) reports ``hp:memo``/``hp:memogroup``/
``hp:paraList`` each at 24/237 files (10.1%) -- comfortably above the
single-sample rarity this class of finding sometimes has (contrast
DEV-033/DEV-035, which currently have 0 corpus/census samples in this
checkout). Memo *render* fidelity itself has separate real-Hancom
verification history (owner memory ``s058-s059-progress.md``, the
``MemoShapeIDRef`` bug fix) -- this entry is about the subsystem's schema
invisibility, not its render correctness.

Our handling: ``memo.py`` already treats ``paraList`` as a valid memo-body
child alongside ``p`` (local-name matched, schema-unaware). This probe
exercises the real authoring API (``doc.notes.add_memo``) live and
confirms the full undeclared triple appears in the serialized output.

Run: ``python probes/dev034_memo_subsystem_undeclared.py``
"""

from __future__ import annotations

import io
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
        for name in ("memo", "memogroup", "paraList"):
            assert f'name="{name}"' not in schema_text, name
        print("confirmed memo/memogroup/paraList declared nowhere as element names in the "
              "7 vendored schema files")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.document import HwpxDocument

    # 7.0: python-hwpx writes a memo as Hangul 2024 saves it -- in the MEMO field's hp:subList, with
    # no hp:memogroup/hp:memo/hp:paraList (the undeclared triple is only read, from 6.x documents).
    doc = HwpxDocument.new()
    doc.notes.add_memo("메모 본문 텍스트", paragraph=doc.add_paragraph("메모가 달린 문단"))
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(n for n in archive.namelist() if n.startswith("Contents/section"))
        section_xml = archive.read(name).decode("utf-8")

    for literal in ("<hp:memo ", "<hp:memogroup", "<hp:paraList"):
        assert literal not in section_xml, f"{literal!r} written: 7.0 keeps a memo only in its field"
    assert 'type="MEMO"' in section_xml and "메모 본문 텍스트" in section_xml
    print("confirmed doc.notes.add_memo() writes the memo in its MEMO field only (no undeclared triple)")

    fixture = ROOT / "tests" / "fixtures" / "fuzz_regressions" / "seed-000000-baseline.hwpx"
    if fixture.exists():
        legacy = HwpxDocument.open(fixture)  # a document holding the triple (6.x form) still reads
        assert any(memo.text for memo in legacy.notes.memos)
        print("confirmed a document holding hp:memogroup/hp:memo/hp:paraList still reads its memos")

    print("PASS: DEV-034 (schema absence; 7.0 writes no undeclared memo element, reads them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
