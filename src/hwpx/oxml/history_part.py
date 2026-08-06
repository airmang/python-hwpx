# SPDX-License-Identifier: Apache-2.0
"""``history.xml`` (``hhs:*``) read model — schema-only, corpus-unverified.

**정직 표기**: 이 파트는 실코퍼스에 0건이다 — 벤더드 47파일(``hwpxlib_corpus``)
전수와, 접근 가능한 개인 실문서 6,262건(홈 디렉터리 전수 검색, DIVE-2 연구
문서군 등)을 찾아봤지만 ``history.xml``을 가진 문서를 하나도 못 찾았다(변경
이력 저장을 켠 문서에서만 생기는 옵션 파트로 보인다 — 같은 검색이
``masterpage*.xml``은 110건 찾아 그 부재가 검색 범위의 한계가 아님을
뒷받침한다). 이 모듈은 순전히 ``DevDoc/OWPML SCHEMA/Document History XML
schema.xml``에서 유도했다 — 실측 대조가 전혀 없다.

이 신중함은 근거가 있다: 같은 2024 초안 스키마 계열의 ``version.xml``·
``masterpage.xml``이 둘 다 실 산출물과 어긋났다(``version_part.py``·
``master_page.py`` 참조 — 루트 이름·네임스페이스가 다르거나 아예 없었다).
그래서 여기서는 ``historyEntry``의 평평한 메타데이터(리비전 번호·날짜·
작성자·설명·잠금·자동저장 — 스키마가 안정적으로 보이는 부분)만 타입 있는
필드로 옮기고, 중첩되는 diff 본문(``insert``/``update``/``delete``/
``position``, ``update``는 재귀적으로 서로를 포함할 수 있다)은 전용
데이터클래스로 못박지 않는다 — 실 문서 하나 없이 그 중첩 규칙을 확정하면
틀렸을 때 조용히 틀린다. 대신 ``DiffNode``(태그·속성·자식 재귀)로 원문
구조를 보존한 채 노출한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree  # type: ignore[reportAttributeAccessIssue]  # lxml has no complete bundled typing

from .utils import local_name, parse_bool, parse_int, text_or_none

__all__ = [
    "DiffNode",
    "History",
    "HistoryEntry",
    "parse_history",
]

#: 스키마가 diff 어휘로 선언하는 4개 태그 이름 — 검증에는 쓰지 않는다
#: (스키마 자체가 corpus-unverified이므로 미관측 태그를 거부하면 실물을
#: 무음으로 오탐할 위험이 검증 이득보다 크다). 문서화 목적으로만 남긴다.
DIFF_OP_NAMES = frozenset({"insert", "update", "delete", "position"})


@dataclass(slots=True)
class DiffNode:
    """``insert``/``update``/``delete``/``position`` 원문 구조 그대로.

    스키마상 ``path``(``DiffDataType`` 공통)·``update``의 ``oldValue``만
    이름 있는 필드로 뽑고, 나머지 속성은 ``attributes``에 원문 그대로
    보존한다 — 재귀 자식은 ``children``. ``text``는 ``delete``
    (``DeleteType``, ``mixed="true"``)가 직접 담을 수 있는 텍스트 — 다른
    세 op은 스키마상 element-only라 관측상 빈 문자열이 된다.
    """

    op: str
    path: str | None
    old_value: str | None
    text: str | None
    attributes: dict[str, str]
    children: list["DiffNode"] = field(default_factory=list)


@dataclass(slots=True)
class HistoryEntry:
    """``hhs:historyEntry`` — 리비전 하나.

    ``package_diff``/``head_diff``/``tail_diff``는 스키마상 최대 1개,
    ``body_diff``는 스키마상 무제한(``maxOccurs="unbounded"``)이라 리스트.
    """

    revision_number: int | None
    revision_date: str | None
    revision_author: str | None
    revision_desc: str | None
    revision_lock: bool | None
    auto_save: bool | None
    package_diff: DiffNode | None
    head_diff: DiffNode | None
    body_diffs: list[DiffNode] = field(default_factory=list)
    tail_diff: DiffNode | None = None


@dataclass(slots=True)
class History:
    """``hhs:history`` — ``history.xml`` 파트 루트."""

    version: str | None
    entries: list[HistoryEntry] = field(default_factory=list)


def _parse_diff_entry(node: etree._Element) -> DiffNode | None:
    """``DiffEntryType``(insert/update/delete/position 중 하나를 무제한
    나열) — 첫 자식 하나를 ``DiffNode``로 감싼다. 여러 개면 나머지는
    ``children``으로 접히지 않고 유실될 수 있다(스키마가 여러 op를 나열할
    수 있다는데 실 사례가 없어 정확한 그룹핑 규칙을 모른다 — 정직 한계)."""

    for child in node:
        return _parse_diff_op(child)
    return None


def _parse_diff_op(node: etree._Element) -> DiffNode:
    name = local_name(node)
    attrs = dict(node.attrib)
    path = attrs.pop("path", None)
    old_value = attrs.pop("oldValue", None)
    children = [_parse_diff_op(child) for child in node]
    return DiffNode(
        op=name, path=path, old_value=old_value, text=text_or_none(node),
        attributes=attrs, children=children,
    )


def _parse_history_entry(node: etree._Element) -> HistoryEntry:
    package_diff: DiffNode | None = None
    head_diff: DiffNode | None = None
    tail_diff: DiffNode | None = None
    body_diffs: list[DiffNode] = []
    for child in node:
        name = local_name(child)
        if name == "packageDiff":
            package_diff = _parse_diff_entry(child)
        elif name == "headDiff":
            head_diff = _parse_diff_entry(child)
        elif name == "bodyDiff":
            parsed = _parse_diff_entry(child)
            if parsed is not None:
                body_diffs.append(parsed)
        elif name == "tailDiff":
            tail_diff = _parse_diff_entry(child)
    return HistoryEntry(
        revision_number=parse_int(node.get("revisionNumber")),
        revision_date=node.get("revisionDate"),
        revision_author=node.get("revisionAuthor"),
        revision_desc=node.get("revisionDesc"),
        revision_lock=parse_bool(node.get("revisionLock"), default=False),
        auto_save=parse_bool(node.get("autoSave"), default=False),
        package_diff=package_diff,
        head_diff=head_diff,
        body_diffs=body_diffs,
        tail_diff=tail_diff,
    )


def parse_history(node: etree._Element) -> History:
    root_name = local_name(node)
    if root_name != "history":
        from ..errors import HwpxValueError

        raise HwpxValueError(
            "expected a history.xml root named history, "
            f"got {root_name!r}",
            code="document-history-root-invalid",
            context={"requested": root_name},
        )
    entries = [
        _parse_history_entry(child)
        for child in node
        if local_name(child) == "historyEntry"
    ]
    return History(version=node.get("version"), entries=entries)
