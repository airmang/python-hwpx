"use client";

import { useRef, useCallback } from "react";
import type { TableCellVM, MarginVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { hwpToPx } from "@/lib/hwp-units";

interface TableCellProps {
  cell: TableCellVM;
  sectionIndex: number;
  paragraphIndex: number;
  tableIndex: number;
  inMargin?: MarginVM;
}

export function TableCell({
  cell,
  sectionIndex,
  paragraphIndex,
  tableIndex,
  inMargin,
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

  const handleFocus = useCallback(() => {
    setSelection({
      sectionIndex,
      paragraphIndex,
      type: "cell",
      tableIndex,
      row: cell.row,
      col: cell.col,
      objectType: "table",
    });
  }, [sectionIndex, paragraphIndex, tableIndex, cell.row, cell.col, setSelection]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.shiftKey && selection?.type === "cell" && selection.tableIndex === tableIndex) {
        // Extend selection to this cell
        e.preventDefault();
        setSelection({
          ...selection,
          endRow: cell.row,
          endCol: cell.col,
        });
      }
    },
    [selection, tableIndex, cell.row, cell.col, setSelection],
  );

  // Check if this cell is within the selected range
  const isInSelectedRange = useCallback(() => {
    if (!selection || selection.type !== "cell" || selection.tableIndex !== tableIndex) {
      return false;
    }
    const startRow = Math.min(selection.row ?? 0, selection.endRow ?? selection.row ?? 0);
    const endRow = Math.max(selection.row ?? 0, selection.endRow ?? selection.row ?? 0);
    const startCol = Math.min(selection.col ?? 0, selection.endCol ?? selection.col ?? 0);
    const endCol = Math.max(selection.col ?? 0, selection.endCol ?? selection.col ?? 0);

    return cell.row >= startRow && cell.row <= endRow && cell.col >= startCol && cell.col <= endCol;
  }, [selection, tableIndex, cell.row, cell.col]);

  const isSelected = isInSelectedRange();

  if (!cell.isAnchor) return null;

  // Apply inMargin as padding (convert from hwpUnits to px)
  const paddingTop = inMargin ? hwpToPx(inMargin.top) : 4;
  const paddingBottom = inMargin ? hwpToPx(inMargin.bottom) : 4;
  const paddingLeft = inMargin ? hwpToPx(inMargin.left) : 8;
  const paddingRight = inMargin ? hwpToPx(inMargin.right) : 8;

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
      className={`border border-gray-300 text-sm outline-none ${isSelected ? "bg-blue-100" : "focus:bg-blue-50"}`}
      style={{
        minWidth: cell.widthPx > 0 ? cell.widthPx : 40,
        minHeight: cell.heightPx > 0 ? cell.heightPx : 24,
        paddingTop,
        paddingBottom,
        paddingLeft,
        paddingRight,
      }}
    >
      {cell.text}
    </td>
  );
}
