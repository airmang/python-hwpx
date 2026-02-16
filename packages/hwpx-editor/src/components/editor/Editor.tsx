"use client";

import { useEffect, useRef, useCallback, useState, type ReactNode } from "react";
import { HwpxDocument } from "@ubermensch1218/hwpxcore";
import { useEditorStore } from "@/lib/store";
import { ensureSkeletonLoaded } from "@/lib/skeleton-loader";
import { runFeatureScenario } from "@/lib/feature-runner";
import { applyRetypeDump, type RetypeDump } from "@/lib/retype-dump";
import { MenuBar } from "../toolbar/MenuBar";
import { RibbonToolbar } from "../toolbar/RibbonToolbar";
import { SecondaryToolbar } from "../toolbar/SecondaryToolbar";
import { HorizontalRuler } from "../ruler/HorizontalRuler";
import { FormatSidebar } from "../sidebar/FormatSidebar";
import { PageView } from "./PageView";
import { SaveDialog } from "./SaveDialog";
import { FileUpload } from "../upload/FileUpload";
import { NewDocumentButton } from "../upload/NewDocumentButton";
import { CharFormatDialog } from "../dialog/CharFormatDialog";
import { ParaFormatDialog } from "../dialog/ParaFormatDialog";
import { BulletNumberDialog } from "../dialog/BulletNumberDialog";
import { CharMapDialog } from "../dialog/CharMapDialog";
import { TemplateDialog } from "../dialog/TemplateDialog";
import { HeaderFooterDialog } from "../dialog/HeaderFooterDialog";
import { FindReplaceDialog } from "../dialog/FindReplaceDialog";
import { ClipboardDialog } from "../dialog/ClipboardDialog";
import { WordCountDialog } from "../dialog/WordCountDialog";
import { PageNumberDialog } from "../dialog/PageNumberDialog";
import { StyleDialog } from "../dialog/StyleDialog";
import { AutoCorrectDialog } from "../dialog/AutoCorrectDialog";
import { OutlineDialog } from "../dialog/OutlineDialog";
import { ShapeDialog } from "../dialog/ShapeDialog";
import { TocDialog } from "../dialog/TocDialog";
import { CaptionDialog } from "../dialog/CaptionDialog";
import { PanelRight } from "lucide-react";
import { redirectToLoginFromEditor } from "@/lib/auth-redirect";

const MAX_OPEN_FILE_SIZE_BYTES = 25 * 1024 * 1024;

function isHwpxFilename(name: string): boolean {
  return name.toLowerCase().endsWith(".hwpx");
}

function isZipLikePayload(data: Uint8Array): boolean {
  if (data.length < 4) return false;
  return (
    data[0] === 0x50 &&
    data[1] === 0x4b &&
    (data[2] === 0x03 || data[2] === 0x05 || data[2] === 0x07) &&
    (data[3] === 0x04 || data[3] === 0x06 || data[3] === 0x08)
  );
}

declare global {
  interface Window {
    __HWPX_TEST_BRIDGE?: {
      runFeature: (code: string) => Promise<void>;
      retypeFromDump: (dump: RetypeDump) => Promise<void>;
      exportHwpx: () => Promise<number[]>;
      openHwpx: (bytes: number[]) => Promise<void>;
      findFirstTableRef: () => { sectionIndex: number; paragraphIndex: number; tableIndex: number; rowCount: number; colCount: number } | null;
      updateCellText: (args: {
        sectionIndex: number;
        paragraphIndex: number;
        tableIndex: number;
        row: number;
        col: number;
        text: string;
      }) => void;
      getTableRangeTextStyles: (range: {
        sectionIndex: number;
        paragraphIndex: number;
        tableIndex: number;
        row: number;
        col: number;
        endRow: number;
        endCol: number;
      }) => Array<{
        row: number;
        col: number;
        fontFamily: string | null;
        fontSize: number | null;
        textColor: string | null;
      }>;
      setTableSelectionRange: (range: {
        sectionIndex: number;
        paragraphIndex: number;
        tableIndex: number;
        row: number;
        col: number;
        endRow: number;
        endCol: number;
      }) => void;
      getStateSnapshot: () => {
        revision: number;
        hasDocument: boolean;
        selection: unknown;
        nestedTableFocus: unknown;
        sidebarOpen: boolean;
        sidebarTab: string;
        error: string | null;
      };
      getTableDebug: () => {
        rowCount: number;
        colCount: number;
        widthHwp: number;
        heightHwp: number;
        outMargin: { top: number; bottom: number; left: number; right: number } | null;
        inMargin: { top: number; bottom: number; left: number; right: number } | null;
        anchorCellCount: number;
        firstCellStyle: {
          borderLeftType: string | null;
          borderRightType: string | null;
          borderTopType: string | null;
          borderBottomType: string | null;
          backgroundColor: string | null;
        } | null;
        selectedCellStyle: {
          borderLeftType: string | null;
          borderRightType: string | null;
          borderTopType: string | null;
          borderBottomType: string | null;
          backgroundColor: string | null;
        } | null;
        selectedCellTextStyle: {
          fontFamily: string | null;
          fontSize: number | null;
          textColor: string | null;
        } | null;
        selectedCellNestedTableCount: number;
      };
      getPageDebug: () => {
        pageWidthPx: number;
        marginLeftPx: number;
        marginRightPx: number;
      };
      getImageDebug: () => {
        docItems: Array<{
          paragraphIndex: number;
          imageIndex: number;
          sizeProtected: boolean;
          locked: boolean;
          horzRelTo: string;
          vertRelTo: string;
        }>;
        vmItems: Array<{
          paragraphIndex: number;
          imageIndex: number;
          sizeProtected: boolean;
          locked: boolean;
          horzRelTo: string;
          vertRelTo: string;
        }>;
      };
    };
  }
}

interface EditorProps {
  leftPanel?: ReactNode;
  rightPanel?: ReactNode;
  topMenuLeading?: ReactNode;
}

export function Editor(props: EditorProps) {
  return <EditorWithPanels {...props} />;
}

export function EditorWithPanels({ leftPanel, rightPanel, topMenuLeading }: EditorProps = {}) {
  const doc = useEditorStore((s) => s.doc);
  const loading = useEditorStore((s) => s.loading);
  const error = useEditorStore((s) => s.error);
  const uiState = useEditorStore((s) => s.uiState);
  const toggleSidebar = useEditorStore((s) => s.toggleSidebar);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [bootstrapping, setBootstrapping] = useState(true);

  // Always start as a fresh document on mount.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const store = useEditorStore.getState();
        const params = new URLSearchParams(window.location.search);
        const documentId = params.get("documentId")?.trim();

        if (documentId) {
          const response = await fetch(
            `/api/hwpx-documents/${encodeURIComponent(documentId)}/download`,
            { cache: "no-store" },
          );

          if (!response.ok) {
            if (response.status === 401 && redirectToLoginFromEditor()) {
              return;
            }
            const fallback =
              response.status === 401
                ? "로그인 후 내 드라이브 문서를 열 수 있습니다."
                : response.status === 404
                  ? "내 드라이브에서 문서를 찾을 수 없습니다."
                  : "서버 문서를 여는 데 실패했습니다.";
            await ensureSkeletonLoaded();
            await store.newDocument();
            store.setError(fallback);
          } else {
            const bytes = new Uint8Array(await response.arrayBuffer());
            await store.openDocument(bytes);
            useEditorStore.setState({ serverDocumentId: documentId, error: null });
          }
        } else {
          await ensureSkeletonLoaded();
          await store.newDocument();
        }
      } catch (e) {
        console.error("Editor bootstrap failed:", e);
        try {
          const store = useEditorStore.getState();
          await ensureSkeletonLoaded();
          await store.newDocument();
        } catch {
          // If even fallback creation fails, keep existing error path.
        }
      } finally {
        if (alive) setBootstrapping(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // Handle file open from hidden input
  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const store = useEditorStore.getState();
    store.setLoading(true);
    store.setError(null);
    try {
      if (!isHwpxFilename(file.name)) {
        store.setError("HWPX 파일만 업로드할 수 있습니다.");
        return;
      }
      if (file.size > MAX_OPEN_FILE_SIZE_BYTES) {
        store.setError("파일 크기 제한(25MB)을 초과했습니다.");
        return;
      }
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      if (!isZipLikePayload(bytes)) {
        store.setError("유효한 HWPX 파일이 아닙니다.");
        return;
      }
      const newDoc = await HwpxDocument.open(buffer);
      store.setDocument(newDoc);
    } catch (err) {
      console.error("Failed to open file:", err);
      store.setError("파일을 열 수 없습니다. HWPX 파일인지 확인하세요.");
    } finally {
      store.setLoading(false);
    }
    e.target.value = "";
  }, []);

  // Listen for hwpx-open-file custom event
  useEffect(() => {
    const handler = () => fileInputRef.current?.click();
    window.addEventListener("hwpx-open-file", handler);
    return () => window.removeEventListener("hwpx-open-file", handler);
  }, []);

  // Ensure caret lands on the first paragraph when a fresh document opens.
  useEffect(() => {
    if (!doc || bootstrapping) return;
    const raf = window.requestAnimationFrame(() => {
      const firstEditable = document.querySelector<HTMLElement>("[data-page] [contenteditable]");
      if (!firstEditable) return;
      firstEditable.focus();
      const sel = window.getSelection();
      if (!sel) return;
      sel.selectAllChildren(firstEditable);
      sel.collapseToStart();
    });
    return () => window.cancelAnimationFrame(raf);
  }, [doc, bootstrapping]);

  // Expose a minimal bridge for autonomous feature-loop verification.
  useEffect(() => {
    window.__HWPX_TEST_BRIDGE = {
      runFeature: async (code: string) => {
        const store = useEditorStore.getState();
        await runFeatureScenario(store, code);
      },
      retypeFromDump: async (dump: RetypeDump) => {
        const store = useEditorStore.getState();
        await ensureSkeletonLoaded();
        await store.newDocument();
        // Zustand state snapshot won't reflect updates; re-read after newDocument().
        await applyRetypeDump(useEditorStore.getState(), dump);
      },
      exportHwpx: async () => {
        const store = useEditorStore.getState();
        if (!store.doc) return [];
        const bytes = await store.doc.save();
        return Array.from(bytes);
      },
      openHwpx: async (bytes) => {
        const store = useEditorStore.getState();
        await store.openDocument(new Uint8Array(bytes));
      },
      findFirstTableRef: () => {
        const store = useEditorStore.getState();
        const vm = store.viewModel;
        const sectionIndex = 0;
        const paragraphs = vm?.sections?.[sectionIndex]?.paragraphs ?? [];
        for (let pIdx = 0; pIdx < paragraphs.length; pIdx += 1) {
          const para = paragraphs[pIdx];
          if (!para) continue;
          if (para.tables.length > 0) {
            const tableIndex = 0;
            const table = para.tables[tableIndex];
            if (!table) continue;
            return {
              sectionIndex,
              paragraphIndex: pIdx,
              tableIndex,
              rowCount: table.rowCount,
              colCount: table.colCount,
            };
          }
        }
        return null;
      },
      updateCellText: (args) => {
        const store = useEditorStore.getState();
        store.updateCellText(
          args.sectionIndex,
          args.paragraphIndex,
          args.tableIndex,
          args.row,
          args.col,
          args.text,
        );
      },
      getTableRangeTextStyles: (range) => {
        const store = useEditorStore.getState();
        const vm = store.viewModel;
        const table = vm?.sections?.[range.sectionIndex]?.paragraphs?.[range.paragraphIndex]?.tables?.[range.tableIndex];
        if (!table) return [];
        const minRow = Math.min(range.row, range.endRow);
        const maxRow = Math.max(range.row, range.endRow);
        const minCol = Math.min(range.col, range.endCol);
        const maxCol = Math.max(range.col, range.endCol);
        const out: Array<{ row: number; col: number; fontFamily: string | null; fontSize: number | null; textColor: string | null }> = [];
        for (let r = minRow; r <= maxRow; r += 1) {
          for (let c = minCol; c <= maxCol; c += 1) {
            const cell = table.cells[r]?.[c];
            if (!cell?.isAnchor) continue;
            out.push({
              row: r,
              col: c,
              fontFamily: cell.fontFamily ?? null,
              fontSize: cell.fontSize ?? null,
              textColor: cell.textColor ?? null,
            });
          }
        }
        return out;
      },
      setTableSelectionRange: (range) => {
        const store = useEditorStore.getState();
        store.setSelection({
          sectionIndex: range.sectionIndex,
          paragraphIndex: range.paragraphIndex,
          type: "cell",
          tableIndex: range.tableIndex,
          row: range.row,
          col: range.col,
          endRow: range.endRow,
          endCol: range.endCol,
          objectType: "table",
        });
      },
      getStateSnapshot: () => {
        const store = useEditorStore.getState();
        return {
          revision: store.revision,
          hasDocument: Boolean(store.doc),
          selection: store.selection,
          nestedTableFocus: store.nestedTableFocus,
          sidebarOpen: store.uiState.sidebarOpen,
          sidebarTab: store.uiState.sidebarTab,
          error: store.error,
        };
      },
      getTableDebug: () => {
        const store = useEditorStore.getState();
        const sel = store.selection;
        const vm = store.viewModel;
        const sIdx = sel?.sectionIndex ?? 0;
        const pIdx = sel?.paragraphIndex ?? 0;
        const tIdx = sel?.tableIndex ?? 0;
        const table = vm?.sections[sIdx]?.paragraphs[pIdx]?.tables[tIdx];
        if (!table) {
          return {
            rowCount: 0,
            colCount: 0,
            widthHwp: 0,
            heightHwp: 0,
            outMargin: null,
            inMargin: null,
            anchorCellCount: 0,
            firstCellStyle: null,
            selectedCellStyle: null,
            selectedCellTextStyle: null,
            selectedCellNestedTableCount: 0,
          };
        }
        const anchorCellCount = table.cells.flat().filter((c) => c.isAnchor).length;
        const firstAnchor = table.cells.flat().find((c) => c.isAnchor);
        const selectedCell =
          sel?.row != null && sel?.col != null
            ? table.cells[sel.row]?.[sel.col]
            : null;
        const selectedDocCell =
          sel?.row != null && sel?.col != null
            ? store.doc?.sections?.[sIdx]?.paragraphs?.[pIdx]?.tables?.[tIdx]?.cell(sel.row, sel.col)
            : null;
        const countNestedTables = (cell: { element?: Element } | null | undefined): number => {
          const element = cell?.element;
          if (!element) return 0;
          const descendants = element.getElementsByTagName("*");
          let count = 0;
          for (let i = 0; i < descendants.length; i += 1) {
            const el = descendants.item(i);
            if (!el) continue;
            const local = el.localName || el.nodeName.split(":").pop() || "";
            if (local === "tbl") count += 1;
          }
          return count;
        };
        const toStyleDebug = (
          source: {
            borderLeft?: { type?: string } | null;
            borderRight?: { type?: string } | null;
            borderTop?: { type?: string } | null;
            borderBottom?: { type?: string } | null;
            backgroundColor?: string | null;
          } | null | undefined,
        ) =>
          source
            ? {
                borderLeftType: source.borderLeft?.type ?? null,
                borderRightType: source.borderRight?.type ?? null,
                borderTopType: source.borderTop?.type ?? null,
                borderBottomType: source.borderBottom?.type ?? null,
                backgroundColor: source.backgroundColor ?? null,
              }
            : null;
        return {
          rowCount: table.rowCount,
          colCount: table.colCount,
          widthHwp: table.widthHwp,
          heightHwp: table.heightHwp,
          outMargin: table.outMargin,
          inMargin: table.inMargin,
          anchorCellCount,
          firstCellStyle: toStyleDebug(firstAnchor?.style),
          selectedCellStyle: toStyleDebug(selectedCell?.style),
          selectedCellTextStyle: selectedCell
            ? {
                fontFamily: selectedCell.fontFamily ?? null,
                fontSize: selectedCell.fontSize ?? null,
                textColor: selectedCell.textColor ?? null,
              }
            : null,
          selectedCellNestedTableCount: countNestedTables(selectedDocCell),
        };
      },
      getPageDebug: () => {
        const store = useEditorStore.getState();
        const section = store.viewModel?.sections[0];
        if (!section) {
          return {
            pageWidthPx: 0,
            marginLeftPx: 0,
            marginRightPx: 0,
          };
        }
        return {
          pageWidthPx: section.pageWidthPx,
          marginLeftPx: section.marginLeftPx,
          marginRightPx: section.marginRightPx,
        };
      },
      getImageDebug: () => {
        const store = useEditorStore.getState();
        const docItems: Array<{
          paragraphIndex: number;
          imageIndex: number;
          sizeProtected: boolean;
          locked: boolean;
          horzRelTo: string;
          vertRelTo: string;
        }> = [];
        const vmItems: Array<{
          paragraphIndex: number;
          imageIndex: number;
          sizeProtected: boolean;
          locked: boolean;
          horzRelTo: string;
          vertRelTo: string;
        }> = [];

        const section = store.doc?.sections?.[0];
        if (section) {
          for (let pIdx = 0; pIdx < section.paragraphs.length; pIdx += 1) {
            const para = section.paragraphs[pIdx];
            if (!para) continue;
            for (let i = 0; i < para.pictures.length; i += 1) {
              const pos = para.getPicturePosition(i);
              docItems.push({
                paragraphIndex: pIdx,
                imageIndex: i,
                sizeProtected: para.isPictureSizeProtected(i),
                locked: para.getPictureLock(i),
                horzRelTo: pos.horzRelTo,
                vertRelTo: pos.vertRelTo,
              });
            }
          }
        }

        const sectionVm = store.viewModel?.sections?.[0];
        if (sectionVm) {
          for (let pIdx = 0; pIdx < sectionVm.paragraphs.length; pIdx += 1) {
            const paraVm = sectionVm.paragraphs[pIdx];
            if (!paraVm) continue;
            for (let i = 0; i < paraVm.images.length; i += 1) {
              const img = paraVm.images[i]!;
              vmItems.push({
                paragraphIndex: pIdx,
                imageIndex: i,
                sizeProtected: img.sizeProtected,
                locked: img.locked,
                horzRelTo: img.horzRelTo,
                vertRelTo: img.vertRelTo,
              });
            }
          }
        }

        return { docItems, vmItems };
      },
    };
    return () => {
      delete window.__HWPX_TEST_BRIDGE;
    };
  }, []);

  // Capture copy/cut text for clipboard history when selection originates from the editor surface.
  useEffect(() => {
    const handler = () => {
      const store = useEditorStore.getState();
      const sel = window.getSelection();
      const text = sel?.toString() ?? "";
      if (!text.trim()) return;
      const anchor = sel?.anchorNode;
      const host =
        anchor instanceof HTMLElement
          ? anchor
          : anchor?.parentElement ?? null;
      if (!host?.closest('[data-hwpx-editor-root="true"]')) return;
      // Ignore copies from dialogs/inputs.
      if (host.closest("input, textarea, select, [role='dialog']")) return;
      store.pushClipboardHistory(text);
    };

    document.addEventListener("copy", handler, true);
    document.addEventListener("cut", handler, true);
    return () => {
      document.removeEventListener("copy", handler, true);
      document.removeEventListener("cut", handler, true);
    };
  }, []);

  // Keep store selection in sync when a table cell gets focus/click.
  useEffect(() => {
    const syncCellSelection = (target: EventTarget | null) => {
      const base =
        target instanceof HTMLElement
          ? target
          : target instanceof Node
            ? target.parentElement
            : null;
      if (!(base instanceof HTMLElement)) return;
      const td = base.closest("td[data-hwpx-cell='1']");
      if (!(td instanceof HTMLTableCellElement)) return;

      const sectionIndex = Number(td.dataset.sectionIndex);
      const paragraphIndex = Number(td.dataset.paragraphIndex);
      const tableIndex = Number(td.dataset.tableIndex);
      const row = Number(td.dataset.row);
      const col = Number(td.dataset.col);
      if (![sectionIndex, paragraphIndex, tableIndex, row, col].every(Number.isFinite)) return;

      const store = useEditorStore.getState();
      const sel = store.selection;
      if (
        sel?.type === "cell" &&
        sel.sectionIndex === sectionIndex &&
        sel.paragraphIndex === paragraphIndex &&
        sel.tableIndex === tableIndex &&
        sel.row === row &&
        sel.col === col &&
        sel.endRow == null &&
        sel.endCol == null
      ) {
        return;
      }

      store.setSelection({
        sectionIndex,
        paragraphIndex,
        type: "cell",
        tableIndex,
        row,
        col,
        objectType: "table",
      });
    };

    const onMouseDown = (e: MouseEvent) => syncCellSelection(e.target);
    const onFocusIn = (e: FocusEvent) => syncCellSelection(e.target);
    document.addEventListener("mousedown", onMouseDown, true);
    document.addEventListener("focusin", onFocusIn, true);
    return () => {
      document.removeEventListener("mousedown", onMouseDown, true);
      document.removeEventListener("focusin", onFocusIn, true);
    };
  }, []);

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target instanceof HTMLElement ? e.target : null;
      if (!target?.closest('[data-hwpx-editor-root="true"]')) return;

      // Let native browser/input behavior win inside form controls.
      const isFormControl = Boolean(target.closest("input, textarea, select"));
      if (isFormControl) return;

      const store = useEditorStore.getState();
      const mod = e.ctrlKey || e.metaKey;
      const ctrlOnly = e.ctrlKey && !e.metaKey;
      const key = e.key.toLowerCase();

      if (ctrlOnly && e.shiftKey && key === "n") {
        e.preventDefault();
        void store.newDocument();
        return;
      }

      if (ctrlOnly && e.shiftKey && key === "o") {
        e.preventDefault();
        store.openFile();
        return;
      }

      if (ctrlOnly && e.shiftKey && key === "s") {
        e.preventDefault();
        store.openSaveDialog();
        return;
      }

      if (ctrlOnly && e.shiftKey && key === "p") {
        e.preventDefault();
        store.printDocument();
        return;
      }

      // Object delete (image/textbox/table selection)
      if (!mod && !e.altKey && !e.shiftKey && (key === "backspace" || key === "delete")) {
        const sel = store.selection;
        const isObjectSelection =
          sel?.objectType === "image" ||
          sel?.objectType === "textBox" ||
          sel?.type === "table";
        if (isObjectSelection) {
          e.preventDefault();
          store.deleteSelectedObject();
          return;
        }
      }

      // Table selected: Enter inserts a new paragraph below the table.
      if (!mod && !e.altKey && !e.shiftKey && key === "enter") {
        const sel = store.selection;
        if (sel?.type === "table") {
          e.preventDefault();
          const nextParagraphIndex = sel.paragraphIndex + 1;
          store.insertBlockAt(sel.sectionIndex, nextParagraphIndex, "");
          store.setSelection({
            sectionIndex: sel.sectionIndex,
            paragraphIndex: nextParagraphIndex,
            type: "paragraph",
          });
          return;
        }
      }

      if (!store.doc) return;

      // Undo / Redo (works without selection)
      if (mod && key === "z" && !e.shiftKey) {
        e.preventDefault();
        store.undo();
        return;
      }
      if (mod && (key === "y" || (key === "z" && e.shiftKey))) {
        e.preventDefault();
        store.redo();
        return;
      }

      // Dialog shortcuts
      if (e.altKey && e.shiftKey && !mod && key === "l") {
        e.preventDefault();
        store.openCharFormatDialog();
        return;
      }
      if (e.altKey && e.shiftKey && !mod && key === "t") {
        e.preventDefault();
        store.openParaFormatDialog();
        return;
      }
      if (e.altKey && e.shiftKey && !mod && key === "m") {
        e.preventDefault();
        store.openCharMapDialog();
        return;
      }
      if (ctrlOnly && e.shiftKey && (key === "f" || key === "h")) {
        e.preventDefault();
        store.openFindReplaceDialog();
        return;
      }
      if (ctrlOnly && e.shiftKey && key === "v") {
        e.preventDefault();
        store.openClipboardDialog();
        return;
      }
      if (ctrlOnly && e.altKey && key === "c") {
        e.preventDefault();
        store.openCaptionDialog();
        return;
      }
      if (ctrlOnly && e.altKey && key === "w") {
        e.preventDefault();
        store.selectWordAtCursor();
        return;
      }
      if (ctrlOnly && e.altKey && key === "s") {
        e.preventDefault();
        store.selectSentenceAtCursor();
        return;
      }
      if (ctrlOnly && e.altKey && key === "p") {
        e.preventDefault();
        store.selectParagraphAll();
        return;
      }

      if (!store.selection) return;

      if (mod && key === "b") {
        e.preventDefault();
        store.toggleBold();
      } else if (mod && key === "i") {
        e.preventDefault();
        store.toggleItalic();
      } else if (mod && key === "u") {
        e.preventDefault();
        store.toggleUnderline();
      } else if (mod && key === "d") {
        e.preventDefault();
        store.toggleStrikethrough();
      } else if (e.ctrlKey && !e.metaKey && key === "e") {
        e.preventDefault();
        store.setAlignment("CENTER");
      } else if (e.ctrlKey && !e.metaKey && key === "r") {
        // Do not hijack Cmd+R (browser reload) on macOS.
        e.preventDefault();
        store.setAlignment("RIGHT");
      } else if (e.ctrlKey && !e.metaKey && key === "j") {
        e.preventDefault();
        store.setAlignment("JUSTIFY");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (bootstrapping || (loading && !doc)) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-gray-500">새 문서 로딩 중...</div>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-6 bg-gray-100 p-8">
        <h1 className="text-2xl font-bold text-gray-800">HWPX Editor</h1>
        <p className="text-gray-500 max-w-md text-center">
          HWPX 문서를 열거나 새 문서를 만들어 편집하세요.
        </p>
        <div className="w-full max-w-md">
          <FileUpload />
        </div>
        <div className="flex gap-3">
          <NewDocumentButton />
        </div>
        {error && (
          <div className="bg-red-50 text-red-600 px-4 py-2 rounded-lg text-sm">
            {error}
          </div>
        )}
      </div>
    );
  }

  return (
    <div data-hwpx-editor-root="true" className="flex h-screen flex-col">
      <input
        ref={fileInputRef}
        type="file"
        accept=".hwpx"
        className="hidden"
        onChange={handleFileChange}
      />
      <SaveDialog />
      <CharFormatDialog />
      <ParaFormatDialog />
      <BulletNumberDialog />
      <CharMapDialog />
      <TemplateDialog />
      <HeaderFooterDialog />
      <FindReplaceDialog />
      <ClipboardDialog />
      <WordCountDialog />
      <PageNumberDialog />
      <StyleDialog />
      <CaptionDialog />
      <AutoCorrectDialog />
      <OutlineDialog />
      <ShapeDialog />
      <TocDialog />
      {/* Menu bar */}
      <MenuBar leadingContent={topMenuLeading} />
      {/* Ribbon toolbar */}
      <RibbonToolbar />
      {/* Secondary toolbar (formatting bar) */}
      <SecondaryToolbar />
      {/* Error banner */}
      {error && (
        <div className="bg-red-50 text-red-600 px-4 py-2 text-sm border-b border-red-200">
          {error}
        </div>
      )}
      {/* Main content area: Page + Sidebar */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex min-h-0 flex-1 bg-gray-200">
            {leftPanel ? (
              <aside className="hidden xl:block w-80 shrink-0 border-r border-gray-200/50 p-3 overflow-y-auto">
                {leftPanel}
              </aside>
            ) : null}

            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
              {/* Ruler must share the same center column as page view for precise alignment */}
              {uiState.showRuler ? <HorizontalRuler /> : null}
              <PageView />
            </div>

            {rightPanel ? (
              <aside className="hidden xl:block w-80 shrink-0 border-l border-gray-200/60 p-3 overflow-y-auto">
                {rightPanel}
              </aside>
            ) : null}
          </div>
        </div>
        <FormatSidebar />
        {/* Sidebar toggle when closed */}
        {!uiState.sidebarOpen && (
          <button
            type="button"
            onClick={toggleSidebar}
            className="absolute right-2 top-[140px] z-10 p-1.5 bg-white border border-gray-200 rounded shadow-sm text-gray-400 hover:text-gray-600 hover:bg-gray-50"
            title="서식 사이드바 열기"
            aria-label="서식 사이드바 열기"
          >
            <PanelRight aria-hidden="true" className="w-4 h-4" />
          </button>
        )}
      </div>
      {/* Status bar */}
      <StatusBar />
    </div>
  );
}

function StatusBar() {
  const doc = useEditorStore((s) => s.doc);
  const viewModel = useEditorStore((s) => s.viewModel);
  const selection = useEditorStore((s) => s.selection);
  const nestedTableFocus = useEditorStore((s) => s.nestedTableFocus);
  const openWordCountDialog = useEditorStore((s) => s.openWordCountDialog);

  if (!doc || !viewModel) return null;

  const text = doc.text;
  const charCount = text.replace(/\s/g, "").length;
  // Estimate page count (1 section = 1 page minimum)
  const sectionCount = viewModel.sections.length;
  const selectionInfo = (() => {
    if (nestedTableFocus) {
      return `중첩 표 선택 (문단 ${nestedTableFocus.paragraphIndex + 1}, 셀 R${nestedTableFocus.row + 1}C${nestedTableFocus.col + 1})`;
    }
    if (!selection) return "선택 없음";
    if (selection.objectType === "image") return `그림 선택 (문단 ${selection.paragraphIndex + 1})`;
    if (selection.objectType === "textBox") return `글상자 선택 (문단 ${selection.paragraphIndex + 1})`;

    if (selection.type === "table" || selection.objectType === "table") {
      return `표 선택 (문단 ${selection.paragraphIndex + 1})`;
    }

    if (selection.type === "cell" && selection.row != null && selection.col != null) {
      const startRow = selection.row + 1;
      const startCol = selection.col + 1;
      if (selection.endRow != null && selection.endCol != null) {
        const endRow = selection.endRow + 1;
        const endCol = selection.endCol + 1;
        const minRow = Math.min(startRow, endRow);
        const maxRow = Math.max(startRow, endRow);
        const minCol = Math.min(startCol, endCol);
        const maxCol = Math.max(startCol, endCol);
        const count = (maxRow - minRow + 1) * (maxCol - minCol + 1);
        return `셀 범위 R${minRow}C${minCol}~R${maxRow}C${maxCol} (${count}칸)`;
      }
      return `셀 R${startRow}C${startCol}`;
    }

    const textStart = selection.textStartOffset ?? 0;
    const textEnd = selection.textEndOffset ?? textStart;
    if (textEnd > textStart) {
      return `문자 선택 ${textEnd - textStart}자 (문단 ${selection.paragraphIndex + 1})`;
    }
    return `문단 ${selection.paragraphIndex + 1}`;
  })();

  return (
    <div className="h-4 flex items-center justify-between gap-3 px-3 bg-gray-100 border-t border-gray-200 text-[10px] text-gray-500">
      <span className="truncate" title={selectionInfo}>
        {selectionInfo}
      </span>
      <button
        onClick={openWordCountDialog}
        className="hover:text-gray-700 hover:underline"
        title="글자 수 세기 대화상자 열기"
      >
        글자 수 (공백 제외): {charCount.toLocaleString()} | 쪽: {sectionCount}
      </button>
    </div>
  );
}
