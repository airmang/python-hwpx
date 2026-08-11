# SPDX-License-Identifier: Apache-2.0
"""날짜/시간 필드·교정 부호 표시 필드 저작 (6.13 트레인㊻, GUI 프로브 1·3).

`add_hyperlink`(`paragraph.py`)의 3-run 격리(표시 텍스트 런만 별도
charPr, fieldBegin/fieldEnd 런은 주변 서식 유지)와 달리, 실측(팀장 GUI
프로브 gold, macOS 실한컴)은 이 두 필드를 **단일 run 안에 ctrl/t를
나란히** 담는다 -- `hp:run`의 선택군이 반복을 허용한다는 사실은 이미
DEV-017이 확인했고(다른 축이지만), 여기서도 같은 유연성이 실사용됨을
재확인한다. 표시 텍스트(날짜)가 주변 서식을 그대로 물려받아야 자연스러운
필드라 격리가 필요 없다고 보는 게 더 근거 있다 -- 무리해서
hyperlink식으로 3-run 분리하지 않는다.

## 날짜/시간 필드(``type="DATE"``)

실측 원문(``hp:fieldBegin``): ``id``/``fieldid``는 각각 독립 난수(같은
값 아님) · ``editable="0"``·``dirty="0"``(TOC와 달리 열기 시 재계산
트리거가 **아니다** -- 캐시 텍스트가 정본) · ``zorder="-1"``·
``metaTag=""``. ``hp:parameters``(``cnt="4"``): ``Prop=8``(유일한 관측값,
고정) · ``Command``는 포맷 **코드가 아니라 예시 문자열**(관측
``":1년 2월 3일"``, 아마 포맷-선택 UI의 미리보기 캐시) · ``DateNation``
(관측 ``"KOR"``) · ``DateFormat``(관측 ``"YYYY년 M월 D일"``). 실제 표시
값은 ``hp:t``에 별도로 캐시된다(필드 자신은 값을 계산하지 않는다).

**v1 스코프 -- 정직 축소**: 실 예시가 이 포맷 1건뿐이라 ``Command``의
포맷-코드 문법을 역산할 근거가 없다(다른 ``DateFormat`` 문자열을 받으면
``Command``가 어떻게 바뀌는지 모른다) -- 그래서 ``date_format``은 이
관측값 하나만 지원한다(typed 거부, curve·connectLine과 같은 원칙).
캐시 텍스트(``cached_text``)는 호출자가 직접 계산해서 준다 -- "오늘
날짜"를 우리가 대신 판단하지 않는다(add_chart가 ChartML을 호출자에게
요구하는 것과 같은 "모르는 알고리즘은 추측하지 않는다" 원칙).

## 교정 부호 표시 필드(``type="PROOFREADING_MARKS_SIGN"``)

**스키마 편차**: `ParaList XML schema.xml`의 ``hp:FieldType`` 열거값은
``PROOFREADING_MARKS``인데 실제 방출은 ``PROOFREADING_MARKS_SIGN``이다
-- ``docs/owpml-deviations.md`` DEV-043 참조. ``hp:parameters``
(``cnt="2"``): ``Prop=0``(유일한 관측값) · ``Command``는
``"$RevisionSign;N;"`` 형태, ``N``은 기호 인덱스로 보인다(관측:
띄움표=1). 캐시 텍스트 없음(``hp:t`` 자체가 없다 -- 표시가 아니라 순수
마크).

**v1 스코프 -- 더 좁게 축소**: 실한컴 교정 부호 대화상자는 21종 기호를
제공하나 인덱스가 확인된 건 "띄움표"(N=1) 하나뿐이다 -- 나머지 20종은
인덱스-기호 대응표 자체가 없어 추측하면 엉뚱한 기호를 저작하게 된다.
``mark="space"``(N=1) 하나만 지원하고 나머지는 typed 거부.

## 파일 이름 필드(``type="PATH"``, 6.14 트레인㊽b)

트레인㊺가 이미 실 코퍼스에서 확보한 계약(`tests/fixtures/markdown_export/
99_all_in_one_stress.hwpx`, 페이지 머리말 안 `hp:header/hp:subList/hp:p`) --
GUI 프로브 불필요했다. 구조는 DATE와 동형(단일 run, 캐시 텍스트 있음)이고
``Prop=8``도 DATE와 같다(둘 다 "자동 삽입 캐시 필드"류 공유값으로 보인다
-- 교정 부호의 ``Prop=0``과 대조). ``hp:parameters``(``cnt="3"``):
``Command="$F"``·``Format="$F"`` 둘 다 리터럴 고정(관측 1건, 다른 값이
있는지 알 근거 없음). 캐시 텍스트는 관측 예시에서 파일명 그대로
(``"99_all_in_one_stress.hwpx"``) -- 우리가 문서의 "현재 저장 경로"를
추측해 채우지 않는다(DATE의 "오늘 날짜"와 같은 이유 -- 파일명만인지
전체 경로인지조차 이 표본 하나로는 확정 못 한다, 호출자가 계산해서 준다).

**v1 스코프**: ``Command``/``Format`` 둘 다 이 관측값("$F") 하나만
지원(typed 거부) -- 포맷 코드 문법을 역산할 근거가 없는 건 DATE의
``Command`` 미리보기 문자열과 같은 사정이다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from lxml import etree as LET  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from ._document_primitives import _HP, _append_child, _object_id, _sanitize_text

if TYPE_CHECKING:
    from .objects import HwpxOxmlInlineObject
    from .paragraph import HwpxOxmlParagraph

__all__ = [
    "DATE_FORMATS",
    "PROOFREADING_MARKS",
    "PATH_FORMATS",
    "create_date_field",
    "create_proofreading_mark_field",
    "create_path_field",
]

#: 실측된 유일한 (date_format -> command 미리보기 문자열) 매핑. 다른
#: 포맷의 command 문자열을 역산할 근거가 없어 이 하나만 지원한다.
DATE_FORMATS: dict[str, str] = {
    "YYYY년 M월 D일": ":1년 2월 3일",
}

#: 실측된 유일한 (기호 이름 -> $RevisionSign 인덱스) 매핑. 대화상자의
#: 21종 중 인덱스가 확인된 건 "띄움표" 하나뿐이다.
PROOFREADING_MARKS: dict[str, int] = {
    "space": 1,  # 띄움표
}

#: 실측된 유일한 (사람이 읽는 이름 -> Command/Format 리터럴) 매핑.
#: Command와 Format이 항상 같은 값을 쓰는지, 아니면 우연히 이 표본에서만
#: 같았는지 역산할 근거가 없어 하나로 묶어 둔다(둘 다 이 값만 지원).
PATH_FORMATS: dict[str, str] = {
    "filename": "$F",
}


def _field_begin(field_type: str) -> tuple[ET.Element, ET.Element, str, str]:
    """``hp:ctrl > hp:fieldBegin`` -- 관측된 고정 속성 그대로.

    Returns ``(ctrl, fieldBegin, field_id, field_ref_id)`` -- *field_id*는
    ``fieldEnd``의 ``beginIDRef``에, *field_ref_id*(fieldBegin 자신의
    ``fieldid``, ``id``와는 독립 난수)는 ``fieldEnd``의 ``fieldid``에
    그대로 쓴다(둘 다 실측 gold에 있는 속성 -- 값이 다른데도 fieldEnd가
    양쪽을 다 반복해서 갖는다).
    """
    field_id = _object_id()
    field_ref_id = _object_id()
    ctrl = ET.Element(f"{_HP}ctrl")
    begin = _append_child(ctrl, f"{_HP}fieldBegin", {
        "id": field_id,
        "type": field_type,
        "name": "",
        "editable": "0",
        "dirty": "0",
        "zorder": "-1",
        "fieldid": field_ref_id,
        "metaTag": "",
    })
    return ctrl, begin, field_id, field_ref_id


def _field_end(field_id: str, field_ref_id: str) -> ET.Element:
    ctrl = ET.Element(f"{_HP}ctrl")
    _append_child(ctrl, f"{_HP}fieldEnd", {"beginIDRef": field_id, "fieldid": field_ref_id})
    return ctrl


def create_date_field(
    cached_text: str,
    *,
    date_format: str = "YYYY년 M월 D일",
    date_nation: str = "KOR",
) -> list[ET.Element]:
    """날짜/시간 필드(``type="DATE"``) 요소열을 만든다.

    *cached_text*는 지금 이 순간 표시할 값(호출자가 계산) -- 예:
    ``f"{now.year}년 {now.month}월 {now.day}일"``. 반환값은 한 run에
    순서대로 append할 요소 리스트(``[ctrl(begin), t, ctrl(end)]``).
    """
    if date_format not in DATE_FORMATS:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"unsupported date field format: {date_format!r}",
            code="field-date-format-unsupported",
            context={"requested": date_format, "supported": sorted(DATE_FORMATS)},
            suggestion=f"Supported: {', '.join(sorted(DATE_FORMATS))}",
        )

    ctrl_begin, begin, field_id, field_ref_id = _field_begin("DATE")
    params = _append_child(begin, f"{_HP}parameters", {"cnt": "4", "name": ""})
    prop = _append_child(params, f"{_HP}integerParam", {"name": "Prop"})
    prop.text = "8"
    command = _append_child(params, f"{_HP}stringParam", {"name": "Command"})
    command.text = DATE_FORMATS[date_format]
    nation = _append_child(params, f"{_HP}stringParam", {"name": "DateNation"})
    nation.text = date_nation
    fmt = _append_child(params, f"{_HP}stringParam", {"name": "DateFormat"})
    fmt.text = date_format

    text_el = ET.Element(f"{_HP}t")
    text_el.text = _sanitize_text(cached_text)

    ctrl_end = _field_end(field_id, field_ref_id)
    return [ctrl_begin, text_el, ctrl_end]


def create_proofreading_mark_field(mark: str = "space") -> list[ET.Element]:
    """교정 부호 표시 필드(``type="PROOFREADING_MARKS_SIGN"``) 요소열을
    만든다. 캐시 텍스트 없음(순수 마크) -- 반환값은
    ``[ctrl(begin), ctrl(end)]``."""
    if mark not in PROOFREADING_MARKS:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"unsupported proofreading mark: {mark!r}",
            code="field-proofreading-mark-unsupported",
            context={"requested": mark, "supported": sorted(PROOFREADING_MARKS)},
            suggestion=(
                "Only marks with a confirmed $RevisionSign index are supported: "
                f"{', '.join(sorted(PROOFREADING_MARKS))}. The real dialog offers "
                "21 kinds total but the other 20 have no confirmed index."
            ),
        )

    ctrl_begin, begin, field_id, field_ref_id = _field_begin("PROOFREADING_MARKS_SIGN")
    params = _append_child(begin, f"{_HP}parameters", {"cnt": "2", "name": ""})
    prop = _append_child(params, f"{_HP}integerParam", {"name": "Prop"})
    prop.text = "0"
    command = _append_child(params, f"{_HP}stringParam", {"name": "Command"})
    command.text = f"$RevisionSign;{PROOFREADING_MARKS[mark]};"

    ctrl_end = _field_end(field_id, field_ref_id)
    return [ctrl_begin, ctrl_end]


def create_path_field(
    cached_text: str,
    *,
    path_format: str = "filename",
) -> list[ET.Element]:
    """파일 이름 필드(``type="PATH"``) 요소열을 만든다.

    *cached_text*는 지금 이 순간 표시할 값(호출자가 계산) -- 파일명만인지
    전체 경로인지도 호출자 책임(관측 1건은 파일명만). 반환값은 DATE와
    동형(``[ctrl(begin), t, ctrl(end)]``).
    """
    if path_format not in PATH_FORMATS:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"unsupported path field format: {path_format!r}",
            code="field-path-format-unsupported",
            context={"requested": path_format, "supported": sorted(PATH_FORMATS)},
            suggestion=f"Supported: {', '.join(sorted(PATH_FORMATS))}",
        )

    literal = PATH_FORMATS[path_format]
    ctrl_begin, begin, field_id, field_ref_id = _field_begin("PATH")
    params = _append_child(begin, f"{_HP}parameters", {"cnt": "3", "name": ""})
    prop = _append_child(params, f"{_HP}integerParam", {"name": "Prop"})
    prop.text = "8"
    command = _append_child(params, f"{_HP}stringParam", {"name": "Command"})
    command.text = literal
    fmt = _append_child(params, f"{_HP}stringParam", {"name": "Format"})
    fmt.text = literal

    text_el = ET.Element(f"{_HP}t")
    text_el.text = _sanitize_text(cached_text)

    ctrl_end = _field_end(field_id, field_ref_id)
    return [ctrl_begin, text_el, ctrl_end]


def _append_field_elements(
    paragraph: "HwpxOxmlParagraph",
    elements: list[ET.Element],
    *,
    char_pr_id_ref: str | int | None,
) -> "HwpxOxmlInlineObject":
    """공용 삽입 배관: 새 run을 만들고 *elements*를 순서대로 그 run에
    append한다(하이퍼링크의 3-run 격리와 달리 단일 run -- 모듈 독스트링
    참조). run과 타입이 다르면(stdlib ET vs lxml) 표준 브리지로 변환한다
    (``objects.py``의 ``_paragraph_insert_shape_element`)와 같은 패턴)."""
    from .objects import HwpxOxmlInlineObject

    run = paragraph._create_run_for_object(char_pr_id_ref=char_pr_id_ref)
    first: ET.Element | None = None
    for element in elements:
        if type(element) is not type(run):
            element = LET.fromstring(ET.tostring(element, encoding="utf-8"))
        run.append(element)
        if first is None:
            first = element
    paragraph.section.mark_dirty()
    assert first is not None  # elements is always non-empty by construction
    return HwpxOxmlInlineObject(first, paragraph)


def _paragraph_add_date_field(
    self: "HwpxOxmlParagraph",
    cached_text: str,
    *,
    date_format: str = "YYYY년 M월 D일",
    date_nation: str = "KOR",
    char_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlInlineObject":
    """날짜/시간 필드를 이 문단에 삽입한다. 돌려주는 객체의 ``.element``는
    ``hp:fieldBegin``을 감싼 ``hp:ctrl``이다.

    ``paragraph.py``가 owner-file 1600줄 캡에 헤드룸이 없어(``dutmal_
    compose.py``/``objects.py``와 같은 이유) 클래스 속성 대입으로만
    붙는다(``paragraph.py``의 ``add_date_field = _paragraph_add_date_field``
    참조) -- ``paragraph``가 아니라 ``self``인 것도 그 관행 그대로.
    """
    elements = create_date_field(cached_text, date_format=date_format, date_nation=date_nation)
    return _append_field_elements(self, elements, char_pr_id_ref=char_pr_id_ref)


def _paragraph_add_proofreading_mark(
    self: "HwpxOxmlParagraph",
    mark: str = "space",
    *,
    char_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlInlineObject":
    """교정 부호 표시 필드를 이 문단에 삽입한다."""
    elements = create_proofreading_mark_field(mark)
    return _append_field_elements(self, elements, char_pr_id_ref=char_pr_id_ref)


def _paragraph_add_path_field(
    self: "HwpxOxmlParagraph",
    cached_text: str,
    *,
    path_format: str = "filename",
    char_pr_id_ref: str | int | None = None,
) -> "HwpxOxmlInlineObject":
    """파일 이름 필드를 이 문단에 삽입한다."""
    elements = create_path_field(cached_text, path_format=path_format)
    return _append_field_elements(self, elements, char_pr_id_ref=char_pr_id_ref)
