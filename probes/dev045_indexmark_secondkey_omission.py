#!/usr/bin/env python3
"""DEV-045 -- the schema declares ``hp:indexmark``'s two key children as a
required sequence, but real Hancom omits ``secondKey`` entirely for a
one-level index entry.

Schema claim: ``ParaList XML schema.xml:209-216`` declares ``indexmark`` as
one of ``hp:ctrl``'s choice-group children with no attributes and a
``xs:sequence`` of ``firstKey`` and ``secondKey``. Neither carries
``minOccurs``, so both default to 1 -- both are required. Neither carries a
``type`` either, so both are ``xs:anyType``: the schema does not even say
whether the key string is a text node or an attribute. There is no
``xs:documentation`` anywhere in the declaration.

Real-document measurement: real Hancom (HWP 13.0.0.3901, 도구 > 차례/색인 >
색인 표시) puts the key in the child element's *text node*
(``<hp:firstKey>apple</hp:firstKey>``), which settles the ``xs:anyType``
silence. And when the [두 번째 낱말] field is left blank, ``hp:secondKey``
is **not emitted at all** -- not as an empty element. Two golds pin both
sides: ``index_mark_first_only.hwpx`` (one key) and
``index_mark_two_keys.hwpx`` (both). Placement is confirmed too: the mark
sits in an ``hp:ctrl`` that is a *preceding sibling* of the run's ``hp:t``,
unlike ``hp:titleMark`` (DEV-044) which goes *inside* ``hp:t``.

Note that the vendored corpus has zero ``hp:indexmark`` occurrences (71
fixtures and a repo-wide scan of 8,869 hwpx files both found none) -- these
GUI golds are the only real-document evidence that exists.

Our handling: ``HwpxOxmlParagraph.add_index_mark(first, *, second=None)``
follows the measurement -- omitting *second* omits the element, and an
empty string is rejected outright, because omission and empty string
produce different XML and a caller should not be able to conflate them.
Local schema validation is a convergence lint rather than a hard gate, so a
one-key index mark is reported as a schema mismatch without blocking
authoring -- the same measurement-over-schema stance as DEV-043.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import lxml.etree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = REPO_ROOT / "tests" / "fixtures" / "gui_probes"
GOLD_ONE_KEY = GOLD_DIR / "index_mark_first_only.hwpx"
GOLD_TWO_KEYS = GOLD_DIR / "index_mark_two_keys.hwpx"
SCHEMA_FILE = REPO_ROOT / "DevDoc" / "OWPML SCHEMA" / "ParaList XML schema.xml"

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_XS = "{http://www.w3.org/2001/XMLSchema}"


def _index_mark_declaration() -> ET._Element:
    tree = ET.parse(str(SCHEMA_FILE))
    for element in tree.getroot().iter(f"{_XS}element"):
        if element.get("name") == "indexmark":
            return element
    raise AssertionError(
        "hp:indexmark element declaration not found in the vendored schema "
        "-- DEV-045's premise no longer holds, recheck the deviation entry"
    )


def _check_schema() -> None:
    declaration = _index_mark_declaration()

    assert not declaration.findall(f".//{_XS}attribute"), (
        "expected hp:indexmark to declare zero attributes -- DEV-045's "
        "premise no longer holds"
    )
    assert not declaration.findall(f".//{_XS}annotation"), (
        "expected zero xs:documentation on hp:indexmark -- DEV-045's "
        "premise no longer holds"
    )

    sequence = declaration.find(f"./{_XS}complexType/{_XS}sequence")
    assert sequence is not None, "expected hp:indexmark to declare an xs:sequence"
    children = [child.get("name") for child in sequence.findall(f"./{_XS}element")]
    assert children == ["firstKey", "secondKey"], (
        f"expected the key sequence to be [firstKey, secondKey], got "
        f"{children} -- DEV-045's premise no longer holds"
    )

    for child in sequence.findall(f"./{_XS}element"):
        name = child.get("name")
        assert child.get("minOccurs") is None, (
            f"{name} now carries an explicit minOccurs "
            f"({child.get('minOccurs')!r}) -- DEV-045's premise (both "
            "children default to required) no longer holds"
        )
        assert child.get("type") is None, (
            f"{name} now carries a type ({child.get('type')!r}) -- DEV-045's "
            "premise (untyped xs:anyType, schema silent on text-vs-attribute) "
            "no longer holds"
        )

    print(
        "confirmed: schema declares firstKey+secondKey as a required, "
        "untyped, undocumented sequence (both minOccurs default to 1)"
    )


def _index_marks(gold: Path) -> list[ET._Element]:
    with zipfile.ZipFile(gold) as archive:
        section_xml = archive.read("Contents/section0.xml")
    root = ET.parse(io.BytesIO(section_xml)).getroot()
    return [el for el in root.iter(f"{_HP}indexmark")]


def _check_golds() -> None:
    one_key_marks = _index_marks(GOLD_ONE_KEY)
    assert len(one_key_marks) == 1, (
        f"expected exactly one hp:indexmark in {GOLD_ONE_KEY.name}, found "
        f"{len(one_key_marks)}"
    )
    mark = one_key_marks[0]

    children = [ET.QName(child).localname for child in mark]
    assert children == ["firstKey"], (
        f"expected the one-key gold to emit firstKey only, got {children} -- "
        "DEV-045's premise (secondKey omitted entirely, not emitted empty) "
        "no longer holds"
    )
    first_key = mark.find(f"{_HP}firstKey")
    assert first_key is not None and first_key.text == "apple", (
        f"expected the key as the child element's text node, got "
        f"{first_key.text!r} -- DEV-045's premise no longer holds"
    )
    assert not first_key.attrib, "expected the key to be text, not an attribute"
    print(
        "real Hancom output (one-level index): hp:secondKey is NOT emitted "
        "at all, and the key lives in firstKey's text node"
    )

    two_key_marks = _index_marks(GOLD_TWO_KEYS)
    assert len(two_key_marks) == 1
    children = [ET.QName(child).localname for child in two_key_marks[0]]
    assert children == ["firstKey", "secondKey"], (
        f"expected the two-key gold to emit both keys, got {children}"
    )
    keys = [child.text for child in two_key_marks[0]]
    assert keys == ["fruit", "banana"], f"unexpected key texts {keys}"
    print("real Hancom output (two-level index): both keys emitted, as text nodes")

    # Placement: the mark's hp:ctrl is a preceding sibling of the run's
    # hp:t -- distinct from hp:titleMark (DEV-044), which sits inside hp:t.
    ctrl = mark.getparent()
    assert ctrl is not None and ctrl.tag == f"{_HP}ctrl"
    run = ctrl.getparent()
    assert run is not None and run.tag == f"{_HP}run"
    siblings = [child.tag for child in run]
    assert siblings.index(f"{_HP}ctrl") < siblings.index(f"{_HP}t"), (
        "expected the indexmark's hp:ctrl to precede the run's hp:t"
    )
    print("confirmed: hp:ctrl>hp:indexmark precedes hp:t as a run sibling")


def _check_our_handling() -> None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from hwpx.document import HwpxDocument
    from hwpx.errors import HwpxValueError

    document = HwpxDocument.new()

    one_key = document.add_paragraph("apple item paragraph.")
    one_key.add_index_mark("apple")
    mark = one_key.element.find(f".//{_HP}indexmark")
    assert mark is not None
    assert [ET.QName(child).localname for child in mark] == ["firstKey"], (
        "add_index_mark(second=None) must not emit hp:secondKey -- it would "
        "no longer follow the measured contract"
    )

    two_keys = document.add_paragraph("banana item paragraph.")
    two_keys.add_index_mark("fruit", second="banana")
    marks = document.paragraphs[-1].element.findall(f".//{_HP}indexmark")
    assert len(marks) == 1
    assert [ET.QName(child).localname for child in marks[0]] == [
        "firstKey",
        "secondKey",
    ]

    blank = document.add_paragraph("blank key paragraph.")
    try:
        blank.add_index_mark("fruit", second="")
    except HwpxValueError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError(
            "an empty second key must be rejected -- omission and empty "
            "string produce different XML and must not be conflated"
        )

    print(
        "confirmed: add_index_mark follows the measurement (second=None "
        "omits the element, empty string is refused)"
    )


def main() -> None:
    _check_schema()

    missing = [gold for gold in (GOLD_ONE_KEY, GOLD_TWO_KEYS) if not gold.exists()]
    if missing:
        print(
            "SKIP: gold not present locally: "
            + ", ".join(gold.name for gold in missing)
        )
    else:
        _check_golds()

    _check_our_handling()


if __name__ == "__main__":
    main()
