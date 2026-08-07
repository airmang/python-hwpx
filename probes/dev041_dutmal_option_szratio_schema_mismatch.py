#!/usr/bin/env python3
"""DEV-041 -- ``hp:dutmal`` (덧말/ruby-style annotation text) has two
attributes whose real Hancom output directly contradicts the schema's own
declared constraint.

Schema claim (``ParaList XML schema.xml``, ``dutmal`` element): ``option``
is declared ``xs:unsignedInt fixed="4"`` -- XSD's ``fixed`` means every
valid instance document must carry exactly that value (or omit the
attribute and have it implied). ``szRatio`` is declared
``xs:positiveInteger`` -- must be 1 or greater, 0 is not a legal value for
that type at all.

Real-document measurement: the vendored corpus's only real ``hp:dutmal``
sample (``tests/fixtures/hwpxlib_corpus/reader_writer__SimpleDutmal.hwpx``,
a hwpxlib reader/writer round-trip fixture -- genuinely Hancom-produced,
not synthetic) has ``option="0"`` (not "4") and ``szRatio="0"`` (not >= 1).
Single sample, low frequency (cycle 6.8 train 29's macOS editor menu scan
confirmed 덧말 is a first-class Hancom menu item, but this is the only
real corpus occurrence in this project across every corpus checked so
far) -- so whether "0"/"0" is this one document's own quirk or the actual
Hancom convention is honestly unknown. What is certain: the schema's own
claims (fixed=4, positiveInteger) are contradicted by real output at
least once, so this module does not enforce them as validation rules.

Our handling: ``hwpx.oxml.body.Dutmal``/``parse_dutmal_element``/
``_dutmal_to_xml`` round-trip whatever value is present, faithfully, no
enforcement. The authoring API (``HwpxOxmlParagraph.add_dutmal``, cycle
6.9 train 34) defaults ``sz_ratio``/``option`` to the one real sample's
own observed values (0/0) rather than schema-plausible guesses (4/1),
since a wrong guess authored into new documents would be worse than
faithfully reproducing the only real evidence available.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import lxml.etree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "hwpxlib_corpus"
    / "reader_writer__SimpleDutmal.hwpx"
)

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def main() -> None:
    with zipfile.ZipFile(FIXTURE) as archive:
        section_xml = archive.read("Contents/section0.xml")

    tree = ET.parse(io.BytesIO(section_xml))
    dutmal_elements = [el for el in tree.getroot().iter() if el.tag == f"{_HP}dutmal"]
    assert len(dutmal_elements) == 1, (
        f"expected exactly one hp:dutmal in the fixture, found {len(dutmal_elements)}"
    )
    dutmal = dutmal_elements[0]

    option = dutmal.get("option")
    sz_ratio = dutmal.get("szRatio")
    print(f"real Hancom output: option={option!r} szRatio={sz_ratio!r}")

    assert option == "0", (
        f"expected the real sample's option to be '0' (contradicting the schema's "
        f"fixed='4'), got {option!r} -- DEV-041's premise no longer holds, recheck "
        "the deviation entry"
    )
    assert sz_ratio == "0", (
        f"expected the real sample's szRatio to be '0' (contradicting the schema's "
        f"xs:positiveInteger, which forbids 0), got {sz_ratio!r} -- DEV-041's "
        "premise no longer holds, recheck the deviation entry"
    )

    print(
        "confirmed: schema claims option=fixed(4)/szRatio>=1, "
        "real Hancom output has option=0/szRatio=0 for both"
    )

    # Round-trip through this project's own read model + authoring default,
    # confirming our handling matches what the docstring above claims.
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from hwpx.document import HwpxDocument
    from hwpx.oxml.body import Dutmal

    doc = HwpxDocument.open(FIXTURE)
    p0 = doc.sections[0].paragraphs[0]
    model = p0.runs[0].to_model()
    parsed = next(c for c in model.content if isinstance(c, Dutmal))
    assert parsed.option == 0
    assert parsed.sz_ratio == 0
    print(f"read model round-trip: {parsed}")

    fresh = HwpxDocument.new()
    fresh_p = fresh.add_paragraph("")
    obj = fresh_p.add_dutmal("본말", "덧말")
    assert obj.element.get("option") == "0"
    assert obj.element.get("szRatio") == "0"
    print("authoring default confirmed: add_dutmal() defaults to option=0/szRatio=0")


if __name__ == "__main__":
    main()
