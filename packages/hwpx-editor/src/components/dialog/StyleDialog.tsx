"use client";

import { useState, useEffect } from "react";
import { useEditorStore } from "@/lib/store";
import { Dialog } from "./Dialog";
import { DialogSection } from "./DialogSection";
import { parseHeaderXml, serializeXml } from "@ubermensch1218/hwpxcore";

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
  const applyStyleToDocument = useEditorStore((s) => s.applyStyleToDocument);

  const [styles, setStyles] = useState<StyleItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (uiState.styleDialogOpen && doc) {
      try {
        const styleList: StyleItem[] = [];
        const header = doc.headers[0];
        if (header) {
          const parsed = parseHeaderXml(serializeXml(header.element));
          const styles = parsed.refList?.styles?.styles ?? [];
          for (const style of styles) {
            if (style.name) {
              const id = style.rawId ?? (style.id != null ? String(style.id) : null);
              if (!id) continue;
              styleList.push({
                id,
                name: style.name,
                type: style.type ?? "para",
              });
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
        <div>선택한 스타일을 현재 문단에 적용합니다.</div>
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            className="px-3 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 text-gray-700"
            disabled={!selectedId}
            onClick={() => {
              if (!selectedId) return;
              applyStyleToDocument(selectedId);
              closeStyleDialog();
            }}
            title="문서 전체 문단에 스타일을 적용합니다."
          >
            문서 전체 적용
          </button>
        </div>
      </div>
    </Dialog>
  );
}
