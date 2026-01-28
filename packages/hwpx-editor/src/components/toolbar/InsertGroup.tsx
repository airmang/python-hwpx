"use client";

import { useCallback, useRef, useState } from "react";
import { Table, BarChart3, Shapes, ImageIcon, Save, Columns, FileDown } from "lucide-react";
import { useEditorStore } from "@/lib/store";
import { ToolbarButton } from "./ToolbarButton";
import { RibbonGroup } from "./RibbonGroup";

export function InsertGroup() {
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const addTable = useEditorStore((s) => s.addTable);
  const insertImage = useEditorStore((s) => s.insertImage);
  const insertColumnBreak = useEditorStore((s) => s.insertColumnBreak);
  const insertPageBreak = useEditorStore((s) => s.insertPageBreak);
  const saveDocument = useEditorStore((s) => s.saveDocument);
  const loading = useEditorStore((s) => s.loading);

  const [showTableDialog, setShowTableDialog] = useState(false);
  const [tableRows, setTableRows] = useState(3);
  const [tableCols, setTableCols] = useState(3);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const disabled = !doc;

  const handleAddTable = useCallback(() => {
    if (!selection) return;
    addTable(selection.sectionIndex, selection.paragraphIndex, tableRows, tableCols);
    setShowTableDialog(false);
  }, [selection, tableRows, tableCols, addTable]);

  const handleImageSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const buffer = await file.arrayBuffer();
      const data = new Uint8Array(buffer);

      const img = new window.Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        const widthMm = (img.naturalWidth / 96) * 25.4;
        const heightMm = (img.naturalHeight / 96) * 25.4;
        insertImage(data, file.type, widthMm, heightMm);
        URL.revokeObjectURL(url);
      };
      img.src = url;
      e.target.value = "";
    },
    [insertImage],
  );

  return (
    <>
      <RibbonGroup label="삽입">
        <ToolbarButton
          icon={<Table className="w-4 h-4" />}
          title="표 삽입"
          disabled={disabled || !selection}
          onClick={() => setShowTableDialog(true)}
        />
        <ToolbarButton
          icon={<BarChart3 className="w-4 h-4" />}
          title="차트 삽입"
          disabled
        />
        <ToolbarButton
          icon={<Shapes className="w-4 h-4" />}
          title="도형 삽입"
          disabled
        />
        <ToolbarButton
          icon={<ImageIcon className="w-4 h-4" />}
          title="그림 삽입"
          disabled={disabled}
          onClick={() => imageInputRef.current?.click()}
        />
        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleImageSelect}
        />
        <ToolbarButton
          icon={<Columns className="w-4 h-4" />}
          title="단 나누기"
          disabled={disabled || !selection}
          onClick={() => insertColumnBreak()}
        />
        <ToolbarButton
          icon={<FileDown className="w-4 h-4" />}
          title="쪽 나누기"
          disabled={disabled || !selection}
          onClick={() => insertPageBreak()}
        />
      </RibbonGroup>

      <RibbonGroup label="파일">
        <ToolbarButton
          icon={<Save className="w-4 h-4" />}
          title="저장 (Ctrl+S)"
          disabled={disabled || loading}
          onClick={() => saveDocument()}
        />
      </RibbonGroup>

      {/* Table dialog */}
      {showTableDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-lg shadow-xl p-6 min-w-[280px]">
            <h3 className="font-semibold mb-4">표 삽입</h3>
            <div className="flex gap-4 mb-4">
              <label className="flex flex-col gap-1">
                <span className="text-sm text-gray-600">행</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={tableRows}
                  onChange={(e) => setTableRows(Number(e.target.value))}
                  className="border rounded px-2 py-1 w-20"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-sm text-gray-600">열</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={tableCols}
                  onChange={(e) => setTableCols(Number(e.target.value))}
                  className="border rounded px-2 py-1 w-20"
                />
              </label>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowTableDialog(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded"
              >
                취소
              </button>
              <button
                onClick={handleAddTable}
                className="px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                삽입
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
