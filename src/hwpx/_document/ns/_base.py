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

import inspect
from typing import TYPE_CHECKING, Any

from ...errors import rejects_removed_arguments

if TYPE_CHECKING:
    from ...document import HwpxDocument


class _Namespace:
    """문서 하나에 묶인 도메인 표면."""

    __slots__ = ("_doc",)

    #: `doc.<이 이름>`으로 접근하는 경로. 오류 메시지·`__repr__`에 쓰인다.
    _path = "doc"

    def __init__(self, document: "HwpxDocument") -> None:
        self._doc = document

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """구역을 받는 메서드(``section=``)에 7.0에서 없어진 인자 안내를 붙인다.

        ``section_index=``·``style_id_ref=`` 를 주면 평범한 ``TypeError`` 대신
        :func:`hwpx.errors.rejects_removed_arguments` 가 ``section=``·``style=`` 을
        알려 준다. 묶음마다 손으로 붙이지 않고 여기 한 곳에서 붙인다 — 새 메서드도 따라온다.
        """

        super().__init_subclass__(**kwargs)
        for name, member in list(vars(cls).items()):
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            if "section" in inspect.signature(member).parameters:
                setattr(cls, name, rejects_removed_arguments(member, caller=f"{cls._path}.{name}"))

    @property
    def document(self) -> "HwpxDocument":
        """이 네임스페이스가 붙어 있는 문서."""

        return self._doc

    if not TYPE_CHECKING:  # 타입 검사기에는 숨긴다: 없는 이름을 정적으로 계속 잡게.

        def __getattr__(self, name: str) -> Any:
            """7.0에서 python-hwpx-automation으로 옮긴 메서드(``doc.text.markdown`` 등)면 새 자리를 알려 준다.

            ``HwpxAttributeError`` 는 ``AttributeError`` 이기도 해서 ``hasattr`` 은 ``False`` 다.
            """

            from .._legacy import moved_method_error

            error = moved_method_error(type(self)._path, name)
            if error is None:
                error = AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
            error.name = name
            error.obj = self
            raise error

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._path}>"
