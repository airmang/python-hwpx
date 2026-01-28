/**
 * Zustand store — manages HwpxDocument + EditorViewModel + actions.
 */

import { create } from "zustand";
import type { HwpxDocument } from "@ubermensch1218/hwpxcore";
import { buildViewModel, type EditorViewModel } from "./view-model";
import {
  readFormatFromSelection,
  type CharFormat,
  type ParaFormat,
} from "./format-bridge";
import type { AlignmentType, OrientationType, SidebarTab } from "./constants";
import { mmToHwp } from "./hwp-units";

export interface SelectionState {
  sectionIndex: number;
  paragraphIndex: number;
  type: "paragraph" | "cell";
  // For cell selection
  tableIndex?: number;
  row?: number;
  col?: number;
  // For object selection (image/table context)
  objectType?: "image" | "table";
  imageIndex?: number;
}

export interface ActiveFormat {
  bold: boolean;
  italic: boolean;
  underline: boolean;
  strikethrough: boolean;
}

export interface ExtendedFormat {
  char: CharFormat;
  para: ParaFormat;
}

export interface UIState {
  sidebarOpen: boolean;
  sidebarTab: SidebarTab;
  saveDialogOpen: boolean;
}

interface UndoEntry {
  sectionElements: Element[];
  headerElements: Element[];
  selection: SelectionState | null;
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
  undoStack: UndoEntry[];
  redoStack: UndoEntry[];

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
  toggleStrikethrough: () => void;
  setFontFamily: (fontFamily: string) => void;
  setFontSize: (size: number) => void;
  setTextColor: (color: string) => void;
  setHighlightColor: (color: string) => void;
  setAlignment: (alignment: AlignmentType) => void;
  setLineSpacing: (spacing: number) => void;

  // Block operations
  deleteBlock: (sectionIndex: number, paragraphIndex: number) => void;
  insertBlockAt: (
    sectionIndex: number,
    paragraphIndex: number,
    text?: string,
  ) => void;

  // Paragraph editing
  splitParagraph: (
    sectionIndex: number,
    paragraphIndex: number,
    offset: number,
  ) => void;
  mergeParagraphWithPrevious: (
    sectionIndex: number,
    paragraphIndex: number,
  ) => void;

  // Undo/Redo
  pushUndo: () => void;
  undo: () => void;
  redo: () => void;

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
  insertColumnBreak: () => void;
  insertPageBreak: () => void;

  // Image editing
  updatePictureSize: (widthMm: number, heightMm: number) => void;

  // Table editing
  setTablePageBreak: (mode: "CELL" | "NONE") => void;
  setTableRepeatHeader: (repeat: boolean) => void;

  // Page setup
  updatePageSize: (width: number, height: number) => void;
  updatePageMargins: (margins: Partial<{ left: number; right: number; top: number; bottom: number; header: number; footer: number; gutter: number }>) => void;
  updatePageOrientation: (orientation: OrientationType) => void;

  // File operations
  saveDocument: () => Promise<void>;
  saveDocumentAs: (filename: string) => Promise<void>;
  openSaveDialog: () => void;
  closeSaveDialog: () => void;
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
  activeFormat: { bold: false, italic: false, underline: false, strikethrough: false },
  undoStack: [],
  redoStack: [],
  extendedFormat: { char: defaultCharFormat, para: defaultParaFormat },
  uiState: { sidebarOpen: true, sidebarTab: "char", saveDialogOpen: false },
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
          strikethrough: fmt.char.strikethrough,
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
      const oldText = para.text;
      if (oldText === text) return;
      get().pushUndo();
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
      get().pushUndo();
      const charPrIdRef = doc.ensureRunStyle({
        bold: newBold,
        italic: activeFormat.italic,
        underline: activeFormat.underline,
        strikethrough: activeFormat.strikethrough,
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
      get().pushUndo();
      const charPrIdRef = doc.ensureRunStyle({
        bold: activeFormat.bold,
        italic: newItalic,
        underline: activeFormat.underline,
        strikethrough: activeFormat.strikethrough,
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
      get().pushUndo();
      const charPrIdRef = doc.ensureRunStyle({
        bold: activeFormat.bold,
        italic: activeFormat.italic,
        underline: newUnderline,
        strikethrough: activeFormat.strikethrough,
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

  toggleStrikethrough: () => {
    const { doc, activeFormat, selection } = get();
    if (!doc || !selection) return;
    const newStrike = !activeFormat.strikethrough;
    try {
      get().pushUndo();
      const cf = get().extendedFormat.char;
      const charPrIdRef = doc.ensureRunStyle({
        bold: activeFormat.bold,
        italic: activeFormat.italic,
        underline: activeFormat.underline,
        strikethrough: newStrike,
        fontFamily: cf.fontFamily ?? undefined,
        fontSize: cf.fontSize ?? undefined,
        textColor: cf.textColor ?? undefined,
        highlightColor: cf.highlightColor ?? undefined,
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.charPrIdRef = charPrIdRef;
      set({ activeFormat: { ...activeFormat, strikethrough: newStrike } });
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("toggleStrikethrough failed:", e);
    }
  },

  setFontFamily: (fontFamily) => {
    const { doc, extendedFormat, selection } = get();
    if (!doc || !selection) return;
    try {
      const cf = extendedFormat.char;
      const charPrIdRef = doc.ensureRunStyle({
        bold: cf.bold,
        italic: cf.italic,
        underline: cf.underline,
        fontFamily,
        fontSize: cf.fontSize ?? undefined,
        textColor: cf.textColor ?? undefined,
        highlightColor: cf.highlightColor ?? undefined,
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.charPrIdRef = charPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setFontFamily failed:", e);
    }
  },

  setFontSize: (size) => {
    const { doc, extendedFormat, selection } = get();
    if (!doc || !selection) return;
    try {
      const cf = extendedFormat.char;
      const charPrIdRef = doc.ensureRunStyle({
        bold: cf.bold,
        italic: cf.italic,
        underline: cf.underline,
        fontFamily: cf.fontFamily ?? undefined,
        fontSize: size,
        textColor: cf.textColor ?? undefined,
        highlightColor: cf.highlightColor ?? undefined,
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.charPrIdRef = charPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setFontSize failed:", e);
    }
  },

  setTextColor: (color) => {
    const { doc, extendedFormat, selection } = get();
    if (!doc || !selection) return;
    try {
      const cf = extendedFormat.char;
      const charPrIdRef = doc.ensureRunStyle({
        bold: cf.bold,
        italic: cf.italic,
        underline: cf.underline,
        fontFamily: cf.fontFamily ?? undefined,
        fontSize: cf.fontSize ?? undefined,
        textColor: color,
        highlightColor: cf.highlightColor ?? undefined,
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.charPrIdRef = charPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setTextColor failed:", e);
    }
  },

  setHighlightColor: (color) => {
    const { doc, extendedFormat, selection } = get();
    if (!doc || !selection) return;
    try {
      const cf = extendedFormat.char;
      const charPrIdRef = doc.ensureRunStyle({
        bold: cf.bold,
        italic: cf.italic,
        underline: cf.underline,
        fontFamily: cf.fontFamily ?? undefined,
        fontSize: cf.fontSize ?? undefined,
        textColor: cf.textColor ?? undefined,
        highlightColor: color,
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.charPrIdRef = charPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setHighlightColor failed:", e);
    }
  },

  setAlignment: (alignment) => {
    const { doc, extendedFormat, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const pf = extendedFormat.para;
      const paraPrIdRef = doc.ensureParaStyle({
        alignment,
        lineSpacingValue: Math.round(pf.lineSpacing * 100),
        baseParaPrId: (() => {
          const section = doc.sections[selection.sectionIndex];
          if (!section) return undefined;
          const para = section.paragraphs[selection.paragraphIndex];
          return para?.paraPrIdRef ?? undefined;
        })(),
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.paraPrIdRef = paraPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setAlignment failed:", e);
    }
  },

  setLineSpacing: (spacing) => {
    const { doc, extendedFormat, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const pf = extendedFormat.para;
      const paraPrIdRef = doc.ensureParaStyle({
        alignment: pf.alignment,
        lineSpacingValue: Math.round(spacing * 100),
        baseParaPrId: (() => {
          const section = doc.sections[selection.sectionIndex];
          if (!section) return undefined;
          const para = section.paragraphs[selection.paragraphIndex];
          return para?.paraPrIdRef ?? undefined;
        })(),
      });
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.paraPrIdRef = paraPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setLineSpacing failed:", e);
    }
  },

  splitParagraph: (sectionIndex, paragraphIndex, offset) => {
    const { doc } = get();
    if (!doc) return;
    try {
      get().pushUndo();
      const section = doc.sections[sectionIndex];
      if (!section) return;
      const para = section.paragraphs[paragraphIndex];
      if (!para) return;
      const fullText = para.text;
      const before = fullText.substring(0, offset);
      const after = fullText.substring(offset);

      // Update current paragraph text
      para.text = before;

      // Insert new paragraph after current one
      doc.insertParagraphAt(sectionIndex, paragraphIndex + 1, after, {
        paraPrIdRef: para.paraPrIdRef ?? undefined,
        charPrIdRef: para.charPrIdRef ?? undefined,
      });

      // Move selection to the new paragraph
      set({
        selection: {
          sectionIndex,
          paragraphIndex: paragraphIndex + 1,
          type: "paragraph",
        },
      });
      get().rebuild();
    } catch (e) {
      console.error("splitParagraph failed:", e);
    }
  },

  mergeParagraphWithPrevious: (sectionIndex, paragraphIndex) => {
    const { doc } = get();
    if (!doc) return;
    if (paragraphIndex <= 0) return;
    try {
      get().pushUndo();
      const section = doc.sections[sectionIndex];
      if (!section) return;
      const prevPara = section.paragraphs[paragraphIndex - 1];
      const currPara = section.paragraphs[paragraphIndex];
      if (!prevPara || !currPara) return;

      const prevText = prevPara.text;
      const currText = currPara.text;

      // Merge text into previous paragraph
      prevPara.text = prevText + currText;

      // Remove current paragraph
      doc.removeParagraph(sectionIndex, paragraphIndex);

      // Move selection to previous paragraph
      set({
        selection: {
          sectionIndex,
          paragraphIndex: paragraphIndex - 1,
          type: "paragraph",
        },
      });
      get().rebuild();
    } catch (e) {
      console.error("mergeParagraphWithPrevious failed:", e);
    }
  },

  pushUndo: () => {
    const { doc, selection, undoStack } = get();
    if (!doc) return;
    try {
      const sections = doc.oxml.sections;
      const headers = doc.oxml.headers;
      const entry: UndoEntry = {
        sectionElements: sections.map((s) => s.element.cloneNode(true) as Element),
        headerElements: headers.map((h) => h.element.cloneNode(true) as Element),
        selection: selection ? { ...selection } : null,
      };
      // Limit stack size to 50
      const newStack = undoStack.length >= 50
        ? [...undoStack.slice(undoStack.length - 49), entry]
        : [...undoStack, entry];
      set({ undoStack: newStack, redoStack: [] });
    } catch (e) {
      console.error("pushUndo failed:", e);
    }
  },

  undo: () => {
    const { doc, selection, undoStack, redoStack } = get();
    if (!doc || undoStack.length === 0) return;
    try {
      const sections = doc.oxml.sections;
      const headers = doc.oxml.headers;

      // Save current state to redo stack
      const currentEntry: UndoEntry = {
        sectionElements: sections.map((s) => s.element.cloneNode(true) as Element),
        headerElements: headers.map((h) => h.element.cloneNode(true) as Element),
        selection: selection ? { ...selection } : null,
      };

      // Pop from undo stack
      const entry = undoStack[undoStack.length - 1]!;
      const newUndoStack = undoStack.slice(0, -1);

      // Restore section elements
      sections.forEach((s, i) => {
        if (entry.sectionElements[i]) {
          s.replaceElement(entry.sectionElements[i]!);
        }
      });
      // Restore header elements
      headers.forEach((h, i) => {
        if (entry.headerElements[i]) {
          h.replaceElement(entry.headerElements[i]!);
        }
      });

      doc.oxml.invalidateCharPropertyCache();
      set({
        undoStack: newUndoStack,
        redoStack: [...redoStack, currentEntry],
        selection: entry.selection,
      });
      get().rebuild();
    } catch (e) {
      console.error("undo failed:", e);
    }
  },

  redo: () => {
    const { doc, selection, undoStack, redoStack } = get();
    if (!doc || redoStack.length === 0) return;
    try {
      const sections = doc.oxml.sections;
      const headers = doc.oxml.headers;

      // Save current state to undo stack
      const currentEntry: UndoEntry = {
        sectionElements: sections.map((s) => s.element.cloneNode(true) as Element),
        headerElements: headers.map((h) => h.element.cloneNode(true) as Element),
        selection: selection ? { ...selection } : null,
      };

      // Pop from redo stack
      const entry = redoStack[redoStack.length - 1]!;
      const newRedoStack = redoStack.slice(0, -1);

      // Restore section elements
      sections.forEach((s, i) => {
        if (entry.sectionElements[i]) {
          s.replaceElement(entry.sectionElements[i]!);
        }
      });
      // Restore header elements
      headers.forEach((h, i) => {
        if (entry.headerElements[i]) {
          h.replaceElement(entry.headerElements[i]!);
        }
      });

      doc.oxml.invalidateCharPropertyCache();
      set({
        undoStack: [...undoStack, currentEntry],
        redoStack: newRedoStack,
        selection: entry.selection,
      });
      get().rebuild();
    } catch (e) {
      console.error("redo failed:", e);
    }
  },

  deleteBlock: (sectionIndex, paragraphIndex) => {
    const { doc } = get();
    if (!doc) return;
    try {
      get().pushUndo();
      doc.removeParagraph(sectionIndex, paragraphIndex);
      // Adjust selection if it pointed at or after the deleted block
      const { selection } = get();
      if (selection && selection.sectionIndex === sectionIndex) {
        if (selection.paragraphIndex === paragraphIndex) {
          set({ selection: null });
        } else if (selection.paragraphIndex > paragraphIndex) {
          set({
            selection: {
              ...selection,
              paragraphIndex: selection.paragraphIndex - 1,
            },
          });
        }
      }
      get().rebuild();
    } catch (e) {
      console.error("deleteBlock failed:", e);
    }
  },

  insertBlockAt: (sectionIndex, paragraphIndex, text = "") => {
    const { doc } = get();
    if (!doc) return;
    try {
      get().pushUndo();
      doc.insertParagraphAt(sectionIndex, paragraphIndex, text);
      // Shift selection if it's at or after the insertion point
      const { selection } = get();
      if (
        selection &&
        selection.sectionIndex === sectionIndex &&
        selection.paragraphIndex >= paragraphIndex
      ) {
        set({
          selection: {
            ...selection,
            paragraphIndex: selection.paragraphIndex + 1,
          },
        });
      }
      get().rebuild();
    } catch (e) {
      console.error("insertBlockAt failed:", e);
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

  insertColumnBreak: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      const para = doc.addParagraph("");
      para.columnBreak = true;
      get().rebuild();
    } catch (e) {
      console.error("insertColumnBreak failed:", e);
    }
  },

  insertPageBreak: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      const para = doc.addParagraph("");
      para.pageBreak = true;
      get().rebuild();
    } catch (e) {
      console.error("insertPageBreak failed:", e);
    }
  },

  // Image editing actions
  updatePictureSize: (widthMm, heightMm) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    try {
      para.setPictureSize(selection.imageIndex ?? 0, mmToHwp(widthMm), mmToHwp(heightMm));
      get().rebuild();
    } catch (e) {
      console.error("updatePictureSize failed:", e);
    }
  },

  // Table editing actions
  setTablePageBreak: (mode) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      table.pageBreak = mode;
      get().rebuild();
    } catch (e) {
      console.error("setTablePageBreak failed:", e);
    }
  },

  setTableRepeatHeader: (repeat) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      table.repeatHeader = repeat;
      get().rebuild();
    } catch (e) {
      console.error("setTableRepeatHeader failed:", e);
    }
  },

  // Page setup actions
  updatePageSize: (width, height) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sIdx = selection?.sectionIndex ?? 0;
    const section = doc.sections[sIdx];
    if (!section) return;
    try {
      section.properties.setPageSize({ width: mmToHwp(width), height: mmToHwp(height) });
      get().rebuild();
    } catch (e) {
      console.error("updatePageSize failed:", e);
    }
  },

  updatePageMargins: (margins) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sIdx = selection?.sectionIndex ?? 0;
    const section = doc.sections[sIdx];
    if (!section) return;
    try {
      const converted: Record<string, number> = {};
      for (const [k, v] of Object.entries(margins)) {
        if (v !== undefined) converted[k] = mmToHwp(v);
      }
      section.properties.setPageMargins(converted);
      get().rebuild();
    } catch (e) {
      console.error("updatePageMargins failed:", e);
    }
  },

  updatePageOrientation: (orientation) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sIdx = selection?.sectionIndex ?? 0;
    const section = doc.sections[sIdx];
    if (!section) return;
    try {
      const ps = section.properties.pageSize;
      if (orientation === "LANDSCAPE" && ps.width < ps.height) {
        section.properties.setPageSize({ width: ps.height, height: ps.width, orientation: "LANDSCAPE" });
      } else if (orientation === "PORTRAIT" && ps.width > ps.height) {
        section.properties.setPageSize({ width: ps.height, height: ps.width, orientation: "PORTRAIT" });
      } else {
        section.properties.setPageSize({ orientation });
      }
      get().rebuild();
    } catch (e) {
      console.error("updatePageOrientation failed:", e);
    }
  },

  // File operations
  saveDocument: async () => {
    get().openSaveDialog();
  },

  saveDocumentAs: async (filename) => {
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
      a.download = filename.endsWith(".hwpx") ? filename : `${filename}.hwpx`;
      a.click();
      URL.revokeObjectURL(url);
      get().closeSaveDialog();
    } catch (e) {
      console.error("save failed:", e);
      set({ error: "문서 저장에 실패했습니다." });
    } finally {
      set({ loading: false });
    }
  },

  openSaveDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, saveDialogOpen: true } })),

  closeSaveDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, saveDialogOpen: false } })),
}));
