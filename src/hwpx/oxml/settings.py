# SPDX-License-Identifier: Apache-2.0
"""``settings.xml`` (``ha:HWPApplicationSetting``) read model.

실코퍼스 177파일 전수 실측: 이 파트는 OWPML 스키마 문서(``DevDoc/OWPML SCHEMA``)
어디에도 선언돼 있지 않다 — 완전성 감사가 "census 맹점"으로 지적한 자리
그대로다(``ha:*`` 네임스페이스 통째로 모집단 밖이었다). 아래 모델은 스키마가
아니라 실문서에서 직접 역설계했다.

구조(177/177 관측): ``ha:HWPApplicationSetting`` 루트에
``ha:CaretPosition``(177/177, listIDRef/paraIDRef/pos)와 최대 1개의
``config:config-item-set``(77/177 — 전부 ``name="PrintInfo"``)가 자식으로
온다. ``config:`` 네임스페이스는 Hancom 고유 어휘가 아니라 OASIS ODF 1.0의
config 스키마(``urn:oasis:...:config:1.0``)를 그대로 재사용한 것이다.
관측된 config-item 8종은 전부 ``type="boolean"`` 또는 ``"short"`` 이지만,
ODF 스펙 도메인(int/long/double/string/datetime/base64Binary)을 전부
받는다 — 이름·값 보존형 모델이지 하드코딩 열거가 아니다(문단 탭 정의
트레인의 같은 원칙).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from lxml import etree

from .utils import local_name, parse_bool, parse_int, text_or_none

__all__ = [
    "ApplicationSettings",
    "CaretPosition",
    "ConfigItem",
    "ConfigItemSet",
    "parse_application_settings",
    "parse_caret_position",
    "parse_config_item",
    "parse_config_item_set",
]


@dataclass(slots=True)
class CaretPosition:
    """``ha:CaretPosition`` — 마지막 저장 시점의 커서 위치(177/177 관측)."""

    list_id_ref: Optional[int]
    para_id_ref: Optional[int]
    pos: Optional[int]


@dataclass(slots=True)
class ConfigItem:
    """``config:config-item`` — ODF config 스키마 그대로 보존한다.

    ``value``는 ``type``에 따라 코어싱한다(boolean/short/int/long/double →
    파이썬 타입, 그 외 타입은 원문 문자열 그대로 — ODF 스펙은
    string/datetime/base64Binary도 허용한다).
    """

    name: str
    type: str
    raw_value: Optional[str]

    @property
    def value(self) -> "bool | int | float | str | None":
        if self.raw_value is None:
            return None
        if self.type == "boolean":
            return parse_bool(self.raw_value, default=False)
        if self.type in ("short", "int", "long"):
            try:
                return int(self.raw_value)
            except ValueError:
                return self.raw_value
        if self.type == "double":
            try:
                return float(self.raw_value)
            except ValueError:
                return self.raw_value
        return self.raw_value


@dataclass(slots=True)
class ConfigItemSet:
    """``config:config-item-set`` — 이름 있는 설정 그룹(실코퍼스는
    ``PrintInfo`` 하나만 관측했으나, 이름·항목 어휘를 하드코딩하지 않고
    문서가 실제로 가진 대로 보존한다— 문서마다 다를 수 있다)."""

    name: str
    items: Dict[str, ConfigItem] = field(default_factory=dict)


@dataclass(slots=True)
class ApplicationSettings:
    """``ha:HWPApplicationSetting`` — ``settings.xml`` 파트 루트."""

    caret_position: Optional[CaretPosition] = None
    config_item_sets: Dict[str, ConfigItemSet] = field(default_factory=dict)


def parse_caret_position(node: etree._Element) -> CaretPosition:
    return CaretPosition(
        list_id_ref=parse_int(node.get("listIDRef")),
        para_id_ref=parse_int(node.get("paraIDRef")),
        pos=parse_int(node.get("pos")),
    )


def parse_config_item(node: etree._Element) -> ConfigItem:
    return ConfigItem(
        name=node.get("name") or "",
        type=node.get("type") or "string",
        raw_value=text_or_none(node),
    )


def parse_config_item_set(node: etree._Element) -> ConfigItemSet:
    items: Dict[str, ConfigItem] = {}
    for child in node:
        if local_name(child) != "config-item":
            continue
        item = parse_config_item(child)
        if item.name:
            items[item.name] = item
    return ConfigItemSet(name=node.get("name") or "", items=items)


def parse_application_settings(node: etree._Element) -> ApplicationSettings:
    root_name = local_name(node)
    if root_name != "HWPApplicationSetting":
        from ..errors import HwpxValueError

        # 태그 리터럴 형태(<ha:...>)를 메시지에 안 쓴다 — 원장 write 분류기가
        # 여는 태그 리터럴 근방을 api로 오인한다(감사 §3-C2와 같은 부류의
        # 오탐, hp:lineseg 선례 그대로).
        raise HwpxValueError(
            "expected a settings.xml root named HWPApplicationSetting, "
            f"got {root_name!r}",
            code="document-settings-root-invalid",
            context={"requested": root_name},
        )

    caret_position: Optional[CaretPosition] = None
    config_item_sets: Dict[str, ConfigItemSet] = {}
    for child in node:
        name = local_name(child)
        if name == "CaretPosition":
            caret_position = parse_caret_position(child)
        elif name == "config-item-set":
            item_set = parse_config_item_set(child)
            if item_set.name:
                config_item_sets[item_set.name] = item_set
    return ApplicationSettings(
        caret_position=caret_position,
        config_item_sets=config_item_sets,
    )
