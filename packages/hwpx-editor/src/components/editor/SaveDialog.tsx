"use client";

import { useState, useEffect, useRef } from "react";
import { useEditorStore } from "@/lib/store";

export function SaveDialog() {
  const saveDialogOpen = useEditorStore((s) => s.uiState.saveDialogOpen);
  const closeSaveDialog = useEditorStore((s) => s.closeSaveDialog);
  const saveDocumentAs = useEditorStore((s) => s.saveDocumentAs);
  const [filename, setFilename] = useState("document");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (saveDialogOpen) {
      setFilename("document");
      // Focus and select text after modal opens
      setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 0);
    }
  }, [saveDialogOpen]);

  if (!saveDialogOpen) return null;

  const handleSave = () => {
    const name = filename.trim();
    if (!name) return;
    saveDocumentAs(name);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSave();
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeSaveDialog();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) closeSaveDialog();
      }}
    >
      <div className="bg-white rounded-lg shadow-xl w-96 p-5">
        <h2 className="text-sm font-semibold text-gray-800 mb-4">
          다른 이름으로 저장
        </h2>

        <label className="block text-xs text-gray-600 mb-1.5">파일 이름</label>
        <div className="flex items-center gap-0 mb-5">
          <input
            ref={inputRef}
            type="text"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 h-8 px-2 text-sm border border-gray-300 rounded-l focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            placeholder="파일 이름 입력"
          />
          <span className="h-8 px-2 flex items-center text-sm text-gray-500 bg-gray-100 border border-l-0 border-gray-300 rounded-r">
            .hwpx
          </span>
        </div>

        <div className="flex justify-end gap-2">
          <button
            onClick={closeSaveDialog}
            className="px-4 py-1.5 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
          >
            취소
          </button>
          <button
            onClick={handleSave}
            disabled={!filename.trim()}
            className="px-4 py-1.5 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
