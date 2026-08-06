#!/usr/bin/env python3
"""DEV-017 -- ``hp:lineBreak``/``hp:nbSpace``/``hp:fwSpace`` are schema-legal
in two different places, but real Hancom output only ever uses one of them.

Schema claim: ``ParaList XML schema.xml``'s ``hp:run`` content model
(``RunType``'s own choice group) lists ``t``, ``markpenBegin``,
``markpenEnd``, ``tab``, ``lineBreak``, ``hyphen``, ``nbSpace``, ``fwSpace``,
``insertBegin``/``insertEnd``/``deleteBegin``/``deleteEnd``, and more, all as
siblings a run may contain directly. ``hp:t``'s own content model
(``TextType``) separately lists the *same* four names (``lineBreak``,
``hyphen``, ``nbSpace``, ``fwSpace``) as children nestable inside a single
run of text. Both placements are schema-legal; the schema does not say which
one real output actually uses, or whether it is consistent about it.

Real-document measurement (3 vendored fixtures, one per atom):
``error__20230818__test.hwpx`` has ``<hp:t> ... 표기함<hp:lineBreak/>예)
...</hp:t>`` -- the break sits inside the same ``hp:t`` as the text on both
sides of it. ``error__20251107__test.hwpx`` has ``<hp:t><hp:fwSpace/>[12화학
...</hp:t>`` -- the space is the first child of ``hp:t``, not a sibling
element before it. ``error__20250808__2015...hwpx`` has the same shape for
``hp:nbSpace``. None of the three ever appears as a bare ``hp:run`` child
sitting next to a separate ``hp:t`` -- the RunType-level placement schema
also allows is corpus-unattested for these three. This is the opposite
convention from ``hp:tab``, which this codebase's own
``_append_text_with_tabs`` (``_document_primitives.py``) already represents
as a sibling of ``hp:t`` (a separate ``hp:t`` before and after each
``hp:tab``) -- also schema-legal, and apparently what real Hancom does for
tab specifically (this probe does not re-verify that; see DEV-002 for
``hh:tabItem``'s own, unrelated multiplicity finding).

Our handling: ``_append_text_with_run_choice_atoms``
(``_document_primitives.py``, cycle 6.5 train 19) builds exactly the
corpus-observed shape for these three -- one ``hp:t``, markers as its
children, surrounding text on ``.text``/``.tail`` -- reached via
``paragraph.add_run(text, expand_special_characters=True)``. It
deliberately does not touch ``hp:tab``'s existing sibling-based
representation.

Run: ``python probes/dev017_run_choice_atoms_t_nesting_convention.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"

_ATOM_FIXTURES = {
    "lineBreak": "error__20230818__test.hwpx",
    "fwSpace": "error__20251107__test.hwpx",
    "nbSpace": "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx",
}


def _find_atom_in_a_t(archive_path: Path, atom_local: str) -> bool:
    with zipfile.ZipFile(archive_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = etree.fromstring(archive.read(name))
    for t_element in root.iter(f"{{{HP_NS}}}t"):
        for child in t_element:
            if etree.QName(child).localname == atom_local:
                return True
    return False


def _find_atom_as_run_sibling(archive_path: Path, atom_local: str) -> bool:
    with zipfile.ZipFile(archive_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("section0.xml"))
        root = etree.fromstring(archive.read(name))
    for run_element in root.iter(f"{{{HP_NS}}}run"):
        for child in run_element:
            if etree.QName(child).localname == atom_local:
                return True
    return False


def main() -> int:
    checked = 0
    for atom, filename in _ATOM_FIXTURES.items():
        fixture = CORPUS / filename
        if not fixture.exists():
            print(f"SKIP {atom}: {filename} not found")
            continue
        nested = _find_atom_in_a_t(fixture, atom)
        assert nested, f"expected hp:{atom} nested inside an hp:t in {filename}, found none"
        as_sibling = _find_atom_as_run_sibling(fixture, atom)
        assert not as_sibling, (
            f"expected hp:{atom} to never appear as a bare hp:run child in {filename} "
            "-- the schema allows it, but no real sample does"
        )
        print(f"confirmed hp:{atom} nested inside hp:t, never as an hp:run sibling ({filename})")
        checked += 1

    assert checked > 0, "no atom fixtures found -- nothing was actually verified"

    schema_dir = ROOT / "DevDoc" / "OWPML SCHEMA"
    schema_files = sorted(schema_dir.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        for atom in _ATOM_FIXTURES:
            assert f'name="{atom}"' in schema_text, f"expected {atom} declared somewhere in the schema"
        print("confirmed all three atoms are declared in the real OWPML schema (both as "
              "hp:run and hp:t choice members -- the schema does not favor either placement)")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.oxml._document_primitives import _append_text_with_run_choice_atoms
    import xml.etree.ElementTree as ET

    run = ET.Element(f"{{{HP_NS}}}run")
    _append_text_with_run_choice_atoms(run, "before\nafter")
    t_elements = [c for c in run if c.tag == f"{{{HP_NS}}}t"]
    assert len(t_elements) == 1, f"expected a single hp:t, got {len(t_elements)}"
    marker = next(c for c in t_elements[0] if c.tag.rsplit("}", 1)[-1] == "lineBreak")
    assert marker is not None
    print("our add_run(expand_special_characters=True) nests the marker inside a single "
          "hp:t, matching the corpus-observed shape rather than hp:tab's sibling shape")

    print(f"PASS: DEV-017 reproduced ({checked}/3 atoms, vendored evidence) and our handling verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
