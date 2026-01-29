"use client";

import { useState } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";

const OUTLINE_STYLES = [
  {
    id: "none",
    name: "없음",
    levels: [],
  },
  {
    id: "numeric",
    name: "숫자 (1, 1.1, 1.1.1)",
    levels: ["1.", "1.1.", "1.1.1.", "1.1.1.1."],
  },
  {
    id: "korean",
    name: "가나다 (가, 나, 다)",
    levels: ["가.", "나.", "다.", "라."],
  },
  {
    id: "roman",
    name: "로마자 (I, II, III)",
    levels: ["I.", "II.", "III.", "IV."],
  },
  {
    id: "alpha",
    name: "알파벳 (A, B, C)",
    levels: ["A.", "B.", "C.", "D."],
  },
  {
    id: "mixed1",
    name: "혼합1 (1, 가, 1), (1))",
    levels: ["1.", "가.", "1)", "(1)"],
  },
  {
    id: "mixed2",
    name: "혼합2 (I, A, 1, a)",
    levels: ["I.", "A.", "1.", "a."],
  },
  {
    id: "circle",
    name: "원문자 (①, ②, ③)",
    levels: ["①", "②", "③", "④"],
  },
];

export function OutlineDialog() {
  const uiState = useEditorStore((s) => s.uiState);
  const closeOutlineDialog = useEditorStore((s) => s.closeOutlineDialog);
  const applyOutlineLevel = useEditorStore((s) => s.applyOutlineLevel);

  const [selectedStyle, setSelectedStyle] = useState(0);
  const [selectedLevel, setSelectedLevel] = useState(1);

  const handleApply = () => {
    if (selectedStyle === 0) {
      // Remove outline
      applyOutlineLevel(0);
    } else {
      applyOutlineLevel(selectedLevel);
    }
    closeOutlineDialog();
  };

  const currentStyle = OUTLINE_STYLES[selectedStyle];

  return (
    <Dialog
      title="개요 번호 모양"
      open={uiState.outlineDialogOpen}
      onClose={closeOutlineDialog}
      onApply={handleApply}
      width={480}
    >
      <DialogSection title="개요 스타일">
        <div className="grid grid-cols-2 gap-2">
          {OUTLINE_STYLES.map((style, idx) => (
            <button
              key={style.id}
              onClick={() => setSelectedStyle(idx)}
              className={`p-3 rounded border text-left transition-colors ${
                selectedStyle === idx
                  ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
            >
              <div className="text-sm font-medium">{style.name}</div>
              {style.levels.length > 0 && (
                <div className="text-xs text-gray-500 mt-1">
                  {style.levels.slice(0, 3).join(" → ")}
                </div>
              )}
            </button>
          ))}
        </div>
      </DialogSection>

      {selectedStyle !== 0 && (
        <DialogSection title="개요 수준">
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5, 6, 7].map((level) => (
              <button
                key={level}
                onClick={() => setSelectedLevel(level)}
                className={`w-10 h-10 rounded border text-sm font-medium transition-colors ${
                  selectedLevel === level
                    ? "border-blue-500 bg-blue-500 text-white"
                    : "border-gray-300 bg-white hover:bg-gray-50"
                }`}
              >
                {level}
              </button>
            ))}
          </div>
          <div className="text-xs text-gray-500 mt-2">
            선택한 수준: {selectedLevel} (들여쓰기 {(selectedLevel - 1) * 10}mm)
          </div>
        </DialogSection>
      )}

      <DialogSection title="미리보기">
        <div className="border border-gray-200 rounded p-3 bg-gray-50 min-h-[100px]">
          {currentStyle && currentStyle.levels.length > 0 ? (
            <div className="space-y-1">
              {currentStyle.levels.map((prefix, idx) => (
                <div
                  key={idx}
                  className="flex items-center text-sm"
                  style={{ paddingLeft: `${idx * 16}px` }}
                >
                  <span className="text-blue-600 font-medium mr-2">{prefix}</span>
                  <span className="text-gray-600">
                    {idx + 1}수준 개요 항목
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-gray-400 text-sm text-center py-4">
              개요 없음
            </div>
          )}
        </div>
      </DialogSection>
    </Dialog>
  );
}
