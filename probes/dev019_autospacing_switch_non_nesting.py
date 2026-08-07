#!/usr/bin/env python3
"""DEV-019 -- ``hh:autoSpacing`` never nests inside ``hp:switch``/``case``/
``default`` -- the exact opposite convention from its ``hh:paraPr`` siblings
``hh:margin``/``hh:lineSpacing`` (DEV-018).

Schema claim: ``ParaList XML schema.xml``'s ``ParaPrType`` sequence lists
``align``/``heading``/``breakSetting``/``autoSpacing``/``margin``/
``lineSpacing``/``border`` (plus more) as ordinary sibling children of
``hh:paraPr`` -- nothing in the schema treats ``autoSpacing`` any
differently from ``margin``/``lineSpacing`` in terms of where it may sit.

Real-document measurement (47-file vendored corpus): every one of the 1832
real ``hh:autoSpacing`` occurrences is a *direct* ``hh:paraPr`` child --
zero are nested inside a ``hp:switch``'s ``hp:case``/``hp:default`` branch.
This is the opposite of ``hh:margin``/``hh:lineSpacing``, which are
*always* found only inside ``hp:switch``'s branches in real output
(DEV-018) -- so within the very same ``hh:paraPr``, sibling schema
elements follow opposite version-compat-wrapping conventions. This was
discovered the hard way: cycle 6.6 train 23's first draft of
``apply_paragraph_auto_spacing`` (``oxml/header_compat.py``) assumed, by
analogy with margin/lineSpacing, that autoSpacing would also be
switch-wrapped in real documents -- checked directly before shipping, and
the assumption was wrong. The setter still walks descendants defensively
(matching the sibling setters' idiom at zero cost, and correctly finding
the direct child either way), but the module's docstring makes the
checked claim, not the wrong assumed one.

Run: ``python probes/dev019_autospacing_switch_non_nesting.py``
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


def main() -> int:
    fixtures = sorted(CORPUS.glob("*.hwpx"))
    if not fixtures:
        print("SKIP: no vendored hwpxlib corpus files found")
        return 0

    direct_auto_spacing = 0
    nested_auto_spacing = 0
    direct_margin = 0
    nested_margin = 0

    for path in fixtures:
        try:
            with zipfile.ZipFile(path) as archive:
                names = [n for n in archive.namelist() if n.endswith("header.xml")]
                if not names:
                    continue
                root = etree.fromstring(archive.read(names[0]))
        except (zipfile.BadZipFile, KeyError):
            continue

        for para_pr in root.iter(f"{{{HH_NS}}}paraPr"):
            direct_children = {etree.QName(c).localname for c in para_pr}
            if "autoSpacing" in direct_children:
                direct_auto_spacing += 1
            if "margin" in direct_children:
                direct_margin += 1

            switch = next(
                (c for c in para_pr if etree.QName(c).localname == "switch"), None
            )
            if switch is None:
                continue
            for branch in switch:
                branch_children = {etree.QName(c).localname for c in branch}
                if "autoSpacing" in branch_children:
                    nested_auto_spacing += 1
                if "margin" in branch_children:
                    nested_margin += 1

    print(
        f"autoSpacing: {direct_auto_spacing} direct paraPr children, "
        f"{nested_auto_spacing} nested in hp:switch branches"
    )
    print(
        f"margin: {direct_margin} direct paraPr children, "
        f"{nested_margin} nested in hp:switch branches"
    )

    assert direct_auto_spacing > 0, "expected real autoSpacing occurrences in the corpus"
    assert nested_auto_spacing == 0, (
        "expected zero switch-nested autoSpacing -- DEV-019's core claim no longer holds"
    )
    assert nested_margin > 0, (
        "expected real switch-nested margin occurrences (DEV-018's contract) -- "
        "if this is 0 the corpus fixture set changed and the contrast this probe "
        "demonstrates no longer has a real comparison point"
    )
    # DEV-018's own framing is 236/237 files (99.6%), not 237/237 -- a small
    # minority of real paraPr entries carry margin as a direct child with no
    # switch at all (e.g. error__20240626__no_manifest.hwpx). The contrast
    # this probe demonstrates is about the *dominant* convention, not an
    # absolute -- so this assert is a strong majority check, not ==0.
    assert nested_margin > direct_margin, (
        f"expected switch-nested margin ({nested_margin}) to dominate over direct-"
        f"child margin ({direct_margin}) -- if this flips, DEV-018's 'usually "
        "switch-wrapped' framing needs re-checking, not just this probe's assertion"
    )

    import xml.etree.ElementTree as ET

    from hwpx.oxml.header import parse_paragraph_property
    from hwpx.oxml.header_compat import apply_paragraph_auto_spacing
    from hwpx.oxml.header_part import HwpxOxmlHeader

    with zipfile.ZipFile(CORPUS / "tool__blank.hwpx") as archive:
        header_xml = archive.read(next(n for n in archive.namelist() if n.endswith("header.xml")))
    stdlib_root = ET.fromstring(header_xml)
    header = HwpxOxmlHeader("header.xml", stdlib_root)
    para_pr = next(stdlib_root.iter(f"{{{HH_NS}}}paraPr"))
    assert any(c.tag.rsplit("}", 1)[-1] == "switch" for c in para_pr), (
        "expected the fixture's first paraPr to carry hp:switch (margin/lineSpacing "
        "wrapped) so the setter is exercised on a genuinely mixed-convention paraPr"
    )

    apply_paragraph_auto_spacing(header, para_pr, e_asian_eng=True, e_asian_num=True)
    updated = parse_paragraph_property(para_pr)
    assert updated.auto_spacing is not None
    assert updated.auto_spacing.e_asian_eng is True
    assert updated.auto_spacing.e_asian_num is True
    auto_spacing_direct_children = {
        c.tag.rsplit("}", 1)[-1] for c in para_pr if c.tag.rsplit("}", 1)[-1] == "autoSpacing"
    }
    assert "autoSpacing" in auto_spacing_direct_children, (
        "expected the setter to place autoSpacing as a direct paraPr child, matching "
        "the real-corpus convention, not inside hp:switch"
    )
    print(
        "confirmed apply_paragraph_auto_spacing writes a direct paraPr child on a "
        "real switch-wrapped fixture, matching the observed convention"
    )

    print("PASS: DEV-019 reproduced (vendored evidence, real contrast with DEV-018)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
