"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Table, BarChart3, Shapes, ImageIcon, Save, Columns, FileDown } from "lucide-react";
import { useEditorStore } from "@/lib/store";
import { ToolbarButton } from "./ToolbarButton";
import { RibbonGroup } from "./RibbonGroup";

export function InsertGroup() {
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const addTable = useEditorStore((s) => s.addTable);
  const insertChart = useEditorStore((s) => s.insertChart);
  const insertImage = useEditorStore((s) => s.insertImage);
  const openShapeDialog = useEditorStore((s) => s.openShapeDialog);
  const insertColumnBreak = useEditorStore((s) => s.insertColumnBreak);
  const insertPageBreak = useEditorStore((s) => s.insertPageBreak);
  const saveDocument = useEditorStore((s) => s.saveDocument);
  const loading = useEditorStore((s) => s.loading);

  const [showTableDialog, setShowTableDialog] = useState(false);
  const [showChartDialog, setShowChartDialog] = useState(false);
  const [tableRows, setTableRows] = useState(3);
  const [tableCols, setTableCols] = useState(3);
  const [chartTitle, setChartTitle] = useState("문서 차트");
  const [chartType, setChartType] = useState<"bar" | "line">("bar");
  const [chartRowsText, setChartRowsText] = useState("항목 1: 100\n항목 2: 80\n항목 3: 60");
  const imageInputRef = useRef<HTMLInputElement>(null);

  const disabled = !doc;

  useEffect(() => {
    const handleOpenTableDialog = () => {
      if (disabled || !selection) return;
      setShowTableDialog(true);
    };
    const handleOpenImagePicker = () => {
      if (disabled) return;
      imageInputRef.current?.click();
    };

    window.addEventListener("hwpx-open-insert-table-dialog", handleOpenTableDialog);
    window.addEventListener("hwpx-open-insert-image-file", handleOpenImagePicker);
    return () => {
      window.removeEventListener("hwpx-open-insert-table-dialog", handleOpenTableDialog);
      window.removeEventListener("hwpx-open-insert-image-file", handleOpenImagePicker);
    };
  }, [disabled, selection]);

  const handleAddTable = useCallback(() => {
    if (!selection) return;
    addTable(selection.sectionIndex, selection.paragraphIndex, tableRows, tableCols);
    setShowTableDialog(false);
  }, [selection, tableRows, tableCols, addTable]);

  const handleInsertChart = useCallback(() => {
    const rows = chartRowsText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    const categories: string[] = [];
    const values: number[] = [];

    for (const row of rows) {
      const [left, right] = row.split(/[:=]/, 2).map((part) => part?.trim() ?? "");
      if (right) {
        const parsed = Number(right.replace(/,/g, ""));
        if (!Number.isFinite(parsed)) continue;
        categories.push(left || `항목 ${categories.length + 1}`);
        values.push(parsed);
        continue;
      }

      const parsed = Number(row.replace(/,/g, ""));
      if (!Number.isFinite(parsed)) continue;
      categories.push(`항목 ${categories.length + 1}`);
      values.push(parsed);
    }

    insertChart({ title: chartTitle, chartType, categories, values });
    setShowChartDialog(false);
  }, [chartRowsText, chartTitle, chartType, insertChart]);

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
          icon={<Table className="w-5 h-5" />}
          label="표"
          layout="vertical"
          title="표 삽입"
          disabled={disabled || !selection}
          onClick={() => setShowTableDialog(true)}
        />
        <ToolbarButton
          icon={<BarChart3 className="w-5 h-5" />}
          label="차트"
          layout="vertical"
          title="차트 삽입"
          disabled={disabled}
          onClick={() => setShowChartDialog(true)}
        />
        <ToolbarButton
          icon={<Shapes className="w-5 h-5" />}
          label="도형"
          layout="vertical"
          title="도형 삽입"
          disabled={disabled}
          onClick={() => openShapeDialog()}
        />
        <ToolbarButton
          icon={<ImageIcon className="w-5 h-5" />}
          label="그림"
          layout="vertical"
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
          icon={<Columns className="w-5 h-5" />}
          label="단"
          layout="vertical"
          title="단 나누기"
          disabled={disabled || !selection}
          onClick={() => insertColumnBreak()}
        />
        <ToolbarButton
          icon={<FileDown className="w-5 h-5" />}
          label="쪽"
          layout="vertical"
          title="쪽 나누기"
          disabled={disabled || !selection}
          onClick={() => insertPageBreak()}
        />
      </RibbonGroup>

      <RibbonGroup label="파일">
        <ToolbarButton
          icon={<Save className="w-5 h-5" />}
          label="저장"
          layout="vertical"
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

      {showChartDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-lg shadow-xl p-6 min-w-[360px] max-w-[480px]">
            <h3 className="font-semibold mb-4">차트 삽입</h3>
            <div className="space-y-3">
              <label className="flex flex-col gap-1">
                <span className="text-sm text-gray-600">제목</span>
                <input
                  value={chartTitle}
                  onChange={(e) => setChartTitle(e.target.value)}
                  className="border rounded px-2 py-1.5 text-sm"
                  placeholder="차트 제목"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-sm text-gray-600">차트 종류</span>
                <select
                  value={chartType}
                  onChange={(e) => setChartType((e.target.value === "line" ? "line" : "bar"))}
                  className="border rounded px-2 py-1.5 text-sm bg-white"
                >
                  <option value="bar">막대 차트</option>
                  <option value="line">선 차트</option>
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-sm text-gray-600">데이터 (한 줄에 하나, `항목: 값`)</span>
                <textarea
                  value={chartRowsText}
                  onChange={(e) => setChartRowsText(e.target.value)}
                  className="border rounded px-2 py-1.5 text-sm min-h-[110px] resize-y"
                  placeholder={"예시\n1분기: 120\n2분기: 95\n3분기: 140"}
                />
              </label>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setShowChartDialog(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded"
              >
                취소
              </button>
              <button
                onClick={handleInsertChart}
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
