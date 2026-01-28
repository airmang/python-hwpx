"use client";

import { useRef, useCallback } from "react";
import type { TableVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { pxToHwp } from "@/lib/hwp-units";
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

  // Compute cumulative column positions for handle placement
  const colPositions: number[] = [];
  let cumX = 0;
  for (let c = 0; c < table.colCount; c++) {
    const cell = table.cells[0]?.[c];
    const w = cell ? cell.widthPx : 0;
    cumX += w;
    colPositions.push(cumX);
  }

  const tableHeightPx = tableRef.current?.offsetHeight ?? 0;

  return (
    <div className="my-2 overflow-x-auto relative" ref={tableRef}>
      <table className="border-collapse border border-gray-400">
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
