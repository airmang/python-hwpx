#!/usr/bin/env python3
"""DEV-004 — settings.xml has no vendored OWPML schema; its config-item
vocabulary is OASIS ODF 1.0, not a Hancom-authored schema.

Schema claim: none. ``DevDoc/OWPML SCHEMA/`` vendors 7 XSD files (Header,
Body, Core, Document History, MasterPage, ParaList, Version) — there is no
Settings schema. The completeness audit's census (§3-C1) independently
flagged this as a "census blind spot": the ``ha:`` namespace fell entirely
outside the modelled population.

Real-document measurement: ``settings.xml`` (``ha:HWPApplicationSetting``)
is present in 100% of the reachable corpus. Its ``config:config-item-set``/
``config:config-item`` children are declared under
``urn:oasis:names:tc:opendocument:xmlns:config:1.0`` — the *OASIS
OpenDocument Format 1.0* config schema, verbatim, not a Hancom-private
vocabulary.

Our handling: ``hwpx.oxml.settings`` was reverse-engineered directly from
177 real files (no schema to check against) — ``ApplicationSettings``,
``CaretPosition``, ``ConfigItem``/``ConfigItemSet`` preserve whatever
config-item-set/item names and types actually appear rather than
hard-coding the one observed set (``PrintInfo``).

Run: ``python probes/dev004_settings_xml_no_schema.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    schema_dir = ROOT / "DevDoc" / "OWPML SCHEMA"
    schema_files = sorted(p.name for p in schema_dir.glob("*.xml"))
    print(f"vendored OWPML schema files: {schema_files}")
    assert not any("settings" in name.lower() for name in schema_files), (
        "expected no vendored Settings schema"
    )

    fixture = ROOT / "tests/fixtures/hwpxlib_corpus/error__20251107__test.hwpx"
    if not fixture.exists():
        print(f"SKIP: evidence file not present locally: {fixture}")
        return 0

    data = zipfile.ZipFile(fixture).read("settings.xml")
    assert b"urn:oasis:names:tc:opendocument:xmlns:config:1.0" in data, (
        "expected the OASIS ODF config namespace in settings.xml"
    )
    print("real settings.xml declares xmlns:config=\"urn:oasis:names:tc:opendocument:xmlns:config:1.0\"")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.open(str(fixture))
    model = doc.parts.settings.to_model()
    doc.close()
    assert model.caret_position is not None
    assert "PrintInfo" in model.config_item_sets
    print(f"our model: caret_position={model.caret_position}, config sets={list(model.config_item_sets)}")
    print("PASS: DEV-004 reproduced (real evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
