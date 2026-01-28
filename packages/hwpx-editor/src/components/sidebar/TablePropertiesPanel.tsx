"use client";

import { useEditorStore } from "@/lib/store";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";

export function TablePropertiesPanel() {
  const selection = useEditorStore((s) => s.selection);
  const viewModel = useEditorStore((s) => s.viewModel);
  const setTablePageBreak = useEditorStore((s) => s.setTablePageBreak);
  const setTableRepeatHeader = useEditorStore((s) => s.setTableRepeatHeader);

  const sIdx = selection?.sectionIndex ?? 0;
  const pIdx = selection?.paragraphIndex ?? 0;
  const tIdx = selection?.tableIndex ?? 0;

  const table = viewModel?.sections[sIdx]?.paragraphs[pIdx]?.tables[tIdx];
  const hasTable = !!table;

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
