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

export function ImagePropertiesPanel() {
  const selection = useEditorStore((s) => s.selection);
  const viewModel = useEditorStore((s) => s.viewModel);
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
      <SidebarSection title="그림">
        <SidebarField label="파일 이름">
          <div className="flex items-center gap-1">
            <span className="text-[11px] text-gray-600 truncate flex-1">
              {image?.binaryItemIdRef ?? "-"}
            </span>
            <button disabled className="h-6 px-2 text-[10px] border border-gray-300 rounded bg-white text-gray-500 disabled:opacity-40 flex-shrink-0">
              삽입 그림
            </button>
          </div>
        </SidebarField>
        <label className="flex items-center gap-2 text-[11px] text-gray-600 mt-1">
          <input type="checkbox" checked disabled className="w-3 h-3" />
          문서에 포함
        </label>
      </SidebarSection>

      <SidebarSection title="확대/축소 비율">
        <SidebarField label="가로">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.01"
              value={100}
              disabled
              onChange={() => {}}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">%</span>
          </div>
        </SidebarField>
        <SidebarField label="세로">
          <div className="flex items-center gap-1">
            <input
              type="number"
              step="0.01"
              value={100}
              disabled
              onChange={() => {}}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">%</span>
          </div>
        </SidebarField>
        <label className="flex items-center gap-2 text-[11px] text-gray-600 mt-1">
          <input type="checkbox" disabled className="w-3 h-3" />
          가로 세로 같은 비율 유지
        </label>
      </SidebarSection>

      <SidebarSection title="자르기" defaultOpen={false}>
        {["왼쪽", "오른쪽", "위쪽", "아래쪽"].map((label) => (
          <SidebarField key={label} label={label}>
            <div className="flex items-center gap-1">
              <input type="number" step="0.1" disabled value={0} onChange={() => {}} className={inputClass} />
              <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
            </div>
          </SidebarField>
        ))}
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

      <SidebarSection title="색 조절" defaultOpen={false}>
        <SidebarField label="색조">
          <select disabled className={inputClass}>
            <option>효과 없음</option>
          </select>
        </SidebarField>
        <SidebarField label="밝기">
          <div className="flex items-center gap-1">
            <input type="number" disabled value={0} onChange={() => {}} className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">%</span>
          </div>
        </SidebarField>
        <SidebarField label="대비">
          <div className="flex items-center gap-1">
            <input type="number" disabled value={0} onChange={() => {}} className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">%</span>
          </div>
        </SidebarField>
        <div className="mt-2 space-y-1">
          <label className="flex items-center gap-2 text-[11px] text-gray-600">
            <input type="checkbox" disabled className="w-3 h-3" />
            워터마크 효과
          </label>
          <label className="flex items-center gap-2 text-[11px] text-gray-600">
            <input type="checkbox" disabled className="w-3 h-3" />
            그림 반전
          </label>
        </div>
      </SidebarSection>
    </div>
  );
}
