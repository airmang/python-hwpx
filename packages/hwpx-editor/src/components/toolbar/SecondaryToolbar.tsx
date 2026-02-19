"use client";

import { useEditorStore } from "@/lib/store";
import { StyleSelector } from "./StyleSelector";
import { FontSelector } from "./FontSelector";
import { FontSizeInput } from "./FontSizeInput";
import { CharFormatButtons } from "./CharFormatButtons";
import { AlignmentButtons } from "./AlignmentButtons";
import { LineSpacingControl } from "./LineSpacingControl";
import { ToolbarDivider } from "./ToolbarDivider";
import { Plus } from "lucide-react";

export function SecondaryToolbar() {
  const doc = useEditorStore((s) => s.doc);
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const addParagraph = useEditorStore((s) => s.addParagraph);

  const disabled = !doc;

  return (
    <div className="flex items-center gap-1 bg-gray-50 border-b border-gray-200 px-3 py-1 flex-wrap min-h-[36px]">
      {/* Style selector */}
      <StyleSelector
        value="0"
        onChange={() => {
          // Style change — placeholder
        }}
        disabled={disabled}
      />

      <ToolbarDivider />

      {/* Font selector */}
      <FontSelector
        value={extendedFormat.char.fontFamily || "맑은 고딕"}
        onChange={() => {
          // Font change — placeholder
        }}
        disabled={disabled}
      />

      {/* Font size */}
      <FontSizeInput
        value={extendedFormat.char.fontSize || 10}
        onChange={() => {
          // Font size change — placeholder
        }}
        disabled={disabled}
      />

      <ToolbarDivider />

      {/* Character format buttons */}
      <CharFormatButtons />

      <ToolbarDivider />

      {/* Alignment buttons */}
      <AlignmentButtons />

      <ToolbarDivider />

      {/* Line spacing */}
      <LineSpacingControl />

      {/* Spacer */}
      <div className="flex-1" />

      {/* Add paragraph */}
      <button
        disabled={disabled}
        onClick={() => addParagraph("")}
        className="flex items-center gap-1 px-2.5 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Plus className="w-3 h-3" />
        문단 추가
      </button>
    </div>
  );
}
