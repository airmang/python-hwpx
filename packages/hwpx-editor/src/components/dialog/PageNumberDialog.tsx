"use client";

import { useState } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";

export function PageNumberDialog() {
  const uiState = useEditorStore((s) => s.uiState);
  const closePageNumberDialog = useEditorStore((s) => s.closePageNumberDialog);
  const setPageNumbering = useEditorStore((s) => s.setPageNumbering);

  const [position, setPosition] = useState<string>("footer-center");
  const [startNumber, setStartNumber] = useState(1);
  const [format, setFormat] = useState<string>("arabic");

  const handleApply = () => {
    setPageNumbering({ position, startNumber });
    closePageNumberDialog();
  };

  const inputClass =
    "w-full px-2 py-1.5 text-sm border border-gray-300 rounded bg-white focus:outline-none focus:border-blue-400";

  return (
    <Dialog
      title="쪽 번호 매기기"
      open={uiState.pageNumberDialogOpen}
      onClose={closePageNumberDialog}
      onApply={handleApply}
      width={400}
    >
      <DialogSection title="위치">
        <div className="space-y-2">
          <div className="text-xs text-gray-600 mb-2">머리말</div>
          <div className="flex gap-2">
            <label className="flex items-center gap-1 text-xs flex-1">
              <input
                type="radio"
                name="pageNumPos"
                value="header-left"
                checked={position === "header-left"}
                onChange={(e) => setPosition(e.target.value)}
              />
              왼쪽
            </label>
            <label className="flex items-center gap-1 text-xs flex-1">
              <input
                type="radio"
                name="pageNumPos"
                value="header-center"
                checked={position === "header-center"}
                onChange={(e) => setPosition(e.target.value)}
              />
              가운데
            </label>
            <label className="flex items-center gap-1 text-xs flex-1">
              <input
                type="radio"
                name="pageNumPos"
                value="header-right"
                checked={position === "header-right"}
                onChange={(e) => setPosition(e.target.value)}
              />
              오른쪽
            </label>
          </div>

          <div className="text-xs text-gray-600 mb-2 mt-3">꼬리말</div>
          <div className="flex gap-2">
            <label className="flex items-center gap-1 text-xs flex-1">
              <input
                type="radio"
                name="pageNumPos"
                value="footer-left"
                checked={position === "footer-left"}
                onChange={(e) => setPosition(e.target.value)}
              />
              왼쪽
            </label>
            <label className="flex items-center gap-1 text-xs flex-1">
              <input
                type="radio"
                name="pageNumPos"
                value="footer-center"
                checked={position === "footer-center"}
                onChange={(e) => setPosition(e.target.value)}
              />
              가운데
            </label>
            <label className="flex items-center gap-1 text-xs flex-1">
              <input
                type="radio"
                name="pageNumPos"
                value="footer-right"
                checked={position === "footer-right"}
                onChange={(e) => setPosition(e.target.value)}
              />
              오른쪽
            </label>
          </div>

          <label className="flex items-center gap-1 text-xs mt-3">
            <input
              type="radio"
              name="pageNumPos"
              value="none"
              checked={position === "none"}
              onChange={(e) => setPosition(e.target.value)}
            />
            쪽 번호 없음
          </label>
        </div>
      </DialogSection>

      <DialogSection title="번호 형식">
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          className={inputClass}
        >
          <option value="arabic">1, 2, 3, ...</option>
          <option value="roman-lower">i, ii, iii, ...</option>
          <option value="roman-upper">I, II, III, ...</option>
          <option value="alpha-lower">a, b, c, ...</option>
          <option value="alpha-upper">A, B, C, ...</option>
          <option value="korean">가, 나, 다, ...</option>
          <option value="hanja">一, 二, 三, ...</option>
        </select>
      </DialogSection>

      <DialogSection title="시작 번호">
        <input
          type="number"
          min={1}
          value={startNumber}
          onChange={(e) => setStartNumber(Math.max(1, parseInt(e.target.value) || 1))}
          className={`${inputClass} w-24`}
        />
      </DialogSection>

      <div className="text-xs text-gray-500 mt-3">
        <p>미리보기: <span className="font-mono bg-gray-100 px-2 py-0.5 rounded">- {startNumber} -</span></p>
      </div>
    </Dialog>
  );
}
