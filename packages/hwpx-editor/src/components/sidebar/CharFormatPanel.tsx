"use client";

import { useEditorStore } from "@/lib/store";
import { FONT_FAMILIES, FONT_SIZES } from "@/lib/constants";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";
import { BorderSettings } from "./BorderSettings";
import { BackgroundSettings } from "./BackgroundSettings";

export function CharFormatPanel() {
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const activeFormat = useEditorStore((s) => s.activeFormat);
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const setFontFamily = useEditorStore((s) => s.setFontFamily);
  const setFontSize = useEditorStore((s) => s.setFontSize);
  const setTextColor = useEditorStore((s) => s.setTextColor);
  const setHighlightColor = useEditorStore((s) => s.setHighlightColor);

  const disabled = !doc || !selection;
  const cf = extendedFormat.char;

  return (
    <div className="text-xs">
      <SidebarSection title="기본">
        <SidebarField label="스타일">
          <select
            disabled={disabled}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
            defaultValue="0"
          >
            <option value="0">바탕글</option>
            <option value="1">본문</option>
            <option value="2">개요 1</option>
            <option value="3">개요 2</option>
          </select>
        </SidebarField>
        <SidebarField label="글꼴">
          <select
            disabled={disabled}
            value={cf.fontFamily || "맑은 고딕"}
            onChange={(e) => setFontFamily(e.target.value)}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          >
            {FONT_FAMILIES.map((f) => (
              <option key={f} value={f} style={{ fontFamily: fontFamilyCss(f) }}>
                {f}
              </option>
            ))}
          </select>
        </SidebarField>
        <SidebarField label="크기">
          <select
            disabled={disabled}
            value={String(cf.fontSize || 10)}
            onChange={(e) => setFontSize(Number(e.target.value))}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          >
            {FONT_SIZES.map((s) => (
              <option key={s} value={String(s)}>
                {s}pt
              </option>
            ))}
          </select>
        </SidebarField>
        <SidebarField label="색상">
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={cf.textColor && cf.textColor !== "none" ? cf.textColor : "#000000"}
              onChange={(e) => setTextColor(e.target.value)}
              disabled={disabled}
              className="w-6 h-6 border border-gray-300 rounded cursor-pointer disabled:opacity-40"
            />
            <span className="text-[10px] text-gray-400">
              {cf.textColor && cf.textColor !== "none" ? cf.textColor : "#000000"}
            </span>
          </div>
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="꾸밈">
        <div className="flex flex-wrap gap-1 mb-2">
          <FormatTag label="굵게" active={activeFormat.bold} onClick={() => useEditorStore.getState().toggleBold()} disabled={disabled} />
          <FormatTag label="기울임" active={activeFormat.italic} onClick={() => useEditorStore.getState().toggleItalic()} disabled={disabled} />
          <FormatTag label="밑줄" active={activeFormat.underline} onClick={() => useEditorStore.getState().toggleUnderline()} disabled={disabled} />
          <FormatTag label="취소선" active={activeFormat.strikethrough} onClick={() => useEditorStore.getState().toggleStrikethrough()} disabled={disabled} />
        </div>
      </SidebarSection>

      <SidebarSection title="형광펜">
        <SidebarField label="색상">
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={cf.highlightColor && cf.highlightColor !== "none" ? cf.highlightColor : "#FFFF00"}
              onChange={(e) => setHighlightColor(e.target.value)}
              disabled={disabled}
              className="w-6 h-6 border border-gray-300 rounded cursor-pointer disabled:opacity-40"
            />
            <span className="text-[10px] text-gray-400">
              {cf.highlightColor || "없음"}
            </span>
          </div>
        </SidebarField>
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

function fontFamilyCss(name: string): string {
  if (name === "Noto Sans KR") return "var(--font-noto-sans-kr), sans-serif";
  if (name === "Noto Serif KR") return "var(--font-noto-serif-kr), serif";
  return `"${name}", sans-serif`;
}

function FormatTag({ label, active, onClick, disabled }: { label: string; active: boolean; onClick?: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-2 py-0.5 rounded text-[10px] border transition-colors ${
        active
          ? "bg-blue-50 border-blue-300 text-blue-700"
          : "bg-gray-50 border-gray-200 text-gray-400 hover:bg-gray-100"
      } disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      {label}
    </button>
  );
}
