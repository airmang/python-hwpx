"use client";

import { useEffect } from "react";
import { useEditorStore } from "@/lib/store";
import type { SidebarTab } from "@/lib/constants";
import { CharFormatPanel } from "./CharFormatPanel";
import { ParaFormatPanel } from "./ParaFormatPanel";
import { PageSetupPanel } from "./PageSetupPanel";
import { ImageLayoutPanel } from "./ImageLayoutPanel";
import { ImagePropertiesPanel } from "./ImagePropertiesPanel";
import { TablePropertiesPanel } from "./TablePropertiesPanel";
import { CellPropertiesPanel } from "./CellPropertiesPanel";
import { PanelRightClose } from "lucide-react";

type SidebarContext = "text" | "image" | "table";

function getContext(selection: { objectType?: string; type?: string } | null): SidebarContext {
  if (selection?.objectType === "image") return "image";
  if (selection?.objectType === "table" || selection?.type === "cell") return "table";
  return "text";
}

const TEXT_TABS: { tab: SidebarTab; label: string }[] = [
  { tab: "char", label: "글자 모양" },
  { tab: "para", label: "문단 모양" },
  { tab: "page", label: "편집 용지" },
];

const IMAGE_TABS: { tab: SidebarTab; label: string }[] = [
  { tab: "img-layout", label: "배치" },
  { tab: "img-props", label: "그림" },
];

const TABLE_TABS: { tab: SidebarTab; label: string }[] = [
  { tab: "table", label: "표" },
  { tab: "cell", label: "셀" },
];

export function FormatSidebar() {
  const uiState = useEditorStore((s) => s.uiState);
  const selection = useEditorStore((s) => s.selection);
  const setSidebarTab = useEditorStore((s) => s.setSidebarTab);
  const toggleSidebar = useEditorStore((s) => s.toggleSidebar);

  const context = getContext(selection);

  const tabs =
    context === "image" ? IMAGE_TABS :
    context === "table" ? TABLE_TABS :
    TEXT_TABS;

  // Auto-switch to first tab of current context when context changes
  useEffect(() => {
    const validTabs = tabs.map((t) => t.tab);
    if (!validTabs.includes(uiState.sidebarTab)) {
      setSidebarTab(validTabs[0]!);
    }
  }, [context]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!uiState.sidebarOpen) return null;

  const activeTab = uiState.sidebarTab;

  return (
    <div className="w-72 border-l border-gray-200 bg-white flex flex-col overflow-hidden flex-shrink-0">
      {/* Tab header */}
      <div className="flex items-center border-b border-gray-200">
        {tabs.map(({ tab, label }) => (
          <button
            key={tab}
            onClick={() => setSidebarTab(tab)}
            className={`flex-1 py-2 text-xs font-medium text-center transition-colors ${
              activeTab === tab
                ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
                : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
            }`}
          >
            {label}
          </button>
        ))}
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
        {activeTab === "char" && <CharFormatPanel />}
        {activeTab === "para" && <ParaFormatPanel />}
        {activeTab === "page" && <PageSetupPanel />}
        {activeTab === "img-layout" && <ImageLayoutPanel />}
        {activeTab === "img-props" && <ImagePropertiesPanel />}
        {activeTab === "table" && <TablePropertiesPanel />}
        {activeTab === "cell" && <CellPropertiesPanel />}
      </div>
    </div>
  );
}
