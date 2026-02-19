"use client";

import { useState, useEffect } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";
import { DialogTabs } from "./DialogTabs";

export function HeaderFooterDialog() {
  const doc = useEditorStore((s) => s.doc);
  const viewModel = useEditorStore((s) => s.viewModel);
  const selection = useEditorStore((s) => s.selection);
  const uiState = useEditorStore((s) => s.uiState);
  const closeHeaderFooterDialog = useEditorStore((s) => s.closeHeaderFooterDialog);
  const setHeaderFooter = useEditorStore((s) => s.setHeaderFooter);

  const sectionIdx = selection?.sectionIndex ?? 0;
  const section = viewModel?.sections[sectionIdx];

  const [activeTab, setActiveTab] = useState<"header" | "footer">("header");
  const [headerText, setHeaderText] = useState(section?.headerText ?? "");
  const [footerText, setFooterText] = useState(section?.footerText ?? "");
  const [headerPosition, setHeaderPosition] = useState<"left" | "center" | "right">("center");
  const [footerPosition, setFooterPosition] = useState<"left" | "center" | "right">("center");

  useEffect(() => {
    if (uiState.headerFooterDialogOpen && section) {
      setHeaderText(section.headerText);
      setFooterText(section.footerText);
    }
  }, [uiState.headerFooterDialogOpen, section?.headerText, section?.footerText]);

  const handleApply = () => {
    setHeaderFooter({ headerText, footerText });
    closeHeaderFooterDialog();
  };

  const insertPlaceholder = (placeholder: string) => {
    if (activeTab === "header") {
      setHeaderText((prev) => prev + placeholder);
    } else {
      setFooterText((prev) => prev + placeholder);
    }
  };

  const inputClass =
    "w-full px-2 py-1.5 text-sm border border-gray-300 rounded bg-white focus:outline-none focus:border-blue-400";
  const btnClass =
    "px-2 py-1 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 text-gray-700";

  return (
    <Dialog
      title="머리말/꼬리말"
      open={uiState.headerFooterDialogOpen}
      onClose={closeHeaderFooterDialog}
      onApply={handleApply}
      width={480}
    >
      <DialogTabs
        tabs={[
          { id: "header", label: "머리말" },
          { id: "footer", label: "꼬리말" },
        ]}
        activeTab={activeTab}
        onTabChange={(id) => setActiveTab(id as "header" | "footer")}
      />

      {activeTab === "header" && (
        <DialogSection title="머리말 내용">
          <textarea
            value={headerText}
            onChange={(e) => setHeaderText(e.target.value)}
            placeholder="머리말 내용을 입력하세요"
            className={`${inputClass} h-20 resize-none`}
          />
          <div className="flex gap-2 mt-2">
            <button className={btnClass} onClick={() => insertPlaceholder("{{page}}")}>
              쪽 번호
            </button>
            <button className={btnClass} onClick={() => insertPlaceholder("{{total}}")}>
              총 쪽 수
            </button>
            <button className={btnClass} onClick={() => insertPlaceholder("{{date}}")}>
              날짜
            </button>
          </div>
          <div className="flex items-center gap-4 mt-3">
            <span className="text-xs text-gray-600">정렬:</span>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="radio"
                name="headerPos"
                checked={headerPosition === "left"}
                onChange={() => setHeaderPosition("left")}
              />
              왼쪽
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="radio"
                name="headerPos"
                checked={headerPosition === "center"}
                onChange={() => setHeaderPosition("center")}
              />
              가운데
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="radio"
                name="headerPos"
                checked={headerPosition === "right"}
                onChange={() => setHeaderPosition("right")}
              />
              오른쪽
            </label>
          </div>
        </DialogSection>
      )}

      {activeTab === "footer" && (
        <DialogSection title="꼬리말 내용">
          <textarea
            value={footerText}
            onChange={(e) => setFooterText(e.target.value)}
            placeholder="꼬리말 내용을 입력하세요"
            className={`${inputClass} h-20 resize-none`}
          />
          <div className="flex gap-2 mt-2">
            <button className={btnClass} onClick={() => insertPlaceholder("{{page}}")}>
              쪽 번호
            </button>
            <button className={btnClass} onClick={() => insertPlaceholder("{{total}}")}>
              총 쪽 수
            </button>
            <button className={btnClass} onClick={() => insertPlaceholder("{{date}}")}>
              날짜
            </button>
          </div>
          <div className="flex items-center gap-4 mt-3">
            <span className="text-xs text-gray-600">정렬:</span>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="radio"
                name="footerPos"
                checked={footerPosition === "left"}
                onChange={() => setFooterPosition("left")}
              />
              왼쪽
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="radio"
                name="footerPos"
                checked={footerPosition === "center"}
                onChange={() => setFooterPosition("center")}
              />
              가운데
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="radio"
                name="footerPos"
                checked={footerPosition === "right"}
                onChange={() => setFooterPosition("right")}
              />
              오른쪽
            </label>
          </div>
        </DialogSection>
      )}

      <div className="text-xs text-gray-500 mt-3">
        <p>사용 가능한 변수:</p>
        <ul className="list-disc pl-4 mt-1 space-y-0.5">
          <li><code className="bg-gray-100 px-1 rounded">{"{{page}}"}</code> - 현재 쪽 번호</li>
          <li><code className="bg-gray-100 px-1 rounded">{"{{total}}"}</code> - 총 쪽 수</li>
          <li><code className="bg-gray-100 px-1 rounded">{"{{date}}"}</code> - 오늘 날짜</li>
        </ul>
      </div>
    </Dialog>
  );
}
