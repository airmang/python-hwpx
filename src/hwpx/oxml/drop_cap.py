# SPDX-License-Identifier: Apache-2.0
"""문단 첫 글자 장식(drop cap) 저작 -- ``hp:rect``의 ``dropcapstyle``.

cycle 6.12 트레인㊸, 갭②(편집기 메뉴 표면 역매핑 트레인㊷가 찾은 신규 갭).

**어휘(스키마)**: `hc:DropCapStyleType`(`Core XML schema.xml:429`)은
`None`/`DoubleLine`/`TripleLine`/`Margin` 4종을 선언한다. 이 속성 자체는
`hh:paraPr`가 아니라 `AbstractShapeObjectType`(rect/picture/table/chart 등
모든 삽입 개체가 공유하는 공통 속성군)에 산다 -- `ParaList XML schema.xml
:2006`, 이 라이브러리의 `_create_rectangle_element`/`_create_ellipse_
element` 등이 전부 이 속성을 `"None"`으로 기본 방출하는 이유가 이거다.

**실코퍼스 실측(67파일 전수, 벤더드 코퍼스)**: `error__20230809__test.hwpx`
단 1건에서 `dropcapstyle="TripleLine"`을 관측했다(나머지는 전부 "None").
이 파일을 역설계한 실제 구조:

- 드롭캡은 **문단의 첫 글자를 잘라낸 게 아니라, 별도 `hp:rect` 개체를
  그 문단의 run 안에 끼워 넣는** 방식이다. rect는 투명(선 `style="NONE"`,
  채움/그림자 `alpha="0"`)하고 잠겨 있다(`lock="1"`).
- rect 안에는 `hp:drawText`(텍스트 상자)가 있고, 그 안의
  `subList/p/run/t`가 드롭캡으로 키운 실제 문자 하나를 담는다 --
  즉 문자 자체는 원래 문단 텍스트가 아니라 이 내부 텍스트 상자
  안에서 산다.
- 배치는 `treatAsChar="0"`(흐르는 개체 아님)·`vertRelTo="PARA"`·
  `horzRelTo="PARA"`·`horzAlign="LEFT"`·`vertAlign="TOP"`·
  `flowWithText="1"` -- 일반 도형 빌더의 "treat_as_char=False" 기본값
  (`horzRelTo="COLUMN"`·`flowWithText="0"`)과 **다르다**, 그래서 이
  모듈은 기존 `_create_rectangle_element`를 재사용하지 않고 이 구조
  전용으로 새로 짠다.
- `outMargin right="850"`(다른 셋은 0) -- 드롭캡과 뒤따르는 본문 사이
  간격으로 추정.
- `curSz width="0" height="0"` -- `orgSz`(실제 크기)와 다르다(일반
  도형 빌더는 `curSz`를 항상 `orgSz`와 같게 방출한다) -- "리사이즈
  안 됨" 센티널로 추정.
- 정체불명의 `hp:parameterset`(`name="539"`, 중첩
  `listParam[name="12291"]/unsignedintegerParam[name="28673"]` 값
  `"2"`)이 붙는다 -- 의미 불명, DEV-011(hp:parameterset 불투명 보존
  전례)과 같은 원칙으로 **그대로 복사**한다(추측 안 함).

**v1 스코프 -- 정직 축소**: 실 예시가 `TripleLine` 딱 1건뿐이라 `DoubleLine`/
`Margin`은 구조 자체가 같은지(같은 rect+drawText 패턴인지, 다른 메커니즘인지)
검증 근거가 없다 -- **`TripleLine`만 지원**, 다른 두 값은 typed 오류로
거부한다(curve·connectLine과 같은 원칙: 실증 없는 값을 추측 구현하면
무음 오류 위험). 크기(width/height)도 실측된 폰트-크기→박스-크기 변환
공식이 없어(1건으로는 공식을 못 세운다) **호출자가 직접 지정**한다 --
자동 계산 시도 안 함(add_chart가 ChartML을 호출자에게 요구하는 것과 같은
"모르는 알고리즘은 추측하지 않는다" 원칙).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ._document_primitives import _HC, _HP, _append_child, _object_id, _paragraph_id

__all__ = ["DROP_CAP_STYLES", "create_drop_cap_element"]

#: v1이 지원하는 유일한 값 -- 실코퍼스에 구조가 검증된 단 하나(위 모듈
#: 독스트링 참조). "DoubleLine"/"Margin"은 스키마엔 있으나 실 구조 근거가
#: 없어 v1 범위 밖(정직 보류).
DROP_CAP_STYLES = frozenset({"TripleLine"})

#: 정체불명 parameterset -- 유일한 실 예시(`error__20230809__test.hwpx`)의
#: TripleLine 인스턴스에서 그대로 복사(의미 불명, 추측 안 함).
_TRIPLE_LINE_PARAMETERSET = {
    "cnt": "1",
    "name": "539",
}


def create_drop_cap_element(
    width: int,
    height: int,
    character: str,
    *,
    style: str = "TripleLine",
    char_pr_id_ref: str | int | None = None,
    para_pr_id_ref: str | int | None = None,
) -> ET.Element:
    """실측된 ``TripleLine`` 드롭캡 ``hp:rect`` 구조를 그대로 재현한다.

    *width*/*height*는 HWPUNIT -- 호출자가 직접 지정(자동 계산 안 함, 위
    모듈 독스트링의 "정직 축소" 참조). *character*는 드롭캡으로 키울 문자
    (보통 1자, 그러나 실측이 길이를 강제하지 않아 문자열 그대로 받는다).
    """

    if style not in DROP_CAP_STYLES:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            f"drop cap style {style!r} is not supported yet",
            code="shape-drop-cap-style-unsupported",
            context={"style": style, "supported": sorted(DROP_CAP_STYLES)},
            suggestion=(
                "Only 'TripleLine' has real-corpus structural evidence "
                "(exactly one sample, error__20230809__test.hwpx) -- "
                "'DoubleLine'/'Margin' are schema-declared but structurally "
                "unverified, so this function refuses to guess their shape."
            ),
        )
    if not character:
        from ..errors import HwpxValueError

        raise HwpxValueError(
            "drop cap character must be non-empty",
            code="shape-drop-cap-character-empty",
            suggestion="Pass the character(s) to enlarge into the drop cap.",
        )

    w = str(width)
    h = str(height)
    object_id = _object_id()

    el = ET.Element(f"{_HP}rect", {
        "id": object_id,
        "zOrder": "1",
        "numberingType": "NONE",
        "textWrap": "SQUARE",
        "textFlow": "RIGHT_ONLY",
        "lock": "1",
        "dropcapstyle": style,
        "href": "",
        "groupLevel": "0",
        "instid": object_id,
        "ratio": "0",
    })

    _append_child(el, f"{_HP}offset", {"x": "0", "y": "0"})
    _append_child(el, f"{_HP}orgSz", {"width": w, "height": h})
    # Real sample: curSz stays "0"/"0", unlike every other shape builder in
    # this codebase (which sets curSz == orgSz) -- a "never resized"
    # sentinel, kept verbatim rather than normalized to match the others.
    _append_child(el, f"{_HP}curSz", {"width": "0", "height": "0"})
    _append_child(el, f"{_HP}flip", {"horizontal": "0", "vertical": "0"})
    cx = str(width // 2)
    cy = str(height // 2)
    _append_child(el, f"{_HP}rotationInfo", {
        "angle": "0", "centerX": cx, "centerY": cy, "rotateimage": "1",
    })
    rendering_info = _append_child(el, f"{_HP}renderingInfo", {})
    identity = {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"}
    _append_child(rendering_info, f"{_HC}transMatrix", dict(identity))
    _append_child(rendering_info, f"{_HC}scaMatrix", dict(identity))
    _append_child(rendering_info, f"{_HC}rotMatrix", dict(identity))

    # Invisible/transparent line+fill+shadow -- the drop cap box itself is
    # never seen, only the enlarged character inside it.
    _append_child(el, f"{_HP}lineShape", {
        "color": "#000000", "width": "28", "style": "NONE",
        "endCap": "ROUND", "headStyle": "NORMAL", "tailStyle": "NORMAL",
        "headfill": "1", "tailfill": "1", "headSz": "SMALL_SMALL",
        "tailSz": "SMALL_SMALL", "outlineStyle": "NORMAL", "alpha": "0",
    })
    fill_brush = _append_child(el, f"{_HC}fillBrush", {})
    _append_child(fill_brush, f"{_HC}winBrush", {
        "faceColor": "#333399", "hatchColor": "#000000", "alpha": "0",
    })
    _append_child(el, f"{_HP}shadow", {
        "type": "NONE", "color": "#B2B2B2",
        "offsetX": "0", "offsetY": "0", "alpha": "0",
    })

    draw_text = _append_child(el, f"{_HP}drawText", {
        "lastWidth": w, "name": "", "editable": "0",
    })
    sub_list = _append_child(draw_text, f"{_HP}subList", {
        "id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK",
        "vertAlign": "CENTER", "linkListIDRef": "0", "linkListNextIDRef": "0",
        "textWidth": "0", "textHeight": "0", "hasTextRef": "0", "hasNumRef": "0",
    })
    inner_paragraph = _append_child(sub_list, f"{_HP}p", {
        "id": _paragraph_id(),
        "paraPrIDRef": str(para_pr_id_ref) if para_pr_id_ref is not None else "0",
        "styleIDRef": "0", "pageBreak": "0", "columnBreak": "0", "merged": "0",
    })
    inner_run = _append_child(inner_paragraph, f"{_HP}run", {
        "charPrIDRef": str(char_pr_id_ref) if char_pr_id_ref is not None else "0",
    })
    text_el = _append_child(inner_run, f"{_HP}t", {})
    text_el.text = character
    _append_child(inner_paragraph, f"{_HP}linesegarray")
    _append_child(draw_text, f"{_HP}textMargin", {
        "left": "0", "right": "0", "top": "0", "bottom": "0",
    })

    _append_child(el, f"{_HC}pt0", {"x": "0", "y": "0"})
    _append_child(el, f"{_HC}pt1", {"x": w, "y": "0"})
    _append_child(el, f"{_HC}pt2", {"x": w, "y": h})
    _append_child(el, f"{_HC}pt3", {"x": "0", "y": h})

    _append_child(el, f"{_HP}sz", {
        "width": w, "height": h,
        "widthRelTo": "ABSOLUTE", "heightRelTo": "ABSOLUTE", "protect": "1",
    })
    _append_child(el, f"{_HP}pos", {
        "treatAsChar": "0", "affectLSpacing": "0", "flowWithText": "1",
        "allowOverlap": "1", "holdAnchorAndSO": "0",
        "vertRelTo": "PARA", "horzRelTo": "PARA",
        "vertAlign": "TOP", "horzAlign": "LEFT",
        "vertOffset": "0", "horzOffset": "0",
    })
    _append_child(el, f"{_HP}outMargin", {
        "left": "0", "right": "850", "top": "0", "bottom": "0",
    })
    # AbstractShapeObjectType tail's last slot -- every other shape builder
    # in this codebase (pic/container) closes with an empty shapeComment
    # too; the real sample carries default Hancom alt-text ("사각형입니다.")
    # here, but that's autogenerated boilerplate for a plain rectangle, not
    # something meaningful to a drop cap, so this follows the established
    # empty-tail convention rather than reproducing wrong-genre text.
    _append_child(el, f"{_HP}shapeComment", {})

    parameterset = _append_child(el, f"{_HP}parameterset", dict(_TRIPLE_LINE_PARAMETERSET))
    list_param = _append_child(parameterset, f"{_HP}listParam", {"cnt": "1", "name": "12291"})
    int_param = _append_child(list_param, f"{_HP}unsignedintegerParam", {"name": "28673"})
    int_param.text = "2"

    return el
