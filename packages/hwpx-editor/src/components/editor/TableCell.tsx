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

export function TableCell({
  cell,
  sectionIndex,
  paragraphIndex,
  tableIndex,
}: TableCellProps) {
  const updateCellText = useEditorStore((s) => s.updateCellText);
  const setSelection = useEditorStore((s) => s.setSelection);
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
    });
  }, [sectionIndex, paragraphIndex, tableIndex, cell.row, cell.col, setSelection]);

  if (!cell.isAnchor) return null;

  return (
    <td
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      colSpan={cell.colSpan > 1 ? cell.colSpan : undefined}
      rowSpan={cell.rowSpan > 1 ? cell.rowSpan : undefined}
      onBlur={handleBlur}
      onFocus={handleFocus}
      className="border border-gray-300 px-2 py-1 text-sm outline-none focus:bg-blue-50"
      style={{
        minWidth: cell.widthPx > 0 ? cell.widthPx : 40,
        minHeight: cell.heightPx > 0 ? cell.heightPx : 24,
      }}
    >
      {cell.text}
    </td>
  );
}
