# SPDX-License-Identifier: Apache-2.0
"""`doc.tables` — 표 탐색·매핑·병합·구조 편집.

표를 **만드는** 것은 루트에 남았다(`doc.add_table` — python-docx 대응이자
automation 최다 사용 저작 동사 중 하나). 만든 다음에 하는 일들이 여기 모인다.

`merge_table_cells` 는 이름의 `table_` 접두사를 네임스페이스가 흡수해
`merge_cells` 가 됐고, 반환 주석 `Any` 도 함께 고쳤다 — 5.x 는 런타임에
`HwpxOxmlTableCell` 을 돌려주면서 타입만 `Any` 라고 말하고 있었다.

이름표 옆 칸을 찾아 채우는 `find_cell_by_label`·`form_slots`·`fill_by_path` 는 양식의
뜻을 짐작하는 일이라 7.0에서 python-hwpx-automation(`hwpx_automation.forms`)으로
옮겼다. 표 지도(`map`)는 파일에 적힌 표를 그대로 보고하므로 남는다.
"""

from __future__ import annotations

from types import ModuleType
from typing import TYPE_CHECKING, Iterable, Iterator, overload

from ...model import Table, TableCell
from ._base import _LazyModule, _Namespace


# Named in annotations only; loaded when a hint is resolved (``import hwpx`` stays light).
def _load_table_navigation() -> ModuleType:
    from ...tools import table_navigation

    return table_navigation


if TYPE_CHECKING:
    from ...tools import table_navigation as _table_navigation
else:
    _table_navigation = _LazyModule(_load_table_navigation)

__all__ = ["TablesNamespace"]


class TablesNamespace(_Namespace):
    """표 탐색·매핑·병합·구조 편집."""

    __slots__ = ()
    _path = "doc.tables"

    @property
    def all(self) -> tuple["Table", ...]:
        """본문 문단에 바로 놓인 표를 문서 순서로.

        표 칸 안의 표, 머리말·꼬리말·각주·미주·글상자 안의 표는 들어 있지 않다.
        칸 안의 표는 그 칸에서(``cell.tables``, 본문 표와 칸 안의 표 모두는 :attr:`with_nested`),
        글까지 모두 훑으려면 ``doc.text.iter_blocks()``를 쓴다. ``len(doc.tables)``와
        ``for table in doc.tables``도 같은 범위다.
        """

        return tuple(table for paragraph in self._doc.paragraphs for table in paragraph.tables)

    @property
    def with_nested(self) -> tuple["Table", ...]:
        """본문의 표와 그 칸 안의 표(중첩 포함)를 표 지도(:meth:`map`)와 같은 순서·번호로.

        표 하나 뒤에 그 칸들의 표가(행 순서, 칸 순서, 칸 문단 순서로, 다시 그 안의 표까지)
        오고, 다음 표로 넘어간다. ``doc.tables.with_nested[i]`` 가 지도의
        ``table_index == i`` 인 표다. 머리말·꼬리말·각주·미주·글상자·캡션 안의 표는
        지도처럼 들어 있지 않다(그것까지는 ``doc.text.iter_objects(kinds="table")``).
        """

        found: list["Table"] = []

        def visit(table: "Table") -> None:
            found.append(table)
            for row in table.rows:
                for cell in row.cells:
                    for nested in cell.tables:
                        visit(nested)

        for paragraph in self._doc.paragraphs:
            for table in paragraph.tables:
                visit(table)
        return tuple(found)

    def __len__(self) -> int:
        return len(self.all)

    def __iter__(self) -> Iterator["Table"]:
        return iter(self.all)

    @overload
    def __getitem__(self, index: int) -> "Table": ...

    @overload
    def __getitem__(self, index: slice) -> tuple["Table", ...]: ...

    def __getitem__(self, index: int | slice) -> "Table | tuple[Table, ...]":
        """문서 순서의 ``index`` 번째 표(``doc.tables[0]``, ``doc.tables[-1]``, ``doc.tables[1:3]``).

        ``doc.tables.all[index]``와 같다. 범위 밖이면 ``HwpxIndexError``
        (``code="table-not-found"``, ``IndexError`` 이기도 하다).
        """

        tables = self.all
        if isinstance(index, slice):
            return tables[index]
        if isinstance(index, bool) or not isinstance(index, int):
            from ...errors import argument_type_error

            raise argument_type_error("index", index, "int or slice", suggestion="doc.tables[0] 처럼 번호로 고르세요.")
        try:
            return tables[index]
        except IndexError:
            from ...errors import HwpxIndexError

            raise HwpxIndexError(
                f"표 인덱스 {index} 가 범위를 벗어났습니다(표 {len(tables)}개).",
                code="table-not-found",
                context={"requested": index, "count": len(tables)},
                suggestion=(
                    f"이 문서의 표 인덱스는 0..{len(tables) - 1} 입니다. 칸 안의 표는 cell.tables 에 있습니다."
                    if tables else "이 문서 본문에는 표가 없습니다. 칸 안의 표는 cell.tables 에 있습니다."
                ),
            ) from None

    def map(self) -> "_table_navigation.TableMapResult":
        """모든 표의 위치·모양·헤더 미리보기를 담은 간결 지도."""

        from ...tools.table_navigation import get_table_map

        return get_table_map(self._doc)

    def merge_cells(self, table: "Table", cell_range: str) -> "TableCell":
        """``"A1:B2"`` 범위를 병합하고 살아남은 셀을 돌려준다.

        5.x 의 반환 주석은 ``Any`` 였지만 런타임 타입은 늘 셀이었다.
        """

        return table.merge_cells(cell_range)

    def insert_rows(
        self, table: "Table", ref_row: int, count: int = 1, *, side: str = "below", copy_content: bool = False
    ) -> None:
        """``ref_row`` 행 아래(``side="above"``면 위)에 빈 행 ``count``개를 한/글처럼 넣는다.

        새 칸은 같은 열 기준 칸의 서식(칸 속성·테두리/배경·여백·크기·문단 모양·글자 모양)만 받고 빈 문단 하나를 둔다.
        ``copy_content=True``면 기준 칸의 글·개체까지 복사한다.
        """

        table.insert_rows(ref_row, count, side=side, copy_content=copy_content)

    def insert_columns(
        self, table: "Table", ref_col: int, count: int = 1, *, side: str = "right", copy_content: bool = False
    ) -> None:
        """``ref_col`` 열 오른쪽(``side="left"``면 왼쪽)에 빈 열 ``count``개를 한/글처럼 넣는다(표가 넓어진다).

        ``copy_content=True``면 기준 칸의 글·개체까지 복사한다.
        """

        table.insert_columns(ref_col, count, side=side, copy_content=copy_content)

    def delete_rows(self, table: "Table", rows: int | Iterable[int]) -> None:
        """행을 지운다. 모든 행은 지울 수 없다(표 삭제를 쓴다)."""

        table.delete_rows(rows)

    def delete_columns(self, table: "Table", cols: int | Iterable[int]) -> None:
        """열을 지우고 그 폭을 남은 열에 나눈다. 모든 열은 지울 수 없다."""

        table.delete_columns(cols)

    def split_cell(self, table: "Table", row: int, col: int, *, rows: int = 1, cols: int = 1) -> None:
        """(``row``, ``col``) 칸을 ``rows`` 줄 × ``cols`` 칸으로 나눈다(한/글의 셀 나누기)."""

        table.split_cell(row, col, rows=rows, cols=cols)
