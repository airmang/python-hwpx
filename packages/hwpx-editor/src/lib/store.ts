/**
 * Zustand store — manages HwpxDocument + EditorViewModel + actions.
 */

import { create } from "zustand";
import type { HwpxDocument } from "@hwpx/core";
import { buildViewModel, type EditorViewModel } from "./view-model";
import {
  readFormatFromSelection,
  type CharFormat,
  type ParaFormat,
} from "./format-bridge";
import type { AlignmentType, SidebarTab } from "./constants";

export interface SelectionState {
  sectionIndex: number;
  paragraphIndex: number;
  type: "paragraph" | "cell";
  // For cell selection
  tableIndex?: number;
  row?: number;
  col?: number;
}

export interface ActiveFormat {
  bold: boolean;
  italic: boolean;
  underline: boolean;
}

export interface ExtendedFormat {
  char: CharFormat;
  para: ParaFormat;
}

export interface UIState {
  sidebarOpen: boolean;
  sidebarTab: SidebarTab;
}

export interface EditorStore {
  doc: HwpxDocument | null;
  viewModel: EditorViewModel | null;
  revision: number;
  selection: SelectionState | null;
  activeFormat: ActiveFormat;
  extendedFormat: ExtendedFormat;
  uiState: UIState;
  loading: boolean;
  error: string | null;

  // Actions
  setDocument: (doc: HwpxDocument) => void;
  rebuild: () => void;
  setSelection: (sel: SelectionState | null) => void;
  setActiveFormat: (fmt: Partial<ActiveFormat>) => void;
  refreshExtendedFormat: () => void;

  // UI actions
  toggleSidebar: () => void;
  setSidebarTab: (tab: SidebarTab) => void;

  // Text editing
  updateParagraphText: (
    sectionIndex: number,
    paragraphIndex: number,
    text: string,
  ) => void;
  updateCellText: (
    sectionIndex: number,
    paragraphIndex: number,
    tableIndex: number,
    row: number,
    col: number,
    text: string,
  ) => void;

  // Formatting
  toggleBold: () => void;
  toggleItalic: () => void;
  toggleUnderline: () => void;

  // Content insertion
  addParagraph: (text?: string) => void;
  addTable: (
    sectionIndex: number,
    paragraphIndex: number,
    rows: number,
    cols: number,
  ) => void;
  insertImage: (
    data: Uint8Array,
    mediaType: string,
    widthMm: number,
    heightMm: number,
  ) => void;

  // File operations
  saveDocument: () => Promise<void>;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

const defaultCharFormat: CharFormat = {
  bold: false,
  italic: false,
  underline: false,
  strikethrough: false,
  fontFamily: null,
  fontSize: null,
  textColor: null,
  highlightColor: null,
  letterSpacing: null,
};

const defaultParaFormat: ParaFormat = {
  alignment: "LEFT",
  lineSpacing: 1.6,
  spacingBefore: 0,
  spacingAfter: 0,
  indentLeft: 0,
  indentRight: 0,
  firstLineIndent: 0,
};

export const useEditorStore = create<EditorStore>((set, get) => ({
  doc: null,
  viewModel: null,
  revision: 0,
  selection: null,
  activeFormat: { bold: false, italic: false, underline: false },
  extendedFormat: { char: defaultCharFormat, para: defaultParaFormat },
  uiState: { sidebarOpen: true, sidebarTab: "char" },
  loading: false,
  error: null,

  setDocument: (doc) => {
    const viewModel = buildViewModel(doc);
    set({ doc, viewModel, revision: get().revision + 1, error: null });
  },

  rebuild: () => {
    const { doc } = get();
    if (!doc) return;
    const viewModel = buildViewModel(doc);
    set({ viewModel, revision: get().revision + 1 });
  },

  setSelection: (selection) => {
    set({ selection });
    // Auto-refresh extended format when selection changes
    if (selection) {
      // Use setTimeout to avoid synchronous read during render
      setTimeout(() => get().refreshExtendedFormat(), 0);
    }
  },

  setActiveFormat: (fmt) =>
    set((s) => ({ activeFormat: { ...s.activeFormat, ...fmt } })),

  refreshExtendedFormat: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      const fmt = readFormatFromSelection(
        doc,
        selection.sectionIndex,
        selection.paragraphIndex,
      );
      set({
        extendedFormat: fmt,
        activeFormat: {
          bold: fmt.char.bold,
          italic: fmt.char.italic,
          underline: fmt.char.underline,
        },
      });
    } catch (e) {
      console.error("refreshExtendedFormat failed:", e);
    }
  },

  // UI actions
  toggleSidebar: () =>
    set((s) => ({
      uiState: { ...s.uiState, sidebarOpen: !s.uiState.sidebarOpen },
    })),

  setSidebarTab: (tab) =>
    set((s) => ({
      uiState: { ...s.uiState, sidebarTab: tab },
    })),

  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  updateParagraphText: (sectionIndex, paragraphIndex, text) => {
    const { doc } = get();
    if (!doc) return;
    try {
      const section = doc.sections[sectionIndex];
      if (!section) return;
      const paras = section.paragraphs;
      const para = paras[paragraphIndex];
      if (!para) return;
      para.text = text;
      get().rebuild();
    } catch (e) {
      console.error("updateParagraphText failed:", e);
    }
  },

  updateCellText: (sectionIndex, paragraphIndex, tableIndex, row, col, text) => {
    const { doc } = get();
    if (!doc) return;
    try {
      const section = doc.sections[sectionIndex];
      if (!section) return;
      const paras = section.paragraphs;
      const para = paras[paragraphIndex];
      if (!para) return;
      const table = para.tables[tableIndex];
      if (!table) return;
      table.setCellText(row, col, text);
      get().rebuild();
    } catch (e) {
      console.error("updateCellText failed:", e);
    }
  },

  toggleBold: () => {
    const { doc, activeFormat, selection } = get();
    if (!doc || !selection) return;
    const newBold = !activeFormat.bold;
    try {
      const charPrIdRef = doc.ensureRunStyle({
        bold: newBold,
        italic: activeFormat.italic,
        underline: activeFormat.underline,
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.charPrIdRef = charPrIdRef;
      set({ activeFormat: { ...activeFormat, bold: newBold } });
      get().rebuild();
    } catch (e) {
      console.error("toggleBold failed:", e);
    }
  },

  toggleItalic: () => {
    const { doc, activeFormat, selection } = get();
    if (!doc || !selection) return;
    const newItalic = !activeFormat.italic;
    try {
      const charPrIdRef = doc.ensureRunStyle({
        bold: activeFormat.bold,
        italic: newItalic,
        underline: activeFormat.underline,
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.charPrIdRef = charPrIdRef;
      set({ activeFormat: { ...activeFormat, italic: newItalic } });
      get().rebuild();
    } catch (e) {
      console.error("toggleItalic failed:", e);
    }
  },

  toggleUnderline: () => {
    const { doc, activeFormat, selection } = get();
    if (!doc || !selection) return;
    const newUnderline = !activeFormat.underline;
    try {
      const charPrIdRef = doc.ensureRunStyle({
        bold: activeFormat.bold,
        italic: activeFormat.italic,
        underline: newUnderline,
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.charPrIdRef = charPrIdRef;
      set({ activeFormat: { ...activeFormat, underline: newUnderline } });
      get().rebuild();
    } catch (e) {
      console.error("toggleUnderline failed:", e);
    }
  },

  addParagraph: (text = "") => {
    const { doc } = get();
    if (!doc) return;
    try {
      doc.addParagraph(text);
      get().rebuild();
    } catch (e) {
      console.error("addParagraph failed:", e);
    }
  },

  addTable: (sectionIndex, paragraphIndex, rows, cols) => {
    const { doc } = get();
    if (!doc) return;
    try {
      const section = doc.sections[sectionIndex];
      if (!section) return;
      const para = section.paragraphs[paragraphIndex];
      if (!para) return;
      para.addTable(rows, cols);
      get().rebuild();
    } catch (e) {
      console.error("addTable failed:", e);
    }
  },

  insertImage: (data, mediaType, widthMm, heightMm) => {
    const { doc } = get();
    if (!doc) return;
    try {
      doc.addImage(data, { mediaType, widthMm, heightMm });
      get().rebuild();
    } catch (e) {
      console.error("insertImage failed:", e);
    }
  },

  saveDocument: async () => {
    const { doc } = get();
    if (!doc) return;
    try {
      set({ loading: true });
      const bytes = await doc.save();
      const blob = new Blob([bytes as unknown as BlobPart], {
        type: "application/vnd.hancom.hwpx",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "document.hwpx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("save failed:", e);
      set({ error: "문서 저장에 실패했습니다." });
    } finally {
      set({ loading: false });
    }
  },
}));
