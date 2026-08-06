# SPDX-License-Identifier: Apache-2.0
"""Simple package-part OXML wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING
import xml.etree.ElementTree as ET

from ._document_primitives import _serialize_xml

if TYPE_CHECKING:
    from .document_parts import HwpxOxmlDocument
    from .history_part import History
    from .master_page import MasterPage
    from .settings import ApplicationSettings
    from .version_part import HcfVersion


class _HwpxOxmlSimplePart:
    """Common base for standalone XML parts that are not sections or headers."""

    def __init__(
        self,
        part_name: str,
        element: ET.Element,
        document: "HwpxOxmlDocument" | None = None,  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
    ):
        self.part_name = part_name
        self._element = element
        self._document = document
        self._dirty = False

    @property
    def element(self) -> ET.Element:
        return self._element

    @property
    def document(self) -> "HwpxOxmlDocument" | None:  # type: ignore[reportGeneralTypeIssues]  # frozen public annotation
        return self._document

    def attach_document(self, document: "HwpxOxmlDocument") -> None:
        self._document = document

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def reset_dirty(self) -> None:
        self._dirty = False

    def replace_element(self, element: ET.Element) -> None:
        self._element = element
        self.mark_dirty()

    def to_bytes(self) -> bytes:
        return _serialize_xml(self._element)


class HwpxOxmlMasterPage(_HwpxOxmlSimplePart):
    """Represents a master page part in the package.

    실코퍼스 1파일 실측 기반 역설계(스키마 미선언 루트 네임스페이스 —
    :mod:`.master_page` 독스트링 참조). 읽기 전용: 이 트레인은 원장 read=none
    해소가 목표라 쓰기 경로는 열지 않는다.
    """

    def to_model(self) -> "MasterPage":
        from .master_page import parse_master_page

        return parse_master_page(self._element)


class HwpxOxmlHistory(_HwpxOxmlSimplePart):
    """Represents a document history part.

    스키마 전용 역설계, 실코퍼스 0건(``.history_part`` 독스트링 참조) — 실
    문서 하나 확보 전까지 잠정으로 표기한다. 읽기 전용: 이 트레인은 원장
    read=none 해소가 목표라 쓰기 경로는 열지 않는다.
    """

    def to_model(self) -> "History":
        from .history_part import parse_history

        return parse_history(self._element)


class HwpxOxmlVersion(_HwpxOxmlSimplePart):
    """Represents the ``version.xml`` part.

    실코퍼스 47/47 전수 실측 기반 역설계(스키마 미선언 루트 네임스페이스 —
    :mod:`.version_part` 독스트링 참조). 읽기 전용: 이 트레인은 원장 read=none
    해소가 목표라 쓰기 경로는 열지 않는다.
    """

    def to_model(self) -> "HcfVersion":
        from .version_part import parse_hcf_version

        return parse_hcf_version(self._element)


class HwpxOxmlSettings(_HwpxOxmlSimplePart):
    """Represents the ``settings.xml`` part (``ha:HWPApplicationSetting``).

    실코퍼스 177파일 전수 실측 기반 역설계(스키마 미선언 — :mod:`.settings`
    독스트링 참조). 읽기 전용: 이 트레인은 원장 read=none 해소가 목표라
    쓰기 경로는 열지 않는다.
    """

    def to_model(self) -> "ApplicationSettings":
        from .settings import parse_application_settings

        return parse_application_settings(self._element)


__all__ = [
    "HwpxOxmlHistory",
    "HwpxOxmlMasterPage",
    "HwpxOxmlSettings",
    "HwpxOxmlVersion",
]
