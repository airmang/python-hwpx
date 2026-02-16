"use client";

import { Highlighter, Type } from "lucide-react";
import { useEditorStore } from "@/lib/store";
import {
  DEFAULT_FONT_FAMILY,
  FONT_FAMILIES,
  FONT_SIZES,
  fontFamilyCssStack,
} from "@/lib/constants";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";
import { BorderSettings } from "./BorderSettings";
import { BackgroundSettings } from "./BackgroundSettings";
import { ColorPicker } from "../toolbar/ColorPicker";

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
            data-hwpx-testid="char-font-family"
            value={cf.fontFamily || DEFAULT_FONT_FAMILY}
            onChange={(e) => setFontFamily(e.target.value)}
            className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
          >
            {FONT_FAMILIES.map((f) => (
              <option key={f} value={f} style={{ fontFamily: fontFamilyCssStack(f) }}>
                {f}
              </option>
            ))}
          </select>
        </SidebarField>
        <SidebarField label="크기">
          <select
            disabled={disabled}
            data-hwpx-testid="char-font-size"
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
          <ColorPicker
            color={cf.textColor ?? "#000000"}
            onChange={(color) => setTextColor(color)}
            icon={<Type className="w-4 h-4" />}
            title="글자 색"
            disabled={disabled}
            buttonClassName="p-1.5"
          />
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
          <ColorPicker
            color={cf.highlightColor ?? "none"}
            onChange={(color) => setHighlightColor(color)}
            icon={<Highlighter className="w-4 h-4" />}
            title="형광펜 색"
            disabled={disabled}
            allowNone
            buttonClassName="p-1.5"
          />
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
