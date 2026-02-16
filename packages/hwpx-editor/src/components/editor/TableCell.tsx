"use client";

import { useRef, useCallback, useEffect } from "react";
import type { TableCellVM, CellBorderStyleVM, MarginVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { hwpToPx } from "@/lib/hwp-units";
import { fontFamilyCssStack } from "@/lib/constants";

interface TableCellProps {
  cell: TableCellVM;
  sectionIndex: number;
  paragraphIndex: number;
  tableIndex: number;
  inMargin?: MarginVM;
}

type DragAnchor = {
  sectionIndex: number;
  paragraphIndex: number;
  tableIndex: number;
  startRow: number;
  startCol: number;
};

let dragAnchor: DragAnchor | null = null;
let dragSelecting = false;
let prevBodyUserSelect = "";

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
  inMargin,
}: TableCellProps) {
  const updateCellText = useEditorStore((s) => s.updateCellText);
  const insertBlockAt = useEditorStore((s) => s.insertBlockAt);
  const deleteTable = useEditorStore((s) => s.deleteTable);
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
    if (e.button !== 0) return;

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

    dragAnchor = {
      sectionIndex,
      paragraphIndex,
      tableIndex,
      startRow: cell.row,
      startCol: cell.col,
    };
    dragSelecting = true;
    prevBodyUserSelect = document.body.style.userSelect;
    document.body.style.userSelect = "none";

    const clearDragAnchor = () => {
      dragAnchor = null;
      dragSelecting = false;
      document.body.style.userSelect = prevBodyUserSelect;
      document.removeEventListener("mousemove", handleDragMove);
      document.removeEventListener("mouseup", clearDragAnchor);
      window.removeEventListener("blur", clearDragAnchor);
    };
    const handleDragMove = (me: MouseEvent) => {
      if (!(me.buttons & 1)) return;
      if (!dragSelecting || !dragAnchor) return;

      const target = document.elementFromPoint(me.clientX, me.clientY);
      if (!(target instanceof HTMLElement)) return;
      const td = target.closest("td[data-hwpx-cell='1']");
      if (!(td instanceof HTMLTableCellElement)) return;

      const tableIdx = Number(td.dataset.tableIndex);
      const sectionIdx = Number(td.dataset.sectionIndex);
      const paraIdx = Number(td.dataset.paragraphIndex);
      const row = Number(td.dataset.row);
      const col = Number(td.dataset.col);
      if (![tableIdx, sectionIdx, paraIdx, row, col].every(Number.isFinite)) return;
      if (tableIdx !== dragAnchor.tableIndex) return;
      if (sectionIdx !== dragAnchor.sectionIndex) return;
      if (paraIdx !== dragAnchor.paragraphIndex) return;

      setSelection({
        sectionIndex: dragAnchor.sectionIndex,
        paragraphIndex: dragAnchor.paragraphIndex,
        type: "cell",
        tableIndex: dragAnchor.tableIndex,
        row: dragAnchor.startRow,
        col: dragAnchor.startCol,
        endRow: row,
        endCol: col,
        objectType: "table",
      });
    };
    document.addEventListener("mousemove", handleDragMove);
    document.addEventListener("mouseup", clearDragAnchor);
    window.addEventListener("blur", clearDragAnchor);
  }, [sectionIndex, paragraphIndex, tableIndex, cell.row, cell.col, setSelection, selection]);

  const handleMouseEnter = useCallback((e: React.MouseEvent) => {
    if (!(e.buttons & 1)) return;
    if (!dragSelecting) return;
    if (!dragAnchor) return;
    if (dragAnchor.tableIndex !== tableIndex) return;

    setSelection({
      sectionIndex: dragAnchor.sectionIndex,
      paragraphIndex: dragAnchor.paragraphIndex,
      type: "cell",
      tableIndex: dragAnchor.tableIndex,
      row: dragAnchor.startRow,
      col: dragAnchor.startCol,
      endRow: cell.row,
      endCol: cell.col,
      objectType: "table",
    });
  }, [tableIndex, cell.row, cell.col, setSelection]);

  const handleFocus = useCallback(() => {
    if (dragSelecting) return;
    if (selection?.tableIndex === tableIndex && selection.endRow != null && selection.endCol != null) return;
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

  const handleClick = useCallback(() => {
    if (dragSelecting) return;
    setSelection({
      sectionIndex,
      paragraphIndex,
      type: "cell",
      tableIndex,
      row: cell.row,
      col: cell.col,
      objectType: "table",
    });
  }, [cell.col, cell.row, paragraphIndex, sectionIndex, setSelection, tableIndex]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const syncSelection = () => {
      if (dragSelecting) return;
      setSelection({
        sectionIndex,
        paragraphIndex,
        type: "cell",
        tableIndex,
        row: cell.row,
        col: cell.col,
        objectType: "table",
      });
    };
    el.addEventListener("mousedown", syncSelection);
    el.addEventListener("click", syncSelection);
    el.addEventListener("focus", syncSelection);
    return () => {
      el.removeEventListener("mousedown", syncSelection);
      el.removeEventListener("click", syncSelection);
      el.removeEventListener("focus", syncSelection);
    };
  }, [cell.col, cell.row, paragraphIndex, sectionIndex, setSelection, tableIndex]);

  const insertParagraphBelow = useCallback(() => {
    const currentText = ref.current?.textContent ?? "";
    if (currentText !== cell.text) {
      updateCellText(sectionIndex, paragraphIndex, tableIndex, cell.row, cell.col, currentText);
    }
    const nextParagraphIndex = paragraphIndex + 1;
    insertBlockAt(sectionIndex, nextParagraphIndex, "");
    setSelection({
      sectionIndex,
      paragraphIndex: nextParagraphIndex,
      type: "paragraph",
    });
  }, [
    cell.col,
    cell.row,
    cell.text,
    insertBlockAt,
    paragraphIndex,
    sectionIndex,
    setSelection,
    tableIndex,
    updateCellText,
  ]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTableCellElement>) => {
    const key = e.key.toLowerCase();
    const mod = e.ctrlKey || e.metaKey;

    if (mod && !e.altKey && !e.shiftKey && key === "enter") {
      e.preventDefault();
      insertParagraphBelow();
      return;
    }

    if (mod && !e.altKey && !e.shiftKey && (key === "delete" || key === "backspace")) {
      e.preventDefault();
      setSelection({
        sectionIndex,
        paragraphIndex,
        type: "table",
        tableIndex,
        objectType: "table",
      });
      deleteTable();
      return;
    }

    if (key === "escape") {
      e.preventDefault();
      setSelection({
        sectionIndex,
        paragraphIndex,
        type: "table",
        tableIndex,
        objectType: "table",
      });
      const tableContainer = ref.current?.closest("div[tabindex='0']") as HTMLElement | null;
      tableContainer?.focus();
    }
  }, [deleteTable, insertParagraphBelow, paragraphIndex, sectionIndex, setSelection, tableIndex]);

  if (!cell.isAnchor) return null;

  // Determine if this cell is in the selected range
  const inRange = selection?.tableIndex === tableIndex
    && selection.row != null && selection.col != null
    && selection.endRow != null && selection.endCol != null
    && isInRange(cell.row, cell.col, cell.rowSpan, cell.colSpan, selection.row, selection.col, selection.endRow, selection.endCol);
  const isSingleSelected = selection?.type === "cell"
    && selection.tableIndex === tableIndex
    && selection.row === cell.row
    && selection.col === cell.col
    && selection.endRow == null
    && selection.endCol == null;

  const cellBorders = cell.style;
  const hasCustomStyle = !!cellBorders;

  const padTop = inMargin ? Math.max(hwpToPx(inMargin.top), 1) : 2;
  const padBottom = inMargin ? Math.max(hwpToPx(inMargin.bottom), 1) : 2;
  const padLeft = inMargin ? Math.max(hwpToPx(inMargin.left), 1) : 4;
  const padRight = inMargin ? Math.max(hwpToPx(inMargin.right), 1) : 4;

  const tdStyle: React.CSSProperties = {
    width: cell.widthPx > 0 ? cell.widthPx : undefined,
    minWidth: cell.widthPx > 0 ? cell.widthPx : 40,
    minHeight: cell.heightPx > 0 ? cell.heightPx : 24,
    verticalAlign: vertAlignToCss(cell.vertAlign),
    boxSizing: "border-box",
    paddingTop: padTop,
    paddingBottom: padBottom,
    paddingLeft: padLeft,
    paddingRight: padRight,
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
    wordBreak: "break-word",
    lineHeight: 1.45,
  };
  if (cell.fontFamily) tdStyle.fontFamily = fontFamilyCssStack(cell.fontFamily);
  if (cell.fontSize) tdStyle.fontSize = `${cell.fontSize}pt`;
  if (cell.textColor) tdStyle.color = cell.textColor;
  if (cell.bold) tdStyle.fontWeight = 700;
  if (cell.italic) tdStyle.fontStyle = "oblique 10deg";
  if (cell.underline || cell.strikethrough) {
    const decorations: string[] = [];
    if (cell.underline) decorations.push("underline");
    if (cell.strikethrough) decorations.push("line-through");
    tdStyle.textDecoration = decorations.join(" ");
  }
  if (hasCustomStyle) {
    tdStyle.borderLeft = borderToCss(cellBorders.borderLeft);
    tdStyle.borderRight = borderToCss(cellBorders.borderRight);
    tdStyle.borderTop = borderToCss(cellBorders.borderTop);
    tdStyle.borderBottom = borderToCss(cellBorders.borderBottom);
    if (cellBorders.backgroundColor && !inRange) {
      tdStyle.backgroundColor = cellBorders.backgroundColor;
    }
  }

  return (
    <td
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      data-hwpx-cell="1"
      data-section-index={sectionIndex}
      data-paragraph-index={paragraphIndex}
      data-table-index={tableIndex}
      data-row={cell.row}
      data-col={cell.col}
      colSpan={cell.colSpan > 1 ? cell.colSpan : undefined}
      rowSpan={cell.rowSpan > 1 ? cell.rowSpan : undefined}
      onBlur={handleBlur}
      onFocus={handleFocus}
      onMouseDown={handleMouseDown}
      onMouseEnter={handleMouseEnter}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={`text-sm outline-none caret-gray-900 ${
        !hasCustomStyle ? "border border-gray-300" : ""
      } ${
        inRange ? "bg-blue-100" : isSingleSelected ? "bg-blue-50" : (!hasCustomStyle || !cellBorders?.backgroundColor) ? "focus:bg-blue-50" : ""
      } ${
        isSingleSelected ? "ring-2 ring-inset ring-blue-400" : ""
      }`}
      style={tdStyle}
    >
      {cell.text}
    </td>
  );
}
