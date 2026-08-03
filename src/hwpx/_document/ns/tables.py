# SPDX-License-Identifier: Apache-2.0
"""`doc.tables` — 표 탐색·매핑·병합·경로 채움.

표를 **만드는** 것은 루트에 남았다(`doc.add_table` — python-docx 대응이자
automation 최다 사용 저작 동사 중 하나). 만든 다음에 하는 일들이 여기 모인다.

`merge_table_cells` 는 이름의 `table_` 접두사를 네임스페이스가 흡수해
`merge_cells` 가 됐고, 반환 주석 `Any` 도 함께 고쳤다 — 5.x 는 런타임에
`HwpxOxmlTableCell` 을 돌려주면서 타입만 `Any` 라고 말하고 있었다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from ._base import _Namespace

if TYPE_CHECKING:
    from ...model import Table, TableCell
    from ...tools.table_navigation import (
        SearchDirection,
        TableFillResult,
        TableLabelSearchResult,
        TableMapResult,
    )

__all__ = ["TablesNamespace"]


class TablesNamespace(_Namespace):
    """표 탐색·매핑·병합·경로 채움."""

    __slots__ = ()
    _path = "doc.tables"

    @property
    def all(self) -> list["Table"]:
        """문서의 모든 표를 문서 순서로."""

        tables: list["Table"] = []
        for paragraph in self._doc.paragraphs:
            tables.extend(paragraph.tables)
        return tables

    def __len__(self) -> int:
        return len(self.all)

    def __iter__(self):
        return iter(self.all)

    def map(self) -> "TableMapResult":
        """모든 표의 위치·모양·헤더 미리보기를 담은 간결 지도."""

        from ...tools.table_navigation import get_table_map

        return get_table_map(self._doc)

    def find_cell_by_label(
        self, label_text: str, direction: "SearchDirection" = "right"
    ) -> "TableLabelSearchResult":
        """라벨 셀과 그 옆(기본 오른쪽) 대상 셀 쌍을 전부 찾는다."""

        from ...tools.table_navigation import find_cell_by_label

        return find_cell_by_label(self._doc, label_text, direction)

    def fill_by_path(self, mappings: Mapping[str, str]) -> "TableFillResult":
        """``표/행/열`` 경로 → 값 매핑으로 셀을 채운다."""

        from ...tools.table_navigation import fill_by_path

        return fill_by_path(self._doc, mappings)

    def merge_cells(self, table: "Table", cell_range: str) -> "TableCell":
        """``"A1:B2"`` 범위를 병합하고 살아남은 셀을 돌려준다.

        5.x 의 반환 주석은 ``Any`` 였지만 런타임 타입은 늘 셀이었다.
        """

        return table.merge_cells(cell_range)
