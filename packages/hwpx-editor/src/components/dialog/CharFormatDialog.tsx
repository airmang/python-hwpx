"use client";

import { useCallback, useEffect, useState } from "react";
import { Highlighter, Type } from "lucide-react";
import { useEditorStore } from "@/lib/store";
import { DEFAULT_FONT_FAMILY, FONT_FAMILIES } from "@/lib/constants";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";
import { ColorPicker } from "../toolbar/ColorPicker";

export function CharFormatDialog() {
  const open = useEditorStore((s) => s.uiState.charFormatDialogOpen);
  const closeCharFormatDialog = useEditorStore((s) => s.closeCharFormatDialog);
  const extendedFormat = useEditorStore((s) => s.extendedFormat);

  const toggleBold = useEditorStore((s) => s.toggleBold);
  const toggleItalic = useEditorStore((s) => s.toggleItalic);
  const toggleUnderline = useEditorStore((s) => s.toggleUnderline);
  const toggleStrikethrough = useEditorStore((s) => s.toggleStrikethrough);
  const setFontFamily = useEditorStore((s) => s.setFontFamily);
  const setFontSize = useEditorStore((s) => s.setFontSize);
  const setTextColor = useEditorStore((s) => s.setTextColor);
  const setHighlightColor = useEditorStore((s) => s.setHighlightColor);

  const cf = extendedFormat.char;
  const [fontSize, setLocalFontSize] = useState(cf.fontSize ?? 10);
  const [fontFamily, setLocalFontFamily] = useState(cf.fontFamily ?? DEFAULT_FONT_FAMILY);
  const [textColor, setLocalTextColor] = useState(cf.textColor ?? "#000000");
  const [highlightColor, setLocalHighlightColor] = useState(cf.highlightColor ?? "none");
  const [bold, setBold] = useState(cf.bold);
  const [italic, setItalic] = useState(cf.italic);
  const [underline, setUnderline] = useState(cf.underline);
  const [strikethrough, setStrikethrough] = useState(cf.strikethrough);

  useEffect(() => {
    if (!open) return;
    setLocalFontSize(cf.fontSize ?? 10);
    setLocalFontFamily(cf.fontFamily ?? DEFAULT_FONT_FAMILY);
    setLocalTextColor(cf.textColor ?? "#000000");
    setLocalHighlightColor(cf.highlightColor ?? "none");
    setBold(cf.bold);
    setItalic(cf.italic);
    setUnderline(cf.underline);
    setStrikethrough(cf.strikethrough);
  }, [cf.bold, cf.fontFamily, cf.fontSize, cf.highlightColor, cf.italic, cf.strikethrough, cf.textColor, cf.underline, open]);

  const handleApply = useCallback(() => {
    if (fontFamily !== (cf.fontFamily ?? DEFAULT_FONT_FAMILY)) {
      setFontFamily(fontFamily);
    }

    const safeFontSize = Number.isFinite(fontSize) ? Math.max(1, Math.round(fontSize * 10) / 10) : 10;
    if (safeFontSize !== (cf.fontSize ?? 10)) {
      setFontSize(safeFontSize);
    }

    if (textColor !== (cf.textColor ?? "#000000")) {
      setTextColor(textColor);
    }

    const nextHighlightColor = highlightColor || "none";
    if (nextHighlightColor !== (cf.highlightColor ?? "none")) {
      setHighlightColor(nextHighlightColor);
    }

    if (bold !== cf.bold) {
      toggleBold();
    }
    if (italic !== cf.italic) {
      toggleItalic();
    }
    if (underline !== cf.underline) {
      toggleUnderline();
    }
    if (strikethrough !== cf.strikethrough) {
      toggleStrikethrough();
    }

    closeCharFormatDialog();
  }, [
    bold,
    cf.bold,
    cf.fontFamily,
    cf.fontSize,
    cf.highlightColor,
    cf.italic,
    cf.strikethrough,
    cf.textColor,
    cf.underline,
    closeCharFormatDialog,
    fontFamily,
    fontSize,
    highlightColor,
    italic,
    setFontFamily,
    setFontSize,
    setHighlightColor,
    setTextColor,
    strikethrough,
    textColor,
    toggleBold,
    toggleItalic,
    toggleStrikethrough,
    toggleUnderline,
    underline,
  ]);

  const inputClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";
  const selectClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";

  const attrButtons = [
    { label: "B", title: "굵게", active: bold, toggle: () => setBold((v) => !v), className: "font-bold" },
    { label: "I", title: "기울임", active: italic, toggle: () => setItalic((v) => !v), className: "italic" },
    { label: "U", title: "밑줄", active: underline, toggle: () => setUnderline((v) => !v), className: "underline" },
    { label: "S", title: "취소선", active: strikethrough, toggle: () => setStrikethrough((v) => !v), className: "line-through" },
  ];

  return (
    <Dialog title="글자 모양" open={open} onClose={closeCharFormatDialog} onApply={handleApply} width={520}>
      <DialogSection title="기본">
        <div className="grid grid-cols-2 gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">글꼴</span>
            <select
              className={`${selectClass} flex-1`}
              value={fontFamily}
              onChange={(e) => setLocalFontFamily(e.target.value)}
            >
              {FONT_FAMILIES.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-10">크기</span>
            <input
              type="number"
              step="0.5"
              min={1}
              max={200}
              value={fontSize}
              onChange={(e) => setLocalFontSize(Number(e.target.value))}
              className={`${inputClass} flex-1`}
            />
          </div>
        </div>
      </DialogSection>

      <DialogSection title="속성">
        <div className="flex gap-1.5 mb-3">
          {attrButtons.map((attr) => (
            <button
              key={attr.title}
              type="button"
              onClick={attr.toggle}
              title={attr.title}
              className={`w-10 h-10 rounded border text-lg flex items-center justify-center transition-colors ${
                attr.active
                  ? "bg-blue-50 border-blue-300 text-blue-700"
                  : "bg-white border-gray-300 text-gray-700 hover:bg-gray-50"
              }`}
            >
              <span className={attr.className}>{attr.label}</span>
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">글자 색</span>
            <ColorPicker
              color={textColor}
              onChange={setLocalTextColor}
              icon={<Type className="w-4 h-4" />}
              title="글자 색"
              buttonClassName="p-1.5"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-12">형광펜</span>
            <ColorPicker
              color={highlightColor}
              onChange={setLocalHighlightColor}
              icon={<Highlighter className="w-4 h-4" />}
              title="형광펜 색"
              allowNone
              buttonClassName="p-1.5"
            />
          </div>
        </div>
      </DialogSection>
    </Dialog>
  );
}
