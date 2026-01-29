"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useEditorStore } from "@/lib/store";

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
    const blob = new Blob([data], { type: mediaType });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve({ width: 100, height: 100 });
    };
    img.src = url;
  });
}

// ── Menu data types ──────────────────────────────────────────────────────────

interface MenuItem {
  label: string;
  shortcut?: string;
  disabled?: boolean;
  dividerAfter?: boolean;
  action?: () => void;
}

interface Menu {
  label: string;
  items: MenuItem[];
}

// ── MenuBar component ────────────────────────────────────────────────────────

export function MenuBar() {
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const zoomLevel = useEditorStore((s) => s.uiState.zoomLevel);
  const [openMenu, setOpenMenu] = useState<number | null>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const disabled = !doc;

  const handleFileOpen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const buffer = await file.arrayBuffer();
      await useEditorStore.getState().openDocument(new Uint8Array(buffer));
    } catch (err) {
      console.error("Failed to open file:", err);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleImageSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const buffer = await file.arrayBuffer();
      const data = new Uint8Array(buffer);
      const mediaType = getMediaType(file);
      const dims = await getImageDimensions(data, mediaType);
      const maxWidth = 150;
      const scale = dims.width * PX_TO_MM > maxWidth ? maxWidth / (dims.width * PX_TO_MM) : 1;
      const widthMm = dims.width * PX_TO_MM * scale;
      const heightMm = dims.height * PX_TO_MM * scale;
      useEditorStore.getState().insertImage(data, mediaType, widthMm, heightMm);
    } catch (err) {
      console.error("Failed to insert image:", err);
    } finally {
      if (imageInputRef.current) imageInputRef.current.value = "";
    }
  };

  // Close menu on outside click
  useEffect(() => {
    if (openMenu === null) return;
    const handler = (e: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(e.target as Node)) {
        setOpenMenu(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [openMenu]);

  // Close on Escape
  useEffect(() => {
    if (openMenu === null) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenMenu(null);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [openMenu]);

  const store = useEditorStore.getState;

  const menus: Menu[] = [
    {
      label: "파일",
      items: [
        { label: "새 문서", shortcut: "Ctrl+N", action: () => store().newDocument() },
        { label: "불러오기...", shortcut: "Ctrl+O", action: () => fileInputRef.current?.click() },
        { label: "템플릿 관리...", action: () => store().openTemplateDialog(), dividerAfter: true },
        { label: "저장", shortcut: "Ctrl+S", disabled, action: () => store().openSaveDialog() },
        { label: "다른 이름으로 저장...", disabled, action: () => store().openSaveDialog(), dividerAfter: true },
        { label: "문서 정보", disabled: true },
        { label: "PDF로 내보내기", disabled, action: () => store().exportPDF(), dividerAfter: true },
        { label: "인쇄...", shortcut: "Ctrl+P", disabled, action: () => store().printDocument() },
      ],
    },
    {
      label: "편집",
      items: [
        { label: "실행 취소", shortcut: "Ctrl+Z", disabled, action: () => store().undo() },
        { label: "다시 실행", shortcut: "Ctrl+Y", disabled, action: () => store().redo(), dividerAfter: true },
        { label: "오려두기", shortcut: "Ctrl+X", action: () => document.execCommand("cut") },
        { label: "복사", shortcut: "Ctrl+C", action: () => document.execCommand("copy") },
        { label: "붙이기", shortcut: "Ctrl+V", action: () => document.execCommand("paste"), dividerAfter: true },
        { label: "모두 선택", shortcut: "Ctrl+A", action: () => document.execCommand("selectAll") },
        { label: "찾기", shortcut: "Ctrl+F", disabled, action: () => store().openFindReplaceDialog() },
        { label: "찾아 바꾸기", shortcut: "Ctrl+H", disabled, action: () => store().openFindReplaceDialog() },
      ],
    },
    {
      label: "보기",
      items: [
        { label: "서식 사이드바", action: () => store().toggleSidebar() },
        { label: "눈금자", disabled: true, dividerAfter: true },
        { label: `확대 (${zoomLevel}%)`, shortcut: "Ctrl++", action: () => store().zoomIn() },
        { label: "축소", shortcut: "Ctrl+-", action: () => store().zoomOut() },
        { label: "100%", action: () => store().setZoom(100) },
        { label: "전체 화면", shortcut: "F11", disabled: true },
      ],
    },
    {
      label: "입력",
      items: [
        { label: "표...", disabled: disabled || !selection, action: () => { /* handled via InsertGroup dialog */ } },
        { label: "그림...", disabled, action: () => imageInputRef.current?.click() },
        { label: "도형...", disabled, action: () => store().openShapeDialog() },
        { label: "차트", disabled: true, dividerAfter: true },
        { label: "문자표...", shortcut: "⌃F10", disabled, action: () => store().openCharMapDialog(), dividerAfter: true },
        { label: "각주", shortcut: "Ctrl+N,N", disabled, action: () => store().insertFootnote() },
        { label: "미주", shortcut: "Ctrl+N,E", disabled, action: () => store().insertEndnote(), dividerAfter: true },
        { label: "머리말/꼬리말...", disabled, action: () => store().openHeaderFooterDialog() },
        { label: "쪽 번호...", disabled: true, dividerAfter: true },
        { label: "단 나누기", disabled: disabled || !selection, action: () => store().insertColumnBreak() },
        { label: "쪽 나누기", disabled: disabled || !selection, action: () => store().insertPageBreak() },
      ],
    },
    {
      label: "서식",
      items: [
        { label: "글자 모양...", shortcut: "⌘L", disabled, action: () => store().openCharFormatDialog() },
        { label: "문단 모양...", shortcut: "⌘T", disabled, action: () => store().openParaFormatDialog(), dividerAfter: true },
        { label: "문단 첫 글자 장식...", disabled: true },
        { label: "문단 번호 모양...", disabled, action: () => store().openBulletNumberDialog() },
        { label: "문단 번호 적용/해제", disabled: true },
        { label: "글머리표 적용/해제", shortcut: "⌃⇧⌫", disabled, action: () => store().openBulletNumberDialog(), dividerAfter: true },
        { label: "개요 번호 모양...", disabled, action: () => store().openOutlineDialog() },
        { label: "개요 적용/해제", disabled, action: () => store().openOutlineDialog() },
        { label: "한 수준 증가", shortcut: "⌃-", disabled, action: () => store().applyOutlineLevel(Math.min(7, (store().selection?.paragraphIndex ?? 0) + 1)) },
        { label: "한 수준 감소", shortcut: "⌃+", disabled, action: () => store().applyOutlineLevel(Math.max(0, (store().selection?.paragraphIndex ?? 1) - 1)), dividerAfter: true },
        { label: "스타일...", shortcut: "F6", disabled, action: () => store().openStyleDialog() },
      ],
    },
    {
      label: "쪽",
      items: [
        { label: "편집 용지...", disabled, action: () => { store().setSidebarTab("page"); if (!store().uiState.sidebarOpen) store().toggleSidebar(); } },
        { label: "쪽 번호 매기기...", disabled, action: () => store().openPageNumberDialog(), dividerAfter: true },
        { label: "머리말...", disabled, action: () => store().openHeaderFooterDialog() },
        { label: "꼬리말...", disabled, action: () => store().openHeaderFooterDialog(), dividerAfter: true },
        { label: "바탕쪽", disabled: true },
        { label: "워터마크...", disabled, action: () => store().setWatermarkText("DRAFT") },
        { label: "워터마크 제거", disabled, action: () => store().setWatermarkText("") },
      ],
    },
    {
      label: "도구",
      items: [
        { label: "맞춤법 검사...", shortcut: "F8", disabled: true },
        { label: "자동 고침...", action: () => store().openAutoCorrectDialog(), dividerAfter: true },
        { label: "글자 수 세기", disabled, action: () => store().openWordCountDialog() },
        { label: "매크로...", disabled: true },
        { label: "환경 설정...", disabled: true },
      ],
    },
    {
      label: "표",
      items: [
        { label: "표 속성...", disabled: disabled || selection?.tableIndex == null, action: () => { store().setSidebarTab("table"); if (!store().uiState.sidebarOpen) store().toggleSidebar(); } },
        { label: "셀 합치기", disabled: disabled || selection?.type !== "cell", action: () => store().mergeSelectedCells() },
        { label: "셀 나누기", disabled: disabled || selection?.type !== "cell", action: () => store().unmergeSelectedCells(), dividerAfter: true },
        { label: "줄 삽입 (위)", disabled: disabled || selection?.type !== "cell", action: () => store().insertTableRow("above") },
        { label: "줄 삽입 (아래)", disabled: disabled || selection?.type !== "cell", action: () => store().insertTableRow("below") },
        { label: "칸 삽입 (왼쪽)", disabled: disabled || selection?.type !== "cell", action: () => store().insertTableColumn("left") },
        { label: "칸 삽입 (오른쪽)", disabled: disabled || selection?.type !== "cell", action: () => store().insertTableColumn("right"), dividerAfter: true },
        { label: "줄 삭제", disabled: disabled || selection?.type !== "cell", action: () => store().deleteTableRow() },
        { label: "칸 삭제", disabled: disabled || selection?.type !== "cell", action: () => store().deleteTableColumn() },
        { label: "표 삭제", disabled: disabled || selection?.tableIndex == null, action: () => store().deleteTable() },
      ],
    },
  ];

  const handleMenuClick = useCallback((menuIdx: number) => {
    setOpenMenu((prev) => (prev === menuIdx ? null : menuIdx));
  }, []);

  const handleItemClick = useCallback((item: MenuItem) => {
    if (item.disabled) return;
    item.action?.();
    setOpenMenu(null);
  }, []);

  return (
    <div ref={barRef} className="flex items-center bg-gray-50 border-b border-gray-200 text-xs select-none relative z-50">
      <input
        ref={imageInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/bmp"
        className="hidden"
        onChange={handleImageSelect}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept=".hwpx"
        className="hidden"
        onChange={handleFileOpen}
      />
      {menus.map((menu, mIdx) => (
        <div key={menu.label} className="relative">
          <button
            onClick={() => handleMenuClick(mIdx)}
            onMouseEnter={() => { if (openMenu !== null) setOpenMenu(mIdx); }}
            className={`px-3 py-1.5 transition-colors ${
              openMenu === mIdx
                ? "bg-blue-100 text-blue-700"
                : "text-gray-700 hover:bg-gray-100"
            }`}
          >
            {menu.label}
          </button>
          {openMenu === mIdx && (
            <div className="absolute left-0 top-full bg-white border border-gray-200 shadow-lg rounded-b min-w-[220px] py-1 z-50">
              {menu.items.map((item, iIdx) => (
                <div key={iIdx}>
                  <button
                    onClick={() => handleItemClick(item)}
                    disabled={item.disabled}
                    className={`w-full text-left px-4 py-1.5 flex items-center justify-between gap-4 ${
                      item.disabled
                        ? "text-gray-300 cursor-default"
                        : "text-gray-700 hover:bg-blue-50 hover:text-blue-700"
                    }`}
                  >
                    <span>{item.label}</span>
                    {item.shortcut && (
                      <span className="text-[10px] text-gray-400 ml-4 flex-shrink-0">{item.shortcut}</span>
                    )}
                  </button>
                  {item.dividerAfter && <div className="border-t border-gray-100 my-0.5" />}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
