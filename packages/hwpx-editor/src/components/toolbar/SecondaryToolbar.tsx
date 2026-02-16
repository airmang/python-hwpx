"use client";

import { useState } from "react";
import { useEditorStore } from "@/lib/store";
import { StyleSelector } from "./StyleSelector";
import { FontSelector } from "./FontSelector";
import { FontSizeInput } from "./FontSizeInput";
import { CharFormatButtons } from "./CharFormatButtons";
import { AlignmentButtons } from "./AlignmentButtons";
import { LineSpacingControl } from "./LineSpacingControl";
import { ToolbarDivider } from "./ToolbarDivider";
import { ToolbarDropdown } from "./ToolbarDropdown";
import { DEFAULT_FONT_FAMILY, type SidebarTab } from "@/lib/constants";
import { readStyleInfo } from "@/lib/format-bridge";
import { Paintbrush, PanelRightOpen } from "lucide-react";

export function SecondaryToolbar() {
  const doc = useEditorStore((s) => s.doc);
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const selection = useEditorStore((s) => s.selection);
  const uiState = useEditorStore((s) => s.uiState);
  const setSidebarTab = useEditorStore((s) => s.setSidebarTab);
  const toggleSidebar = useEditorStore((s) => s.toggleSidebar);
  const applyStyle = useEditorStore((s) => s.applyStyle);
  const setFontFamily = useEditorStore((s) => s.setFontFamily);
  const setFontSize = useEditorStore((s) => s.setFontSize);
  const formatPainter = useEditorStore((s) => s.formatPainter);
  const startFormatPainter = useEditorStore((s) => s.startFormatPainter);
  const cancelFormatPainter = useEditorStore((s) => s.cancelFormatPainter);

  const [painterMode, setPainterMode] = useState<"char" | "para" | "both" | "cell">("both");

  const disabled = !doc || !selection;
  const styleValue = (() => {
    if (!doc || !selection) return "0";
    const section = doc.sections[selection.sectionIndex];
    const paragraph = section?.paragraphs[selection.paragraphIndex];
    if (!paragraph) return "0";
    const { styleId } = readStyleInfo(doc, paragraph);
    return styleId ?? "0";
  })();

  const context = selection?.objectType === "image"
    ? "image"
    : (selection?.objectType === "table" || selection?.type === "cell")
      ? "table"
      : "text";

  const tabs: { tab: SidebarTab; label: string }[] =
    context === "image"
      ? [
          { tab: "img-layout", label: "배치" },
          { tab: "img-props", label: "그림" },
        ]
      : context === "table"
        ? [
            { tab: "table", label: "표" },
            { tab: "cell", label: "셀" },
          ]
        : [
            { tab: "char", label: "글자 모양" },
            { tab: "para", label: "문단 모양" },
            { tab: "page", label: "편집 용지" },
          ];

  const handleTabClick = (tab: SidebarTab) => {
    setSidebarTab(tab);
    if (!uiState.sidebarOpen) toggleSidebar();
  };

  return (
    <div className="flex items-center gap-1.5 bg-gray-50 border-b border-gray-200 px-3 py-1 flex-wrap min-h-[38px]">
      {/* Style selector */}
      <StyleSelector
        value={styleValue}
        onChange={applyStyle}
        disabled={disabled}
      />

      <ToolbarDivider />

      {/* Font selector */}
      <FontSelector
        value={extendedFormat.char.fontFamily || DEFAULT_FONT_FAMILY}
        onChange={setFontFamily}
        disabled={disabled}
      />

      {/* Font size */}
      <FontSizeInput
        value={extendedFormat.char.fontSize || 10}
        onChange={setFontSize}
        disabled={disabled}
      />

      <ToolbarDivider />

      {/* Character format buttons */}
      <CharFormatButtons />

      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={disabled}
          onClick={(e) => {
            if (formatPainter.active) {
              cancelFormatPainter();
              return;
            }
            startFormatPainter(painterMode, { locked: e.shiftKey });
          }}
          className={`h-9 px-2.5 text-sm border rounded bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed ${
            formatPainter.active ? "border-blue-400 text-blue-700 bg-blue-50" : "border-gray-300 text-gray-700"
          }`}
          title={formatPainter.active ? "서식 복사 취소" : "서식 복사(Shift+Click: 잠금)"}
          aria-label="서식 복사"
        >
          <Paintbrush aria-hidden="true" className="w-4 h-4" />
        </button>
        <ToolbarDropdown
          value={painterMode}
          options={[
            { value: "both", label: "서식: 글자+문단" },
            { value: "char", label: "서식: 글자만" },
            { value: "para", label: "서식: 문단만" },
            { value: "cell", label: "서식: 표/셀(글자)" },
          ]}
          onChange={(value) => setPainterMode(value as any)}
          disabled={disabled}
          width="w-36"
          title="서식 복사 옵션"
        />
      </div>

      <ToolbarDivider />

      {/* Alignment buttons */}
      <AlignmentButtons />

      <ToolbarDivider />

      {/* Line spacing */}
      <LineSpacingControl />

      {/* Spacer */}
      <div className="flex-1" />

      <div className="flex items-center gap-1 border border-gray-200 bg-white rounded-md px-1 py-0.5">
        {tabs.map(({ tab, label }) => (
          <button
            key={tab}
            disabled={disabled}
            onClick={() => handleTabClick(tab)}
            className={`px-2.5 py-1 text-xs font-medium rounded transition-colors disabled:opacity-40 ${
              uiState.sidebarOpen && uiState.sidebarTab === tab
                ? "bg-blue-50 text-blue-700"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {label}
          </button>
        ))}
        {!uiState.sidebarOpen ? (
          <button
            type="button"
            onClick={toggleSidebar}
            className="p-1 rounded text-gray-500 hover:text-gray-700 hover:bg-gray-100"
            title="서식 사이드바 열기"
            aria-label="서식 사이드바 열기"
          >
            <PanelRightOpen aria-hidden="true" className="w-4 h-4" />
          </button>
        ) : null}
      </div>
    </div>
  );
}
