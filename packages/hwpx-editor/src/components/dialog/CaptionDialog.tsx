"use client";

import { useMemo, useState } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogTabs } from "./DialogTabs";

type CaptionKind = "figure" | "table";

export function CaptionDialog() {
  const open = useEditorStore((s) => s.uiState.captionDialogOpen);
  const close = useEditorStore((s) => s.closeCaptionDialog);
  const insertCaption = useEditorStore((s) => s.insertCaption);
  const insertCaptionList = useEditorStore((s) => s.insertCaptionList);

  const [activeTab, setActiveTab] = useState(0);
  const [kind, setKind] = useState<CaptionKind>("figure");
  const [text, setText] = useState("");

  const titleLabel = useMemo(() => (kind === "table" ? "표" : "그림"), [kind]);

  const inputClass =
    "w-full px-2 py-1.5 text-sm border border-gray-300 rounded bg-white focus:outline-none focus:border-blue-400";
  const btnClass =
    "px-3 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 text-gray-700 disabled:opacity-40 disabled:cursor-not-allowed";
  const primaryBtnClass =
    "px-3 py-1.5 text-xs border border-blue-500 rounded bg-blue-500 hover:bg-blue-600 text-white disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <Dialog title="캡션/목차" open={open} onClose={close} width={480}>
      <DialogTabs
        tabs={["캡션", "목차"]}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      <div className="mt-3 space-y-3">
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-600">종류</label>
          <select
            className="h-8 px-2 text-sm border border-gray-300 rounded bg-white"
            value={kind}
            onChange={(e) => setKind(e.target.value as CaptionKind)}
          >
            <option value="figure">그림</option>
            <option value="table">표</option>
          </select>
        </div>

        {activeTab === 0 ? (
          <>
            <div>
              <label className="block text-xs text-gray-600 mb-1">
                {titleLabel} 캡션 내용
              </label>
              <input
                className={inputClass}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="예: 시스템 구성도"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    if (!text.trim()) return;
                    insertCaption({ kind, text: text.trim() });
                    setText("");
                    close();
                  }
                }}
              />
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className={primaryBtnClass}
                disabled={!text.trim()}
                onClick={() => {
                  insertCaption({ kind, text: text.trim() });
                  setText("");
                  close();
                }}
              >
                캡션 삽입
              </button>
              <button type="button" className={btnClass} onClick={close}>
                닫기
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="text-xs text-gray-600">
              현재 문서의 {titleLabel} 캡션을 수집해 목록을 삽입합니다.
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className={primaryBtnClass}
                onClick={() => {
                  insertCaptionList({ kind });
                  close();
                }}
              >
                {titleLabel} 목차 삽입
              </button>
              <button type="button" className={btnClass} onClick={close}>
                닫기
              </button>
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}

