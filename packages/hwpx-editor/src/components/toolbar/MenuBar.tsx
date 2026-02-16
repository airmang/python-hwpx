"use client";

import { useState, useRef, useEffect, useCallback, type ReactNode } from "react";
import { useEditorStore } from "@/lib/store";

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

interface MenuBarProps {
  leadingContent?: ReactNode;
}

export function MenuBar({ leadingContent }: MenuBarProps) {
  const doc = useEditorStore((s) => s.doc);
  const selection = useEditorStore((s) => s.selection);
  const showRuler = useEditorStore((s) => s.uiState.showRuler);
  const toggleRuler = useEditorStore((s) => s.toggleRuler);
  const [openMenu, setOpenMenu] = useState<number | null>(null);
  const barRef = useRef<HTMLDivElement>(null);

  const disabled = !doc;

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

  const getCurrentParagraph = () => {
    const s = store();
    const docRef = s.doc;
    const sel = s.selection;
    if (!docRef || !sel) return null;
    const section = docRef.sections[sel.sectionIndex];
    const para = section?.paragraphs[sel.paragraphIndex];
    if (!para) return null;
    return para;
  };

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
      }
      await document.documentElement.requestFullscreen();
    } catch (error) {
      console.error("toggleFullscreen failed:", error);
    }
  };

  const showDocumentInfo = () => {
    const s = store();
    const docRef = s.doc;
    if (!docRef) return;
    const sectionCount = docRef.sections.length;
    const paragraphCount = docRef.sections.reduce((sum, section) => sum + section.paragraphs.length, 0);
    const textLength = (docRef.text ?? "").length;
    const documentId = s.serverDocumentId ?? "로컬 문서";
    window.alert(
      [
        "문서 정보",
        `- 섹션: ${sectionCount}`,
        `- 문단: ${paragraphCount}`,
        `- 글자 수(공백 포함): ${textLength}`,
        `- 문서 ID: ${documentId}`,
      ].join("\n"),
    );
  };

  const showBridgeNotice = (feature: string, target: string) => {
    window.alert(`${feature} 전용 UI는 준비 중입니다.\n현재는 ${target} 화면으로 연결합니다.`);
  };

  const handleSelectAll = () => {
    const s = store();
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const editable = active?.isContentEditable
      ? active
      : active?.closest<HTMLElement>("[contenteditable='true']") ?? null;

    const selectContents = (el: HTMLElement) => {
      const selection = window.getSelection();
      if (!selection) return;
      const range = document.createRange();
      range.selectNodeContents(el);
      selection.removeAllRanges();
      selection.addRange(range);
    };

    if (editable) {
      selectContents(editable);
      if (editable.dataset.hwpxParagraph === "1") {
        const sectionIndex = Number(editable.dataset.sectionIndex);
        const paragraphIndex = Number(editable.dataset.paragraphIndex);
        if (Number.isFinite(sectionIndex) && Number.isFinite(paragraphIndex)) {
          const length = (editable.textContent ?? "").length;
          s.setSelection({
            sectionIndex,
            paragraphIndex,
            type: "paragraph",
            textStartOffset: 0,
            textEndOffset: length,
            cursorOffset: length,
          });
        }
      }
      return;
    }

    if (s.selection?.type === "paragraph") {
      s.selectParagraphAll();
      return;
    }

    const firstParagraph = document.querySelector<HTMLElement>(
      "[data-page] [data-hwpx-paragraph='1'][contenteditable='true']",
    );
    if (!firstParagraph) return;
    firstParagraph.focus();
    selectContents(firstParagraph);
  };

  const menus: Menu[] = [
    {
      label: "파일",
      items: [
        { label: "새 문서", shortcut: "Ctrl+Shift+N", disabled: false, action: () => { void store().newDocument(); } },
        { label: "불러오기…", shortcut: "Ctrl+Shift+O", disabled: false, action: () => store().openFile(), dividerAfter: true },
        { label: "저장", shortcut: "Ctrl+Shift+S", disabled, action: () => store().openSaveDialog() },
        { label: "다른 이름으로 저장…", disabled, action: () => store().openSaveDialog(), dividerAfter: true },
        { label: "문서 정보", disabled, action: () => showDocumentInfo() },
        { label: "인쇄…", shortcut: "Ctrl+Shift+P", disabled, action: () => store().printDocument() },
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
        { label: "클립보드/스니펫", shortcut: "Ctrl+Shift+V", disabled, action: () => store().openClipboardDialog(), dividerAfter: true },
        { label: "모두 선택", shortcut: "Ctrl+A", action: () => handleSelectAll() },
        { label: "찾기", shortcut: "Ctrl+Shift+F", disabled, action: () => store().openFindReplaceDialog() },
        { label: "찾아 바꾸기", shortcut: "Ctrl+Shift+H", disabled, action: () => store().openFindReplaceDialog() },
      ],
    },
    {
      label: "보기",
      items: [
        { label: "서식 사이드바", action: () => store().toggleSidebar() },
        { label: showRuler ? "눈금자 숨기기" : "눈금자 표시", disabled: false, action: () => toggleRuler(), dividerAfter: true },
        { label: "확대", shortcut: "Ctrl++", disabled: false, action: () => store().zoomIn() },
        { label: "축소", shortcut: "Ctrl+-", disabled: false, action: () => store().zoomOut() },
        { label: "전체 화면", shortcut: "F11", disabled: false, action: () => { void toggleFullscreen(); } },
      ],
    },
    {
      label: "입력",
      items: [
        {
          label: "표…",
          disabled: disabled || !selection,
          action: () => window.dispatchEvent(new CustomEvent("hwpx-open-insert-table-dialog")),
        },
        {
          label: "그림…",
          disabled,
          action: () => window.dispatchEvent(new CustomEvent("hwpx-open-insert-image-file")),
        },
        { label: "도형", disabled, action: () => store().openShapeDialog() },
        { label: "캡션/목차…", shortcut: "Ctrl+Alt+C", disabled, action: () => store().openCaptionDialog() },
        { label: "차트", disabled, action: () => store().insertChart(), dividerAfter: true },
        { label: "문자표…", shortcut: "Alt+Shift+M", disabled, action: () => store().openCharMapDialog(), dividerAfter: true },
        { label: "각주", shortcut: "Ctrl+N,N", disabled, action: () => store().insertFootnote() },
        { label: "미주", shortcut: "Ctrl+N,E", disabled, action: () => store().insertEndnote(), dividerAfter: true },
        { label: "머리말/꼬리말…", disabled, action: () => store().openHeaderFooterDialog() },
        { label: "쪽 번호…", disabled, action: () => store().openPageNumberDialog(), dividerAfter: true },
        { label: "단 나누기", disabled: disabled || !selection, action: () => store().insertColumnBreak() },
        { label: "쪽 나누기", disabled: disabled || !selection, action: () => store().insertPageBreak() },
      ],
    },
    {
      label: "서식",
      items: [
        { label: "글자 모양…", shortcut: "Alt+Shift+L", disabled, action: () => store().openCharFormatDialog() },
        { label: "문단 모양…", shortcut: "Alt+Shift+T", disabled, action: () => store().openParaFormatDialog(), dividerAfter: true },
        {
          label: "문단 첫 글자 장식…",
          disabled: disabled || !selection,
          action: () => {
            showBridgeNotice("문단 첫 글자 장식", "글자 모양");
            store().openCharFormatDialog();
          },
        },
        { label: "문단 번호 모양…", disabled, action: () => store().openBulletNumberDialog() },
        {
          label: "문단 번호 적용/해제",
          disabled: disabled || !selection,
          action: () => {
            const s = store();
            const para = getCurrentParagraph();
            if (!para) return;
            if ((para.outlineLevel ?? 0) > 0 && !para.bulletIdRef) {
              s.removeBulletNumbering();
            } else {
              s.applyNumbering(1);
            }
          },
        },
        { label: "글머리표 적용/해제", shortcut: "⌃⇧⌫", disabled, action: () => store().openBulletNumberDialog(), dividerAfter: true },
        { label: "개요 번호 모양…", disabled, action: () => store().openOutlineDialog() },
        {
          label: "개요 적용/해제",
          disabled: disabled || !selection,
          action: () => {
            const s = store();
            const para = getCurrentParagraph();
            if (!para) return;
            const level = para.outlineLevel ?? 0;
            s.applyOutlineLevel(level > 0 ? 0 : 1);
          },
        },
        {
          label: "한 수준 증가",
          shortcut: "⌃-",
          disabled: disabled || !selection,
          action: () => {
            const s = store();
            const para = getCurrentParagraph();
            if (!para) return;
            const level = para.outlineLevel ?? 0;
            s.applyOutlineLevel(Math.max(1, Math.min(9, level + 1)));
          },
        },
        {
          label: "한 수준 감소",
          shortcut: "⌃+",
          disabled: disabled || !selection,
          action: () => {
            const s = store();
            const para = getCurrentParagraph();
            if (!para) return;
            const level = para.outlineLevel ?? 0;
            s.applyOutlineLevel(level <= 1 ? 0 : level - 1);
          },
          dividerAfter: true,
        },
        { label: "스타일…", shortcut: "F6", disabled, action: () => store().openStyleDialog() },
      ],
    },
    {
      label: "쪽",
      items: [
        { label: "편집 용지…", disabled, action: () => { store().setSidebarTab("page"); if (!store().uiState.sidebarOpen) store().toggleSidebar(); } },
        { label: "쪽 번호 매기기…", disabled, action: () => store().openPageNumberDialog(), dividerAfter: true },
        { label: "머리말…", disabled, action: () => store().openHeaderFooterDialog() },
        { label: "꼬리말…", disabled, action: () => store().openHeaderFooterDialog(), dividerAfter: true },
        {
          label: "바탕쪽",
          disabled,
          action: () => {
            showBridgeNotice("바탕쪽", "머리말/꼬리말");
            store().openHeaderFooterDialog();
          },
        },
        { label: "워터마크…", disabled, action: () => store().setWatermarkText("DRAFT") },
        { label: "워터마크 제거", disabled, action: () => store().setWatermarkText("") },
      ],
    },
    {
      label: "도구",
      items: [
        {
          label: "맞춤법 검사…",
          shortcut: "F8",
          disabled,
          action: () => {
            showBridgeNotice("맞춤법 검사", "자동 고침");
            store().openAutoCorrectDialog();
          },
        },
        { label: "자동 고침…", disabled: false, action: () => store().openAutoCorrectDialog(), dividerAfter: true },
        { label: "글자 수 세기", disabled, action: () => store().openWordCountDialog() },
        {
          label: "매크로…",
          disabled,
          action: () => {
            showBridgeNotice("매크로", "서식 사이드바");
            if (!store().uiState.sidebarOpen) {
              store().toggleSidebar();
            }
          },
        },
        {
          label: "환경 설정…",
          disabled,
          action: () => {
            showBridgeNotice("환경 설정", "편집 용지");
            store().setSidebarTab("page");
            if (!store().uiState.sidebarOpen) {
              store().toggleSidebar();
            }
          },
        },
      ],
    },
    {
      label: "표",
      items: (() => {
        const noCell = disabled || selection?.tableIndex == null;
        const hasRange = !disabled && selection?.endRow != null && selection?.endCol != null;
        const hasSelection = !disabled && selection != null;
        return [
          {
            label: "표 삽입 (3x3)",
            disabled: !hasSelection,
            action: () => {
              const s = store();
              const sel = s.selection;
              if (!sel) return;
              s.addTable(sel.sectionIndex, sel.paragraphIndex, 3, 3);
            },
            dividerAfter: true,
          },
          { label: "표 속성…", disabled: noCell, action: () => { store().setSidebarTab("table"); if (!store().uiState.sidebarOpen) store().toggleSidebar(); } },
          { label: "셀 합치기", disabled: !hasRange, action: () => store().mergeTableCells() },
          { label: "셀 나누기", disabled: noCell, action: () => store().splitTableCell(), dividerAfter: true },
          { label: "줄 삽입 (위)", disabled: noCell, action: () => store().insertTableRow("above") },
          { label: "줄 삽입 (아래)", disabled: noCell, action: () => store().insertTableRow("below") },
          { label: "칸 삽입 (왼쪽)", disabled: noCell, action: () => store().insertTableColumn("left") },
          { label: "칸 삽입 (오른쪽)", disabled: noCell, action: () => store().insertTableColumn("right"), dividerAfter: true },
          { label: "줄 삭제", disabled: noCell, action: () => store().deleteTableRow() },
          { label: "칸 삭제", disabled: noCell, action: () => store().deleteTableColumn() },
          { label: "표 삭제", disabled: noCell, action: () => store().deleteTable() },
        ];
      })(),
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
    <div ref={barRef} className="flex items-center bg-gray-50 border-b border-gray-200 text-sm select-none relative z-50 min-h-[42px]">
      {leadingContent ? (
        <>
          <div className="flex items-center gap-1.5 px-2 py-1 overflow-x-auto whitespace-nowrap">
            {leadingContent}
          </div>
          <div className="h-6 w-px bg-gray-200 mx-1" />
        </>
      ) : null}
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
                    className={`w-full text-left px-4 py-2 flex items-center justify-between gap-4 ${
                      item.disabled
                        ? "text-gray-300 cursor-default"
                        : "text-gray-700 hover:bg-blue-50 hover:text-blue-700"
                    }`}
                  >
                    <span>{item.label}</span>
                    {item.shortcut && (
                      <span className="text-[11px] text-gray-400 ml-4 flex-shrink-0">{item.shortcut}</span>
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
