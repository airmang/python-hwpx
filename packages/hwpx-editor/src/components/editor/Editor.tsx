"use client";

import { useEffect } from "react";
import { useEditorStore } from "@/lib/store";
import { ensureSkeletonLoaded } from "@/lib/skeleton-loader";
import { RibbonToolbar } from "../toolbar/RibbonToolbar";
import { SecondaryToolbar } from "../toolbar/SecondaryToolbar";
import { HorizontalRuler } from "../ruler/HorizontalRuler";
import { FormatSidebar } from "../sidebar/FormatSidebar";
import { PageView } from "./PageView";
import { SaveDialog } from "./SaveDialog";
import { FileUpload } from "../upload/FileUpload";
import { NewDocumentButton } from "../upload/NewDocumentButton";
import { PanelRight } from "lucide-react";

export function Editor() {
  const doc = useEditorStore((s) => s.doc);
  const loading = useEditorStore((s) => s.loading);
  const error = useEditorStore((s) => s.error);
  const uiState = useEditorStore((s) => s.uiState);
  const toggleSidebar = useEditorStore((s) => s.toggleSidebar);

  // Pre-load skeleton on mount
  useEffect(() => {
    ensureSkeletonLoaded().catch(console.error);
  }, []);

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const store = useEditorStore.getState();
      if (!store.doc) return;

      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        store.openSaveDialog();
        return;
      }

      if (!store.selection) return;

      if ((e.ctrlKey || e.metaKey) && e.key === "b") {
        e.preventDefault();
        store.toggleBold();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "i") {
        e.preventDefault();
        store.toggleItalic();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "u") {
        e.preventDefault();
        store.toggleUnderline();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-gray-500">로딩 중...</div>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-6 bg-gray-100 p-8">
        <h1 className="text-2xl font-bold text-gray-800">HWPX Editor</h1>
        <p className="text-gray-500 max-w-md text-center">
          HWPX 문서를 열거나 새 문서를 만들어 편집하세요.
        </p>
        <div className="w-full max-w-md">
          <FileUpload />
        </div>
        <div className="flex gap-3">
          <NewDocumentButton />
        </div>
        {error && (
          <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg text-sm">
            {error}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <SaveDialog />
      {/* Ribbon toolbar */}
      <RibbonToolbar />
      {/* Secondary toolbar (formatting bar) */}
      <SecondaryToolbar />
      {/* Horizontal ruler */}
      <HorizontalRuler />
      {/* Error banner */}
      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 text-sm border-b border-red-200">
          {error}
        </div>
      )}
      {/* Main content area: Page + Sidebar */}
      <div className="flex flex-1 overflow-hidden">
        <PageView />
        <FormatSidebar />
        {/* Sidebar toggle when closed */}
        {!uiState.sidebarOpen && (
          <button
            onClick={toggleSidebar}
            className="absolute right-2 top-[140px] z-10 p-1.5 bg-white border border-gray-200 rounded shadow-sm text-gray-400 hover:text-gray-600 hover:bg-gray-50"
            title="서식 사이드바 열기"
          >
            <PanelRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
