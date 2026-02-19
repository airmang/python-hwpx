"use client";

import { useState, useEffect } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";

interface StyleItem {
  id: string;
  name: string;
  type: string;
}

export function StyleDialog() {
  const doc = useEditorStore((s) => s.doc);
  const uiState = useEditorStore((s) => s.uiState);
  const closeStyleDialog = useEditorStore((s) => s.closeStyleDialog);
  const applyStyle = useEditorStore((s) => s.applyStyle);

  const [styles, setStyles] = useState<StyleItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (uiState.styleDialogOpen && doc) {
      try {
        const headers = doc.oxml.headers;
        const styleList: StyleItem[] = [];
        for (const header of headers) {
          const refList = header.refList;
          if (refList?.styles?.styles) {
            for (const style of refList.styles.styles) {
              if (style.id != null && style.name) {
                styleList.push({
                  id: String(style.id),
                  name: style.name,
                  type: style.type ?? "para",
                });
              }
            }
          }
        }
        setStyles(styleList);
        if (styleList.length > 0 && !selectedId) {
          setSelectedId(styleList[0]?.id ?? null);
        }
      } catch (e) {
        console.error("Failed to load styles:", e);
      }
    }
  }, [uiState.styleDialogOpen, doc]);

  const handleApply = () => {
    if (selectedId) {
      applyStyle(selectedId);
    }
    closeStyleDialog();
  };

  const paraStyles = styles.filter((s) => s.type === "para" || s.type === "Paragraph");
  const charStyles = styles.filter((s) => s.type === "char" || s.type === "Character");

  return (
    <Dialog
      title="스타일"
      open={uiState.styleDialogOpen}
      onClose={closeStyleDialog}
      onApply={handleApply}
      width={400}
    >
      <DialogSection title="문단 스타일">
        <div className="max-h-48 overflow-y-auto border border-gray-200 rounded">
          {paraStyles.length === 0 ? (
            <div className="p-2 text-xs text-gray-400">스타일 없음</div>
          ) : (
            paraStyles.map((style) => (
              <button
                key={style.id}
                onClick={() => setSelectedId(style.id)}
                className={`w-full text-left px-3 py-2 text-sm border-b border-gray-100 last:border-0 ${
                  selectedId === style.id
                    ? "bg-blue-50 text-blue-700"
                    : "hover:bg-gray-50"
                }`}
              >
                {style.name}
              </button>
            ))
          )}
        </div>
      </DialogSection>

      {charStyles.length > 0 && (
        <DialogSection title="글자 스타일">
          <div className="max-h-32 overflow-y-auto border border-gray-200 rounded">
            {charStyles.map((style) => (
              <button
                key={style.id}
                onClick={() => setSelectedId(style.id)}
                className={`w-full text-left px-3 py-2 text-sm border-b border-gray-100 last:border-0 ${
                  selectedId === style.id
                    ? "bg-blue-50 text-blue-700"
                    : "hover:bg-gray-50"
                }`}
              >
                {style.name}
              </button>
            ))}
          </div>
        </DialogSection>
      )}

      <div className="text-xs text-gray-500 mt-3">
        선택한 스타일을 현재 문단에 적용합니다.
      </div>
    </Dialog>
  );
}
