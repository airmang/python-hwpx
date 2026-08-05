#!/usr/bin/env python3
"""DEV-009 — ``hh:memoPr`` id numbering and ``memoType`` spelling conventions.

Schema claim (id numbering): the schema declares ``hh:memoPr/@id`` as
``xs:nonNegativeInteger`` (``0`` is a legal value) with no stated starting
convention. Reusing ``hh:borderFill``'s own id-allocation habit (0-based —
its first id is ``"0"``) would be a reasonable-looking default.

Schema claim (spelling): ``hh:memoPr/@memoType``'s enumeration
(``Header XML schema.xml:1740-1752``) literally declares the value
``"NOMAL"`` — not ``"NORMAL"``. This reads as a vendor typo baked into the
format itself, not a transcription error in our schema copy.

Real-document measurement: every ``hh:memoPr`` in the vendored corpus
starts numbering at ``id="1"`` — ``id="0"`` is never observed, unlike
``hh:borderFill``'s 0-based sequence. Every ``memoType`` value present is
the literal ``"NOMAL"`` (never ``"NORMAL"``, matching the schema's own
spelling). A resaved variant of the same source
(``error__20251107__test_re.hwpx``) drops ``memoType`` from both of its
``hh:memoPr`` entries entirely on the round trip — corroborating DEV-010's
finding that this specific resave loses attributes, not fabricates them.

Our handling: ``_document_primitives._allocate_memo_shape_id`` starts
numbering at ``1`` (explicitly *not* reusing
``_allocate_border_fill_id``'s 0-based logic), and
``_normalize_memo_shape_spec``'s ``memo_type`` default is ``"NOMAL"``
verbatim — the schema's spelling, preserved rather than "corrected"
(cycle-6.2 train 8).

Run: ``python probes/dev009_memopr_id_and_spelling_conventions.py``
"""

from __future__ import annotations

import glob
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"


def main() -> int:
    fixtures = sorted(glob.glob(str(ROOT / "tests/fixtures/*/*.hwpx")))
    if not fixtures:
        print("SKIP: no vendored corpus files found")
        return 0

    ids: set[str | None] = set()
    memo_types: set[str | None] = set()
    total = 0
    files_with_memopr: set[str] = set()

    for path in fixtures:
        try:
            with zipfile.ZipFile(path) as archive:
                try:
                    data = archive.read("Contents/header.xml")
                except KeyError:
                    continue
                root = etree.fromstring(data)
                for element in root.iter(f"{{{HH_NS}}}memoPr"):
                    total += 1
                    files_with_memopr.add(path)
                    ids.add(element.get("id"))
                    memo_types.add(element.get("memoType"))
        except (zipfile.BadZipFile, KeyError):
            continue

    print(f"hh:memoPr found in {len(files_with_memopr)} file(s), {total} element(s) total")
    print(f"id values observed: {sorted(ids, key=lambda v: int(v) if v else -1)}")
    print(f"memoType values observed: {memo_types}")
    if total == 0:
        print("SKIP: no hh:memoPr instances in the local vendored corpus")
        return 0
    assert "0" not in ids, "expected hh:memoPr id numbering to never start at 0"
    assert memo_types <= {"NOMAL", None}, "expected only the schema's own 'NOMAL' spelling"

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    first_id = doc.styles.ensure_memo_shape()
    assert first_id == "1", f"expected our first allocated memoPr id to be '1', got {first_id!r}"
    shape = doc.styles.memo_shapes[first_id]
    assert shape.memo_type == "NOMAL", "expected our default memo_type to preserve the schema spelling"
    doc.close()
    print("our authoring matches: memoPr ids start at 1, memoType defaults to 'NOMAL'")
    print("PASS: DEV-009 reproduced (vendored evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
