# SPDX-License-Identifier: Apache-2.0
"""도메인 네임스페이스의 공통 베이스.

6.0의 `HwpxDocument` 루트는 34개다. 5.x의 나머지 표면은 이 베이스를 상속한
11개 네임스페이스(`doc.styles`, `doc.page`, `doc.fields` …)로 옮겨간다.
네임스페이스는 **상태를 갖지 않는다** — 문서 하나를 붙들고 소유 모듈
(`hwpx/_document/*.py`)로 위임할 뿐이다. 그래서 두 번 접근해도 같은 값을
보고, 문서가 바뀌면 즉시 따라간다.

경계 규칙(설계서 §9): 이 파일과 형제 모듈의 **클래스 정의·`_doc` 결합**은
WP-A 소유다. 각 네임스페이스의 **메서드 본문**은 WP-B1/B2/B3이 채운다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...document import HwpxDocument


class _Namespace:
    """문서 하나에 묶인 도메인 표면."""

    __slots__ = ("_doc",)

    #: `doc.<이 이름>`으로 접근하는 경로. 오류 메시지·`__repr__`에 쓰인다.
    _path = "doc"

    def __init__(self, document: "HwpxDocument") -> None:
        self._doc = document

    @property
    def document(self) -> "HwpxDocument":
        """이 네임스페이스가 붙어 있는 문서."""

        return self._doc

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._path}>"
