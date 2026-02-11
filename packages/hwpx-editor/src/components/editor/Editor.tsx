"use client";

import { useEffect, useRef, useCallback } from "react";
import { HwpxDocument } from "@ubermensch1218/hwpxcore";
import { useEditorStore } from "@/lib/store";
import { ensureSkeletonLoaded } from "@/lib/skeleton-loader";
import { MenuBar } from "../toolbar/MenuBar";
import { RibbonToolbar } from "../toolbar/RibbonToolbar";
import { SecondaryToolbar } from "../toolbar/SecondaryToolbar";
import { HorizontalRuler } from "../ruler/HorizontalRuler";
import { FormatSidebar } from "../sidebar/FormatSidebar";
import { PageView } from "./PageView";
import { SaveDialog } from "./SaveDialog";
import { FileUpload } from "../upload/FileUpload";
import { NewDocumentButton } from "../upload/NewDocumentButton";
import { CharFormatDialog } from "../dialog/CharFormatDialog";
import { ParaFormatDialog } from "../dialog/ParaFormatDialog";
import { BulletNumberDialog } from "../dialog/BulletNumberDialog";
import { CharMapDialog } from "../dialog/CharMapDialog";
import { PanelRight } from "lucide-react";

export function Editor() {
  const doc = useEditorStore((s) => s.doc);
  const loading = useEditorStore((s) => s.loading);
  const error = useEditorStore((s) => s.error);
  const uiState = useEditorStore((s) => s.uiState);
  const toggleSidebar = useEditorStore((s) => s.toggleSidebar);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pre-load skeleton on mount
  useEffect(() => {
    ensureSkeletonLoaded().catch(console.error);
  }, []);

  // Handle file open from hidden input
  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const store = useEditorStore.getState();
    store.setLoading(true);
    store.setError(null);
    try {
      const buffer = await file.arrayBuffer();
      const newDoc = await HwpxDocument.open(buffer);
      store.setDocument(newDoc);
    } catch (err) {
      console.error("Failed to open file:", err);
      store.setError("파일을 열 수 없습니다. HWPX 파일인지 확인하세요.");
    } finally {
      store.setLoading(false);
    }
    e.target.value = "";
  }, []);

  // Listen for hwpx-open-file custom event
  useEffect(() => {
    const handler = () => fileInputRef.current?.click();
    window.addEventListener("hwpx-open-file", handler);
    return () => window.removeEventListener("hwpx-open-file", handler);
  }, []);

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const store = useEditorStore.getState();
      if (!store.doc) return;

      const mod = e.ctrlKey || e.metaKey;

      if (mod && e.key === "o") {
        e.preventDefault();
        store.openFile();
        return;
      }

      if (mod && e.key === "s") {
        e.preventDefault();
        store.openSaveDialog();
        return;
      }

      // Undo / Redo (works without selection)
      if (mod && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        store.undo();
        return;
      }
      if (mod && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
        e.preventDefault();
        store.redo();
        return;
      }

      // Dialog shortcuts (⌘L = char format, ⌘T = para format, Ctrl+F10 = char map)
      if (mod && e.key === "l") {
        e.preventDefault();
        store.openCharFormatDialog();
        return;
      }
      if (mod && e.key === "t") {
        e.preventDefault();
        store.openParaFormatDialog();
        return;
      }
      if (e.key === "F10" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        store.openCharMapDialog();
        return;
      }

      if (!store.selection) return;

      if (mod && e.key === "b") {
        e.preventDefault();
        store.toggleBold();
      } else if (mod && e.key === "i") {
        e.preventDefault();
        store.toggleItalic();
      } else if (mod && e.key === "u") {
        e.preventDefault();
        store.toggleUnderline();
      } else if (mod && e.key === "d") {
        e.preventDefault();
        store.toggleStrikethrough();
      } else if (mod && e.key === "e") {
        e.preventDefault();
        store.setAlignment("CENTER");
      } else if (mod && e.key === "r") {
        e.preventDefault();
        store.setAlignment("RIGHT");
      } else if (mod && e.key === "j") {
        e.preventDefault();
        store.setAlignment("JUSTIFY");
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
      <input
        ref={fileInputRef}
        type="file"
        accept=".hwpx"
        className="hidden"
        onChange={handleFileChange}
      />
      <SaveDialog />
      <CharFormatDialog />
      <ParaFormatDialog />
      <BulletNumberDialog />
      <CharMapDialog />
      {/* Menu bar */}
      <MenuBar />
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
