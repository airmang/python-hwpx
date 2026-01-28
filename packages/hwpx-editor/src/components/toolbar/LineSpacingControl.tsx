"use client";

import { useEditorStore } from "@/lib/store";
import { LINE_SPACING_OPTIONS } from "@/lib/constants";
import { ToolbarDropdown } from "./ToolbarDropdown";

export function LineSpacingControl() {
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const setLineSpacing = useEditorStore((s) => s.setLineSpacing);

  const disabled = !doc || !selection;
  const currentSpacing = extendedFormat.para.lineSpacing;

  // Find closest matching option
  const closestValue = LINE_SPACING_OPTIONS.reduce((prev, curr) =>
    Math.abs(curr.value - currentSpacing) < Math.abs(prev.value - currentSpacing)
      ? curr
      : prev,
  ).value;

  const options = LINE_SPACING_OPTIONS.map((o) => ({
    value: String(o.value),
    label: o.label,
  }));

  return (
    <ToolbarDropdown
      value={String(closestValue)}
      options={options}
      onChange={(val) => setLineSpacing(Number(val))}
      disabled={disabled}
      title="줄 간격"
      width="w-14"
    />
  );
}
