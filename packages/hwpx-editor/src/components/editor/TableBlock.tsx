"use client";

import { useRef, useCallback } from "react";
import type { TableVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { pxToHwp, hwpToPx } from "@/lib/hwp-units";
import { TableCell } from "./TableCell";

interface TableBlockProps {
  table: TableVM;
  sectionIndex: number;
  paragraphIndex: number;
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

      const onMouseMove = (me: MouseEvent) => {
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
  const setSelection = useEditorStore((s) => s.setSelection);
  const selection = useEditorStore((s) => s.selection);
  const insertBlockAt = useEditorStore((s) => s.insertBlockAt);
  const deleteTable = useEditorStore((s) => s.deleteTable);

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

  const tableHeightPx = tableRef.current?.offsetHeight ?? 0;

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
      style={{ marginTop, marginBottom, marginLeft, marginRight }}
    >
      {/* Table selection and quick actions */}
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
        className={`border-collapse ${isTableSelected ? "outline outline-2 outline-blue-500" : ""}`}
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
    </div>
  );
}
