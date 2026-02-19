"use client";

import { useState, useEffect, useCallback } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";

export function FindReplaceDialog() {
  const doc = useEditorStore((s) => s.doc);
  const uiState = useEditorStore((s) => s.uiState);
  const closeFindReplaceDialog = useEditorStore((s) => s.closeFindReplaceDialog);
  const findAndReplaceAdvanced = useEditorStore((s) => s.findAndReplaceAdvanced);
  const findNextMatch = useEditorStore((s) => s.findNextMatch);
  const selection = useEditorStore((s) => s.selection);

  const [activeTab, setActiveTab] = useState(0);
  const [findText, setFindText] = useState("");
  const [replaceText, setReplaceText] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [useRegex, setUseRegex] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [scope, setScope] = useState<"document" | "paragraph" | "selection">("document");
  const [resultMessage, setResultMessage] = useState<string | null>(null);

  // Reset result message when find text changes
  useEffect(() => {
    setResultMessage(null);
  }, [findText]);

  const handleFind = useCallback(() => {
    if (!doc || !findText) return;

    if (scope === "selection") {
      if (selection?.type !== "paragraph" || selection.textStartOffset == null || selection.textEndOffset == null) {
        setResultMessage("선택 영역이 없습니다.");
        return;
      }
      const section = doc.sections[selection.sectionIndex];
      const para = section?.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const full = String(para.text ?? "");
      const a = Math.max(0, Math.min(full.length, Math.min(selection.textStartOffset, selection.textEndOffset)));
      const b = Math.max(0, Math.min(full.length, Math.max(selection.textStartOffset, selection.textEndOffset)));
      const mid = full.slice(a, b);

      const pattern = buildPattern(findText, { matchCase, useRegex, wholeWord });
      const count = countMatches(mid, pattern);
      setResultMessage(count > 0 ? `"${findText}"을(를) ${count}개 찾았습니다.` : `"${findText}"을(를) 찾을 수 없습니다.`);
      return;
    }

    const { found, matchCount } = findNextMatch({ search: findText, matchCase, useRegex, wholeWord, scope });
    if (matchCount <= 0) {
      setResultMessage(`"${findText}"을(를) 찾을 수 없습니다.`);
      return;
    }
    setResultMessage(found ? `"${findText}"을(를) ${matchCount}개 찾았습니다.` : `"${findText}"을(를) ${matchCount}개 찾았지만 다음 항목이 없습니다.`);
  }, [doc, findText, matchCase, useRegex, wholeWord, scope, findNextMatch, selection]);

  const handleReplace = useCallback(() => {
    if (!doc || !findText) return;
    const count = findAndReplaceAdvanced({
      search: findText,
      replacement: replaceText,
      count: 1,
      matchCase,
      useRegex,
      wholeWord,
      scope,
    });
    setResultMessage(count > 0 ? `1개를 바꿨습니다.` : `"${findText}"을(를) 찾을 수 없습니다.`);
  }, [doc, findText, replaceText, findAndReplaceAdvanced, matchCase, scope, useRegex, wholeWord]);

  const handleReplaceAll = useCallback(() => {
    if (!doc || !findText) return;
    const count = findAndReplaceAdvanced({
      search: findText,
      replacement: replaceText,
      matchCase,
      useRegex,
      wholeWord,
      scope,
    });
    setResultMessage(count > 0 ? `${count}개를 모두 바꿨습니다.` : `"${findText}"을(를) 찾을 수 없습니다.`);
  }, [doc, findText, replaceText, findAndReplaceAdvanced, matchCase, scope, useRegex, wholeWord]);

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
        tabs={["찾기", "바꾸기"]}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      <div className="space-y-3 mt-3">
        <div>
          <label className="block text-xs text-gray-600 mb-1">찾을 내용</label>
          <input
            type="text"
            value={findText}
            onChange={(e) => setFindText(e.target.value)}
            aria-label="찾을 내용"
            className={inputClass}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (activeTab === 0) handleFind();
                else handleReplace();
              }
            }}
          />
        </div>

        {activeTab === 1 && (
          <div>
            <label className="block text-xs text-gray-600 mb-1">바꿀 내용</label>
            <input
              type="text"
              value={replaceText}
              onChange={(e) => setReplaceText(e.target.value)}
              aria-label="바꿀 내용"
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
              checked={useRegex}
              onChange={(e) => setUseRegex(e.target.checked)}
              className="w-3.5 h-3.5"
            />
            정규식
          </label>
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={wholeWord}
              onChange={(e) => setWholeWord(e.target.checked)}
              className="w-3.5 h-3.5"
              disabled={useRegex}
            />
            단어 단위
          </label>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-600">범위</label>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as any)}
            className="h-8 px-2 text-sm border border-gray-300 rounded bg-white"
          >
            <option value="document">전체 문서</option>
            <option value="paragraph">현재 문단</option>
            <option value="selection">선택 영역</option>
          </select>
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
          {activeTab === 0 ? (
            <>
              <button
                className={primaryBtnClass}
                disabled={!findText}
                onClick={handleFind}
              >
                찾기
              </button>
              <button
                className={btnClass}
                onClick={() => {
                  if (!findText) return;
                  const { found, matchCount } = findNextMatch({
                    search: findText,
                    matchCase,
                    useRegex,
                    wholeWord,
                    scope: scope === "selection" ? "paragraph" : scope,
                  });
                  if (matchCount <= 0) setResultMessage(`"${findText}"을(를) 찾을 수 없습니다.`);
                  else setResultMessage(found ? `"${findText}" 다음 항목으로 이동했습니다. (${matchCount}개)` : `"${findText}" 다음 항목이 없습니다. (${matchCount}개)`);
                }}
                disabled={!findText || scope === "selection"}
                title={scope === "selection" ? "선택 영역 범위에서는 다음 찾기를 지원하지 않습니다." : "다음 찾기"}
              >
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

function buildPattern(
  input: string,
  opts: { matchCase: boolean; useRegex: boolean; wholeWord: boolean },
): RegExp {
  const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const source = opts.useRegex ? input : escape(input);
  const wrapped = opts.wholeWord ? `\\b(?:${source})\\b` : source;
  const flags = `${opts.matchCase ? "" : "i"}g`;
  return new RegExp(wrapped, flags);
}

function countMatches(text: string, pattern: RegExp): number {
  let count = 0;
  pattern.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(text))) {
    count += 1;
    if (m[0].length === 0) pattern.lastIndex += 1;
  }
  return count;
}
