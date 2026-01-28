"use client";

import type { TextBoxVM } from "@/lib/view-model";

interface TextBoxBlockProps {
  textBox: TextBoxVM;
  selected?: boolean;
  onClick?: () => void;
}

export function TextBoxBlock({ textBox, selected, onClick }: TextBoxBlockProps) {
  return (
    <div
      className={`inline-block relative cursor-pointer ${selected ? "ring-2 ring-blue-500" : ""}`}
      style={{
        width: textBox.widthPx,
        minHeight: textBox.heightPx,
        backgroundColor: textBox.fillColor,
        border: `1px solid ${textBox.borderColor}`,
        padding: "4px 8px",
        boxSizing: "border-box",
      }}
      onClick={onClick}
    >
      <div className="whitespace-pre-wrap break-words text-sm">
        {textBox.text || "\u00A0"}
      </div>
    </div>
  );
}
