"use client";

import { useEffect, useState } from "react";
import { useEditorStore } from "@/lib/store";
import { PAGE_SIZE_PRESETS, type OrientationType } from "@/lib/constants";
import { hwpToMm } from "@/lib/hwp-units";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";

const PAGE_NUMBER_POSITIONS = [
  { value: "none", label: "없음" },
  { value: "header-left", label: "머리말 왼쪽" },
  { value: "header-center", label: "머리말 가운데" },
  { value: "header-right", label: "머리말 오른쪽" },
  { value: "footer-left", label: "꼬리말 왼쪽" },
  { value: "footer-center", label: "꼬리말 가운데" },
  { value: "footer-right", label: "꼬리말 오른쪽" },
] as const;

function uiPageNumPosition(pos?: string | null): string {
  const upper = (pos ?? "").toUpperCase();
  if (!upper) return "none";
  if (upper.includes("TOP") && upper.includes("LEFT")) return "header-left";
  if (upper.includes("TOP") && upper.includes("RIGHT")) return "header-right";
  if (upper.includes("TOP")) return "header-center";
  if (upper.includes("BOTTOM") && upper.includes("LEFT")) return "footer-left";
  if (upper.includes("BOTTOM") && upper.includes("RIGHT")) return "footer-right";
  if (upper.includes("BOTTOM")) return "footer-center";
  return "none";
}

export function PageSetupPanel() {
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const updatePageSize = useEditorStore((s) => s.updatePageSize);
  const updatePageMargins = useEditorStore((s) => s.updatePageMargins);
  const updatePageOrientation = useEditorStore((s) => s.updatePageOrientation);
  const setPageNumbering = useEditorStore((s) => s.setPageNumbering);
  const setColumnCount = useEditorStore((s) => s.setColumnCount);
  const viewModel = useEditorStore((s) => s.viewModel);

  const [pageNumPosition, setPageNumPosition] = useState("none");
  const [pageNumStart, setPageNumStart] = useState(1);

  const disabled = !doc;
  const sIdx = selection?.sectionIndex ?? 0;
  const section = doc?.sections[sIdx];
  const sectionVm = viewModel?.sections[sIdx];

  const pageSize = section?.properties.pageSize;
  const pageMargins = section?.properties.pageMargins;
  const columnLayout = section?.properties.columnLayout;

  const widthMm = pageSize ? parseFloat(hwpToMm(pageSize.width).toFixed(1)) : 210;
  const heightMm = pageSize ? parseFloat(hwpToMm(pageSize.height).toFixed(1)) : 297;
  const orientation: OrientationType =
    pageSize && pageSize.width > pageSize.height ? "LANDSCAPE" : "PORTRAIT";

  const leftMm = pageMargins ? parseFloat(hwpToMm(pageMargins.left).toFixed(1)) : 30;
  const rightMm = pageMargins ? parseFloat(hwpToMm(pageMargins.right).toFixed(1)) : 30;
  const topMm = pageMargins ? parseFloat(hwpToMm(pageMargins.top).toFixed(1)) : 20;
  const bottomMm = pageMargins ? parseFloat(hwpToMm(pageMargins.bottom).toFixed(1)) : 15;
  const headerMm = pageMargins ? parseFloat(hwpToMm(pageMargins.header).toFixed(1)) : 15;
  const footerMm = pageMargins ? parseFloat(hwpToMm(pageMargins.footer).toFixed(1)) : 15;
  const gutterMm = pageMargins ? parseFloat(hwpToMm(pageMargins.gutter).toFixed(1)) : 0;
  const columnCount = columnLayout?.colCount ?? 1;
  const columnGapMm = columnLayout ? parseFloat(hwpToMm(columnLayout.sameGap).toFixed(1)) : 8;

  useEffect(() => {
    const pos = uiPageNumPosition(sectionVm?.pageNum?.pos);
    setPageNumPosition(pos);
    setPageNumStart(Math.max(1, sectionVm?.startPageNumber ?? 1));
  }, [sectionVm?.pageNum?.pos, sectionVm?.startPageNumber]);

  // Find matching preset
  const matchedPreset = PAGE_SIZE_PRESETS.find(
    (p) => p.width === Math.round(widthMm) && p.height === Math.round(heightMm),
  );
  // Also check landscape match
  const matchedPresetLandscape = PAGE_SIZE_PRESETS.find(
    (p) => p.height === Math.round(widthMm) && p.width === Math.round(heightMm),
  );
  const presetValue = matchedPreset?.name ?? matchedPresetLandscape?.name ?? "custom";

  const handlePresetChange = (name: string) => {
    const preset = PAGE_SIZE_PRESETS.find((p) => p.name === name);
    if (!preset) return;
    if (orientation === "LANDSCAPE") {
      updatePageSize(preset.height, preset.width);
    } else {
      updatePageSize(preset.width, preset.height);
    }
  };

  const inputClass =
    "w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40";

  return (
    <div className="text-xs">
      <SidebarSection title="용지 크기">
        <SidebarField label="종류">
          <select
            disabled={disabled}
            value={presetValue}
            onChange={(e) => handlePresetChange(e.target.value)}
            className={inputClass}
          >
            {PAGE_SIZE_PRESETS.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
            {presetValue === "custom" && (
              <option value="custom">사용자 지정</option>
            )}
          </select>
        </SidebarField>
        <SidebarField label="폭">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={widthMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v > 0) updatePageSize(v, heightMm);
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="길이">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={heightMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v > 0) updatePageSize(widthMm, v);
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="용지 방향">
        <div className="flex gap-2 mb-2">
          <button
            disabled={disabled}
            onClick={() => updatePageOrientation("PORTRAIT")}
            className={`flex-1 py-2 rounded border text-[10px] flex flex-col items-center gap-1 transition-colors ${
              orientation === "PORTRAIT"
                ? "bg-blue-50 border-blue-300 text-blue-700"
                : "bg-white border-gray-200 text-gray-500 hover:bg-gray-50"
            } disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            <svg width="20" height="26" viewBox="0 0 20 26" fill="none" className="mx-auto">
              <rect x="1" y="1" width="18" height="24" rx="1" stroke="currentColor" strokeWidth="1.5" fill="none" />
              <line x1="4" y1="6" x2="16" y2="6" stroke="currentColor" strokeWidth="1" opacity="0.4" />
              <line x1="4" y1="10" x2="16" y2="10" stroke="currentColor" strokeWidth="1" opacity="0.4" />
              <line x1="4" y1="14" x2="12" y2="14" stroke="currentColor" strokeWidth="1" opacity="0.4" />
            </svg>
            세로
          </button>
          <button
            disabled={disabled}
            onClick={() => updatePageOrientation("LANDSCAPE")}
            className={`flex-1 py-2 rounded border text-[10px] flex flex-col items-center gap-1 transition-colors ${
              orientation === "LANDSCAPE"
                ? "bg-blue-50 border-blue-300 text-blue-700"
                : "bg-white border-gray-200 text-gray-500 hover:bg-gray-50"
            } disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            <svg width="26" height="20" viewBox="0 0 26 20" fill="none" className="mx-auto">
              <rect x="1" y="1" width="24" height="18" rx="1" stroke="currentColor" strokeWidth="1.5" fill="none" />
              <line x1="4" y1="5" x2="22" y2="5" stroke="currentColor" strokeWidth="1" opacity="0.4" />
              <line x1="4" y1="9" x2="22" y2="9" stroke="currentColor" strokeWidth="1" opacity="0.4" />
              <line x1="4" y1="13" x2="16" y2="13" stroke="currentColor" strokeWidth="1" opacity="0.4" />
            </svg>
            가로
          </button>
        </div>
      </SidebarSection>

      <SidebarSection title="제본">
        <div className="flex gap-1 mb-2">
          {(["LEFT", "FACING", "TOP"] as const).map((type) => (
            <button
              key={type}
              disabled={disabled}
              className={`flex-1 py-1 rounded text-[10px] border transition-colors ${
                "bg-white border-gray-200 text-gray-500 hover:bg-gray-50"
              } disabled:opacity-40 disabled:cursor-not-allowed`}
            >
              {type === "LEFT" && "한쪽"}
              {type === "FACING" && "맞쪽"}
              {type === "TOP" && "위로"}
            </button>
          ))}
        </div>
      </SidebarSection>

      <SidebarSection title="단(열) 설정">
        <SidebarField label="열 개수">
          <select
            disabled={disabled}
            value={columnCount}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (!Number.isNaN(v)) setColumnCount(v, columnGapMm);
            }}
            className={inputClass}
          >
            {[1, 2, 3, 4].map((v) => (
              <option key={v} value={v}>
                {v}단
              </option>
            ))}
          </select>
        </SidebarField>
        <SidebarField label="열 간격">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              min={0}
              value={columnGapMm}
              disabled={disabled || columnCount <= 1}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0) setColumnCount(columnCount, v);
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="용지 여백">
        <SidebarField label="왼쪽">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={leftMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0) updatePageMargins({ left: v });
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="오른쪽">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={rightMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0) updatePageMargins({ right: v });
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="위쪽">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={topMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0) updatePageMargins({ top: v });
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="아래쪽">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={bottomMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0) updatePageMargins({ bottom: v });
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="머리말">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={headerMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0) updatePageMargins({ header: v });
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="꼬리말">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={footerMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0) updatePageMargins({ footer: v });
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="제본">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              value={gutterMm}
              disabled={disabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v >= 0) updatePageMargins({ gutter: v });
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="쪽 번호">
        <SidebarField label="위치">
          <select
            disabled={disabled}
            value={pageNumPosition}
            onChange={(e) => {
              setPageNumPosition(e.target.value);
              setPageNumbering({ position: e.target.value, startNumber: pageNumStart });
            }}
            className={inputClass}
          >
            {PAGE_NUMBER_POSITIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </SidebarField>
        <SidebarField label="시작 번호">
          <input
            type="number"
            value={pageNumStart}
            disabled={disabled}
            min={1}
            step={1}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!isNaN(v) && v >= 1) {
                setPageNumStart(v);
              }
            }}
            onBlur={() => {
              if (!disabled && pageNumPosition !== "none") {
                setPageNumbering({ position: pageNumPosition, startNumber: pageNumStart });
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !disabled && pageNumPosition !== "none") {
                setPageNumbering({ position: pageNumPosition, startNumber: pageNumStart });
              }
            }}
            className={inputClass}
          />
        </SidebarField>
      </SidebarSection>
    </div>
  );
}
