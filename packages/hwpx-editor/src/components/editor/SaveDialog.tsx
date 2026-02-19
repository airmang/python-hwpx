"use client";

import { useState, useEffect, useRef } from "react";
import { useEditorStore } from "@/lib/store";
import { redirectToLoginFromEditor } from "@/lib/auth-redirect";
import { Dialog } from "../dialog/Dialog";

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
    }
  };

  const footer = (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
      <button
        type="button"
        onClick={closeSaveDialog}
        className="h-11 w-full rounded-xl border border-gray-300 bg-white px-4 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        취소
      </button>
      <button
        type="button"
        onClick={handleLocalSave}
        disabled={!filename.trim() || loading}
        className="h-11 w-full rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        로컬 저장
      </button>
      <button
        type="button"
        onClick={handleServerSave}
        disabled={!filename.trim() || loading}
        className="h-11 w-full rounded-xl bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {serverDocumentId ? "서버 덮어쓰기" : "서버 저장"}
      </button>
    </div>
  );

  return (
    <Dialog
      title="다른 이름으로 저장"
      description="문서를 로컬 파일 또는 서버 드라이브에 저장합니다."
      open={saveDialogOpen}
      onClose={closeSaveDialog}
      width={620}
      footer={footer}
    >
      <div>
        <label className="mb-2 block text-sm font-medium text-gray-700">파일 이름</label>
        <input
          ref={inputRef}
          type="text"
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          onKeyDown={handleKeyDown}
          className="h-11 w-full rounded-xl border border-gray-300 px-3.5 text-base text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
          aria-label="파일 이름"
        />
        <p className="mt-2 text-xs text-gray-500">저장 시 `.hwpx` 확장자가 자동으로 붙습니다.</p>
      </div>

      {serverFeedback ? (
        <div
          className={`mt-5 rounded-xl border px-3.5 py-3 text-sm leading-relaxed break-words ${
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
    </Dialog>
  );
}
