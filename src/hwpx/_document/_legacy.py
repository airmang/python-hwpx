# SPDX-License-Identifier: Apache-2.0
"""루트 ``HwpxDocument`` 의 없어진 이름 — :mod:`hwpx._removed_names` 표의 ``"doc"`` 칸을 보는 창.

안내 표는 :mod:`hwpx._removed_names` 하나다. 이 모듈은 그 가운데 루트 칸과 묶음에서 옮긴
메서드를 6.x·#723·#726 때의 이름으로 다시 보인다(테스트·``describe_capabilities()``·문서 검사가 읽는다).
행을 더하거나 고칠 곳은 :data:`hwpx._removed_names.NAMES` 다.

6.0은 루트 표면을 102개에서 34개로 줄이고 옮겨 간 79개 이름을 경고와 함께 남겨 두었고, 7.0은
그 예고를 실행했다. 7.0은 저장 동사 셋(``save_to_path``·``save_to_stream``·``save_report``)과
``from_package`` 도 지웠다. 지운 이름을 부르면 파이썬의 밋밋한 ``AttributeError`` 대신 그 이름이
어디로 갔는지 한 줄 예와 함께 알려 준다::

    >>> doc.set_header_text("머리말")
    HwpxAttributeError: doc.set_header_text 는 python-hwpx 7.0에서 없어졌습니다.
    doc.page.set_header(text=...) 를 쓰세요. 예: doc.page.set_header(text="머리말")

오류는 :class:`~hwpx.errors.HwpxAttributeError` (``AttributeError`` 이기도 하다)라서
``hasattr(doc, "set_header_text")`` 는 ``False`` 이고 ``getattr(doc, name, None)`` 도 ``None`` 이다.
``moving`` 인 이름(``export_markdown`` 등 5개)과 :data:`MOVED_METHODS` 8개는 7.0에서
python-hwpx-automation 으로 옮겼다(code ``document-name-moved``).
"""

from __future__ import annotations

from .._removed_names import (
    AUTOMATION_INSTALL,
    MIGRATION_GUIDE_6_0_URL,
    MIGRATION_GUIDE_7_0_URL,
    NAMES,
    REMOVED_IN,
    Moved,
    Removed,
    removed_name_error as _removed_name_error,
)
from ..errors import HwpxError

__all__ = [
    "AUTOMATION_INSTALL",
    "LEGACY_REMOVED_IN",
    "MIGRATION_GUIDE_URL",
    "MOVED_GUIDE_URL",
    "MOVED_IN",
    "MOVED_METHODS",
    "MovedMethod",
    "REMOVED_NAMES",
    "RemovedName",
    "moved_method_error",
    "removed_name_error",
]

#: 옛 이름이 사라진 major. ``describe_capabilities()`` 가 이 값을 보고한다.
LEGACY_REMOVED_IN = REMOVED_IN
MOVED_IN = REMOVED_IN
MIGRATION_GUIDE_URL = MIGRATION_GUIDE_6_0_URL
MOVED_GUIDE_URL = MIGRATION_GUIDE_7_0_URL

MovedMethod = Moved
RemovedName = Removed

#: 7.0에서 없어진 루트 이름 → 새 자리(표의 ``"doc"`` 칸 그대로).
REMOVED_NAMES: dict[str, Removed] = NAMES["doc"]

#: 7.0에서 묶음에서 빠져 python-hwpx-automation 으로 옮긴 메서드: ``"doc.<묶음>.<이름>"`` → 새 자리.
MOVED_METHODS: dict[str, Moved] = {
    f"{owner}.{name}": entry.moved
    for owner, rows in NAMES.items()
    if owner.startswith("doc.")
    for name, entry in rows.items()
    if entry.moved is not None
}


def removed_name_error(name: str) -> HwpxError | None:
    """*name* 이 7.0에서 지운 루트 이름이면 그 자리를 알려 주는 오류를, 아니면 ``None``."""

    return _removed_name_error("doc", name)


def moved_method_error(path: str, name: str) -> HwpxError | None:
    """``doc.<묶음>.<name>`` 이 7.0에서 옮긴 메서드면 새 자리를 알려 주는 오류를, 아니면 ``None``."""

    if f"{path}.{name}" not in MOVED_METHODS:
        return None
    return _removed_name_error(path, name)
