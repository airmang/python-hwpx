#!/usr/bin/env python3
"""DEV-048 -- the schema types ``hh:licensemark/@type`` as an unsigned
integer; real Hancom writes the string ``"CCL"``.

Schema claim: ``Header XML schema.xml``'s ``DocOptionType`` declares
``licensemark``'s ``type`` attribute as ``xs:unsignedInt use="required"``,
i.e. the licence kind is a numeric code. Its siblings ``flag`` and ``lang``
are ``xs:byte``. There is no ``xs:documentation`` anywhere on the element,
so the schema never says which integer would mean what.

Real-document measurement: real Hancom (HWP 13.0.0.3901, 파일 > CCL 넣기)
writes ``<hh:licensemark type="CCL" flag="0" lang="6"/>``. This is not a
declared constraint being violated at the margins -- the *type* of the
value is different. Same family as DEV-043, where the field-type enum
member turned out to be a wholly different string. Note that only the one
attribute diverges: ``flag`` and ``lang`` really are integers. The vendored
corpus has no ``licensemark`` at all, so this gold is the only evidence.

Our handling: ``LicenseMark.type`` is ``str``. That was a real read defect,
not a typing preference -- declared ``int`` on schema authority alone, it
made ``to_model()`` raise ``ValueError: Invalid integer value: 'CCL'`` on
any real CCL document. Authoring (``header_compat.set_license_mark``) takes
``mark_type: str`` and passes it through for the same reason: "correcting"
it to the schema's integer would author a value real Hancom cannot read.
With a single observation there is no enumeration to enforce, so only the
empty string is refused.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import lxml.etree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD = REPO_ROOT / "tests" / "fixtures" / "gui_probes" / "license_mark_ccl.hwpx"
SCHEMA_FILE = REPO_ROOT / "DevDoc" / "OWPML SCHEMA" / "Header XML schema.xml"

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_XS = "{http://www.w3.org/2001/XMLSchema}"


def _check_schema() -> None:
    if not SCHEMA_FILE.exists():
        print(f"SKIP: schema not present locally: {SCHEMA_FILE}")
        return

    root = ET.parse(str(SCHEMA_FILE)).getroot()
    declaration = None
    for element in root.iter(f"{_XS}element"):
        if element.get("name") == "licensemark":
            declaration = element
            break
    assert declaration is not None, (
        "hh:licensemark declaration not found in the vendored schema -- "
        "DEV-048's premise no longer holds, recheck the deviation entry"
    )

    attributes = {
        attribute.get("name"): attribute.get("type")
        for attribute in declaration.iter(f"{_XS}attribute")
    }
    assert attributes.get("type") == "xs:unsignedInt", (
        f"the schema now types @type as {attributes.get('type')!r} rather "
        "than xs:unsignedInt -- DEV-048's premise no longer holds"
    )
    type_attribute = next(
        attribute
        for attribute in declaration.iter(f"{_XS}attribute")
        if attribute.get("name") == "type"
    )
    assert type_attribute.get("use") == "required"
    assert not declaration.findall(f".//{_XS}annotation"), (
        "hh:licensemark now carries xs:documentation -- DEV-048's premise "
        "(schema silent on what any code would mean) no longer holds"
    )
    print(
        "confirmed: schema declares @type as xs:unsignedInt use='required', "
        f"undocumented (siblings: flag={attributes.get('flag')!r}, "
        f"lang={attributes.get('lang')!r})"
    )


def _check_gold() -> ET._Element:
    with zipfile.ZipFile(GOLD) as archive:
        header_xml = archive.read("Contents/header.xml")
    root = ET.parse(io.BytesIO(header_xml)).getroot()

    marks = [el for el in root.iter(f"{_HH}licensemark")]
    assert len(marks) == 1, (
        f"expected exactly one hh:licensemark in the gold, found {len(marks)}"
    )
    mark = marks[0]

    doc_option = mark.getparent()
    assert doc_option is not None and doc_option.tag == f"{_HH}docOption", (
        "hh:licensemark is no longer a child of hh:docOption"
    )

    raw_type = mark.get("type")
    assert raw_type == "CCL", (
        f"real Hancom now writes type={raw_type!r} -- DEV-048's premise "
        "no longer holds, recheck the deviation entry"
    )
    try:
        int(raw_type)
    except ValueError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError(
            f"type={raw_type!r} now parses as an integer -- the schema and "
            "reality agree again, retire DEV-048"
        )
    print(f"real Hancom output: type={raw_type!r} -- a string, not an unsignedInt")

    # Only this one attribute diverges: flag/lang really are integers.
    for name in ("flag", "lang"):
        value = mark.get(name)
        assert value is not None and value.lstrip("-").isdigit(), (
            f"{name}={value!r} is no longer an integer -- DEV-048 scopes the "
            "divergence to @type alone"
        )
    print(
        f"confirmed: siblings stay numeric as declared "
        f"(flag={mark.get('flag')!r}, lang={mark.get('lang')!r})"
    )
    return mark


def _check_our_handling(mark: ET._Element) -> None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from hwpx.document import HwpxDocument
    from hwpx.errors import HwpxValueError
    from hwpx.oxml.header import parse_license_mark

    parsed = parse_license_mark(mark)
    assert parsed.type == "CCL", (
        f"parse_license_mark returned type={parsed.type!r} -- it must "
        "preserve the measured string verbatim"
    )
    assert isinstance(parsed.type, str), "LicenseMark.type must stay str"
    assert parsed.flag == 0 and parsed.lang == 6
    print("confirmed: our read model preserves the string verbatim")

    # The defect this fix closed: reading a real CCL document end to end.
    document = HwpxDocument.open(str(GOLD))
    model = document.parts.headers[0].to_model()
    license_mark = model.doc_option.license_mark
    assert license_mark is not None and license_mark.type == "CCL", (
        "to_model() no longer surfaces the licence record -- this is the "
        "exact path that used to raise ValueError: Invalid integer value"
    )
    print(
        "confirmed: to_model() reads a real CCL document (the int declaration "
        "used to raise ValueError here)"
    )

    # Authoring passes the string through rather than 'correcting' it.
    authored = HwpxDocument.new()
    authored.parts.set_license_mark(mark_type="CCL", flag=0, lang=6)
    written = authored.parts.headers[0].element.find(
        f"{_HH}docOption/{_HH}licensemark"
    )
    assert written is not None and written.get("type") == "CCL", (
        "set_license_mark no longer writes the measured string -- authoring "
        "a schema-shaped integer would produce a mark real Hancom cannot read"
    )
    try:
        authored.parts.set_license_mark(mark_type="", flag=0)
    except HwpxValueError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("an empty mark_type must be refused")
    print(
        "confirmed: authoring passes the string through (empty refused, no "
        "enumeration invented from a single observation)"
    )


def main() -> None:
    _check_schema()

    if not GOLD.exists():
        print(f"SKIP: gold not present locally: {GOLD}")
        return

    mark = _check_gold()
    _check_our_handling(mark)


if __name__ == "__main__":
    main()
