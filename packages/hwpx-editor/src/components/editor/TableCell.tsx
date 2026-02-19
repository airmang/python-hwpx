"use client";

import { useRef, useCallback, useEffect, useState } from "react";
import type { TableCellVM, CellBorderStyleVM, MarginVM, NestedTableVM } from "@/lib/view-model";
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

interface NestedSelectionRange {
  startRow: number;
  startCol: number;
  endRow: number;
  endCol: number;
}

const NESTED_FILL_PRESETS: Array<{ key: string; color: string | null; label: string }> = [
  { key: "none", color: null, label: "지우기" },
  { key: "amber", color: "#FFF2CC", label: "노랑" },
  { key: "green", color: "#D9EAD3", label: "연두" },
  { key: "blue", color: "#DCE6F7", label: "하늘" },
  { key: "orange", color: "#FCE5CD", label: "주황" },
  { key: "pink", color: "#F4CCCC", label: "분홍" },
];

function borderToCss(b: CellBorderStyleVM | null | undefined): string {
  if (!b || b.type === "NONE") return "0 solid transparent";
  const widthStr = b.width.replace(/ /g, "");
  const mm = parseFloat(widthStr);
  const px = Math.max(Number.isFinite(mm) ? mm * 3.78 : 0.5, 0.5); // mm to px approx
  let cssStyle = "solid";
  switch (b.type) {
    case "DASH": cssStyle = "dashed"; break;
    case "DOT": cssStyle = "dotted"; break;
    case "DASH_DOT": cssStyle = "dashed"; break;
    case "DOUBLE_SLIM": case "DOUBLE": cssStyle = "double"; break;
  }
  return `${px.toFixed(2)}px ${cssStyle} ${b.color}`;
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

function extractEditableCellText(cell: HTMLTableCellElement): string {
  const clone = cell.cloneNode(true) as HTMLTableCellElement;
  clone.querySelectorAll("[data-hwpx-ui='1']").forEach((el) => el.remove());
  return clone.textContent ?? "";
}

function createFallbackNestedTable(rowCount: number, colCount: number): NestedTableVM {
  const safeRows = Math.max(1, rowCount);
  const safeCols = Math.max(1, colCount);
  return {
    rowCount: safeRows,
    colCount: safeCols,
    cells: Array.from({ length: safeRows }, (_, row) =>
      Array.from({ length: safeCols }, (_, col) => ({
        row,
        col,
        rowSpan: 1,
        colSpan: 1,
        isAnchor: true,
        text: "",
        backgroundColor: null,
      })),
    ),
  };
}

function NestedTablePreview({
  nested,
  index,
  onFocusNested,
  onCommitNestedCell,
  onApplyNestedBackground,
}: {
  nested: NestedTableVM;
  index: number;
  onFocusNested: (nestedIndex: number) => void;
  onCommitNestedCell: (nestedIndex: number, row: number, col: number, text: string) => void;
  onApplyNestedBackground: (
    nestedIndex: number,
    startRow: number,
    startCol: number,
    endRow: number,
    endCol: number,
    color: string | null,
  ) => void;
}) {
  const rowCount = Math.max(1, nested.rowCount);
  const colCount = Math.max(1, nested.colCount);
  const dragAnchorRef = useRef<{ row: number; col: number } | null>(null);
  const [selectionRange, setSelectionRange] = useState<NestedSelectionRange | null>(null);

  useEffect(() => {
    const clearDrag = () => {
      dragAnchorRef.current = null;
    };
    document.addEventListener("mouseup", clearDrag);
    window.addEventListener("blur", clearDrag);
    return () => {
      document.removeEventListener("mouseup", clearDrag);
      window.removeEventListener("blur", clearDrag);
    };
  }, []);

  const selectSingle = useCallback((row: number, col: number) => {
    setSelectionRange({
      startRow: row,
      startCol: col,
      endRow: row,
      endCol: col,
    });
  }, []);

  const selectByPointer = useCallback((row: number, col: number, shiftKey: boolean) => {
    if (shiftKey && selectionRange) {
      setSelectionRange({
        startRow: selectionRange.startRow,
        startCol: selectionRange.startCol,
        endRow: row,
        endCol: col,
      });
      dragAnchorRef.current = {
        row: selectionRange.startRow,
        col: selectionRange.startCol,
      };
      return;
    }
    selectSingle(row, col);
    dragAnchorRef.current = { row, col };
  }, [selectSingle, selectionRange]);

  const applyFillColor = useCallback((color: string | null) => {
    const range = selectionRange ?? {
      startRow: 0,
      startCol: 0,
      endRow: 0,
      endCol: 0,
    };
    onApplyNestedBackground(
      index,
      range.startRow,
      range.startCol,
      range.endRow,
      range.endCol,
      color,
    );
  }, [index, onApplyNestedBackground, selectionRange]);

  return (
    <div
      className="w-full rounded border border-violet-300 bg-white p-1.5 shadow-sm"
      data-hwpx-ui="1"
      onMouseDown={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onFocusNested(index);
      }}
    >
      <div className="mb-1 flex min-w-0 flex-col gap-1">
        <div className="whitespace-normal break-words text-[10px] font-semibold leading-tight text-violet-700">
          중첩 표 {index + 1} ({rowCount}x{colCount})
        </div>
        <div className="flex flex-wrap items-center gap-1" data-hwpx-testid={`nested-table-fill-tools-${index}`}>
          {NESTED_FILL_PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              className={`h-4 min-w-4 rounded border border-violet-300 text-[9px] leading-none text-violet-700 ${
                preset.color ? "" : "px-1"
              }`}
              style={preset.color ? { backgroundColor: preset.color } : undefined}
              title={`선택 영역 ${preset.label} 칠하기`}
              data-hwpx-testid={`nested-table-fill-${index}-${preset.key}`}
              onMouseDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onFocusNested(index);
                applyFillColor(preset.color);
              }}
            >
              {preset.color ? "" : "지움"}
            </button>
          ))}
        </div>
      </div>
      <table className="w-full border-collapse">
        <tbody>
          {Array.from({ length: rowCount }).map((_, rIdx) => (
            <tr key={rIdx}>
              {Array.from({ length: colCount }).map((_, cIdx) => {
                const cell = nested.cells[rIdx]?.[cIdx];
                if (!cell || !cell.isAnchor) return null;
                return (
                  <td
                    key={`${cell.row}-${cell.col}`}
                    rowSpan={cell.rowSpan > 1 ? cell.rowSpan : undefined}
                    colSpan={cell.colSpan > 1 ? cell.colSpan : undefined}
                    className={`border border-violet-300 p-0.5 ${
                      selectionRange &&
                      isInRange(
                        cell.row,
                        cell.col,
                        cell.rowSpan,
                        cell.colSpan,
                        selectionRange.startRow,
                        selectionRange.startCol,
                        selectionRange.endRow,
                        selectionRange.endCol,
                      )
                        ? "ring-2 ring-inset ring-blue-400"
                        : ""
                    }`}
                    style={{ backgroundColor: cell.backgroundColor ?? "rgba(139, 92, 246, 0.08)" }}
                    data-hwpx-testid={`nested-table-cell-${index}-${cell.row}-${cell.col}`}
                    onMouseDown={(e) => {
                      if (e.button !== 0) return;
                      e.preventDefault();
                      e.stopPropagation();
                      onFocusNested(index);
                      selectByPointer(cell.row, cell.col, e.shiftKey);
                    }}
                    onMouseEnter={(e) => {
                      if (!(e.buttons & 1)) return;
                      if (!dragAnchorRef.current) return;
                      e.preventDefault();
                      e.stopPropagation();
                      onFocusNested(index);
                      setSelectionRange({
                        startRow: dragAnchorRef.current.row,
                        startCol: dragAnchorRef.current.col,
                        endRow: cell.row,
                        endCol: cell.col,
                      });
                    }}
                  >
                    <input
                      defaultValue={cell.text}
                      className="h-5 w-full border-none bg-transparent px-1 text-[10px] outline-none"
                      onMouseDown={(e) => {
                        e.stopPropagation();
                        onFocusNested(index);
                        selectByPointer(cell.row, cell.col, e.shiftKey);
                      }}
                      onFocus={() => {
                        onFocusNested(index);
                        if (!dragAnchorRef.current) {
                          selectSingle(cell.row, cell.col);
                        }
                      }}
                      onBlur={(e) => {
                        onCommitNestedCell(index, cell.row, cell.col, e.currentTarget.value);
                      }}
                      onKeyDown={(e) => {
                        e.stopPropagation();
                      }}
                      data-hwpx-testid={`nested-table-input-${index}-${cell.row}-${cell.col}`}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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
  const nestedTableFocus = useEditorStore((s) => s.nestedTableFocus);
  const focusNestedTableInCell = useEditorStore((s) => s.focusNestedTableInCell);
  const updateNestedTableCellText = useEditorStore((s) => s.updateNestedTableCellText);
  const updateNestedTableCellBackground = useEditorStore((s) => s.updateNestedTableCellBackground);
  const ref = useRef<HTMLTableCellElement>(null);

  const handleBlur = useCallback(() => {
    if (!ref.current) return;
    const newText = extractEditableCellText(ref.current);
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

  const handleClick = useCallback((e: React.MouseEvent) => {
    if (dragSelecting) return;
    if (e.shiftKey) return;
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
    const syncSelection = (e: Event) => {
      if (dragSelecting) return;
      if (e instanceof MouseEvent && e.shiftKey) return;
      const currentSelection = useEditorStore.getState().selection;
      if (
        currentSelection?.type === "cell" &&
        currentSelection.tableIndex === tableIndex &&
        currentSelection.endRow != null &&
        currentSelection.endCol != null
      ) {
        return;
      }
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
    const currentText = ref.current ? extractEditableCellText(ref.current) : "";
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
  const isNestedFocusCell =
    nestedTableFocus?.sectionIndex === sectionIndex &&
    nestedTableFocus?.paragraphIndex === paragraphIndex &&
    nestedTableFocus?.tableIndex === tableIndex &&
    nestedTableFocus?.row === cell.row &&
    nestedTableFocus?.col === cell.col;
  const nestedPreviewItems: NestedTableVM[] =
    cell.nestedTables.length > 0
      ? cell.nestedTables
      : cell.nestedTableCount > 0
        ? Array.from({ length: cell.nestedTableCount }, () => createFallbackNestedTable(2, 2))
        : [];

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
    textDecoration: "none",
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
      data-hwpx-nested-table-count={cell.nestedTableCount > 0 ? String(cell.nestedTableCount) : undefined}
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
        isNestedFocusCell
          ? "ring-2 ring-inset ring-violet-500"
          : isSingleSelected
            ? "ring-2 ring-inset ring-blue-400"
            : ""
      }`}
      style={tdStyle}
    >
      {cell.text}
      {cell.nestedTableCount > 0 ? (
        <span
          contentEditable={false}
          className="ml-1 inline-flex items-center rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700"
          data-hwpx-testid="nested-table-badge"
          data-hwpx-ui="1"
          title={`중첩 표 ${cell.nestedTableCount}개`}
          onMouseDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setSelection({
              sectionIndex,
              paragraphIndex,
              type: "cell",
              tableIndex,
              row: cell.row,
              col: cell.col,
              objectType: "table",
            });
            focusNestedTableInCell(0);
          }}
        >
          중첩 표 {cell.nestedTableCount}개
        </span>
      ) : null}
      {nestedPreviewItems.length > 0 ? (
        <div className="mt-2 space-y-1.5" contentEditable={false} data-hwpx-ui="1">
          {nestedPreviewItems.map((nested, idx) => (
            <div
              key={`${idx}-${nested.rowCount}-${nested.colCount}`}
              onMouseDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              className="cursor-pointer"
              data-hwpx-testid="nested-table-preview"
            >
              <NestedTablePreview
                nested={nested}
                index={idx}
                onFocusNested={(nestedIndex) => {
                  setSelection({
                    sectionIndex,
                    paragraphIndex,
                    type: "cell",
                    tableIndex,
                    row: cell.row,
                    col: cell.col,
                    objectType: "table",
                  });
                  focusNestedTableInCell(nestedIndex);
                }}
                onCommitNestedCell={(nestedIndex, nestedRow, nestedCol, text) => {
                  updateNestedTableCellText(
                    sectionIndex,
                    paragraphIndex,
                    tableIndex,
                    cell.row,
                    cell.col,
                    nestedIndex,
                    nestedRow,
                    nestedCol,
                    text,
                  );
                }}
                onApplyNestedBackground={(nestedIndex, startRow, startCol, endRow, endCol, color) => {
                  updateNestedTableCellBackground(
                    sectionIndex,
                    paragraphIndex,
                    tableIndex,
                    cell.row,
                    cell.col,
                    nestedIndex,
                    startRow,
                    startCol,
                    endRow,
                    endCol,
                    color,
                  );
                }}
              />
            </div>
          ))}
        </div>
      ) : null}
    </td>
  );
}
