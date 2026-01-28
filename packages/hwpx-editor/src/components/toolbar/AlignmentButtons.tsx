"use client";

import {
  AlignLeft,
  AlignCenter,
  AlignRight,
  AlignJustify,
  Columns2,
} from "lucide-react";
import { useEditorStore } from "@/lib/store";
import { ToolbarButton } from "./ToolbarButton";
import type { AlignmentType } from "@/lib/constants";

const ALIGNMENT_ICONS: Record<AlignmentType, React.ReactNode> = {
  LEFT: <AlignLeft className="w-3.5 h-3.5" />,
  CENTER: <AlignCenter className="w-3.5 h-3.5" />,
  RIGHT: <AlignRight className="w-3.5 h-3.5" />,
  JUSTIFY: <AlignJustify className="w-3.5 h-3.5" />,
  DISTRIBUTE: <Columns2 className="w-3.5 h-3.5" />,
};

const ALIGNMENT_LABELS: Record<AlignmentType, string> = {
  LEFT: "왼쪽 정렬 (Ctrl+L)",
  CENTER: "가운데 정렬 (Ctrl+E)",
  RIGHT: "오른쪽 정렬 (Ctrl+R)",
  JUSTIFY: "양쪽 정렬 (Ctrl+J)",
  DISTRIBUTE: "배분 정렬",
};

export function AlignmentButtons() {
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const setAlignment = useEditorStore((s) => s.setAlignment);

  const disabled = !doc || !selection;
  const currentAlignment = extendedFormat.para.alignment;

  return (
    <div className="flex items-center gap-0.5">
      {(Object.keys(ALIGNMENT_ICONS) as AlignmentType[]).map((align) => (
        <ToolbarButton
          key={align}
          icon={ALIGNMENT_ICONS[align]}
          active={currentAlignment === align}
          disabled={disabled}
          onClick={() => setAlignment(align)}
          title={ALIGNMENT_LABELS[align]}
        />
      ))}
    </div>
  );
}
