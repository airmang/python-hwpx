"use client";

import { useRef, useCallback } from "react";
import type { TableCellVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";

interface TableCellProps {
  cell: TableCellVM;
  sectionIndex: number;
  paragraphIndex: number;
  tableIndex: number;
}

function isInRange(
  row: number, col: number, rowSpan: number, colSpan: number,
  r1: number, c1: number, r2: number, c2: number,
): boolean {
  const minR = Math.min(r1, r2);
  const maxR = Math.max(r1, r2);
  const minC = Math.min(c1, c2);
  const maxC = Math.max(c1, c2);
  // Cell occupies rows [row, row+rowSpan-1] and cols [col, col+colSpan-1]
  return row + rowSpan - 1 >= minR && row <= maxR && col + colSpan - 1 >= minC && col <= maxC;
}

export function TableCell({
  cell,
  sectionIndex,
  paragraphIndex,
  tableIndex,
}: TableCellProps) {
  const updateCellText = useEditorStore((s) => s.updateCellText);
  const setSelection = useEditorStore((s) => s.setSelection);
  const selection = useEditorStore((s) => s.selection);
  const ref = useRef<HTMLTableCellElement>(null);

  const handleBlur = useCallback(() => {
    if (!ref.current) return;
    const newText = ref.current.textContent ?? "";
    if (newText !== cell.text) {
      updateCellText(
        sectionIndex,
        paragraphIndex,
        tableIndex,
        cell.row,
        cell.col,
        newText,
      );
    }
  }, [cell, sectionIndex, paragraphIndex, tableIndex, updateCellText]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.shiftKey && selection && selection.tableIndex === tableIndex && selection.row != null && selection.col != null) {
      // Shift+click: extend selection range
      e.preventDefault();
      setSelection({
        ...selection,
        endRow: cell.row,
        endCol: cell.col,
      });
    } else {
      // Normal click: single cell selection
      setSelection({
        sectionIndex,
        paragraphIndex,
        type: "cell",
        tableIndex,
        row: cell.row,
        col: cell.col,
        objectType: "table",
      });
    }
  }, [sectionIndex, paragraphIndex, tableIndex, cell.row, cell.col, setSelection, selection]);

  const handleFocus = useCallback(() => {
    if (!selection || selection.tableIndex !== tableIndex || selection.row !== cell.row || selection.col !== cell.col) {
      setSelection({
        sectionIndex,
        paragraphIndex,
        type: "cell",
        tableIndex,
        row: cell.row,
        col: cell.col,
        objectType: "table",
      });
    }
  }, [sectionIndex, paragraphIndex, tableIndex, cell.row, cell.col, setSelection, selection]);

  if (!cell.isAnchor) return null;

  // Determine if this cell is in the selected range
  const inRange = selection?.tableIndex === tableIndex
    && selection.row != null && selection.col != null
    && selection.endRow != null && selection.endCol != null
    && isInRange(cell.row, cell.col, cell.rowSpan, cell.colSpan, selection.row, selection.col, selection.endRow, selection.endCol);

  return (
    <td
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      colSpan={cell.colSpan > 1 ? cell.colSpan : undefined}
      rowSpan={cell.rowSpan > 1 ? cell.rowSpan : undefined}
      onBlur={handleBlur}
      onFocus={handleFocus}
      onMouseDown={handleMouseDown}
      className={`border border-gray-300 px-2 py-1 text-sm outline-none ${
        inRange ? "bg-blue-100" : "focus:bg-blue-50"
      }`}
      style={{
        minWidth: cell.widthPx > 0 ? cell.widthPx : 40,
        minHeight: cell.heightPx > 0 ? cell.heightPx : 24,
      }}
    >
      {cell.text}
    </td>
  );
}
