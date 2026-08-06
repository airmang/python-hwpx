#!/usr/bin/env python3
"""DEV-015 — ``version.xml``'s real root name, namespace, and a required
attribute's spelling all diverge from the vendored 2024-draft OWPML schema
— the same schema-vs-reality gap DEV-007 already found for masterpage.xml.

Schema claim: ``DevDoc/OWPML SCHEMA/Version XML schema.xml`` declares the
part root as a bare element named ``version`` (default namespace
``http://www.owpml.org/owpml/2024/version``), with a required attribute
``targetApplication`` (``WORDPROCESSOR``/``PRESENTATION``/``SPREADSHEET``).

Real-document measurement: every one of the 47 vendored corpus files' own
``version.xml`` has a root named ``hv:HCFVersion`` in a *different*
namespace (``http://www.hancom.co.kr/hwpml/2011/version``) — not the
schema's bare ``version``. Its required "target application" attribute is
present on all 47 files but spelled ``tagetApplication`` — missing the
first "r" of "target" — not the schema's ``targetApplication``. This is not
an isolated typo in one file; it is the verbatim, universal real-Hancom
attribute name.

Our handling: ``hwpx.oxml.version_part.parse_hcf_version``/``HcfVersion``
(``HwpxOxmlVersion.to_model()``, cycle 6.4 train 15) reads the real root
name (``HCFVersion``, matched by local name) and preserves the misspelled
attribute name verbatim as the dataclass field ``taget_application`` — it
does not "correct" the name back toward the schema's spelling, because
correcting it would only create a second gap between the field name and
what real documents actually carry.

Run: ``python probes/dev015_version_xml_root_and_spelling.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"
HV_NS = "http://www.hancom.co.kr/hwpml/2011/version"


def main() -> int:
    fixtures = sorted(CORPUS.glob("*.hwpx"))
    if not fixtures:
        print("SKIP: no vendored hwpxlib corpus files found")
        return 0

    roots_seen: set[str] = set()
    taget_seen = 0
    target_seen = 0
    for path in fixtures:
        with zipfile.ZipFile(path) as archive:
            data = archive.read("version.xml")
        root = etree.fromstring(data)
        roots_seen.add(root.tag)
        if root.get("tagetApplication") is not None:
            taget_seen += 1
        if root.get("targetApplication") is not None:
            target_seen += 1

    assert roots_seen == {f"{{{HV_NS}}}HCFVersion"}, (
        f"expected every version.xml root to be hv:HCFVersion, got {roots_seen}"
    )
    print(f"all {len(fixtures)} vendored version.xml roots are hv:HCFVersion (not the schema's bare 'version')")
    assert taget_seen == len(fixtures), f"expected tagetApplication on all {len(fixtures)} files, got {taget_seen}"
    assert target_seen == 0, f"expected the schema's correct spelling on 0 files, got {target_seen}"
    print(f"tagetApplication (typo, 'r' missing): {taget_seen}/{len(fixtures)} -- targetApplication (schema spelling): {target_seen}/{len(fixtures)}")

    schema_files = sorted(SCHEMA_DIR.glob("*.xml"))
    if schema_files:
        version_schema = SCHEMA_DIR / "Version XML schema.xml"
        if version_schema.exists():
            schema_text = version_schema.read_text("utf-8")
            assert '<xs:element name="version">' in schema_text
            assert "targetApplication" in schema_text
            assert "tagetApplication" not in schema_text
            assert "HCFVersion" not in schema_text
            print("confirmed against the real schema file: it declares root 'version' + 'targetApplication', neither of which real output uses")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    version = doc.parts.version
    assert version is not None
    model = version.to_model()
    assert model.taget_application == "WORDPROCESSOR"
    print(f"our to_model() preserves the real attribute name verbatim: taget_application={model.taget_application!r}")
    doc.close()

    print("PASS: DEV-015 reproduced (vendored evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
