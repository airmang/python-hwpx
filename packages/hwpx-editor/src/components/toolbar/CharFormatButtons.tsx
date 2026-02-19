"use client";

import {
  Bold,
  Italic,
  Underline,
  Strikethrough,
  Highlighter,
  Type,
} from "lucide-react";
import { useEditorStore } from "@/lib/store";
import { ToolbarButton } from "./ToolbarButton";
import { ColorPicker } from "./ColorPicker";

export function CharFormatButtons() {
  const activeFormat = useEditorStore((s) => s.activeFormat);
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const selection = useEditorStore((s) => s.selection);
  const doc = useEditorStore((s) => s.doc);
  const toggleBold = useEditorStore((s) => s.toggleBold);
  const toggleItalic = useEditorStore((s) => s.toggleItalic);
  const toggleUnderline = useEditorStore((s) => s.toggleUnderline);
  const toggleStrikethrough = useEditorStore((s) => s.toggleStrikethrough);
  const setTextColor = useEditorStore((s) => s.setTextColor);
  const setHighlightColor = useEditorStore((s) => s.setHighlightColor);

  const disabled = !doc || !selection;

  return (
    <div className="flex items-center gap-0.5">
      <ColorPicker
        color={extendedFormat.char.textColor || "#000000"}
        onChange={(c) => setTextColor(c)}
        icon={<Type className="w-3.5 h-3.5" />}
        title="글자색"
        disabled={disabled}
      />
      <ColorPicker
        color={extendedFormat.char.highlightColor || "#FFFF00"}
        onChange={(c) => setHighlightColor(c)}
        icon={<Highlighter className="w-3.5 h-3.5" />}
        title="형광펜"
        disabled={disabled}
      />
      <ToolbarButton
        icon={<Bold className="w-3.5 h-3.5" />}
        active={activeFormat.bold}
        disabled={disabled}
        onClick={toggleBold}
        title="굵게 (Ctrl+B)"
      />
      <ToolbarButton
        icon={<Italic className="w-3.5 h-3.5" />}
        active={activeFormat.italic}
        disabled={disabled}
        onClick={toggleItalic}
        title="기울임 (Ctrl+I)"
      />
      <ToolbarButton
        icon={<Underline className="w-3.5 h-3.5" />}
        active={activeFormat.underline}
        disabled={disabled}
        onClick={toggleUnderline}
        title="밑줄 (Ctrl+U)"
      />
      <ToolbarButton
        icon={<Strikethrough className="w-3.5 h-3.5" />}
        active={activeFormat.strikethrough}
        disabled={disabled}
        onClick={toggleStrikethrough}
        title="취소선 (Ctrl+D)"
      />
    </div>
  );
}
