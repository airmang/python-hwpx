"use client";

import { useState, useEffect } from "react";
import { useEditorStore } from "@/lib/store";
import { hwpToMm } from "@/lib/hwp-units";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";

const PX_TO_MM = 25.4 / 96;

function roundMm(hwp: number): number {
  return Math.round(hwpToMm(hwp) * 10) / 10;
}

export function ImageLayoutPanel() {
  const selection = useEditorStore((s) => s.selection);
  const viewModel = useEditorStore((s) => s.viewModel);
  const updatePictureSize = useEditorStore((s) => s.updatePictureSize);
  const setImageOutMargin = useEditorStore((s) => s.setImageOutMargin);

  const sIdx = selection?.sectionIndex ?? 0;
  const pIdx = selection?.paragraphIndex ?? 0;
  const imgIdx = selection?.imageIndex ?? 0;

  const image = viewModel?.sections[sIdx]?.paragraphs[pIdx]?.images[imgIdx];
  const hasImage = !!image;

  const widthMm = image ? parseFloat((image.widthPx * PX_TO_MM).toFixed(2)) : 0;
  const heightMm = image ? parseFloat((image.heightPx * PX_TO_MM).toFixed(2)) : 0;

  const [omTop, setOmTop] = useState(image ? roundMm(image.outMargin.top) : 0);
  const [omBottom, setOmBottom] = useState(image ? roundMm(image.outMargin.bottom) : 0);
  const [omLeft, setOmLeft] = useState(image ? roundMm(image.outMargin.left) : 0);
  const [omRight, setOmRight] = useState(image ? roundMm(image.outMargin.right) : 0);

  useEffect(() => {
    if (!image) return;
    setOmTop(roundMm(image.outMargin.top));
    setOmBottom(roundMm(image.outMargin.bottom));
    setOmLeft(roundMm(image.outMargin.left));
    setOmRight(roundMm(image.outMargin.right));
  }, [image?.outMargin.top, image?.outMargin.bottom, image?.outMargin.left, image?.outMargin.right]);

  const applyOutMargin = () => {
    if (hasImage) setImageOutMargin({ top: omTop, bottom: omBottom, left: omLeft, right: omRight });
  };

  const inputClass =
    "w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40";

  return (
    <div className="text-xs">
      <SidebarSection title="크기">
        <SidebarField label="너비">
          <div className="flex items-center gap-1">
            <select disabled className="h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40 w-20 flex-shrink-0">
              <option>고정 값</option>
            </select>
            <input
              type="number"
              step="0.01"
              value={widthMm}
              disabled={!image}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v > 0) updatePictureSize(v, heightMm);
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="높이">
          <div className="flex items-center gap-1">
            <select disabled className="h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40 w-20 flex-shrink-0">
              <option>고정 값</option>
            </select>
            <input
              type="number"
              step="0.01"
              value={heightMm}
              disabled={!image}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (!isNaN(v) && v > 0) updatePictureSize(widthMm, v);
              }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <label className="flex items-center gap-2 text-[11px] text-gray-600 mt-1">
          <input type="checkbox" disabled className="w-3 h-3" />
          크기 고정
        </label>
      </SidebarSection>

      <SidebarSection title="위치">
        <div className="mb-2">
          <span className="text-[11px] text-gray-600 block mb-1.5">본문과의 배치</span>
          <div className="flex gap-1">
            {["어울림", "자리차지", "글 뒤로", "글 앞으로"].map((label, i) => (
              <button
                key={label}
                disabled
                className={`flex-1 py-1.5 rounded border text-[9px] transition-colors flex flex-col items-center gap-0.5 ${
                  i === 0
                    ? "bg-blue-50 border-blue-300 text-blue-700"
                    : "bg-white border-gray-200 text-gray-500"
                } disabled:opacity-60 disabled:cursor-not-allowed`}
              >
                <svg width="20" height="16" viewBox="0 0 20 16" fill="none" className="mx-auto">
                  <line x1="2" y1="2" x2="18" y2="2" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                  <line x1="2" y1="5" x2="18" y2="5" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                  <rect x="6" y="7" width="8" height="6" rx="0.5" stroke="currentColor" strokeWidth="1" fill="currentColor" fillOpacity="0.15" />
                  {i === 0 && (
                    <>
                      <line x1="2" y1="8" x2="5" y2="8" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                      <line x1="15" y1="8" x2="18" y2="8" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                      <line x1="2" y1="11" x2="5" y2="11" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                      <line x1="15" y1="11" x2="18" y2="11" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                      <line x1="2" y1="14" x2="18" y2="14" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                    </>
                  )}
                  {i === 1 && (
                    <line x1="2" y1="14" x2="18" y2="14" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                  )}
                  {i >= 2 && (
                    <>
                      <line x1="2" y1="8" x2="18" y2="8" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                      <line x1="2" y1="11" x2="18" y2="11" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                      <line x1="2" y1="14" x2="18" y2="14" stroke="currentColor" strokeWidth="1" opacity="0.4" />
                    </>
                  )}
                </svg>
                {label}
              </button>
            ))}
          </div>
        </div>
        <label className="flex items-center gap-2 text-[11px] text-gray-600 mb-3">
          <input type="checkbox" disabled className="w-3 h-3" />
          글자처럼 취급
        </label>
        <SidebarField label="가로">
          <div className="flex items-center gap-1">
            <select disabled className="h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40 w-16 flex-shrink-0">
              <option>문단</option>
            </select>
            <input type="number" disabled value={0} onChange={() => {}} className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="세로">
          <div className="flex items-center gap-1">
            <select disabled className="h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40 w-16 flex-shrink-0">
              <option>문단</option>
            </select>
            <input type="number" disabled value={0} onChange={() => {}} className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="개체 회전/기울이기" defaultOpen={false}>
        <SidebarField label="회전각">
          <input type="number" disabled value={0} onChange={() => {}} className={inputClass} />
        </SidebarField>
        <SidebarField label="가로 기울이기">
          <input type="number" disabled value={0} onChange={() => {}} className={inputClass} />
        </SidebarField>
        <SidebarField label="세로 기울이기">
          <input type="number" disabled value={0} onChange={() => {}} className={inputClass} />
        </SidebarField>
      </SidebarSection>

      <SidebarSection title="기타" defaultOpen={false}>
        <SidebarField label="번호 종류">
          <select disabled className={inputClass}>
            <option>그림</option>
          </select>
        </SidebarField>
        <label className="flex items-center gap-2 text-[11px] text-gray-600">
          <input type="checkbox" disabled className="w-3 h-3" />
          개체 보호
        </label>
      </SidebarSection>

      <SidebarSection title="바깥 여백" defaultOpen={false}>
        <SidebarField label="위쪽">
          <div className="flex items-center gap-1">
            <input type="number" step="0.1" min={0} disabled={!hasImage} value={omTop}
              onChange={(e) => setOmTop(Number(e.target.value))}
              onBlur={applyOutMargin}
              onKeyDown={(e) => { if (e.key === "Enter") applyOutMargin(); }}
              className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="아래쪽">
          <div className="flex items-center gap-1">
            <input type="number" step="0.1" min={0} disabled={!hasImage} value={omBottom}
              onChange={(e) => setOmBottom(Number(e.target.value))}
              onBlur={applyOutMargin}
              onKeyDown={(e) => { if (e.key === "Enter") applyOutMargin(); }}
              className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="왼쪽">
          <div className="flex items-center gap-1">
            <input type="number" step="0.1" min={0} disabled={!hasImage} value={omLeft}
              onChange={(e) => setOmLeft(Number(e.target.value))}
              onBlur={applyOutMargin}
              onKeyDown={(e) => { if (e.key === "Enter") applyOutMargin(); }}
              className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="오른쪽">
          <div className="flex items-center gap-1">
            <input type="number" step="0.1" min={0} disabled={!hasImage} value={omRight}
              onChange={(e) => setOmRight(Number(e.target.value))}
              onBlur={applyOutMargin}
              onKeyDown={(e) => { if (e.key === "Enter") applyOutMargin(); }}
              className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
      </SidebarSection>
    </div>
  );
}
