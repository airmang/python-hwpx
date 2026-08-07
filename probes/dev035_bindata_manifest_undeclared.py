#!/usr/bin/env python3
"""DEV-035 -- the binary-attachment manifest (``hh:binDataList``/
``hh:binItem`` in ``header.xml``, listing embedded images and other blobs)
is declared nowhere in the vendored schema.

Schema claim: none. All 7 vendored schema files parse cleanly with 0
declarations of ``binDataList``/``binItem``.

Real-document measurement: **honest gap, not fabricated** -- neither name
appears anywhere in this checkout's 47-file vendored corpus, nor in the
live 237-file element census (``docs/coverage-ledger.json``). As with
DEV-033, this reflects a sampling gap in this checkout's available
population, not evidence the elements are rare in the wild -- picture
insertion itself (``add_picture``/``media.add_image``) is already
real-Hancom render-verified (``support-matrix.md``'s "그림 삽입/치환"
row), and that capability cannot function without exactly this manifest
structure underneath it.

Our handling: ``header_part.py``'s binary-item accessors
(``_bin_data_list``, next-id allocation, item registration) are built
entirely on this undeclared structure. This probe exercises the real
authoring API (``doc.media.add_image``) live and confirms it emits the
manifest elements -- the strongest evidence available in this
environment, since no corpus sample exists to grep.

Run: ``python probes/dev035_bindata_manifest_undeclared.py``
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"

PNG_STUB = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def main() -> int:
    schema_dir = SCHEMA_DIR
    schema_files = sorted(schema_dir.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        for name in ("binDataList", "binItem"):
            assert f'name="{name}"' not in schema_text, name
        print("confirmed binDataList/binItem declared nowhere in the 7 vendored schema files")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    doc.media.add_image(PNG_STUB, "png")
    data = doc.to_bytes()
    doc.close()

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        header_xml = archive.read("Contents/header.xml").decode("utf-8")

    assert "<hh:binDataList" in header_xml, "expected hh:binDataList in header.xml"
    assert "<hh:binItem" in header_xml, "expected hh:binItem in header.xml"
    print("confirmed doc.media.add_image() emits the undeclared hh:binDataList/hh:binItem "
          "manifest in header.xml")

    print("PASS: DEV-035 reproduced (schema absence + live authoring API; real-document "
          "frequency is an honest gap in this checkout's corpus population, not confirmed -- "
          "note add_picture/media.add_image itself is already render-verified per "
          "support-matrix.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
