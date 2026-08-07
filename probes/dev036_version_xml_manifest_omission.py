#!/usr/bin/env python3
"""DEV-036 -- real Hancom output (and our own writer) never lists
``version.xml`` in either OPC manifest file (``Contents/content.hpf`` or
``META-INF/manifest.xml``); the part exists at a fixed, purely
conventional path instead. Complements DEV-015, which already registered
``version.xml``'s *root element name and attribute-spelling* drift
(``hv:HCFVersion`` / ``tagetApplication``) -- this entry is the separate
*manifest-listing* fact about the same file, not a duplicate.

Schema/OPC claim: package manifest conventions ordinarily list every part
so a reader can discover it; nothing here is an OWPML element, but it is
an adjacent packaging contract our own ``opc/package.py`` already has to
reconcile.

Real-document measurement: live, reproducible in this checkout without a
corpus sample -- our own ``HwpxDocument.new()`` output already omits
``version.xml`` from both ``Contents/content.hpf`` and
``META-INF/manifest.xml`` while the file itself is present as a real zip
entry, mirroring real Hancom output per ``opc/package.py``'s own comment
(see below).

Our handling: ``opc/package.py``'s ``version_path()`` falls back to the
fixed ``VERSION_PATH`` constant when the manifest lookup comes back empty,
with an in-code comment stating this is the normal (not warning-worthy)
case because "실제 한컴 산출물은 version.xml을 manifest에 선언하지 않고
고정 경로로 둔다" (real Hancom output does not declare version.xml in the
manifest, using a fixed path instead) -- logged at debug level rather than
warning, precisely because this is expected, not an error condition.

Run: ``python probes/dev036_version_xml_manifest_omission.py``
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        assert "version.xml" in names, "expected version.xml to exist as a real zip entry"
        hpf = archive.read("Contents/content.hpf").decode("utf-8")
        manifest = archive.read("META-INF/manifest.xml").decode("utf-8")

    assert "version.xml" not in hpf, (
        "expected content.hpf to omit version.xml -- if this fails, our writer now lists "
        "it and this deviation may no longer apply"
    )
    assert "version.xml" not in manifest, (
        "expected META-INF/manifest.xml to omit version.xml"
    )
    print("confirmed version.xml exists as a real zip entry but is listed in neither "
          "Contents/content.hpf nor META-INF/manifest.xml -- matches opc/package.py's "
          "documented real-Hancom-output convention")

    from hwpx.opc.package import HwpxPackage

    package = HwpxPackage.open(io.BytesIO(data))
    resolved = package.version_path()
    assert resolved is not None, "expected version_path() to fall back to the fixed path"
    print(f"confirmed version_path() falls back to the fixed conventional path when the "
          f"manifest lookup is empty: {resolved!r}")

    print("PASS: DEV-036 reproduced (live packaging output; complements DEV-015's "
          "root-name/typo finding about the same file, not a duplicate of it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
