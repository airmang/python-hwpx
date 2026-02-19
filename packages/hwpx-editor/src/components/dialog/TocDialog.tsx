"use client";

import { useState } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";

const TAB_LEADER_STYLES = [
  { id: "DOT", name: "점선 (.....)", preview: "제목 ..... 페이지" },
  { id: "HYPHEN", name: "하이픈 (-----)", preview: "제목 ----- 페이지" },
  { id: "UNDERLINE", name: "밑줄 (_____)", preview: "제목 _____ 페이지" },
  { id: "NONE", name: "없음", preview: "제목 페이지" },
];

const TOC_TITLES = [
  { id: "차례", name: "차례" },
  { id: "목차", name: "목차" },
  { id: "TABLE_OF_CONTENTS", name: "TABLE OF CONTENTS" },
  { id: "CONTENTS", name: "CONTENTS" },
];

export function TocDialog() {
  const uiState = useEditorStore((s) => s.uiState);
  const closeTocDialog = useEditorStore((s) => s.closeTocDialog);
  const applyOutlineLevel = useEditorStore((s) => s.applyOutlineLevel);
  const insertToc = useEditorStore((s) => s.insertToc);

  const [selectedTitle, setSelectedTitle] = useState("차례");
  const [tabLeader, setTabLeader] = useState<"DOT" | "HYPHEN" | "UNDERLINE" | "NONE">("DOT");
  const [tabWidth, setTabWidth] = useState(12000);
  const [maxLevel, setMaxLevel] = useState(9);
  const [showPageNumbers, setShowPageNumbers] = useState(true);

  const handleApply = () => {
    // Generate TOC with selected options
    insertToc({
      title: selectedTitle,
      tabLeader,
      tabWidth,
      maxLevel,
      showPageNumbers,
    });
    closeTocDialog();
  };

  return (
    <Dialog
      title="차례 만들기"
      open={uiState.tocDialogOpen}
      onClose={closeTocDialog}
      onApply={handleApply}
      width={500}
    >
      <DialogSection title="차례 제목">
        <div className="grid grid-cols-2 gap-2">
          {TOC_TITLES.map((title) => (
            <button
              key={title.id}
              onClick={() => setSelectedTitle(title.name)}
              className={`p-3 rounded border text-left transition-colors ${
                selectedTitle === title.name
                  ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
            >
              <div className="text-sm font-medium">{title.name}</div>
            </button>
          ))}
        </div>
        <input
          type="text"
          value={selectedTitle}
          onChange={(e) => setSelectedTitle(e.target.value)}
          className="mt-2 w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="차례 제목 직접 입력"
        />
      </DialogSection>

      <DialogSection title="탭 리더 (점선 스타일)">
        <div className="grid grid-cols-2 gap-2">
          {TAB_LEADER_STYLES.map((style) => (
            <button
              key={style.id}
              onClick={() => setTabLeader(style.id as any)}
              className={`p-3 rounded border text-left transition-colors ${
                tabLeader === style.id
                  ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
            >
              <div className="text-sm font-medium">{style.name}</div>
              <div className="text-xs text-gray-500 mt-1 font-mono">
                {style.preview}
              </div>
            </button>
          ))}
        </div>
      </DialogSection>

      <DialogSection title="옵션">
        <div className="space-y-4">
          {/* 최대 레벨 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              최대 레벨: {maxLevel}
            </label>
            <input
              type="range"
              min="1"
              max="9"
              value={maxLevel}
              onChange={(e) => setMaxLevel(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>1</span>
              <span>9</span>
            </div>
          </div>

          {/* 탭 너비 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              탭 위치: {tabWidth} hwpUnit
            </label>
            <input
              type="range"
              min="5000"
              max="20000"
              step="500"
              value={tabWidth}
              onChange={(e) => setTabWidth(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>5000</span>
              <span>20000</span>
            </div>
          </div>

          {/* 페이지 번호 표시 */}
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">
              페이지 번호 표시
            </label>
            <button
              onClick={() => setShowPageNumbers(!showPageNumbers)}
              className={`w-12 h-6 rounded-full transition-colors ${
                showPageNumbers
                  ? "bg-blue-500 text-white"
                  : "bg-gray-300 text-gray-600"
              }`}
            >
              {showPageNumbers ? "ON" : "OFF"}
            </button>
          </div>
        </div>
      </DialogSection>

      <DialogSection title="미리보기">
        <div className="border border-gray-200 rounded p-4 bg-gray-50">
          <div className="text-center font-bold mb-3">{selectedTitle}</div>
          <div className="space-y-2">
            {[1, 2, 3].slice(0, maxLevel).map((level) => (
              <div
                key={level}
                className="flex items-center text-sm"
                style={{ paddingLeft: `${(level - 1) * 20}px` }}
              >
                <span className="text-gray-700">
                  {level}수준 제목
                </span>
                {tabLeader !== "NONE" && (
                  <span className="flex-1 border-b border-gray-400 mx-2" style={{
                    borderBottomStyle: tabLeader === "DOT" ? "dotted" :
                                   tabLeader === "HYPHEN" ? "dashed" : "solid",
                  }} />
                )}
                {showPageNumbers && (
                  <span className="text-gray-500">{level * 10}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </DialogSection>
    </Dialog>
  );
}
