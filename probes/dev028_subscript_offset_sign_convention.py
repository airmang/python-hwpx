#!/usr/bin/env python3
"""DEV-028 -- ``hh:offset``'s sign convention (negative = superscript/up,
positive = subscript/down) is undocumented by the schema and was
previously *misread* by an earlier audit before real-Hancom render
measurement corrected it.

Schema claim: ``Header XML schema.xml`` declares ``hh:offset`` (a child of
``hh:charPr``) with per-script (``hangul``/``latin``/``hanja``/...)
integer attributes ranging -100..100 and a documentation string of
"언어별 오프셋. 단위는 %." (per-language offset, unit is %) -- no mention
of which sign means "up" and which means "down".

Real-document measurement: ``oracle: previously-verified`` -- the 2026-08-01
authoring-fidelity repair train records that an earlier
audit read the sign backwards and a real-Hancom render remeasurement
corrected it to negative=up(superscript)/positive=down(subscript). This
probe cannot re-run that render measurement (no Hancom oracle in this
environment); it reproduces the convention as our code currently encodes
it, live.

Our handling: ``document_parts.py``'s ``_run_style_script_matches``/
``_run_style_apply_script_extension`` encode ``wanted_offset = "-30" if
script == "sup" else "30"`` -- a value the schema alone could not have
told us. The functions additionally emit a real ``<hh:supscript>``/
``<hh:subscript>`` element in parallel with the numeric offset/relSz
approximation, per a second real-corpus measurement (hwpxlib
``error__20250808`` fixture, charPr id=513) that found Hancom's own
superscript toggle carries that element even when its own numeric offset/
relSz happened to still read the un-toggled default.

Run: ``python probes/dev028_subscript_offset_sign_convention.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_DIR = ROOT / "DevDoc" / "OWPML SCHEMA"


def main() -> int:
    schema_file = SCHEMA_DIR / "Header XML schema.xml"
    if schema_file.exists():
        text = schema_file.read_text("utf-8")
        assert '<xs:element name="offset">' in text
        assert "언어별 오프셋" in text
        print("confirmed hh:offset is schema-documented only as \"per-language offset, "
              "unit %\" -- no up/down sign meaning stated")
    else:
        print("SKIP: DevDoc/OWPML SCHEMA/ not present in this checkout — schema-text step skipped")

    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    sup_id = doc.styles.ensure_run(script="sup")
    sub_id = doc.styles.ensure_run(script="sub")
    sup_style = doc.styles.char_property(sup_id)
    sub_style = doc.styles.char_property(sub_id)

    sup_offset = sup_style.child_attributes["offset"]["hangul"]
    sub_offset = sub_style.child_attributes["offset"]["hangul"]
    assert sup_offset == "-30", f"expected superscript offset -30, got {sup_offset}"
    assert sub_offset == "30", f"expected subscript offset 30, got {sub_offset}"
    print(f"confirmed our writer: script=sup -> hh:offset[hangul]={sup_offset}, "
          f"script=sub -> hh:offset[hangul]={sub_offset}")

    assert "supscript" in sup_style.child_attributes, (
        "expected a real hh:supscript element alongside the numeric offset approximation"
    )
    assert "subscript" in sub_style.child_attributes, (
        "expected a real hh:subscript element alongside the numeric offset approximation"
    )
    print("confirmed both charPr also carry a real hh:supscript/hh:subscript element "
          "(parallel to the numeric offset/relSz approximation, per the error__20250808 "
          "real-corpus finding)")

    print("PASS: DEV-028 reproduced (schema silence + live writer convention, "
          "render confirmation is previously-verified per owner memory only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
