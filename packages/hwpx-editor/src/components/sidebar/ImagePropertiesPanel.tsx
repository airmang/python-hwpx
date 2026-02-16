"use client";

import { useState, useEffect, useRef } from "react";
import { useEditorStore } from "@/lib/store";
import { hwpToMm } from "@/lib/hwp-units";
import { SidebarSection } from "./SidebarSection";
import { SidebarField } from "./SidebarField";

const PX_TO_MM = 25.4 / 96;

function getMediaType(file: File): "image/png" | "image/jpeg" | "image/gif" | "image/bmp" {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  const typeMap: Record<string, "image/png" | "image/jpeg" | "image/gif" | "image/bmp"> = {
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    gif: "image/gif",
    bmp: "image/bmp",
  };
  return typeMap[ext] ?? "image/png";
}

async function getImageDimensions(data: Uint8Array, mediaType: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve) => {
    const blob = new Blob([data as unknown as BlobPart], { type: mediaType });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve({ width: 100, height: 100 }); // fallback
    };
    img.src = url;
  });
}

function roundMm(hwp: number): number {
  return Math.round(hwpToMm(hwp) * 10) / 10;
}

export function ImagePropertiesPanel() {
  const selection = useEditorStore((s) => s.selection);
  const viewModel = useEditorStore((s) => s.viewModel);
  const doc = useEditorStore((s) => s.doc);
  const setImageOutMargin = useEditorStore((s) => s.setImageOutMargin);
  const setImageScale = useEditorStore((s) => s.setImageScale);
  const setImageCrop = useEditorStore((s) => s.setImageCrop);
  const setImageAdjustment = useEditorStore((s) => s.setImageAdjustment);
  const insertImage = useEditorStore((s) => s.insertImage);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isInserting, setIsInserting] = useState(false);

  const sIdx = selection?.sectionIndex ?? 0;
  const pIdx = selection?.paragraphIndex ?? 0;
  const imgIdx = selection?.imageIndex ?? 0;

  const image = viewModel?.sections[sIdx]?.paragraphs[pIdx]?.images[imgIdx];
  const hasImage = !!image;

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsInserting(true);
    try {
      const buffer = await file.arrayBuffer();
      const data = new Uint8Array(buffer);
      const mediaType = getMediaType(file);
      const dims = await getImageDimensions(data, mediaType);
      // Scale to fit max 150mm width while maintaining aspect ratio
      const maxWidth = 150;
      const scale = dims.width * PX_TO_MM > maxWidth ? maxWidth / (dims.width * PX_TO_MM) : 1;
      const widthMm = dims.width * PX_TO_MM * scale;
      const heightMm = dims.height * PX_TO_MM * scale;
      insertImage(data, mediaType, widthMm, heightMm);
    } catch (err) {
      console.error("Failed to insert image:", err);
    } finally {
      setIsInserting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const [omTop, setOmTop] = useState(image ? roundMm(image.outMargin.top) : 0);
  const [omBottom, setOmBottom] = useState(image ? roundMm(image.outMargin.bottom) : 0);
  const [omLeft, setOmLeft] = useState(image ? roundMm(image.outMargin.left) : 0);
  const [omRight, setOmRight] = useState(image ? roundMm(image.outMargin.right) : 0);
  const [scaleX, setScaleX] = useState(image?.scaleXPercent ?? 100);
  const [scaleY, setScaleY] = useState(image?.scaleYPercent ?? 100);
  const [keepAspect, setKeepAspect] = useState(true);
  const [cropLeft, setCropLeft] = useState(image ? roundMm(image.cropLeftHwp) : 0);
  const [cropRight, setCropRight] = useState(image ? roundMm(image.cropRightHwp) : 0);
  const [cropTop, setCropTop] = useState(image ? roundMm(image.cropTopHwp) : 0);
  const [cropBottom, setCropBottom] = useState(image ? roundMm(image.cropBottomHwp) : 0);
  const [brightness, setBrightness] = useState(image?.brightness ?? 0);
  const [contrast, setContrast] = useState(image?.contrast ?? 0);
  const [effect, setEffect] = useState(image?.effect ?? "REAL_PIC");
  const [alpha, setAlpha] = useState(image?.alpha ?? 0);

  useEffect(() => {
    if (!image) return;
    setOmTop(roundMm(image.outMargin.top));
    setOmBottom(roundMm(image.outMargin.bottom));
    setOmLeft(roundMm(image.outMargin.left));
    setOmRight(roundMm(image.outMargin.right));
    setScaleX(image.scaleXPercent);
    setScaleY(image.scaleYPercent);
    setCropLeft(roundMm(image.cropLeftHwp));
    setCropRight(roundMm(image.cropRightHwp));
    setCropTop(roundMm(image.cropTopHwp));
    setCropBottom(roundMm(image.cropBottomHwp));
    setBrightness(image.brightness);
    setContrast(image.contrast);
    setEffect(image.effect);
    setAlpha(image.alpha);
  }, [
    image?.outMargin.top,
    image?.outMargin.bottom,
    image?.outMargin.left,
    image?.outMargin.right,
    image?.scaleXPercent,
    image?.scaleYPercent,
    image?.cropLeftHwp,
    image?.cropRightHwp,
    image?.cropTopHwp,
    image?.cropBottomHwp,
    image?.brightness,
    image?.contrast,
    image?.effect,
    image?.alpha,
  ]);

  const applyOutMargin = () => {
    if (hasImage) setImageOutMargin({ top: omTop, bottom: omBottom, left: omLeft, right: omRight });
  };

  const applyScale = () => {
    if (!hasImage) return;
    setImageScale(scaleX, scaleY);
  };

  const applyCrop = () => {
    if (!hasImage) return;
    setImageCrop({
      leftMm: cropLeft,
      rightMm: cropRight,
      topMm: cropTop,
      bottomMm: cropBottom,
    });
  };

  const applyAdjustment = () => {
    if (!hasImage) return;
    setImageAdjustment({ brightness, contrast, effect, alpha });
  };

  const inputClass =
    "w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40";

  return (
    <div className="text-xs">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/bmp"
        className="hidden"
        onChange={handleFileSelect}
      />
      <SidebarSection title="그림">
        <SidebarField label="파일 이름">
          <div className="flex items-center gap-1">
            <span className="text-[11px] text-gray-600 truncate flex-1">
              {image?.binaryItemIdRef ?? "-"}
            </span>
            <button
              disabled={!doc || isInserting}
              onClick={() => fileInputRef.current?.click()}
              className="h-6 px-2 text-[10px] border border-gray-300 rounded bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
            >
              {isInserting ? "삽입 중…" : "그림 삽입"}
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
              value={scaleX}
              disabled={!hasImage}
              onChange={(e) => {
                const v = Number(e.target.value);
                setScaleX(v);
                if (keepAspect) setScaleY(v);
              }}
              onBlur={applyScale}
              onKeyDown={(e) => { if (e.key === "Enter") applyScale(); }}
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
              value={scaleY}
              disabled={!hasImage}
              onChange={(e) => {
                const v = Number(e.target.value);
                setScaleY(v);
                if (keepAspect) setScaleX(v);
              }}
              onBlur={applyScale}
              onKeyDown={(e) => { if (e.key === "Enter") applyScale(); }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">%</span>
          </div>
        </SidebarField>
        <label className="flex items-center gap-2 text-[11px] text-gray-600 mt-1">
          <input
            type="checkbox"
            checked={keepAspect}
            onChange={(e) => setKeepAspect(e.target.checked)}
            className="w-3 h-3"
          />
          가로 세로 같은 비율 유지
        </label>
      </SidebarSection>

      <SidebarSection title="자르기" defaultOpen={false}>
        <SidebarField label="왼쪽">
          <div className="flex items-center gap-1">
            <input type="number" step="0.1" min={0} disabled={!hasImage} value={cropLeft}
              onChange={(e) => setCropLeft(Number(e.target.value))}
              onBlur={applyCrop}
              onKeyDown={(e) => { if (e.key === "Enter") applyCrop(); }}
              className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="오른쪽">
          <div className="flex items-center gap-1">
            <input type="number" step="0.1" min={0} disabled={!hasImage} value={cropRight}
              onChange={(e) => setCropRight(Number(e.target.value))}
              onBlur={applyCrop}
              onKeyDown={(e) => { if (e.key === "Enter") applyCrop(); }}
              className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="위쪽">
          <div className="flex items-center gap-1">
            <input type="number" step="0.1" min={0} disabled={!hasImage} value={cropTop}
              onChange={(e) => setCropTop(Number(e.target.value))}
              onBlur={applyCrop}
              onKeyDown={(e) => { if (e.key === "Enter") applyCrop(); }}
              className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
        <SidebarField label="아래쪽">
          <div className="flex items-center gap-1">
            <input type="number" step="0.1" min={0} disabled={!hasImage} value={cropBottom}
              onChange={(e) => setCropBottom(Number(e.target.value))}
              onBlur={applyCrop}
              onKeyDown={(e) => { if (e.key === "Enter") applyCrop(); }}
              className={inputClass} />
            <span className="text-[10px] text-gray-400 flex-shrink-0">mm</span>
          </div>
        </SidebarField>
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
          <select
            disabled={!hasImage}
            value={effect}
            onChange={(e) => {
              setEffect(e.target.value);
              setImageAdjustment({ effect: e.target.value });
            }}
            className={inputClass}
          >
            <option value="REAL_PIC">효과 없음</option>
            <option value="GRAY_SCALE">흑백</option>
            <option value="BLACK_WHITE">흑백(고대비)</option>
          </select>
        </SidebarField>
        <SidebarField label="투명도">
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={0}
              max={100}
              disabled={!hasImage}
              value={Math.round((Math.max(0, Math.min(255, alpha)) / 255) * 100)}
              onChange={(e) => {
                const percent = Math.max(0, Math.min(100, Number(e.target.value)));
                setAlpha(Math.round((percent / 100) * 255));
              }}
              onBlur={applyAdjustment}
              onKeyDown={(e) => { if (e.key === "Enter") applyAdjustment(); }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">%</span>
          </div>
        </SidebarField>
        <SidebarField label="밝기">
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={-100}
              max={100}
              disabled={!hasImage}
              value={brightness}
              onChange={(e) => setBrightness(Number(e.target.value))}
              onBlur={applyAdjustment}
              onKeyDown={(e) => { if (e.key === "Enter") applyAdjustment(); }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">%</span>
          </div>
        </SidebarField>
        <SidebarField label="대비">
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={-100}
              max={100}
              disabled={!hasImage}
              value={contrast}
              onChange={(e) => setContrast(Number(e.target.value))}
              onBlur={applyAdjustment}
              onKeyDown={(e) => { if (e.key === "Enter") applyAdjustment(); }}
              className={inputClass}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">%</span>
          </div>
        </SidebarField>
        <div className="mt-2 space-y-1">
          <label className="flex items-center gap-2 text-[11px] text-gray-600">
            <input
              type="checkbox"
              disabled={!hasImage}
              checked={alpha > 0}
              onChange={(e) => {
                if (!hasImage) return;
                const nextAlpha = e.target.checked ? 128 : 0;
                setAlpha(nextAlpha);
                setImageAdjustment({ alpha: nextAlpha });
              }}
              className="w-3 h-3"
            />
            워터마크 효과
          </label>
          <label className="flex items-center gap-2 text-[11px] text-gray-600">
            <input
              type="checkbox"
              disabled={!hasImage}
              checked={effect === "BLACK_WHITE"}
              onChange={(e) => {
                if (!hasImage) return;
                const nextEffect = e.target.checked ? "BLACK_WHITE" : "REAL_PIC";
                setEffect(nextEffect);
                setImageAdjustment({ effect: nextEffect });
              }}
              className="w-3 h-3"
            />
            그림 반전
          </label>
        </div>
      </SidebarSection>
    </div>
  );
}
