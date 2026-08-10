#!/usr/bin/env python3
"""DEV-043 -- 교정 부호 표시 필드의 ``hp:fieldBegin/@type`` 실측값이
``ParaList XML schema.xml``의 ``hp:FieldType`` 닫힌 열거형에 아예 없는
문자열이다.

Schema claim (``ParaList XML schema.xml``, ``FieldType`` simple type):
15개 값만 허용하는 닫힌 열거형(``xs:enumeration``만, 확장점 없음) --
``CLICK_HERE``/``HYPERLINK``/``BOOKMARK``/``FORMULA``/``SUMMERY``/
``USER_INFO``/``DATE``/``DOC_DATE``/``PATH``/``CROSSREF``/``MAILMERGE``/
``MEMO``/``PROOFREADING_MARKS``/``PRIVATE_INFO``/``METATAG``. 교정 부호는
접미사 없는 ``PROOFREADING_MARKS``로만 선언되어 있다.

Real-document measurement: 팀장이 macOS 실한컴 GUI로 직접 교정 부호를
삽입해 만든 gold 샘플(``tests/fixtures/gui_probes/date_and_proofreading_mark.hwpx``
-- 사설 스크래치에서 이 프로젝트로 가져온 합성물, hwpxlib류 벤더드
코퍼스는 아니지만 실한컴 산출은 맞다)의 ``hp:fieldBegin/@type``은
``PROOFREADING_MARKS_SIGN`` -- 스키마 열거형 어디에도 없는 값이다.
DEV-002(``maxOccurs`` 누락)나 DEV-041(``fixed``/``positiveInteger``
위반)처럼 선언된 제약을 실측이 어기는 정도가 아니라, 열거형 멤버
자체가 통째로 다른 문자열이라는 점에서 더 근본적인 편차.

Our handling: ``hwpx.oxml.field_marks.create_proofreading_mark_field``가
실측값 ``PROOFREADING_MARKS_SIGN``을 그대로 방출한다(스키마의
``PROOFREADING_MARKS``로 "정정"하지 않음 -- 그러면 실한컴이 인식 못
하는 값을 저작하게 된다). 로컬 스키마 검증은 수렴 lint일 뿐 하드
게이트가 아니므로 이 편차는 저작을 막지 않는다.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import lxml.etree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "gui_probes" / "date_and_proofreading_mark.hwpx"
)
SCHEMA_FILE = REPO_ROOT / "DevDoc" / "OWPML SCHEMA" / "ParaList XML schema.xml"

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_XS = "{http://www.w3.org/2001/XMLSchema}"


def _schema_declared_field_types() -> list[str]:
    tree = ET.parse(str(SCHEMA_FILE))
    for simple_type in tree.getroot().iter(f"{_XS}simpleType"):
        if simple_type.get("name") != "FieldType":
            continue
        return [
            enum.get("value")
            for enum in simple_type.iter(f"{_XS}enumeration")
            if enum.get("value") is not None
        ]
    raise AssertionError("hp:FieldType simpleType not found in the vendored schema")


def main() -> None:
    declared = _schema_declared_field_types()
    print(f"schema hp:FieldType enumeration ({len(declared)} values): {declared}")
    assert "PROOFREADING_MARKS" in declared
    assert "PROOFREADING_MARKS_SIGN" not in declared, (
        "expected the schema enumeration to NOT contain the _SIGN variant -- "
        "DEV-043's premise no longer holds, recheck the deviation entry"
    )

    with zipfile.ZipFile(FIXTURE) as archive:
        section_xml = archive.read("Contents/section0.xml")
    tree = ET.parse(io.BytesIO(section_xml))
    field_begins = [
        el for el in tree.getroot().iter(f"{_HP}fieldBegin") if el.get("type", "").startswith("PROOFREADING")
    ]
    assert len(field_begins) == 1, (
        f"expected exactly one proofreading-mark hp:fieldBegin, found {len(field_begins)}"
    )
    real_type = field_begins[0].get("type")
    print(f"real Hancom output hp:fieldBegin/@type: {real_type!r}")
    assert real_type == "PROOFREADING_MARKS_SIGN", (
        f"expected the real gold sample's type to be 'PROOFREADING_MARKS_SIGN', "
        f"got {real_type!r} -- DEV-043's premise no longer holds, recheck the "
        "deviation entry"
    )
    assert real_type not in declared, (
        "real output value unexpectedly IS in the schema enumeration -- "
        "DEV-043's premise no longer holds"
    )

    print(
        "confirmed: schema hp:FieldType enumerates 'PROOFREADING_MARKS' only, "
        "real Hancom output emits 'PROOFREADING_MARKS_SIGN' (not a member of "
        "the declared enumeration at all)"
    )

    # Round-trip through this project's own authoring API, confirming our
    # handling matches what the docstring above claims: we emit the real
    # (schema-violating) value faithfully, not the schema's declared one.
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("", include_run=False)
    result = paragraph.add_proofreading_mark("space")
    field_begin = result.element.find(f".//{_HP}fieldBegin")
    assert field_begin is not None
    assert field_begin.get("type") == "PROOFREADING_MARKS_SIGN"
    print("authoring confirmed: add_proofreading_mark() emits the real (non-schema) type value")


if __name__ == "__main__":
    main()
