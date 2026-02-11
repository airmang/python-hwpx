"use client";

import { useMemo, useRef, useCallback } from "react";
import type { TableCellVM, CellBorderStyleVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";

interface TableCellProps {
  cell: TableCellVM;
  sectionIndex: number;
  paragraphIndex: number;
  tableIndex: number;
}

function borderToCss(b: CellBorderStyleVM | null | undefined): string {
  if (!b || b.type === "NONE") return "1px solid #d1d5db"; // fallback gray-300
  const widthStr = b.width.replace(/ /g, "");
  const mm = parseFloat(widthStr);
  const px = Math.max(Math.round(mm * 3.78), 1); // mm to px approx
  let cssStyle = "solid";
  switch (b.type) {
    case "DASH": cssStyle = "dashed"; break;
    case "DOT": cssStyle = "dotted"; break;
    case "DASH_DOT": cssStyle = "dashed"; break;
    case "DOUBLE_SLIM": case "DOUBLE": cssStyle = "double"; break;
  }
  return `${px}px ${cssStyle} ${b.color}`;
}

function vertAlignToCss(va: string): string {
  switch (va) {
    case "TOP": return "top";
    case "BOTTOM": return "bottom";
    default: return "middle";
  }
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

  const cellBorders = cell.style;
  const hasCustomStyle = !!cellBorders;

  const tdStyle: React.CSSProperties = useMemo(() => {
    const s: React.CSSProperties = {
      minWidth: cell.widthPx > 0 ? cell.widthPx : 40,
      minHeight: cell.heightPx > 0 ? cell.heightPx : 24,
      verticalAlign: vertAlignToCss(cell.vertAlign),
    };
    if (hasCustomStyle) {
      s.borderLeft = borderToCss(cellBorders.borderLeft);
      s.borderRight = borderToCss(cellBorders.borderRight);
      s.borderTop = borderToCss(cellBorders.borderTop);
      s.borderBottom = borderToCss(cellBorders.borderBottom);
      if (cellBorders.backgroundColor && !inRange) {
        s.backgroundColor = cellBorders.backgroundColor;
      }
    }
    return s;
  }, [cell, cellBorders, hasCustomStyle, inRange]);

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
      className={`px-2 py-1 text-sm outline-none ${
        !hasCustomStyle ? "border border-gray-300" : ""
      } ${
        inRange ? "bg-blue-100" : (!hasCustomStyle || !cellBorders?.backgroundColor) ? "focus:bg-blue-50" : ""
      }`}
      style={tdStyle}
    >
      {cell.text}
    </td>
  );
}
