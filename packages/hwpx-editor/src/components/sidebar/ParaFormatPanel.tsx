"use client";

import { useEditorStore } from "@/lib/store";
import {
  ALIGNMENT_OPTIONS,
  LINE_SPACING_OPTIONS,
} from "@/lib/constants";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";
import { BorderSettings } from "./BorderSettings";
import { BackgroundSettings } from "./BackgroundSettings";

export function ParaFormatPanel() {
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const setAlignment = useEditorStore((s) => s.setAlignment);
  const setLineSpacing = useEditorStore((s) => s.setLineSpacing);
  const setLeftIndent = useEditorStore((s) => s.setLeftIndent);
  const setRightIndent = useEditorStore((s) => s.setRightIndent);
  const setFirstLineIndent = useEditorStore((s) => s.setFirstLineIndent);
  const setParagraphSpacingBefore = useEditorStore((s) => s.setParagraphSpacingBefore);
  const setParagraphSpacingAfter = useEditorStore((s) => s.setParagraphSpacingAfter);

  const disabled = !doc || !selection;
  const pf = extendedFormat.para;

  return (
    <div className="text-xs">
      <SidebarSection title="정렬">
        <div className="flex gap-1 mb-2">
          {ALIGNMENT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              disabled={disabled}
              onClick={() => setAlignment(opt.value)}
              className={`flex-1 py-1 rounded text-[10px] border transition-colors ${
                pf.alignment === opt.value
                  ? "bg-blue-50 border-blue-300 text-blue-700"
                  : "bg-white border-gray-200 text-gray-500 hover:bg-gray-50"
              } disabled:opacity-40 disabled:cursor-not-allowed`}
              title={opt.label}
            >
              {opt.value === "LEFT" && "왼"}
              {opt.value === "CENTER" && "중"}
              {opt.value === "RIGHT" && "오"}
              {opt.value === "JUSTIFY" && "양"}
              {opt.value === "DISTRIBUTE" && "배"}
            </button>
          ))}
        </div>
      </SidebarSection>

      <SidebarSection title="여백">
        <SidebarField label="왼쪽">
          <input
            type="number"
            value={pf.indentLeft}
            disabled={disabled}
            onChange={(e) => setLeftIndent(Number(e.target.value) || 0)}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          />
        </SidebarField>
        <SidebarField label="오른쪽">
          <input
            type="number"
            value={pf.indentRight}
            disabled={disabled}
            onChange={(e) => setRightIndent(Number(e.target.value) || 0)}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          />
        </SidebarField>
        <SidebarField label="첫줄">
          <input
            type="number"
            value={pf.firstLineIndent}
            disabled={disabled}
            onChange={(e) => setFirstLineIndent(Number(e.target.value) || 0)}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          />
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="간격">
        <SidebarField label="줄 간격">
          <select
            disabled={disabled}
            value={String(
              LINE_SPACING_OPTIONS.reduce((prev, curr) =>
                Math.abs(curr.value - pf.lineSpacing) <
                Math.abs(prev.value - pf.lineSpacing)
                  ? curr
                  : prev,
              ).value,
            )}
            onChange={(e) => setLineSpacing(Number(e.target.value))}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          >
            {LINE_SPACING_OPTIONS.map((o) => (
              <option key={o.value} value={String(o.value)}>
                {o.label}
              </option>
            ))}
          </select>
        </SidebarField>
        <SidebarField label="문단 앞">
          <input
            type="number"
            value={pf.spacingBefore}
            disabled={disabled}
            onChange={(e) => setParagraphSpacingBefore(Number(e.target.value) || 0)}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          />
        </SidebarField>
        <SidebarField label="문단 뒤">
          <input
            type="number"
            value={pf.spacingAfter}
            disabled={disabled}
            onChange={(e) => setParagraphSpacingAfter(Number(e.target.value) || 0)}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          />
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="줄 나눔" defaultOpen={false}>
        <div className="space-y-1">
          <label className="flex items-center gap-2 text-[11px] text-gray-600">
            <input type="checkbox" disabled={disabled} className="w-3 h-3" />
            한글 단어 잘림 허용
          </label>
          <label className="flex items-center gap-2 text-[11px] text-gray-600">
            <input type="checkbox" disabled={disabled} className="w-3 h-3" />
            영어 단어 잘림 허용
          </label>
          <label className="flex items-center gap-2 text-[11px] text-gray-600">
            <input type="checkbox" disabled={disabled} className="w-3 h-3" />
            외톨이줄 방지
          </label>
        </div>
      </SidebarSection>

      <SidebarSection title="테두리" defaultOpen={false}>
        <BorderSettings disabled={disabled} />
      </SidebarSection>

      <SidebarSection title="배경" defaultOpen={false}>
        <BackgroundSettings disabled={disabled} />
      </SidebarSection>
    </div>
  );
}
