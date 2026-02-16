"use client";

import { useCallback, useEffect, useState } from "react";
import { useEditorStore } from "@/lib/store";
import type { AlignmentType } from "@/lib/constants";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";

const ALIGNMENTS: Array<{ value: AlignmentType; label: string }> = [
  { value: "LEFT", label: "왼쪽" },
  { value: "CENTER", label: "가운데" },
  { value: "RIGHT", label: "오른쪽" },
  { value: "JUSTIFY", label: "양쪽" },
  { value: "DISTRIBUTE", label: "배분" },
];

export function ParaFormatDialog() {
  const open = useEditorStore((s) => s.uiState.paraFormatDialogOpen);
  const closeParaFormatDialog = useEditorStore((s) => s.closeParaFormatDialog);
  const pf = useEditorStore((s) => s.extendedFormat.para);

  const setAlignment = useEditorStore((s) => s.setAlignment);
  const setLineSpacing = useEditorStore((s) => s.setLineSpacing);
  const setLeftIndent = useEditorStore((s) => s.setLeftIndent);
  const setRightIndent = useEditorStore((s) => s.setRightIndent);
  const setFirstLineIndent = useEditorStore((s) => s.setFirstLineIndent);
  const setParagraphSpacingBefore = useEditorStore((s) => s.setParagraphSpacingBefore);
  const setParagraphSpacingAfter = useEditorStore((s) => s.setParagraphSpacingAfter);

  const [alignment, setLocalAlignment] = useState<AlignmentType>(pf.alignment);
  const [leftIndent, setLocalLeftIndent] = useState(pf.indentLeft);
  const [rightIndent, setLocalRightIndent] = useState(pf.indentRight);
  const [firstLineIndent, setLocalFirstLineIndent] = useState(pf.firstLineIndent);
  const [lineSpacingPercent, setLocalLineSpacingPercent] = useState(Math.round(pf.lineSpacing * 100));
  const [spacingBefore, setLocalSpacingBefore] = useState(pf.spacingBefore);
  const [spacingAfter, setLocalSpacingAfter] = useState(pf.spacingAfter);

  useEffect(() => {
    if (!open) return;
    setLocalAlignment(pf.alignment);
    setLocalLeftIndent(pf.indentLeft);
    setLocalRightIndent(pf.indentRight);
    setLocalFirstLineIndent(pf.firstLineIndent);
    setLocalLineSpacingPercent(Math.round(pf.lineSpacing * 100));
    setLocalSpacingBefore(pf.spacingBefore);
    setLocalSpacingAfter(pf.spacingAfter);
  }, [open, pf.alignment, pf.firstLineIndent, pf.indentLeft, pf.indentRight, pf.lineSpacing, pf.spacingAfter, pf.spacingBefore]);

  const handleApply = useCallback(() => {
    if (alignment !== pf.alignment) {
      setAlignment(alignment);
    }
    if (leftIndent !== pf.indentLeft) {
      setLeftIndent(leftIndent);
    }
    if (rightIndent !== pf.indentRight) {
      setRightIndent(rightIndent);
    }
    if (firstLineIndent !== pf.firstLineIndent) {
      setFirstLineIndent(firstLineIndent);
    }

    const nextLineSpacing = Math.max(0.5, lineSpacingPercent / 100);
    if (Math.abs(nextLineSpacing - pf.lineSpacing) > 0.0001) {
      setLineSpacing(nextLineSpacing);
    }

    if (spacingBefore !== pf.spacingBefore) {
      setParagraphSpacingBefore(spacingBefore);
    }
    if (spacingAfter !== pf.spacingAfter) {
      setParagraphSpacingAfter(spacingAfter);
    }

    closeParaFormatDialog();
  }, [
    alignment,
    closeParaFormatDialog,
    firstLineIndent,
    leftIndent,
    lineSpacingPercent,
    pf.alignment,
    pf.firstLineIndent,
    pf.indentLeft,
    pf.indentRight,
    pf.lineSpacing,
    pf.spacingAfter,
    pf.spacingBefore,
    rightIndent,
    setAlignment,
    setFirstLineIndent,
    setLeftIndent,
    setLineSpacing,
    setParagraphSpacingAfter,
    setParagraphSpacingBefore,
    setRightIndent,
    spacingAfter,
    spacingBefore,
  ]);

  const inputClass = "h-7 px-2 text-xs border border-gray-300 rounded bg-white";

  return (
    <Dialog title="문단 모양" open={open} onClose={closeParaFormatDialog} onApply={handleApply} width={520}>
      <DialogSection title="정렬">
        <div className="flex gap-1.5">
          {ALIGNMENTS.map((a) => (
            <button
              key={a.value}
              type="button"
              onClick={() => setLocalAlignment(a.value)}
              className={`h-8 px-3 rounded border text-xs ${
                alignment === a.value
                  ? "bg-blue-50 border-blue-300 text-blue-700"
                  : "bg-white border-gray-300 text-gray-700 hover:bg-gray-50"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
      </DialogSection>

      <DialogSection title="여백">
        <div className="grid grid-cols-3 gap-2">
          <label className="text-xs text-gray-600 flex flex-col gap-1">
            <span>왼쪽</span>
            <input
              type="number"
              value={leftIndent}
              onChange={(e) => setLocalLeftIndent(Number(e.target.value) || 0)}
              className={inputClass}
            />
          </label>
          <label className="text-xs text-gray-600 flex flex-col gap-1">
            <span>오른쪽</span>
            <input
              type="number"
              value={rightIndent}
              onChange={(e) => setLocalRightIndent(Number(e.target.value) || 0)}
              className={inputClass}
            />
          </label>
          <label className="text-xs text-gray-600 flex flex-col gap-1">
            <span>첫 줄</span>
            <input
              type="number"
              value={firstLineIndent}
              onChange={(e) => setLocalFirstLineIndent(Number(e.target.value) || 0)}
              className={inputClass}
            />
          </label>
        </div>
      </DialogSection>

      <DialogSection title="간격">
        <div className="grid grid-cols-3 gap-2">
          <label className="text-xs text-gray-600 flex flex-col gap-1">
            <span>줄 간격 (%)</span>
            <input
              type="number"
              min={50}
              max={500}
              step={10}
              value={lineSpacingPercent}
              onChange={(e) => setLocalLineSpacingPercent(Number(e.target.value) || 160)}
              className={inputClass}
            />
          </label>
          <label className="text-xs text-gray-600 flex flex-col gap-1">
            <span>문단 앞</span>
            <input
              type="number"
              value={spacingBefore}
              onChange={(e) => setLocalSpacingBefore(Number(e.target.value) || 0)}
              className={inputClass}
            />
          </label>
          <label className="text-xs text-gray-600 flex flex-col gap-1">
            <span>문단 뒤</span>
            <input
              type="number"
              value={spacingAfter}
              onChange={(e) => setLocalSpacingAfter(Number(e.target.value) || 0)}
              className={inputClass}
            />
          </label>
        </div>
      </DialogSection>
    </Dialog>
  );
}
