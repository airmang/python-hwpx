# SPDX-License-Identifier: Apache-2.0
"""`doc.parts` — OPC 파트 접근(`header.xml`·바탕쪽·이력·버전).

## 왜 이 네임스페이스가 생겼나 — 이름 충돌 해소

5.x의 `doc.headers`는 **쪽 머리말이 아니라** `Contents/header.xml` 파트 목록
이었다. 그런데 같은 객체에 `set_header_text`·`remove_header`가 나란히 있어서,
`doc.headers`를 쪽 머리말로 읽는 것이 자연스러웠다. 이름 하나가 두 가지를
가리키는 상태였다.

6.0은 둘을 갈라 놓는다:

- `doc.parts.headers` — 스타일·문단모양 등 **정의가 사는 파트**
- `doc.page.set_header(...)` — 인쇄되는 **쪽 머리말**

`doc.version` 도 같은 부류였다. 그건 라이브러리 버전(`hwpx.__version__`)이
아니라 패키지의 `version.xml` 파트다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import _Namespace

if TYPE_CHECKING:
    from ...oxml import (
        HwpxOxmlHeader,
        HwpxOxmlHistory,
        HwpxOxmlMasterPage,
        HwpxOxmlVersion,
    )

__all__ = ["PartsNamespace"]


class PartsNamespace(_Namespace):
    """OPC 파트 접근 — `header.xml`·바탕쪽·이력·버전."""

    __slots__ = ()
    _path = "doc.parts"

    @property
    def headers(self) -> list["HwpxOxmlHeader"]:
        """문서가 참조하는 `Contents/header.xml` 파트들.

        쪽 머리말이 아니다 — 그쪽은 `doc.page.set_header(...)`.
        """

        return self._doc.oxml.headers

    @property
    def master_pages(self) -> list["HwpxOxmlMasterPage"]:
        """매니페스트가 선언한 바탕쪽 파트들."""

        return self._doc.oxml.master_pages

    @property
    def histories(self) -> list["HwpxOxmlHistory"]:
        """매니페스트가 참조하는 문서 이력 파트들."""

        return self._doc.oxml.histories

    @property
    def version(self) -> "HwpxOxmlVersion | None":
        """패키지의 `version.xml` 파트. 라이브러리 버전이 아니다."""

        return self._doc.oxml.version
