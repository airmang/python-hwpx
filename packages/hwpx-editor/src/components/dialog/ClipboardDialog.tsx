"use client";

import { useEffect, useMemo, useState } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";

export function ClipboardDialog() {
  const open = useEditorStore((s) => s.uiState.clipboardDialogOpen);
  const close = useEditorStore((s) => s.closeClipboardDialog);
  const clipboardHistory = useEditorStore((s) => s.clipboardHistory);
  const clearClipboardHistory = useEditorStore((s) => s.clearClipboardHistory);
  const insertTextAtCursor = useEditorStore((s) => s.insertTextAtCursor);
  const snippets = useEditorStore((s) => s.snippets);
  const addSnippet = useEditorStore((s) => s.addSnippet);
  const removeSnippet = useEditorStore((s) => s.removeSnippet);
  const loadSnippets = useEditorStore((s) => s.loadSnippets);

  const [activeTab, setActiveTab] = useState(0);
  const [newName, setNewName] = useState("");
  const [newText, setNewText] = useState("");

  useEffect(() => {
    loadSnippets();
  }, [loadSnippets]);

  const sortedSnippets = useMemo(
    () => [...(snippets ?? [])].sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0)),
    [snippets],
  );

  const btnClass =
    "px-3 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed";
  const primaryBtnClass =
    "px-3 py-1.5 text-xs border border-blue-500 rounded bg-blue-500 hover:bg-blue-600 text-white disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <Dialog title="클립보드/스니펫" open={open} onClose={close} width={520}>
      <DialogTabs
        tabs={["기록", "스니펫"]}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {activeTab === 0 ? (
        <div className="mt-3 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs text-gray-600">
              최근 복사/잘라내기 텍스트 ({(clipboardHistory ?? []).length}개)
            </div>
            <button
              type="button"
              onClick={clearClipboardHistory}
              className={btnClass}
              disabled={!clipboardHistory?.length}
            >
              전체 삭제
            </button>
          </div>

          <div className="border border-gray-200 bg-white rounded max-h-[360px] overflow-auto">
            {(clipboardHistory ?? []).length === 0 ? (
              <div className="p-4 text-xs text-gray-500">기록이 없습니다. (Ctrl+C / Ctrl+X)</div>
            ) : (
              (clipboardHistory ?? []).map((item, idx) => (
                <div
                  key={`${idx}-${item.slice(0, 12)}`}
                  className="flex items-start gap-2 px-3 py-2 border-b border-gray-100 last:border-b-0"
                >
                  <button
                    type="button"
                    className={primaryBtnClass}
                    onClick={() => insertTextAtCursor(item)}
                  >
                    삽입
                  </button>
                  <div className="text-xs text-gray-700 whitespace-pre-wrap break-words flex-1">
                    {item}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-gray-600 mb-1">이름</label>
              <input
                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded bg-white focus:outline-none focus:border-blue-400"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="예: 서명/자주 쓰는 문구"
              />
            </div>
            <div className="flex items-end">
              <button
                type="button"
                className={primaryBtnClass}
                disabled={!newText.trim()}
                onClick={() => {
                  addSnippet(newName.trim() || "스니펫", newText);
                  setNewName("");
                  setNewText("");
                }}
              >
                추가
              </button>
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-gray-600 mb-1">내용</label>
              <textarea
                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded bg-white focus:outline-none focus:border-blue-400 min-h-[90px]"
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                placeholder="문구를 입력하세요"
              />
            </div>
          </div>

          <div className="border border-gray-200 bg-white rounded max-h-[280px] overflow-auto">
            {sortedSnippets.length === 0 ? (
              <div className="p-4 text-xs text-gray-500">스니펫이 없습니다.</div>
            ) : (
              sortedSnippets.map((snip) => (
                <div
                  key={snip.id}
                  className="flex items-start gap-2 px-3 py-2 border-b border-gray-100 last:border-b-0"
                >
                  <button
                    type="button"
                    className={primaryBtnClass}
                    onClick={() => insertTextAtCursor(snip.text)}
                  >
                    삽입
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-gray-700 truncate">{snip.name}</div>
                    <div className="text-[11px] text-gray-500 whitespace-pre-wrap break-words">
                      {snip.text}
                    </div>
                  </div>
                  <button
                    type="button"
                    className={btnClass}
                    onClick={() => removeSnippet(snip.id)}
                  >
                    삭제
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}

