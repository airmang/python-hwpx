"use client";

import { useEditorStore } from "@/lib/store";
import { CharFormatPanel } from "./CharFormatPanel";
import { ParaFormatPanel } from "./ParaFormatPanel";
import { PanelRightClose } from "lucide-react";

export function FormatSidebar() {
  const uiState = useEditorStore((s) => s.uiState);
  const setSidebarTab = useEditorStore((s) => s.setSidebarTab);
  const toggleSidebar = useEditorStore((s) => s.toggleSidebar);

  if (!uiState.sidebarOpen) return null;

  return (
    <div className="w-72 border-l border-gray-200 bg-white flex flex-col overflow-hidden flex-shrink-0">
      {/* Tab header */}
      <div className="flex items-center border-b border-gray-200">
        <button
          onClick={() => setSidebarTab("char")}
          className={`flex-1 py-2 text-xs font-medium text-center transition-colors ${
            uiState.sidebarTab === "char"
              ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
              : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
          }`}
        >
          글자 모양
        </button>
        <button
          onClick={() => setSidebarTab("para")}
          className={`flex-1 py-2 text-xs font-medium text-center transition-colors ${
            uiState.sidebarTab === "para"
              ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
              : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
          }`}
        >
          문단 모양
        </button>
        <button
          onClick={toggleSidebar}
          className="p-1.5 mr-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          title="사이드바 닫기"
        >
          <PanelRightClose className="w-4 h-4" />
        </button>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {uiState.sidebarTab === "char" ? (
          <CharFormatPanel />
        ) : (
          <ParaFormatPanel />
        )}
      </div>
    </div>
  );
}
