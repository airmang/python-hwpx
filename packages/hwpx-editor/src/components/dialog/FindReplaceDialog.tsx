"use client";

import { useState, useEffect, useCallback } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";

export function FindReplaceDialog() {
  const doc = useEditorStore((s) => s.doc);
  const uiState = useEditorStore((s) => s.uiState);
  const closeFindReplaceDialog = useEditorStore((s) => s.closeFindReplaceDialog);
  const findAndReplace = useEditorStore((s) => s.findAndReplace);

  const [activeTab, setActiveTab] = useState<"find" | "replace">("find");
  const [findText, setFindText] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [resultMessage, setResultMessage] = useState<string | null>(null);

  // Reset result message when find text changes
  useEffect(() => {
    setResultMessage(null);
  }, [findText]);

  const handleFind = useCallback(() => {
    if (!doc || !findText) return;
    // Simple find by checking if text exists
    const text = doc.text;
    const searchText = matchCase ? findText : findText.toLowerCase();
    const docText = matchCase ? text : text.toLowerCase();

    if (docText.includes(searchText)) {
      const count = (docText.match(new RegExp(escapeRegex(searchText), "g")) || []).length;
      setResultMessage(`"${findText}"을(를) ${count}개 찾았습니다.`);
    } else {
      setResultMessage(`"${findText}"을(를) 찾을 수 없습니다.`);
    }
  }, [doc, findText, matchCase]);

  const handleReplace = useCallback(() => {
    if (!doc || !findText) return;
    const count = findAndReplace(findText, replaceText, 1);
    setResultMessage(count > 0 ? `1개를 바꿨습니다.` : `"${findText}"을(를) 찾을 수 없습니다.`);
  }, [doc, findText, replaceText, findAndReplace]);

  const handleReplaceAll = useCallback(() => {
    if (!doc || !findText) return;
    const count = findAndReplace(findText, replaceText);
    setResultMessage(count > 0 ? `${count}개를 모두 바꿨습니다.` : `"${findText}"을(를) 찾을 수 없습니다.`);
  }, [doc, findText, replaceText, findAndReplace]);

  const inputClass =
    "w-full px-2 py-1.5 text-sm border border-gray-300 rounded bg-white focus:outline-none focus:border-blue-400";
  const btnClass =
    "px-3 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed";
  const primaryBtnClass =
    "px-3 py-1.5 text-xs border border-blue-500 rounded bg-blue-500 hover:bg-blue-600 text-white disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <Dialog
      title="찾기/바꾸기"
      open={uiState.findReplaceDialogOpen}
      onClose={closeFindReplaceDialog}
      width={420}
    >
      <DialogTabs
        tabs={[
          { id: "find", label: "찾기" },
          { id: "replace", label: "바꾸기" },
        ]}
        activeTab={activeTab}
        onTabChange={(id) => setActiveTab(id as "find" | "replace")}
      />

      <div className="space-y-3 mt-3">
        <div>
          <label className="block text-xs text-gray-600 mb-1">찾을 내용</label>
          <input
            type="text"
            value={findText}
            onChange={(e) => setFindText(e.target.value)}
            placeholder="찾을 텍스트를 입력하세요"
            className={inputClass}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (activeTab === "find") handleFind();
                else handleReplace();
              }
            }}
          />
        </div>

        {activeTab === "replace" && (
          <div>
            <label className="block text-xs text-gray-600 mb-1">바꿀 내용</label>
            <input
              type="text"
              value={replaceText}
              onChange={(e) => setReplaceText(e.target.value)}
              placeholder="바꿀 텍스트를 입력하세요"
              className={inputClass}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleReplace();
                }
              }}
            />
          </div>
        )}

        <div className="flex gap-4">
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={matchCase}
              onChange={(e) => setMatchCase(e.target.checked)}
              className="w-3.5 h-3.5"
            />
            대/소문자 구분
          </label>
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={wholeWord}
              onChange={(e) => setWholeWord(e.target.checked)}
              className="w-3.5 h-3.5"
              disabled
            />
            온전한 낱말
          </label>
        </div>

        {resultMessage && (
          <div className={`text-xs px-2 py-1.5 rounded ${
            resultMessage.includes("찾을 수 없")
              ? "bg-yellow-50 text-yellow-700 border border-yellow-200"
              : "bg-green-50 text-green-700 border border-green-200"
          }`}>
            {resultMessage}
          </div>
        )}

        <div className="flex gap-2 pt-2">
          {activeTab === "find" ? (
            <>
              <button
                className={primaryBtnClass}
                disabled={!findText}
                onClick={handleFind}
              >
                찾기
              </button>
              <button className={btnClass} disabled>
                다음 찾기
              </button>
            </>
          ) : (
            <>
              <button
                className={primaryBtnClass}
                disabled={!findText}
                onClick={handleReplace}
              >
                바꾸기
              </button>
              <button
                className={btnClass}
                disabled={!findText}
                onClick={handleReplaceAll}
              >
                모두 바꾸기
              </button>
            </>
          )}
          <button className={btnClass} onClick={closeFindReplaceDialog}>
            닫기
          </button>
        </div>
      </div>
    </Dialog>
  );
}

function escapeRegex(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
