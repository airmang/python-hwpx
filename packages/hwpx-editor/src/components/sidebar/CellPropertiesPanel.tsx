"use client";

import { useState, useEffect } from "react";
import { useEditorStore } from "@/lib/store";
import { hwpToMm } from "@/lib/hwp-units";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";
import { ColorPicker } from "../toolbar/ColorPicker";
import {
  AlignVerticalJustifyStart,
  AlignVerticalJustifyCenter,
  AlignVerticalJustifyEnd,
} from "lucide-react";

const BORDER_TYPES = [
  { value: "NONE", label: "없음" },
  { value: "SOLID", label: "실선" },
  { value: "DASH", label: "점선" },
  { value: "DOT", label: "작은 점선" },
  { value: "DASH_DOT", label: "일점 쇄선" },
  { value: "DOUBLE_SLIM", label: "이중선" },
];

const BORDER_WIDTHS = [
  "0.1 mm", "0.12 mm", "0.15 mm", "0.2 mm", "0.25 mm",
  "0.3 mm", "0.4 mm", "0.5 mm", "0.7 mm", "1.0 mm",
];

type BorderSide = "left" | "right" | "top" | "bottom";

function roundMm(hwp: number): number {
  return Math.round(hwpToMm(hwp) * 10) / 10;
}

export function CellPropertiesPanel() {
  const selection = useEditorStore((s) => s.selection);
  const viewModel = useEditorStore((s) => s.viewModel);
  const setCellBorder = useEditorStore((s) => s.setCellBorder);
  const setCellBackground = useEditorStore((s) => s.setCellBackground);
  const setCellVertAlign = useEditorStore((s) => s.setCellVertAlign);

  const sIdx = selection?.sectionIndex ?? 0;
  const pIdx = selection?.paragraphIndex ?? 0;
  const tIdx = selection?.tableIndex ?? 0;
  const row = selection?.row ?? 0;
  const col = selection?.col ?? 0;

  const table = viewModel?.sections[sIdx]?.paragraphs[pIdx]?.tables[tIdx];
  const cell = table?.cells[row]?.[col];
  const hasCell = !!cell;

  // Border state
  const [selectedSides, setSelectedSides] = useState<Set<BorderSide>>(
    new Set(["left", "right", "top", "bottom"]),
  );
  const [borderType, setBorderType] = useState("SOLID");
  const [borderWidth, setBorderWidth] = useState("0.12 mm");
  const [borderColor, setBorderColor] = useState("#000000");

  // Background state
  const [bgColor, setBgColor] = useState("#FFFFFF");
  const [noBg, setNoBg] = useState(true);

  // Vertical align
  const vertAlign = cell?.vertAlign ?? "CENTER";

  // Cell margin state
  const doc = useEditorStore((s) => s.doc);
  const [marginTop, setMarginTop] = useState(0);
  const [marginBottom, setMarginBottom] = useState(0);
  const [marginLeft, setMarginLeft] = useState(0);
  const [marginRight, setMarginRight] = useState(0);

  // Load margin from cell
  useEffect(() => {
    if (!doc || !selection || selection.tableIndex == null || selection.row == null || selection.col == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const tbl = para.tables[selection.tableIndex];
      if (!tbl) return;
      const c = tbl.cell(selection.row, selection.col);
      const m = c.getMargin();
      setMarginTop(roundMm(m.top));
      setMarginBottom(roundMm(m.bottom));
      setMarginLeft(roundMm(m.left));
      setMarginRight(roundMm(m.right));
    } catch { /* ignore */ }
  }, [doc, selection?.sectionIndex, selection?.paragraphIndex, selection?.tableIndex, selection?.row, selection?.col]);

  const toggleSide = (side: BorderSide) => {
    setSelectedSides((prev) => {
      const next = new Set(prev);
      if (next.has(side)) next.delete(side);
      else next.add(side);
      return next;
    });
  };

  const selectPreset = (preset: "all" | "outer" | "none") => {
    if (preset === "all") setSelectedSides(new Set(["left", "right", "top", "bottom"]));
    else if (preset === "outer") setSelectedSides(new Set(["left", "right", "top", "bottom"]));
    else setSelectedSides(new Set());
  };

  const applyBorder = () => {
    if (!hasCell || selectedSides.size === 0) return;
    setCellBorder(
      Array.from(selectedSides),
      { type: borderType, width: borderWidth, color: borderColor },
    );
  };

  const applyBackground = () => {
    if (!hasCell) return;
    setCellBackground(noBg ? null : bgColor);
  };

  const applyMargin = () => {
    if (!doc || !selection || selection.tableIndex == null || selection.row == null || selection.col == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const tbl = para.tables[selection.tableIndex];
      if (!tbl) return;
      const c = tbl.cell(selection.row, selection.col);
      const mmToHwp = (mm: number) => Math.round((mm * 7200) / 25.4);
      c.setMargin({
        top: mmToHwp(marginTop),
        bottom: mmToHwp(marginBottom),
        left: mmToHwp(marginLeft),
        right: mmToHwp(marginRight),
      });
      useEditorStore.getState().rebuild();
    } catch { /* ignore */ }
  };

  const inputClass =
    "w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40";

  const sideBtn = (side: BorderSide, label: string) => (
    <button
      onClick={() => toggleSide(side)}
      className={`w-7 h-7 rounded border text-[10px] font-medium transition-colors ${
        selectedSides.has(side)
          ? "bg-blue-100 border-blue-400 text-blue-700"
          : "bg-white border-gray-200 text-gray-400 hover:bg-gray-50"
      }`}
    >
      {label}
    </button>
  );

  const vertAlignBtn = (
    value: "TOP" | "CENTER" | "BOTTOM",
    Icon: typeof AlignVerticalJustifyStart,
    label: string,
  ) => (
    <button
      disabled={!hasCell}
      onClick={() => setCellVertAlign(value)}
      className={`flex-1 py-1.5 rounded border text-[10px] flex flex-col items-center gap-0.5 transition-colors ${
        vertAlign === value
          ? "bg-blue-50 border-blue-300 text-blue-700"
          : "bg-white border-gray-200 text-gray-500 hover:bg-gray-50"
      } disabled:opacity-60 disabled:cursor-not-allowed`}
      title={label}
    >
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );

  return (
    <div className="text-xs">
      {/* Border section */}
      <SidebarSection title="테두리">
        <div className="mb-2">
          <span className="text-[11px] text-gray-600 block mb-1.5">방향 선택</span>
          <div className="flex items-center gap-1 mb-1.5">
            <div className="grid grid-cols-3 gap-0.5">
              <div />
              {sideBtn("top", "T")}
              <div />
              {sideBtn("left", "L")}
              <button
                onClick={() => selectPreset("all")}
                className="w-7 h-7 rounded border bg-gray-50 border-gray-300 text-[9px] text-gray-600 hover:bg-gray-100"
                title="전체"
              >
                +
              </button>
              {sideBtn("right", "R")}
              <div />
              {sideBtn("bottom", "B")}
              <div />
            </div>
            <div className="flex flex-col gap-0.5 ml-2">
              <button
                onClick={() => selectPreset("all")}
                className="text-[10px] px-2 py-0.5 border border-gray-200 rounded hover:bg-gray-50"
              >
                전체
              </button>
              <button
                onClick={() => selectPreset("none")}
                className="text-[10px] px-2 py-0.5 border border-gray-200 rounded hover:bg-gray-50"
              >
                없음
              </button>
            </div>
          </div>
        </div>
        <SidebarField label="종류">
          <select
            value={borderType}
            disabled={!hasCell}
            onChange={(e) => setBorderType(e.target.value)}
            className={inputClass}
          >
            {BORDER_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </SidebarField>
        <SidebarField label="굵기">
          <select
            value={borderWidth}
            disabled={!hasCell}
            onChange={(e) => setBorderWidth(e.target.value)}
            className={inputClass}
          >
            {BORDER_WIDTHS.map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
        </SidebarField>
        <SidebarField label="색상">
          <ColorPicker
            color={borderColor}
            disabled={!hasCell}
            onChange={setBorderColor}
            variant="swatch"
            title="테두리 색상"
          />
        </SidebarField>
        <button
          disabled={!hasCell || selectedSides.size === 0}
          onClick={applyBorder}
          className="w-full mt-1 py-1.5 rounded bg-blue-600 text-white text-[11px] font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          테두리 적용
        </button>
      </SidebarSection>

      {/* Background section */}
      <SidebarSection title="배경">
        <div className="flex items-center gap-2 mb-2">
          <label className="flex items-center gap-1 text-[11px] text-gray-600">
            <input
              type="checkbox"
              checked={noBg}
              onChange={(e) => {
                setNoBg(e.target.checked);
                if (e.target.checked && hasCell) setCellBackground(null);
              }}
              className="w-3 h-3"
            />
            없음
          </label>
        </div>
        {!noBg && (
          <SidebarField label="색상">
            <ColorPicker
              color={bgColor}
              disabled={!hasCell}
              onChange={(nextColor) => {
                setBgColor(nextColor);
                if (hasCell) setCellBackground(nextColor);
              }}
              variant="swatch"
              title="셀 배경 색상"
            />
          </SidebarField>
        )}
      </SidebarSection>

      {/* Vertical align section */}
      <SidebarSection title="세로 정렬">
        <div className="flex gap-1">
          {vertAlignBtn("TOP", AlignVerticalJustifyStart, "위")}
          {vertAlignBtn("CENTER", AlignVerticalJustifyCenter, "가운데")}
          {vertAlignBtn("BOTTOM", AlignVerticalJustifyEnd, "아래")}
        </div>
      </SidebarSection>

      {/* Cell margin section */}
      <SidebarSection title="셀 여백" defaultOpen={false}>
        <SidebarField label="위 (mm)">
          <input
            type="number"
            value={marginTop}
            disabled={!hasCell}
            step={0.1}
            min={0}
            onChange={(e) => setMarginTop(Number(e.target.value))}
            onBlur={() => hasCell && applyMargin()}
            onKeyDown={(e) => { if (e.key === "Enter" && hasCell) applyMargin(); }}
            className={inputClass}
          />
        </SidebarField>
        <SidebarField label="아래 (mm)">
          <input
            type="number"
            value={marginBottom}
            disabled={!hasCell}
            step={0.1}
            min={0}
            onChange={(e) => setMarginBottom(Number(e.target.value))}
            onBlur={() => hasCell && applyMargin()}
            onKeyDown={(e) => { if (e.key === "Enter" && hasCell) applyMargin(); }}
            className={inputClass}
          />
        </SidebarField>
        <SidebarField label="왼쪽 (mm)">
          <input
            type="number"
            value={marginLeft}
            disabled={!hasCell}
            step={0.1}
            min={0}
            onChange={(e) => setMarginLeft(Number(e.target.value))}
            onBlur={() => hasCell && applyMargin()}
            onKeyDown={(e) => { if (e.key === "Enter" && hasCell) applyMargin(); }}
            className={inputClass}
          />
        </SidebarField>
        <SidebarField label="오른쪽 (mm)">
          <input
            type="number"
            value={marginRight}
            disabled={!hasCell}
            step={0.1}
            min={0}
            onChange={(e) => setMarginRight(Number(e.target.value))}
            onBlur={() => hasCell && applyMargin()}
            onKeyDown={(e) => { if (e.key === "Enter" && hasCell) applyMargin(); }}
            className={inputClass}
          />
        </SidebarField>
      </SidebarSection>
    </div>
  );
}
