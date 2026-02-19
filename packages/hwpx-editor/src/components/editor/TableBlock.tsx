"use client";

import { useRef, useCallback, useEffect, useMemo, useState } from "react";
import type { TableVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { pxToHwp, hwpToPx } from "@/lib/hwp-units";
import { TableCell } from "./TableCell";

interface TableBlockProps {
  table: TableVM;
  sectionIndex: number;
  paragraphIndex: number;
}

interface TableContextMenuState {
  x: number;
  y: number;
  source: "cell" | "table";
}

interface TableContextMenuItem {
  key: string;
  label: string;
  disabled?: boolean;
  danger?: boolean;
  dividerAfter?: boolean;
  action: () => void;
}

/** Invisible drag handle for column boundary. */
function ColumnResizeHandle({
  colIdx,
  tableHeight,
  sectionIndex,
  paragraphIndex,
  tableIndex,
}: {
  colIdx: number;
  tableHeight: number;
  sectionIndex: number;
  paragraphIndex: number;
  tableIndex: number;
}) {
  const resizeTableColumn = useEditorStore((s) => s.resizeTableColumn);
  const startXRef = useRef(0);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      startXRef.current = e.clientX;

      const onMouseMove = () => {
        // visual feedback is handled by cursor; actual resize on mouseup
      };

      const onMouseUp = (me: MouseEvent) => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";
        const deltaX = me.clientX - startXRef.current;
        if (Math.abs(deltaX) < 2) return;
        const deltaHwp = pxToHwp(deltaX);
        resizeTableColumn(sectionIndex, paragraphIndex, tableIndex, colIdx, deltaHwp);
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "col-resize";
    },
    [colIdx, sectionIndex, paragraphIndex, tableIndex, resizeTableColumn],
  );

  return (
    <div
      onMouseDown={onMouseDown}
      className="absolute top-0 z-10"
      style={{
        width: 6,
        height: tableHeight || "100%",
        cursor: "col-resize",
        marginLeft: -3,
      }}
    />
  );
}

export function TableBlock({ table, sectionIndex, paragraphIndex }: TableBlockProps) {
  const tableRef = useRef<HTMLDivElement>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const setSelection = useEditorStore((s) => s.setSelection);
  const selection = useEditorStore((s) => s.selection);
  const insertBlockAt = useEditorStore((s) => s.insertBlockAt);
  const deleteTable = useEditorStore((s) => s.deleteTable);
  const insertTableRow = useEditorStore((s) => s.insertTableRow);
  const insertTableColumn = useEditorStore((s) => s.insertTableColumn);
  const deleteTableRow = useEditorStore((s) => s.deleteTableRow);
  const deleteTableColumn = useEditorStore((s) => s.deleteTableColumn);
  const mergeTableCells = useEditorStore((s) => s.mergeTableCells);
  const splitTableCell = useEditorStore((s) => s.splitTableCell);
  const insertNestedTableInCell = useEditorStore((s) => s.insertNestedTableInCell);
  const focusParentTable = useEditorStore((s) => s.focusParentTable);
  const nestedTableFocus = useEditorStore((s) => s.nestedTableFocus);
  const setSidebarTab = useEditorStore((s) => s.setSidebarTab);
  const toggleSidebar = useEditorStore((s) => s.toggleSidebar);
  const sidebarOpen = useEditorStore((s) => s.uiState.sidebarOpen);
  const [contextMenu, setContextMenu] = useState<TableContextMenuState | null>(null);
  const [tableHeightPx, setTableHeightPx] = useState(0);

  // Check if this table is selected
  const isTableSelected =
    selection?.type === "table" &&
    selection.sectionIndex === sectionIndex &&
    selection.paragraphIndex === paragraphIndex &&
    selection.tableIndex === table.tableIndex;

  // Compute cumulative column positions for handle placement using columnWidths
  const colPositions: number[] = [];
  let cumX = 0;
  for (let c = 0; c < table.colCount; c++) {
    const widthHwp = table.columnWidths[c] ?? 0;
    cumX += hwpToPx(widthHwp);
    colPositions.push(cumX);
  }
  const tableWidthPx = Math.max(hwpToPx(table.widthHwp), colPositions[colPositions.length - 1] ?? 0);

  useEffect(() => {
    const node = tableRef.current;
    if (!node) return;

    const measure = () => {
      setTableHeightPx(node.offsetHeight || 0);
    };
    measure();

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => measure());
      observer.observe(node);
    }

    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  const selectCurrentTable = useCallback(() => {
    setSelection({
      sectionIndex,
      paragraphIndex,
      type: "table",
      tableIndex: table.tableIndex,
      objectType: "table",
    });
  }, [sectionIndex, paragraphIndex, table.tableIndex, setSelection]);

  const insertParagraphBelow = useCallback(() => {
    const nextParagraphIndex = paragraphIndex + 1;
    insertBlockAt(sectionIndex, nextParagraphIndex, "");
    setSelection({
      sectionIndex,
      paragraphIndex: nextParagraphIndex,
      type: "paragraph",
    });
  }, [insertBlockAt, paragraphIndex, sectionIndex, setSelection]);

  const removeCurrentTable = useCallback(() => {
    selectCurrentTable();
    deleteTable();
  }, [deleteTable, selectCurrentTable]);

  const isCellSelectionOnCurrentTable =
    selection?.type === "cell" &&
    selection.tableIndex === table.tableIndex &&
    selection.sectionIndex === sectionIndex &&
    selection.paragraphIndex === paragraphIndex &&
    selection.row != null &&
    selection.col != null;

  const hasRangeOnCurrentTable =
    isCellSelectionOnCurrentTable &&
    selection.endRow != null &&
    selection.endCol != null;

  const canDeleteCurrentTable =
    isTableSelected ||
    (selection?.tableIndex === table.tableIndex &&
      selection.sectionIndex === sectionIndex &&
      selection.paragraphIndex === paragraphIndex);
  const isNestedFocusedCurrentTable =
    nestedTableFocus?.sectionIndex === sectionIndex &&
    nestedTableFocus?.paragraphIndex === paragraphIndex &&
    nestedTableFocus?.tableIndex === table.tableIndex;

  const openTablePropertiesPanel = useCallback(() => {
    setSidebarTab("table");
    if (!sidebarOpen) toggleSidebar();
  }, [setSidebarTab, sidebarOpen, toggleSidebar]);

  const focusCurrentNestedTable = useCallback(() => {
    if (!isCellSelectionOnCurrentTable) return;
    const row = selection?.row;
    const col = selection?.col;
    if (row == null || col == null) return;
    const focusCurrentCellNestedTable = () => {
      const store = useEditorStore.getState();
      store.setSelection({
        sectionIndex,
        paragraphIndex,
        type: "cell",
        tableIndex: table.tableIndex,
        row,
        col,
        objectType: "table",
      });
      store.focusNestedTableInCell(0);
    };

    focusCurrentCellNestedTable();
    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => {
        focusCurrentCellNestedTable();
      });
    }
  }, [
    isCellSelectionOnCurrentTable,
    paragraphIndex,
    sectionIndex,
    selection?.col,
    selection?.row,
    table.tableIndex,
  ]);

  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  const runContextAction = useCallback((action: () => void) => {
    action();
    setContextMenu(null);
  }, []);

  const contextMenuItems = useMemo<TableContextMenuItem[]>(
    () => [
      {
        key: "table-properties",
        label: "표 속성 열기",
        action: openTablePropertiesPanel,
        disabled: !canDeleteCurrentTable,
        dividerAfter: true,
      },
      {
        key: "insert-nested-table-2x2",
        label: "셀 안에 표 삽입 (2x2)",
        action: () => insertNestedTableInCell(2, 2),
        disabled: !isCellSelectionOnCurrentTable,
      },
      {
        key: "insert-nested-table-4x3",
        label: "셀 안에 표 삽입 (4x3)",
        action: () => insertNestedTableInCell(4, 3),
        disabled: !isCellSelectionOnCurrentTable,
        dividerAfter: true,
      },
      {
        key: "focus-nested-table",
        label: "중첩 표 선택",
        action: focusCurrentNestedTable,
        disabled: !isCellSelectionOnCurrentTable,
      },
      {
        key: "focus-parent-table",
        label: "상위 표로 나가기",
        action: focusParentTable,
        disabled: !isNestedFocusedCurrentTable,
        dividerAfter: true,
      },
      {
        key: "insert-row-above",
        label: "줄 삽입 (위)",
        action: () => insertTableRow("above"),
        disabled: !isCellSelectionOnCurrentTable,
      },
      {
        key: "insert-row-below",
        label: "줄 삽입 (아래)",
        action: () => insertTableRow("below"),
        disabled: !isCellSelectionOnCurrentTable,
      },
      {
        key: "insert-col-left",
        label: "칸 삽입 (왼쪽)",
        action: () => insertTableColumn("left"),
        disabled: !isCellSelectionOnCurrentTable,
      },
      {
        key: "insert-col-right",
        label: "칸 삽입 (오른쪽)",
        action: () => insertTableColumn("right"),
        disabled: !isCellSelectionOnCurrentTable,
        dividerAfter: true,
      },
      {
        key: "merge-cells",
        label: "셀 합치기",
        action: mergeTableCells,
        disabled: !hasRangeOnCurrentTable,
      },
      {
        key: "split-cell",
        label: "셀 나누기",
        action: splitTableCell,
        disabled: !isCellSelectionOnCurrentTable,
        dividerAfter: true,
      },
      {
        key: "delete-row",
        label: "줄 삭제",
        action: deleteTableRow,
        disabled: !isCellSelectionOnCurrentTable,
      },
      {
        key: "delete-col",
        label: "칸 삭제",
        action: deleteTableColumn,
        disabled: !isCellSelectionOnCurrentTable,
      },
      {
        key: "delete-table",
        label: "표 삭제",
        action: removeCurrentTable,
        disabled: !canDeleteCurrentTable,
        danger: true,
      },
    ],
    [
      canDeleteCurrentTable,
      deleteTableColumn,
      deleteTableRow,
      focusCurrentNestedTable,
      focusParentTable,
      hasRangeOnCurrentTable,
      insertNestedTableInCell,
      insertTableColumn,
      insertTableRow,
      isNestedFocusedCurrentTable,
      isCellSelectionOnCurrentTable,
      mergeTableCells,
      openTablePropertiesPanel,
      removeCurrentTable,
      splitTableCell,
    ],
  );

  useEffect(() => {
    if (!contextMenu) return;
    const handleOutside = (event: MouseEvent) => {
      if (contextMenuRef.current?.contains(event.target as Node)) return;
      closeContextMenu();
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeContextMenu();
    };
    window.addEventListener("mousedown", handleOutside, true);
    window.addEventListener("scroll", closeContextMenu, true);
    window.addEventListener("resize", closeContextMenu);
    document.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("mousedown", handleOutside, true);
      window.removeEventListener("scroll", closeContextMenu, true);
      window.removeEventListener("resize", closeContextMenu);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [closeContextMenu, contextMenu]);

  const handleContextMenu = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();

      const eventTarget = e.target;
      const target =
        eventTarget instanceof HTMLElement
          ? eventTarget
          : eventTarget instanceof Node
            ? eventTarget.parentElement
            : null;
      const cellEl = target?.closest("td[data-hwpx-cell='1']");
      if (cellEl instanceof HTMLTableCellElement) {
        const row = Number(cellEl.dataset.row);
        const col = Number(cellEl.dataset.col);
        const tableIndex = Number(cellEl.dataset.tableIndex);
        const section = Number(cellEl.dataset.sectionIndex);
        const paragraph = Number(cellEl.dataset.paragraphIndex);
        if ([row, col, tableIndex, section, paragraph].every(Number.isFinite)) {
          const currentSelection = useEditorStore.getState().selection;
          const keepCurrentRange =
            currentSelection?.type === "cell" &&
            currentSelection.tableIndex === tableIndex &&
            currentSelection.sectionIndex === section &&
            currentSelection.paragraphIndex === paragraph &&
            currentSelection.row != null &&
            currentSelection.col != null &&
            currentSelection.endRow != null &&
            currentSelection.endCol != null &&
            row >= Math.min(currentSelection.row, currentSelection.endRow) &&
            row <= Math.max(currentSelection.row, currentSelection.endRow) &&
            col >= Math.min(currentSelection.col, currentSelection.endCol) &&
            col <= Math.max(currentSelection.col, currentSelection.endCol);

          if (!keepCurrentRange) {
            setSelection({
              sectionIndex: section,
              paragraphIndex: paragraph,
              type: "cell",
              tableIndex,
              row,
              col,
              objectType: "table",
            });
          }
          setContextMenu({ x: e.clientX, y: e.clientY, source: "cell" });
          return;
        }
      }

      selectCurrentTable();
      setContextMenu({ x: e.clientX, y: e.clientY, source: "table" });
    },
    [selectCurrentTable, setSelection],
  );

  const handleTableClick = useCallback(
    (e: React.MouseEvent) => {
      // Only select table if clicking on the table border area (not inside cells)
      const target = e.target as HTMLElement;
      if (target.tagName === "TABLE" || target.closest(".table-select-area")) {
        e.stopPropagation();
        selectCurrentTable();
        tableRef.current?.focus();
      }
    },
    [selectCurrentTable],
  );

  const handleTableKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!isTableSelected) return;
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;

    if (e.key === "Enter") {
      e.preventDefault();
      insertParagraphBelow();
      return;
    }

    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      removeCurrentTable();
    }
  }, [insertParagraphBelow, isTableSelected, removeCurrentTable]);

  // Apply outMargin as margin around the table
  const marginTop = hwpToPx(table.outMargin.top) || 8;
  const marginBottom = hwpToPx(table.outMargin.bottom) || 8;
  const marginLeft = hwpToPx(table.outMargin.left) || 0;
  const marginRight = hwpToPx(table.outMargin.right) || 0;

  return (
    <div
      className="overflow-x-auto relative outline-none"
      ref={tableRef}
      tabIndex={0}
      onKeyDown={handleTableKeyDown}
      onContextMenu={handleContextMenu}
      style={{ marginTop, marginBottom, marginLeft, marginRight }}
    >
      {/* Table selection and quick actions */}
      {isNestedFocusedCurrentTable && (
        <div className="table-select-area mb-1 flex items-center gap-1">
          <span className="h-6 px-2 inline-flex items-center rounded border border-violet-200 bg-violet-50 text-[10px] font-semibold text-violet-700">
            중첩 표 선택 중
          </span>
          <button
            type="button"
            className="h-6 px-2 text-[10px] font-semibold bg-white/95 border border-violet-300 hover:bg-violet-50 text-violet-700 rounded shadow-sm"
            onMouseDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
              focusParentTable();
              tableRef.current?.focus();
            }}
            onClick={(e) => {
              e.preventDefault();
            }}
            title="상위 표로 나가기"
            aria-label="상위 표로 나가기"
            data-hwpx-testid="nested-focus-parent-button"
          >
            상위 표로 나가기
          </button>
        </div>
      )}
      {isTableSelected && (
        <div className="table-select-area mb-1 flex items-center gap-1">
        <button
          type="button"
          className="w-6 h-6 cursor-pointer flex items-center justify-center bg-white/95 border border-gray-300 hover:bg-blue-50 rounded shadow-sm"
          onClick={(e) => {
            e.stopPropagation();
            selectCurrentTable();
            tableRef.current?.focus();
          }}
          title="표 전체 선택"
          aria-label="표 전체 선택"
        >
          <svg width="13" height="13" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="1" y="1" width="10" height="10" stroke="#4b5563" strokeWidth="1" fill="none" />
            <line x1="1" y1="4" x2="11" y2="4" stroke="#4b5563" strokeWidth="0.6" />
            <line x1="1" y1="8" x2="11" y2="8" stroke="#4b5563" strokeWidth="0.6" />
            <line x1="4" y1="1" x2="4" y2="11" stroke="#4b5563" strokeWidth="0.6" />
            <line x1="8" y1="1" x2="8" y2="11" stroke="#4b5563" strokeWidth="0.6" />
          </svg>
        </button>
        <button
          type="button"
          className="h-6 px-2 text-[10px] font-semibold bg-white/95 border border-gray-300 hover:bg-blue-50 rounded shadow-sm"
          onClick={(e) => {
            e.stopPropagation();
            insertParagraphBelow();
          }}
          title="표 아래 줄 추가"
          aria-label="표 아래 줄 추가"
        >
          + 줄
        </button>
        <button
          type="button"
          className="h-6 px-2 text-[10px] font-semibold bg-white/95 border border-gray-300 hover:bg-red-50 text-red-600 rounded shadow-sm"
          onClick={(e) => {
            e.stopPropagation();
            removeCurrentTable();
          }}
          title="표 삭제"
          aria-label="표 삭제"
        >
          삭제
        </button>
        </div>
      )}
      <table
        className={`border-collapse ${
          isNestedFocusedCurrentTable
            ? "outline outline-2 outline-violet-400"
            : isTableSelected
              ? "outline outline-2 outline-blue-500"
              : ""
        }`}
        onClick={handleTableClick}
        style={{
          width: tableWidthPx > 0 ? tableWidthPx : undefined,
          tableLayout: "fixed",
          boxSizing: "border-box",
        }}
      >
        <tbody>
          {table.cells.map((row, rIdx) => (
            <tr key={rIdx}>
              {row.map((cell) =>
                cell.isAnchor ? (
                  <TableCell
                    key={`${cell.row}-${cell.col}`}
                    cell={cell}
                    sectionIndex={sectionIndex}
                    paragraphIndex={paragraphIndex}
                    tableIndex={table.tableIndex}
                    inMargin={table.inMargin}
                  />
                ) : null,
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {/* Column resize handles at each column boundary */}
      {colPositions.map((pos, idx) => (
        <div
          key={idx}
          className="absolute top-0"
          style={{ left: pos }}
        >
          <ColumnResizeHandle
            colIdx={idx}
            tableHeight={tableHeightPx}
            sectionIndex={sectionIndex}
            paragraphIndex={paragraphIndex}
            tableIndex={table.tableIndex}
          />
        </div>
      ))}
      {contextMenu ? (
        <div
          ref={contextMenuRef}
          className="fixed z-[80] min-w-[180px] rounded border border-gray-300 bg-white py-1 shadow-xl"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          role="menu"
          aria-label={contextMenu.source === "cell" ? "셀 컨텍스트 메뉴" : "표 컨텍스트 메뉴"}
          data-hwpx-testid="table-context-menu"
        >
          {contextMenuItems.map((item) => (
            <div key={item.key}>
              <button
                type="button"
                disabled={item.disabled}
                onMouseDown={(e) => {
                  if (item.disabled) return;
                  e.preventDefault();
                  e.stopPropagation();
                  runContextAction(item.action);
                }}
                onClick={(e) => {
                  e.preventDefault();
                }}
                className={`w-full px-3 py-1.5 text-left text-xs ${
                  item.disabled
                    ? "cursor-default text-gray-300"
                    : item.danger
                      ? "text-red-600 hover:bg-red-50"
                      : "text-gray-700 hover:bg-blue-50 hover:text-blue-700"
                }`}
                role="menuitem"
                data-hwpx-testid={`table-context-menu-${item.key}`}
              >
                {item.label}
              </button>
              {item.dividerAfter ? <div className="mx-1 my-0.5 border-t border-gray-100" /> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
