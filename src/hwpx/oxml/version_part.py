# SPDX-License-Identifier: Apache-2.0
"""``version.xml`` (``hv:HCFVersion``) read model.

실코퍼스 47/47 전수 실측(``hwpxlib_corpus``): ``DevDoc/OWPML SCHEMA/Version
XML schema.xml``이 선언하는 2024 초안 스키마(루트 이름 ``version``, 네임스페이스
``http://www.owpml.org/owpml/2024/version``)는 실 산출물과 다르다 — 실 문서의
루트는 ``hv:HCFVersion``(``http://www.hancom.co.kr/hwpml/2011/version``)이고,
``targetApplication``이 아니라 오탈자 그대로인 ``tagetApplication``('r' 누락)을
쓴다. ``바탕쪽``(``master_page.py``)에서도 같은 부류의 2024 초안-대-2011 실물
드리프트가 확인됐다 — 이 파트군은 스키마가 아니라 실코퍼스가 진실 원천이다.

필수 8개 속성(``tagetApplication``·``major``·``minor``·``micro``·
``buildNumber``·``xmlVersion``·``application``·``appVersion``)은 47/47 전량
관측, ``os``만 46/47(옵션)."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from .utils import local_name, parse_int

__all__ = ["HcfVersion", "parse_hcf_version"]


@dataclass(slots=True)
class HcfVersion:
    """``hv:HCFVersion`` — ``version.xml`` 파트 루트.

    ``taget_application``은 실 산출물 속성의 오탈자(``tagetApplication``)를
    그대로 보존한 이름이다 — 정정하지 않는다(정정하면 실제 파일의 속성명과
    다시 멀어진다).
    """

    taget_application: str | None
    major: int | None
    minor: int | None
    micro: int | None
    build_number: int | None
    os: int | None
    xml_version: str | None
    application: str | None
    app_version: str | None


def parse_hcf_version(node: etree._Element) -> HcfVersion:
    root_name = local_name(node)
    if root_name != "HCFVersion":
        from ..errors import HwpxValueError

        raise HwpxValueError(
            "expected a version.xml root named HCFVersion, "
            f"got {root_name!r}",
            code="document-version-root-invalid",
            context={"requested": root_name},
        )
    return HcfVersion(
        taget_application=node.get("tagetApplication"),
        major=parse_int(node.get("major")),
        minor=parse_int(node.get("minor")),
        micro=parse_int(node.get("micro")),
        build_number=parse_int(node.get("buildNumber")),
        os=parse_int(node.get("os")),
        xml_version=node.get("xmlVersion"),
        application=node.get("application"),
        app_version=node.get("appVersion"),
    )
