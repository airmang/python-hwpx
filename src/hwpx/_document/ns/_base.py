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
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable

from ..._removed_names import guard_arguments, removed_name_error


class _LazyModule:
    """A module imported on its first attribute access, by the loader function given.

    A namespace method's annotations must resolve under :func:`typing.get_type_hints`
    (tool-schema builders call it on every method), so the names they use are bound at
    run time. A type from a module ``import hwpx`` must not load (``hwpx.tools``,
    ``hwpx.form_fit``) or that would close an import cycle (``hwpx.document``) is named
    through one of these instead, as ``"_module.Name"``: resolving the hint runs the
    loader (a plain ``from ... import module``) then, and ``import hwpx`` stays as light
    as before.
    """

    __slots__ = ("_load",)

    def __init__(self, load: Callable[[], ModuleType]) -> None:
        self._load = load

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._load(), attribute)

    def __repr__(self) -> str:
        return f"<lazy module {self._load.__name__}>"


def _load_document() -> ModuleType:
    from ... import document

    return document


if TYPE_CHECKING:
    from ... import document as _document
else:
    _document = _LazyModule(_load_document)


class _Namespace:
    """문서 하나에 묶인 도메인 표면."""

    __slots__ = ("_doc",)

    #: `doc.<이 이름>`으로 접근하는 경로. 오류 메시지·`__repr__`에 쓰인다.
    _path = "doc"

    def __init__(self, document: "_document.HwpxDocument") -> None:
        self._doc = document

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """공개 메서드마다 7.0에서 없어지거나 바뀐 인자의 안내를 붙인다.

        :data:`hwpx._removed_names.ARGUMENTS` 의 ``"doc.<묶음>.<메서드>"`` 줄(옛 키워드 → 새 키워드,
        키워드 전용이 된 위치 인자)과, 구역을 받는 메서드(``section=``)에는 ``section_index=``·
        ``style_id_ref=`` 를 본다. 옛 이름을 주면 평범한 ``TypeError`` 대신 새 이름을 알려 준다.
        묶음마다 손으로 붙이지 않고 여기 한 곳에서 붙인다 — 새 메서드도, 표의 새 줄도 따라온다.
        """

        super().__init_subclass__(**kwargs)
        for name, member in list(vars(cls).items()):
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            everywhere = "section" in inspect.signature(member).parameters
            guarded = guard_arguments(member, f"{cls._path}.{name}", removed_everywhere=everywhere)
            if guarded is not member:
                setattr(cls, name, guarded)

    @property
    def document(self) -> "_document.HwpxDocument":
        """이 네임스페이스가 붙어 있는 문서."""

        return self._doc

    if not TYPE_CHECKING:  # 타입 검사기에는 숨긴다: 없는 이름을 정적으로 계속 잡게.

        def __getattr__(self, name: str) -> Any:
            """7.0에서 없어지거나 옮긴 이름(``doc.text.runs``, ``doc.text.markdown`` 등)이면 새 자리를 알려 준다.

            표는 :data:`hwpx._removed_names.NAMES` 의 ``"doc.<묶음>"`` 칸이다.
            ``HwpxAttributeError`` 는 ``AttributeError`` 이기도 해서 ``hasattr`` 은 ``False`` 다.
            """

            error = removed_name_error(type(self)._path, name)
            if error is None:
                error = AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
            error.name = name
            error.obj = self
            raise error

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._path}>"
