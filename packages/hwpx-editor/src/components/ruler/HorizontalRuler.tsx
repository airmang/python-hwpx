"use client";

import { useRef, useCallback, useState } from "react";
import { useEditorStore } from "@/lib/store";
import { pxToHwp } from "@/lib/hwp-units";

// ── Indent drag handle components ─────────────────────────────────────────

interface HandleProps {
  /** Offset from left edge of content area in px */
  positionPx: number;
  onDrag: (deltaPx: number) => void;
}

/** ▽ First-line indent handle (top triangle) */
function FirstLineHandle({ positionPx, onDrag }: HandleProps) {
  const startXRef = useRef(0);
  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      startXRef.current = e.clientX;
      const onMove = (me: MouseEvent) => {
        /* visual-only during drag; commit on up */
      };
      const onUp = (me: MouseEvent) => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        const delta = me.clientX - startXRef.current;
        if (Math.abs(delta) >= 2) onDrag(delta);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      document.body.style.cursor = "ew-resize";
    },
    [onDrag],
  );

  return (
    <div
      className="absolute cursor-ew-resize select-none"
      style={{ left: positionPx - 5, top: 0 }}
      onMouseDown={onMouseDown}
      title="첫줄 들여쓰기"
    >
      <svg width="10" height="8" viewBox="0 0 10 8">
        <polygon points="5,8 0,0 10,0" fill="#4A90D9" />
      </svg>
    </div>
  );
}

/** △ Left indent handle (bottom triangle) */
function LeftIndentHandle({ positionPx, onDrag }: HandleProps) {
  const startXRef = useRef(0);
  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      startXRef.current = e.clientX;
      const onMove = (me: MouseEvent) => {};
      const onUp = (me: MouseEvent) => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        const delta = me.clientX - startXRef.current;
        if (Math.abs(delta) >= 2) onDrag(delta);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      document.body.style.cursor = "ew-resize";
    },
    [onDrag],
  );

  return (
    <div
      className="absolute cursor-ew-resize select-none"
      style={{ left: positionPx - 5, bottom: 0 }}
      onMouseDown={onMouseDown}
      title="둘째줄 시작 위치 (왼쪽 들여쓰기)"
    >
      <svg width="10" height="8" viewBox="0 0 10 8">
        <polygon points="5,0 10,8 0,8" fill="#4A90D9" />
      </svg>
    </div>
  );
}

/** □ Combined margin handle (bottom rectangle, moves both) */
function CombinedHandle({ positionPx, onDrag }: HandleProps) {
  const startXRef = useRef(0);
  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      startXRef.current = e.clientX;
      const onMove = (me: MouseEvent) => {};
      const onUp = (me: MouseEvent) => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        const delta = me.clientX - startXRef.current;
        if (Math.abs(delta) >= 2) onDrag(delta);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      document.body.style.cursor = "ew-resize";
    },
    [onDrag],
  );

  return (
    <div
      className="absolute cursor-ew-resize select-none"
      style={{ left: positionPx - 4, bottom: 8 }}
      onMouseDown={onMouseDown}
      title="왼쪽 여백 전체 이동"
    >
      <svg width="8" height="6" viewBox="0 0 8 6">
        <rect x="0" y="0" width="8" height="6" fill="#4A90D9" rx="1" />
      </svg>
    </div>
  );
}

// ── Main ruler ────────────────────────────────────────────────────────────

export function HorizontalRuler() {
  const viewModel = useEditorStore((s) => s.viewModel);
  const extendedFormat = useEditorStore((s) => s.extendedFormat);
  const selection = useEditorStore((s) => s.selection);
  const setFirstLineIndent = useEditorStore((s) => s.setFirstLineIndent);
  const setLeftIndent = useEditorStore((s) => s.setLeftIndent);

  if (!viewModel || viewModel.sections.length === 0) return null;

  const section = viewModel.sections[0]!;
  const pageWidthPx = section.pageWidthPx;
  const marginLeftPx = section.marginLeftPx;
  const marginRightPx = section.marginRightPx;
  const contentWidthPx = pageWidthPx - marginLeftPx - marginRightPx;

  // Current indent values (hwpUnits) from extended format
  const firstLineIndentHwp = extendedFormat.para.firstLineIndent;
  const leftIndentHwp = extendedFormat.para.indentLeft;

  // Convert to px for handle positioning
  const firstLineIndentPx = (firstLineIndentHwp * 96) / 7200;
  const leftIndentPx = (leftIndentHwp * 96) / 7200;

  // Generate tick marks in mm (every 1mm tick, every 10mm major)
  const mmPerPx = 25.4 / 96; // px to mm
  const totalMm = contentWidthPx * mmPerPx;
  const ticks: { position: number; label: string; major: boolean; medium: boolean }[] = [];

  for (let mm = 0; mm <= totalMm + 0.5; mm += 1) {
    const px = mm / mmPerPx;
    const major = mm % 10 === 0;
    const medium = mm % 5 === 0 && !major;
    ticks.push({
      position: px,
      label: major ? String(Math.round(mm / 10)) : "",
      major,
      medium,
    });
  }

  const hasSelection = !!selection;

  const handleFirstLineDrag = useCallback(
    (deltaPx: number) => {
      const deltaHwp = pxToHwp(deltaPx);
      setFirstLineIndent(firstLineIndentHwp + deltaHwp);
    },
    [firstLineIndentHwp, setFirstLineIndent],
  );

  const handleLeftIndentDrag = useCallback(
    (deltaPx: number) => {
      const deltaHwp = pxToHwp(deltaPx);
      setLeftIndent(leftIndentHwp + deltaHwp);
    },
    [leftIndentHwp, setLeftIndent],
  );

  const handleCombinedDrag = useCallback(
    (deltaPx: number) => {
      const deltaHwp = pxToHwp(deltaPx);
      // Move both, keeping relative position
      setLeftIndent(leftIndentHwp + deltaHwp);
      // firstLineIndent moves with left indent (same delta)
      setTimeout(() => {
        setFirstLineIndent(firstLineIndentHwp + deltaHwp);
      }, 0);
    },
    [firstLineIndentHwp, leftIndentHwp, setFirstLineIndent, setLeftIndent],
  );

  return (
    <div className="bg-white border-b border-gray-200 overflow-hidden flex-shrink-0">
      <div className="flex justify-center">
        <div
          className="relative"
          style={{ width: pageWidthPx, height: 28 }}
        >
          {/* Left margin area */}
          <div
            className="absolute top-0 left-0 h-full bg-gray-100"
            style={{ width: marginLeftPx }}
          />
          {/* Right margin area */}
          <div
            className="absolute top-0 right-0 h-full bg-gray-100"
            style={{ width: marginRightPx }}
          />
          {/* Ruler content area with ticks */}
          <div
            className="absolute top-0 h-full"
            style={{ left: marginLeftPx, width: contentWidthPx }}
          >
            {ticks.map((tick, i) => (
              <div
                key={i}
                className="absolute bottom-0"
                style={{ left: tick.position }}
              >
                <div
                  className={`w-px ${
                    tick.major
                      ? "h-3 bg-gray-500"
                      : tick.medium
                        ? "h-2 bg-gray-400"
                        : "h-1 bg-gray-300"
                  }`}
                />
                {tick.label && (
                  <span className="absolute -top-0.5 left-1/2 -translate-x-1/2 text-[8px] text-gray-400 leading-none select-none">
                    {tick.label}
                  </span>
                )}
              </div>
            ))}

            {/* Indent handles (only shown when a paragraph is selected) */}
            {hasSelection && (
              <>
                <FirstLineHandle
                  positionPx={leftIndentPx + firstLineIndentPx}
                  onDrag={handleFirstLineDrag}
                />
                <LeftIndentHandle
                  positionPx={leftIndentPx}
                  onDrag={handleLeftIndentDrag}
                />
                <CombinedHandle
                  positionPx={leftIndentPx}
                  onDrag={handleCombinedDrag}
                />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
