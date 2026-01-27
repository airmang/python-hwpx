"use client";

import type { TableVM } from "@/lib/view-model";
import { TableCell } from "./TableCell";

interface TableBlockProps {
  table: TableVM;
  sectionIndex: number;
  paragraphIndex: number;
}

export function TableBlock({ table, sectionIndex, paragraphIndex }: TableBlockProps) {
  return (
    <div className="my-2 overflow-x-auto">
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
    </div>
  );
}
