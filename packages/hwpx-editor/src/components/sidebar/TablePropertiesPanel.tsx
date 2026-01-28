"use client";

import { useState, useEffect } from "react";
import { useEditorStore, type SelectionState } from "@/lib/store";
import { hwpToMm } from "@/lib/hwp-units";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";

function roundMm(hwp: number): number {
  return Math.round(hwpToMm(hwp) * 10) / 10;
}

/** Cell size adjustment for selected cells */
function CellSizeSection({
  selection,
  hasTable,
  inputClass,
}: {
  selection: SelectionState | null;
  hasTable: boolean;
  inputClass: string;
}) {
  const setSelectedCellsSize = useEditorStore((s) => s.setSelectedCellsSize);
  const [cellWidth, setCellWidth] = useState<number>(30);
  const [cellHeight, setCellHeight] = useState<number>(10);

  const isCellSelected = selection?.type === "cell" && hasTable;
  const hasMultipleCells =
    isCellSelected &&
    (selection.endRow != null || selection.endCol != null) &&
    (selection.endRow !== selection.row || selection.endCol !== selection.col);

  const startRow = Math.min(selection?.row ?? 0, selection?.endRow ?? selection?.row ?? 0);
  const endRow = Math.max(selection?.row ?? 0, selection?.endRow ?? selection?.row ?? 0);
  const startCol = Math.min(selection?.col ?? 0, selection?.endCol ?? selection?.col ?? 0);
  const endCol = Math.max(selection?.col ?? 0, selection?.endCol ?? selection?.col ?? 0);

  const selectedRowCount = endRow - startRow + 1;
  const selectedColCount = endCol - startCol + 1;

  return (
    <SidebarSection title="셀 크기" defaultOpen={true}>
      <div className="text-[10px] text-gray-500 mb-2">
        {isCellSelected ? (
          hasMultipleCells ? (
            `선택: ${selectedRowCount}행 × ${selectedColCount}열`
          ) : (
            `셀 (${(selection?.row ?? 0) + 1}, ${(selection?.col ?? 0) + 1})`
          )
        ) : (
          "셀을 선택하세요 (Shift+클릭으로 범위 선택)"
        )}
      </div>
      <SidebarField label="너비 (mm)">
        <input
          type="number"
          value={cellWidth}
          disabled={!isCellSelected}
          step={1}
          min={5}
          onChange={(e) => setCellWidth(Number(e.target.value))}
          onBlur={() => isCellSelected && cellWidth > 0 && setSelectedCellsSize(cellWidth, undefined)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && isCellSelected && cellWidth > 0) {
              setSelectedCellsSize(cellWidth, undefined);
            }
          }}
          className={inputClass}
        />
      </SidebarField>
      <SidebarField label="높이 (mm)">
        <input
          type="number"
          value={cellHeight}
          disabled={!isCellSelected}
          step={1}
          min={3}
          onChange={(e) => setCellHeight(Number(e.target.value))}
          onBlur={() => isCellSelected && cellHeight > 0 && setSelectedCellsSize(undefined, cellHeight)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && isCellSelected && cellHeight > 0) {
              setSelectedCellsSize(undefined, cellHeight);
            }
          }}
          className={inputClass}
        />
      </SidebarField>
    </SidebarSection>
  );
}

export function TablePropertiesPanel() {
  const selection = useEditorStore((s) => s.selection);
  const viewModel = useEditorStore((s) => s.viewModel);
  const setTablePageBreak = useEditorStore((s) => s.setTablePageBreak);
  const setTableRepeatHeader = useEditorStore((s) => s.setTableRepeatHeader);
  const setTableSize = useEditorStore((s) => s.setTableSize);
  const setTableOutMargin = useEditorStore((s) => s.setTableOutMargin);
  const setTableInMargin = useEditorStore((s) => s.setTableInMargin);

  const sIdx = selection?.sectionIndex ?? 0;
  const pIdx = selection?.paragraphIndex ?? 0;
  const tIdx = selection?.tableIndex ?? 0;

  const table = viewModel?.sections[sIdx]?.paragraphs[pIdx]?.tables[tIdx];
  const hasTable = !!table;

  const widthMm = table ? roundMm(table.widthHwp) : 0;
  const heightMm = table ? roundMm(table.heightHwp) : 0;

  const [editWidth, setEditWidth] = useState(widthMm);
  const [editHeight, setEditHeight] = useState(heightMm);

  // Outer margin state
  const [outTop, setOutTop] = useState(table ? roundMm(table.outMargin.top) : 0);
  const [outBottom, setOutBottom] = useState(table ? roundMm(table.outMargin.bottom) : 0);
  const [outLeft, setOutLeft] = useState(table ? roundMm(table.outMargin.left) : 0);
  const [outRight, setOutRight] = useState(table ? roundMm(table.outMargin.right) : 0);

  // Inner margin state
  const [inTop, setInTop] = useState(table ? roundMm(table.inMargin.top) : 0);
  const [inBottom, setInBottom] = useState(table ? roundMm(table.inMargin.bottom) : 0);
  const [inLeft, setInLeft] = useState(table ? roundMm(table.inMargin.left) : 0);
  const [inRight, setInRight] = useState(table ? roundMm(table.inMargin.right) : 0);

  useEffect(() => {
    setEditWidth(widthMm);
    setEditHeight(heightMm);
  }, [widthMm, heightMm]);

  useEffect(() => {
    if (!table) return;
    setOutTop(roundMm(table.outMargin.top));
    setOutBottom(roundMm(table.outMargin.bottom));
    setOutLeft(roundMm(table.outMargin.left));
    setOutRight(roundMm(table.outMargin.right));
    setInTop(roundMm(table.inMargin.top));
    setInBottom(roundMm(table.inMargin.bottom));
    setInLeft(roundMm(table.inMargin.left));
    setInRight(roundMm(table.inMargin.right));
  }, [table?.outMargin.top, table?.outMargin.bottom, table?.outMargin.left, table?.outMargin.right,
      table?.inMargin.top, table?.inMargin.bottom, table?.inMargin.left, table?.inMargin.right]);

  const pageBreak = table?.pageBreak ?? "CELL";
  const repeatHeader = table?.repeatHeader ?? false;

  const PAGE_BREAK_OPTIONS = [
    { value: "CELL" as const, label: "나눔", desc: "쪽 경계에서 표를 나눕니다" },
    { value: "CELL" as const, label: "셀 단위로 나눔", desc: "셀 단위로 나눕니다" },
    { value: "NONE" as const, label: "나누지 않음", desc: "표를 나누지 않습니다" },
  ];

  const inputClass =
    "w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40";

  return (
    <div className="text-xs">
      <SidebarSection title="여러 쪽 지원">
        <div className="mb-2">
          <span className="text-[11px] text-gray-600 block mb-1.5">쪽 경계에서</span>
          <div className="flex gap-1">
            {PAGE_BREAK_OPTIONS.map((opt, i) => {
              const isActive =
                (i <= 1 && pageBreak === "CELL") ||
                (i === 2 && pageBreak === "NONE");
              return (
                <button
                  key={opt.label}
                  disabled={!hasTable}
                  onClick={() => setTablePageBreak(opt.value)}
                  className={`flex-1 py-2 rounded border text-[9px] flex flex-col items-center gap-1 transition-colors ${
                    isActive
                      ? "bg-blue-50 border-blue-300 text-blue-700"
                      : "bg-white border-gray-200 text-gray-500 hover:bg-gray-50"
                  } disabled:opacity-60 disabled:cursor-not-allowed`}
                  title={opt.desc}
                >
                  <svg width="22" height="18" viewBox="0 0 22 18" fill="none" className="mx-auto">
                    <rect x="1" y="1" width="20" height="7" rx="0.5" stroke="currentColor" strokeWidth="1" fill="none" />
                    <line x1="8" y1="1" x2="8" y2="8" stroke="currentColor" strokeWidth="0.5" />
                    <line x1="15" y1="1" x2="15" y2="8" stroke="currentColor" strokeWidth="0.5" />
                    {i === 0 && (
                      <>
                        <line x1="1" y1="4.5" x2="21" y2="4.5" stroke="currentColor" strokeWidth="0.5" strokeDasharray="2 1" />
                        <rect x="1" y="10" width="20" height="7" rx="0.5" stroke="currentColor" strokeWidth="1" fill="none" />
                        <line x1="8" y1="10" x2="8" y2="17" stroke="currentColor" strokeWidth="0.5" />
                        <line x1="15" y1="10" x2="15" y2="17" stroke="currentColor" strokeWidth="0.5" />
                      </>
                    )}
                    {i === 1 && (
                      <>
                        <line x1="1" y1="4.5" x2="21" y2="4.5" stroke="currentColor" strokeWidth="0.5" strokeDasharray="2 1" />
                        <rect x="1" y="10" width="20" height="7" rx="0.5" stroke="currentColor" strokeWidth="1" fill="none" />
                        <line x1="8" y1="10" x2="8" y2="17" stroke="currentColor" strokeWidth="0.5" />
                        <line x1="15" y1="10" x2="15" y2="17" stroke="currentColor" strokeWidth="0.5" />
                        <line x1="1" y1="13.5" x2="21" y2="13.5" stroke="currentColor" strokeWidth="0.5" />
                      </>
                    )}
                    {i === 2 && (
                      <line x1="1" y1="4.5" x2="21" y2="4.5" stroke="currentColor" strokeWidth="0.5" />
                    )}
                  </svg>
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>
        <label className="flex items-center gap-2 text-[11px] text-gray-600 mb-2">
          <input
            type="checkbox"
            checked={repeatHeader}
            disabled={!hasTable}
            onChange={(e) => setTableRepeatHeader(e.target.checked)}
            className="w-3 h-3"
          />
          제목 줄 자동 반복
        </label>
        <label className="flex items-center gap-2 text-[11px] text-gray-600">
          <input type="checkbox" disabled className="w-3 h-3" />
          자동으로 나뉜 표의 경계선 설정
        </label>
      </SidebarSection>

      <SidebarSection title="표 크기">
        <SidebarField label="너비 (mm)">
          <input
            type="number"
            value={editWidth}
            disabled={!hasTable}
            step={1}
            min={10}
            onChange={(e) => setEditWidth(Number(e.target.value))}
            onBlur={() => {
              if (hasTable && editWidth > 0) setTableSize(editWidth, editHeight);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && hasTable && editWidth > 0) {
                setTableSize(editWidth, editHeight);
              }
            }}
            className={inputClass}
          />
        </SidebarField>
        <SidebarField label="높이 (mm)">
          <input
            type="number"
            value={editHeight}
            disabled={!hasTable}
            step={1}
            min={10}
            onChange={(e) => setEditHeight(Number(e.target.value))}
            onBlur={() => {
              if (hasTable && editHeight > 0) setTableSize(editWidth, editHeight);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && hasTable && editHeight > 0) {
                setTableSize(editWidth, editHeight);
              }
            }}
            className={inputClass}
          />
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="표 정보">
        <SidebarField label="행">
          <input
            type="number"
            value={table?.rowCount ?? 0}
            disabled
            onChange={() => {}}
            className={inputClass}
          />
        </SidebarField>
        <SidebarField label="열">
          <input
            type="number"
            value={table?.colCount ?? 0}
            disabled
            onChange={() => {}}
            className={inputClass}
          />
        </SidebarField>
      </SidebarSection>

      <CellSizeSection selection={selection} hasTable={hasTable} inputClass={inputClass} />

      <SidebarSection title="바깥 여백" defaultOpen={false}>
        <SidebarField label="위 (mm)">
          <input type="number" value={outTop} disabled={!hasTable} step={0.1} min={0}
            onChange={(e) => setOutTop(Number(e.target.value))}
            onBlur={() => hasTable && setTableOutMargin({ top: outTop, bottom: outBottom, left: outLeft, right: outRight })}
            onKeyDown={(e) => { if (e.key === "Enter" && hasTable) setTableOutMargin({ top: outTop, bottom: outBottom, left: outLeft, right: outRight }); }}
            className={inputClass} />
        </SidebarField>
        <SidebarField label="아래 (mm)">
          <input type="number" value={outBottom} disabled={!hasTable} step={0.1} min={0}
            onChange={(e) => setOutBottom(Number(e.target.value))}
            onBlur={() => hasTable && setTableOutMargin({ top: outTop, bottom: outBottom, left: outLeft, right: outRight })}
            onKeyDown={(e) => { if (e.key === "Enter" && hasTable) setTableOutMargin({ top: outTop, bottom: outBottom, left: outLeft, right: outRight }); }}
            className={inputClass} />
        </SidebarField>
        <SidebarField label="왼쪽 (mm)">
          <input type="number" value={outLeft} disabled={!hasTable} step={0.1} min={0}
            onChange={(e) => setOutLeft(Number(e.target.value))}
            onBlur={() => hasTable && setTableOutMargin({ top: outTop, bottom: outBottom, left: outLeft, right: outRight })}
            onKeyDown={(e) => { if (e.key === "Enter" && hasTable) setTableOutMargin({ top: outTop, bottom: outBottom, left: outLeft, right: outRight }); }}
            className={inputClass} />
        </SidebarField>
        <SidebarField label="오른쪽 (mm)">
          <input type="number" value={outRight} disabled={!hasTable} step={0.1} min={0}
            onChange={(e) => setOutRight(Number(e.target.value))}
            onBlur={() => hasTable && setTableOutMargin({ top: outTop, bottom: outBottom, left: outLeft, right: outRight })}
            onKeyDown={(e) => { if (e.key === "Enter" && hasTable) setTableOutMargin({ top: outTop, bottom: outBottom, left: outLeft, right: outRight }); }}
            className={inputClass} />
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="안쪽 여백" defaultOpen={false}>
        <SidebarField label="위 (mm)">
          <input type="number" value={inTop} disabled={!hasTable} step={0.1} min={0}
            onChange={(e) => setInTop(Number(e.target.value))}
            onBlur={() => hasTable && setTableInMargin({ top: inTop, bottom: inBottom, left: inLeft, right: inRight })}
            onKeyDown={(e) => { if (e.key === "Enter" && hasTable) setTableInMargin({ top: inTop, bottom: inBottom, left: inLeft, right: inRight }); }}
            className={inputClass} />
        </SidebarField>
        <SidebarField label="아래 (mm)">
          <input type="number" value={inBottom} disabled={!hasTable} step={0.1} min={0}
            onChange={(e) => setInBottom(Number(e.target.value))}
            onBlur={() => hasTable && setTableInMargin({ top: inTop, bottom: inBottom, left: inLeft, right: inRight })}
            onKeyDown={(e) => { if (e.key === "Enter" && hasTable) setTableInMargin({ top: inTop, bottom: inBottom, left: inLeft, right: inRight }); }}
            className={inputClass} />
        </SidebarField>
        <SidebarField label="왼쪽 (mm)">
          <input type="number" value={inLeft} disabled={!hasTable} step={0.1} min={0}
            onChange={(e) => setInLeft(Number(e.target.value))}
            onBlur={() => hasTable && setTableInMargin({ top: inTop, bottom: inBottom, left: inLeft, right: inRight })}
            onKeyDown={(e) => { if (e.key === "Enter" && hasTable) setTableInMargin({ top: inTop, bottom: inBottom, left: inLeft, right: inRight }); }}
            className={inputClass} />
        </SidebarField>
        <SidebarField label="오른쪽 (mm)">
          <input type="number" value={inRight} disabled={!hasTable} step={0.1} min={0}
            onChange={(e) => setInRight(Number(e.target.value))}
            onBlur={() => hasTable && setTableInMargin({ top: inTop, bottom: inBottom, left: inLeft, right: inRight })}
            onKeyDown={(e) => { if (e.key === "Enter" && hasTable) setTableInMargin({ top: inTop, bottom: inBottom, left: inLeft, right: inRight }); }}
            className={inputClass} />
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="테두리" defaultOpen={false}>
        <SidebarField label="색">
          <select disabled className={inputClass}>
            <option>검정</option>
          </select>
        </SidebarField>
        <SidebarField label="종류">
          <select disabled className={inputClass}>
            <option>실선</option>
          </select>
        </SidebarField>
        <SidebarField label="굵기">
          <select disabled className={inputClass}>
            <option>0.1 mm</option>
            <option>0.12 mm</option>
            <option>0.15 mm</option>
            <option>0.2 mm</option>
            <option>0.25 mm</option>
            <option>0.3 mm</option>
            <option>0.4 mm</option>
            <option>0.5 mm</option>
            <option>0.6 mm</option>
            <option>0.7 mm</option>
            <option>1.0 mm</option>
          </select>
        </SidebarField>
      </SidebarSection>
    </div>
  );
}
