"use client";

import { useState, useEffect, useRef } from "react";
import { useEditorStore } from "@/lib/store";
import { redirectToLoginFromEditor } from "@/lib/auth-redirect";

export function SaveDialog() {
  const saveDialogOpen = useEditorStore((s) => s.uiState.saveDialogOpen);
  const closeSaveDialog = useEditorStore((s) => s.closeSaveDialog);
  const saveDocumentAs = useEditorStore((s) => s.saveDocumentAs);
  const saveDocumentToServer = useEditorStore((s) => s.saveDocumentToServer);
  const serverDocumentId = useEditorStore((s) => s.serverDocumentId);
  const loading = useEditorStore((s) => s.loading);
  const [filename, setFilename] = useState("document");
  const [serverFeedback, setServerFeedback] = useState<{
    kind: "success" | "error";
    message: string;
    requiresLogin?: boolean;
  } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (saveDialogOpen) {
      setFilename("document");
      setServerFeedback(null);
      // Focus and select text after modal opens
      setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 0);
    }
  }, [saveDialogOpen]);

  if (!saveDialogOpen) return null;

  const handleLocalSave = () => {
    const name = filename.trim();
    if (!name) return;
    saveDocumentAs(name);
  };

  const handleServerSave = async () => {
    const name = filename.trim();
    if (!name) return;
    const result = await saveDocumentToServer(name);
    if (!result.ok) {
      if (result.status === 401 && redirectToLoginFromEditor()) {
        return;
      }
      setServerFeedback({
        kind: "error",
        message: result.error || "서버 저장에 실패했습니다.",
        requiresLogin: result.status === 401,
      });
      return;
    }
    setServerFeedback(null);
  };

  const handleLogin = () => {
    if (redirectToLoginFromEditor()) return;

    const callbackUrl = encodeURIComponent(
      `${window.location.pathname}${window.location.search}`,
    );
    window.location.href = `/login?callbackUrl=${callbackUrl}`;
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleLocalSave();
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
            aria-label="파일 이름"
          />
          <span className="h-8 px-2 flex items-center text-sm text-gray-500 bg-gray-100 border border-l-0 border-gray-300 rounded-r">
            .hwpx
          </span>
        </div>

        {serverFeedback ? (
          <div
            className={`mb-4 rounded border px-3 py-2 text-xs ${
              serverFeedback.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-rose-200 bg-rose-50 text-rose-700"
            }`}
          >
            {serverFeedback.message}
            {serverFeedback.requiresLogin ? (
              <button
                type="button"
                onClick={handleLogin}
                className="ml-1 font-semibold underline underline-offset-2"
              >
                로그인
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <button
            onClick={closeSaveDialog}
            className="px-4 py-1.5 text-xs rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
          >
            취소
          </button>
          <button
            onClick={handleLocalSave}
            disabled={!filename.trim() || loading}
            className="px-4 py-1.5 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            로컬 저장
          </button>
          <button
            onClick={handleServerSave}
            disabled={!filename.trim() || loading}
            className="px-4 py-1.5 text-xs rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {serverDocumentId ? "서버 덮어쓰기" : "서버 저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
