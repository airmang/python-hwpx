#!/usr/bin/env python3
"""DEV-020 -- ``hh:compatibleDocument``/``hh:layoutCompatibility``/
``hh:docOption`` declare a wide schema vocabulary that real Hancom output
only ever exercises a narrow slice of.

Schema claim: ``Header XML schema.xml`` declares ``hh:layoutCompatibility``
with 48 named boolean flag children (``applyFontWeightToBold``,
``useInnerUnderline``, ...) any subset of which may appear, and
``hh:compatibleDocument/@targetProgram`` as an unconstrained string
attribute (no enumeration). ``hh:docOption/hh:linkinfo`` declares ``path``
as an unconstrained string attribute for a master-document link target.

Real-document measurement (47-file vendored corpus, reconfirmed
independently of cycle 6.1's original read-model finding as part of cycle
6.6 train 23's write-side work): ``targetProgram`` is ``"HWP201X"`` in
47/47 files, no other value ever observed. ``layoutCompatibility`` has zero
flag children in 47/47 files despite the 48-name schema vocabulary.
``linkinfo/@path`` is the empty string in 47/47 files. Only
``linkinfo/@pageInherit`` genuinely varies (8/47 ``"1"``, 39/47 ``"0"``) --
the one place in this whole settings group where real documents actually
diverge from each other. All boolean attributes here use the ``"0"``/
``"1"`` convention, not ``"true"``/``"false"`` (0 occurrences across 47
files) -- the same convention DEV-006 already established for
``hh:font``/``hh:tabPr``.

This is not a defect: it is the same "schema declares a wide vocabulary,
real Hancom output exercises a narrow slice" shape DEV-005
(``hh:layoutCompatibility`` itself, from the read-model side) already
registered -- this entry adds the *write*-side confirmation (cycle 6.6
train 23's ``oxml/header_compat.py`` setters) plus the two sibling
elements (``compatibleDocument``, ``docOption/linkinfo``) DEV-005 did not
cover.

Run: ``python probes/dev020_document_options_schema_wide_real_narrow.py``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lxml import etree  # noqa: E402

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    fixtures = sorted(CORPUS.glob("*.hwpx"))
    if not fixtures:
        print("SKIP: no vendored hwpxlib corpus files found")
        return 0

    target_programs: dict[str, int] = {}
    layout_compat_flag_counts: dict[int, int] = {}
    link_paths: dict[str, int] = {}
    page_inherit_values: dict[str | None, int] = {}
    footnote_inherit_values: dict[str | None, int] = {}
    boolean_attr_values: set[str] = set()

    for path in fixtures:
        try:
            with zipfile.ZipFile(path) as archive:
                names = [n for n in archive.namelist() if n.endswith("header.xml")]
                if not names:
                    continue
                root = etree.fromstring(archive.read(names[0]))
        except (zipfile.BadZipFile, KeyError):
            continue

        for compatible_document in root.iter(f"{{{HH_NS}}}compatibleDocument"):
            target_program = compatible_document.get("targetProgram")
            target_programs[target_program] = target_programs.get(target_program, 0) + 1
        for layout_compatibility in root.iter(f"{{{HH_NS}}}layoutCompatibility"):
            count = len(layout_compatibility)
            layout_compat_flag_counts[count] = layout_compat_flag_counts.get(count, 0) + 1
        for link_info in root.iter(f"{{{HH_NS}}}linkinfo"):
            link_paths[link_info.get("path", "")] = link_paths.get(link_info.get("path", ""), 0) + 1
            page_inherit_values[link_info.get("pageInherit")] = (
                page_inherit_values.get(link_info.get("pageInherit"), 0) + 1
            )
            footnote_inherit_values[link_info.get("footnoteInherit")] = (
                footnote_inherit_values.get(link_info.get("footnoteInherit"), 0) + 1
            )
            for value in (link_info.get("pageInherit"), link_info.get("footnoteInherit")):
                if value is not None:
                    boolean_attr_values.add(value)

    print(f"compatibleDocument targetProgram distribution: {target_programs}")
    print(f"layoutCompatibility flag-count distribution: {layout_compat_flag_counts}")
    print(f"linkinfo path distribution (keys are path values): {link_paths}")
    print(f"linkinfo pageInherit distribution: {page_inherit_values}")
    print(f"linkinfo footnoteInherit distribution: {footnote_inherit_values}")

    assert target_programs == {"HWP201X": 47}, target_programs
    assert layout_compat_flag_counts == {0: 47}, layout_compat_flag_counts
    assert link_paths == {"": 47}, link_paths
    assert set(page_inherit_values) == {"0", "1"} and len(page_inherit_values) == 2, (
        "expected pageInherit to be the one attribute in this group that genuinely "
        f"varies -- got {page_inherit_values}"
    )
    assert footnote_inherit_values == {"0": 47}, footnote_inherit_values
    assert boolean_attr_values <= {"0", "1"}, (
        f"expected only the 0/1 convention (DEV-006), found: {boolean_attr_values}"
    )
    print("confirmed: targetProgram single-valued, layoutCompatibility always empty, "
          "linkinfo path always empty, pageInherit the sole varying attribute, "
          "booleans use the 0/1 convention")

    schema_files = sorted(SCHEMA_DIR.glob("*.xml"))
    if schema_files:
        schema_text = "\n".join(p.read_text("utf-8") for p in schema_files)
        # Spot-check a handful of the 48 declared flag names to confirm the
        # schema really does declare a wide vocabulary real output ignores.
        for flag_name in (
            "applyFontWeightToBold",
            "useInnerUnderline",
            "doNotApplyImageEffect",
            "doNotApplyShapeComment",
        ):
            assert f'name="{flag_name}"' in schema_text, flag_name
        print("confirmed the schema declares (at least) 4 spot-checked layoutCompatibility "
              "flag names, none of which appear in any real document")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.oxml.header_compat import (
        set_compatible_document_target_program,
        set_doc_option_link_info,
        set_layout_compatibility_flags,
    )
    from hwpx.oxml.header_part import HwpxOxmlHeader
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(CORPUS / "tool__blank.hwpx") as archive:
        header_xml = archive.read(next(n for n in archive.namelist() if n.endswith("header.xml")))
    stdlib_root = ET.fromstring(header_xml)
    header = HwpxOxmlHeader("header.xml", stdlib_root)

    set_compatible_document_target_program(header, "HWP201X")
    set_layout_compatibility_flags(header, [])
    set_doc_option_link_info(header, path="", page_inherit=True, footnote_inherit=False)

    compatible_document = stdlib_root.find(f"{{{HH_NS}}}compatibleDocument")
    assert compatible_document is not None and compatible_document.get("targetProgram") == "HWP201X"
    link_info = stdlib_root.find(f"{{{HH_NS}}}docOption/{{{HH_NS}}}linkinfo")
    assert link_info is not None and link_info.get("pageInherit") == "1"
    print("confirmed the cycle 6.6 train 23 write surface reproduces the corpus-locked "
          "contract on a real fixture's live tree")

    print("PASS: DEV-020 reproduced (vendored evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
