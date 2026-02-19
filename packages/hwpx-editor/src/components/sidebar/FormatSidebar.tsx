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

  const handleWheelCapture = (e: React.WheelEvent<HTMLDivElement>) => {
    const nativeEvent = e.nativeEvent as WheelEvent & {
      composedPath?: () => EventTarget[];
    };
    const path = nativeEvent.composedPath?.() ?? [];
    const pathNumberInput = path.find(
      (node): node is HTMLInputElement =>
        node instanceof HTMLInputElement && node.type === "number",
    );
    const targetNumberInput =
      e.target instanceof HTMLInputElement && e.target.type === "number"
        ? e.target
        : null;
    const numberInput = pathNumberInput ?? targetNumberInput;
    if (!numberInput) return;

    const container = e.currentTarget;
    const maxScrollTop = Math.max(container.scrollHeight - container.clientHeight, 0);
    const canScrollDown = container.scrollTop < maxScrollTop;
    const canScrollUp = container.scrollTop > 0;
    const scrollingDown = e.deltaY > 0;
    const canConsumeWheel = scrollingDown ? canScrollDown : canScrollUp;

    // Number inputs consume wheel events; reroute wheel to sidebar scroll.
    // At boundaries, do not block default so outer editor/page can continue scrolling.
    if (!canConsumeWheel) return;
    numberInput.blur();
    e.preventDefault();
    container.scrollTop = Math.min(Math.max(container.scrollTop + e.deltaY, 0), maxScrollTop);
  };

  if (!uiState.sidebarOpen) return null;

  const activeTab = uiState.sidebarTab;

  return (
    <div className="w-72 min-h-0 border-l border-gray-200 bg-white flex flex-col overflow-hidden flex-shrink-0">
      <div className="flex items-center justify-end border-b border-gray-200 px-1 py-0.5">
        <button
          type="button"
          onClick={toggleSidebar}
          className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          title="사이드바 닫기"
          aria-label="사이드바 닫기"
        >
          <PanelRightClose aria-hidden="true" className="w-4 h-4" />
        </button>
        {context === "table" && (
          <div className="mr-auto flex rounded-md border border-gray-200 overflow-hidden">
            {tabs.map((tabDef) => (
              <button
                key={tabDef.tab}
                type="button"
                onClick={() => setSidebarTab(tabDef.tab)}
                className={`px-2.5 py-1.5 text-[11px] transition-colors ${
                  activeTab === tabDef.tab
                    ? "bg-blue-50 text-blue-700"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {tabDef.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Tab content */}
      <div
        className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden"
        onWheelCapture={handleWheelCapture}
      >
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
