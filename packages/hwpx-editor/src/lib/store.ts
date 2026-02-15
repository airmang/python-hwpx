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
  // For cell range selection (merge)
  endRow?: number;
  endCol?: number;
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
  charFormatDialogOpen: boolean;
  paraFormatDialogOpen: boolean;
  bulletNumberDialogOpen: boolean;
  charMapDialogOpen: boolean;
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
  resizeImage: (deltaWidthHwp: number, deltaHeightHwp: number) => void;
  setImageOutMargin: (margins: Partial<{ top: number; bottom: number; left: number; right: number }>) => void;

  // Table editing
  setTablePageBreak: (mode: "CELL" | "NONE") => void;
  setTableRepeatHeader: (repeat: boolean) => void;
  setTableSize: (widthMm: number, heightMm: number) => void;
  setTableOutMargin: (margins: Partial<{ top: number; bottom: number; left: number; right: number }>) => void;
  setTableInMargin: (margins: Partial<{ top: number; bottom: number; left: number; right: number }>) => void;
  resizeTableColumn: (sectionIdx: number, paraIdx: number, tableIdx: number, colIdx: number, deltaHwp: number) => void;

  // Paragraph indent
  setFirstLineIndent: (valueHwp: number) => void;
  setLeftIndent: (valueHwp: number) => void;

  // Page numbering
  setPageNumbering: (opts: { position: string; startNumber: number }) => void;

  // Footnote / Endnote
  insertFootnote: () => void;
  insertEndnote: () => void;

  // Watermark
  setWatermarkText: (text: string) => void;

  // Dialog open/close
  openCharFormatDialog: () => void;
  closeCharFormatDialog: () => void;
  openParaFormatDialog: () => void;
  closeParaFormatDialog: () => void;
  openBulletNumberDialog: () => void;
  closeBulletNumberDialog: () => void;
  openCharMapDialog: () => void;
  closeCharMapDialog: () => void;

  // Text insertion at cursor
  insertTextAtCursor: (text: string) => void;

  // Page setup
  updatePageSize: (width: number, height: number) => void;
  updatePageMargins: (margins: Partial<{ left: number; right: number; top: number; bottom: number; header: number; footer: number; gutter: number }>) => void;
  updatePageOrientation: (orientation: OrientationType) => void;

  // Cell style operations
  setCellBorder: (sides: ("left"|"right"|"top"|"bottom")[], style: { type?: string; width?: string; color?: string }) => void;
  setCellBackground: (color: string | null) => void;
  setCellVertAlign: (align: "TOP" | "CENTER" | "BOTTOM") => void;

  // Table-wide border/background
  setTableBorder: (sides: ("left"|"right"|"top"|"bottom")[], style: { type?: string; width?: string; color?: string }) => void;
  setTableBackground: (color: string | null) => void;

  // Table structure operations
  insertTableRow: (position: "above" | "below") => void;
  deleteTableRow: () => void;
  insertTableColumn: (position: "left" | "right") => void;
  deleteTableColumn: () => void;
  mergeTableCells: () => void;
  splitTableCell: () => void;
  deleteTable: () => void;

  // File operations
  openFile: () => void;
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
  templates: [],
  extendedFormat: { char: defaultCharFormat, para: defaultParaFormat },
  uiState: { sidebarOpen: true, sidebarTab: "char", saveDialogOpen: false, charFormatDialogOpen: false, paraFormatDialogOpen: false, bulletNumberDialogOpen: false, charMapDialogOpen: false },
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
      get().pushUndo();
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

  resizeImage: (deltaWidthHwp, deltaHeightHwp) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    const pics = para.pictures;
    const pic = pics[imgIdx];
    if (!pic) return;
    try {
      get().pushUndo();
      // Read current size from curSz
      const vm = get().viewModel;
      const imgVM = vm?.sections[selection.sectionIndex]?.paragraphs[selection.paragraphIndex]?.images[imgIdx];
      if (!imgVM) return;
      const newW = Math.max(imgVM.widthHwp + deltaWidthHwp, 200);
      const newH = Math.max(imgVM.heightHwp + deltaHeightHwp, 200);
      para.setPictureSize(imgIdx, newW, newH);
      get().rebuild();
    } catch (e) {
      console.error("resizeImage failed:", e);
    }
  },

  setImageOutMargin: (margins) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      const converted: Record<string, number> = {};
      for (const [k, v] of Object.entries(margins)) {
        if (v !== undefined) converted[k] = mmToHwp(v);
      }
      para.setPictureOutMargin(imgIdx, converted);
      get().rebuild();
    } catch (e) {
      console.error("setImageOutMargin failed:", e);
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

  setTableSize: (widthMm, heightMm) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      get().pushUndo();
      table.setSize(mmToHwp(widthMm), mmToHwp(heightMm));
      get().rebuild();
    } catch (e) {
      console.error("setTableSize failed:", e);
    }
  },

  setTableOutMargin: (margins) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      get().pushUndo();
      const converted: Record<string, number> = {};
      for (const [k, v] of Object.entries(margins)) {
        if (v !== undefined) converted[k] = mmToHwp(v);
      }
      table.setOutMargin(converted);
      get().rebuild();
    } catch (e) {
      console.error("setTableOutMargin failed:", e);
    }
  },

  setTableInMargin: (margins) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      get().pushUndo();
      const converted: Record<string, number> = {};
      for (const [k, v] of Object.entries(margins)) {
        if (v !== undefined) converted[k] = mmToHwp(v);
      }
      table.setInMargin(converted);
      get().rebuild();
    } catch (e) {
      console.error("setTableInMargin failed:", e);
    }
  },

  resizeTableColumn: (sectionIdx, paraIdx, tableIdx, colIdx, deltaHwp) => {
    const { doc } = get();
    if (!doc) return;
    const section = doc.sections[sectionIdx];
    if (!section) return;
    const para = section.paragraphs[paraIdx];
    if (!para) return;
    const table = para.tables[tableIdx];
    if (!table) return;
    try {
      get().pushUndo();
      const colCount = table.columnCount;
      // Get current widths via the grid
      const grid = table.getCellMap();
      const widths: number[] = [];
      for (let c = 0; c < colCount; c++) {
        const pos = grid[0]?.[c];
        widths.push(pos ? pos.cell.width : 0);
      }
      // Adjust left column (colIdx) and right column (colIdx+1)
      if (colIdx < colCount - 1) {
        const newLeft = Math.max(widths[colIdx]! + deltaHwp, 200);
        const newRight = Math.max(widths[colIdx + 1]! - deltaHwp, 200);
        table.setColumnWidth(colIdx, newLeft);
        table.setColumnWidth(colIdx + 1, newRight);
      } else {
        // Last column: adjust its width and the table total width
        const newWidth = Math.max(widths[colIdx]! + deltaHwp, 200);
        table.setColumnWidth(colIdx, newWidth);
        const totalWidth = widths.reduce((a, b) => a + b, 0) + deltaHwp;
        table.setSize(Math.max(totalWidth, 200));
      }
      get().rebuild();
    } catch (e) {
      console.error("resizeTableColumn failed:", e);
    }
  },

  // Cell style operations
  setCellBorder: (sides, style) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.row == null || selection.col == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      get().pushUndo();
      const cell = table.cell(selection.row, selection.col);
      const baseBorderFillId = cell.borderFillIDRef ?? table.borderFillIDRef ?? undefined;
      const baseInfo = baseBorderFillId ? doc.oxml.getBorderFillInfo(baseBorderFillId) : null;
      const getBorderSide = (s: string) => {
        if (!baseInfo) return null;
        if (s === "left") return baseInfo.left;
        if (s === "right") return baseInfo.right;
        if (s === "top") return baseInfo.top;
        if (s === "bottom") return baseInfo.bottom;
        return null;
      };
      const sideMap: Record<string, { type: string; width: string; color: string }> = {};
      for (const s of sides) {
        const base = getBorderSide(s);
        sideMap[s] = {
          type: style.type ?? base?.type ?? "SOLID",
          width: style.width ?? base?.width ?? "0.12 mm",
          color: style.color ?? base?.color ?? "#000000",
        };
      }
      const newId = doc.oxml.ensureBorderFillStyle({
        baseBorderFillId,
        sides: sideMap as { left?: { type: string; width: string; color: string }; right?: { type: string; width: string; color: string }; top?: { type: string; width: string; color: string }; bottom?: { type: string; width: string; color: string } },
      });
      cell.borderFillIDRef = newId;
      get().rebuild();
    } catch (e) {
      console.error("setCellBorder failed:", e);
    }
  },

  setCellBackground: (color) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.row == null || selection.col == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      get().pushUndo();
      const cell = table.cell(selection.row, selection.col);
      const baseBorderFillId = cell.borderFillIDRef ?? table.borderFillIDRef ?? undefined;
      const newId = doc.oxml.ensureBorderFillStyle({
        baseBorderFillId,
        backgroundColor: color,
      });
      cell.borderFillIDRef = newId;
      get().rebuild();
    } catch (e) {
      console.error("setCellBackground failed:", e);
    }
  },

  setCellVertAlign: (align) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.row == null || selection.col == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      get().pushUndo();
      const cell = table.cell(selection.row, selection.col);
      cell.vertAlign = align;
      get().rebuild();
    } catch (e) {
      console.error("setCellVertAlign failed:", e);
    }
  },

  setTableBorder: (sides, style) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      get().pushUndo();
      // Apply to all cells in the table
      const grid = table.iterGrid();
      const processed = new Set<string>();
      for (const pos of grid) {
        const key = `${pos.anchor[0]},${pos.anchor[1]}`;
        if (processed.has(key)) continue;
        processed.add(key);
        const cell = pos.cell;
        const baseBorderFillId = cell.borderFillIDRef ?? table.borderFillIDRef ?? undefined;
        const baseInfo = baseBorderFillId ? doc.oxml.getBorderFillInfo(baseBorderFillId) : null;
        const getBorderSide = (s: string) => {
          if (!baseInfo) return null;
          if (s === "left") return baseInfo.left;
          if (s === "right") return baseInfo.right;
          if (s === "top") return baseInfo.top;
          if (s === "bottom") return baseInfo.bottom;
          return null;
        };
        const sideMap: Record<string, { type: string; width: string; color: string }> = {};
        for (const s of sides) {
          const base = getBorderSide(s);
          sideMap[s] = {
            type: style.type ?? base?.type ?? "SOLID",
            width: style.width ?? base?.width ?? "0.12 mm",
            color: style.color ?? base?.color ?? "#000000",
          };
        }
        const newId = doc.oxml.ensureBorderFillStyle({
          baseBorderFillId,
          sides: sideMap as { left?: { type: string; width: string; color: string }; right?: { type: string; width: string; color: string }; top?: { type: string; width: string; color: string }; bottom?: { type: string; width: string; color: string } },
        });
        cell.borderFillIDRef = newId;
      }
      get().rebuild();
    } catch (e) {
      console.error("setTableBorder failed:", e);
    }
  },

  setTableBackground: (color) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    try {
      get().pushUndo();
      const grid = table.iterGrid();
      const processed = new Set<string>();
      for (const pos of grid) {
        const key = `${pos.anchor[0]},${pos.anchor[1]}`;
        if (processed.has(key)) continue;
        processed.add(key);
        const cell = pos.cell;
        const baseBorderFillId = cell.borderFillIDRef ?? table.borderFillIDRef ?? undefined;
        const newId = doc.oxml.ensureBorderFillStyle({
          baseBorderFillId,
          backgroundColor: color,
        });
        cell.borderFillIDRef = newId;
      }
      get().rebuild();
    } catch (e) {
      console.error("setTableBackground failed:", e);
    }
  },

  setFirstLineIndent: (valueHwp) => {
    const { doc, extendedFormat, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const pf = extendedFormat.para;
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const paraPrIdRef = doc.ensureParaStyle({
        alignment: pf.alignment,
        lineSpacingValue: Math.round(pf.lineSpacing * 100),
        indent: valueHwp,
        marginLeft: pf.indentLeft,
        baseParaPrId: para.paraPrIdRef ?? undefined,
      });
      para.paraPrIdRef = paraPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setFirstLineIndent failed:", e);
    }
  },

  setLeftIndent: (valueHwp) => {
    const { doc, extendedFormat, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const pf = extendedFormat.para;
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const paraPrIdRef = doc.ensureParaStyle({
        alignment: pf.alignment,
        lineSpacingValue: Math.round(pf.lineSpacing * 100),
        marginLeft: valueHwp,
        indent: pf.firstLineIndent,
        baseParaPrId: para.paraPrIdRef ?? undefined,
      });
      para.paraPrIdRef = paraPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setLeftIndent failed:", e);
    }
  },

  setPageNumbering: (opts) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sIdx = selection?.sectionIndex ?? 0;
    const section = doc.sections[sIdx];
    if (!section) return;
    try {
      get().pushUndo();
      const props = section.properties;
      if (opts.position === "none") {
        // Remove page number text by setting empty header/footer
        props.setHeaderText("");
        props.setFooterText("");
      } else if (opts.position.startsWith("header")) {
        props.setFooterText(""); // clear footer
        const pageNumText = `- {{page}} -`;
        props.setHeaderText(pageNumText);
      } else if (opts.position.startsWith("footer")) {
        props.setHeaderText(""); // clear header
        const pageNumText = `- {{page}} -`;
        props.setFooterText(pageNumText);
      }
      // Set start number if > 0
      if (opts.startNumber > 0) {
        section.properties.setStartNumbering({ page: opts.startNumber });
      }
      get().rebuild();
    } catch (e) {
      console.error("setPageNumbering failed:", e);
    }
  },

  // Footnote / Endnote
  insertFootnote: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    try {
      get().pushUndo();
      // Insert a footnote element into the paragraph's run
      // Since the core doesn't have a dedicated API, we'll add via raw XML manipulation
      const paraEl = para.element;
      const NS = "http://www.hancom.co.kr/hwpml/2011/paragraph";
      const runs = paraEl.getElementsByTagNameNS(NS, "run");
      const lastRun = runs.length > 0 ? runs[runs.length - 1]! : null;
      if (lastRun) {
        const fnEl = paraEl.ownerDocument.createElementNS(NS, "hp:footNote");
        // Count existing footnotes in the section to get the marker number
        const existingFn = section.element.getElementsByTagNameNS(NS, "footNote");
        const fnNum = existingFn.length + 1;
        fnEl.setAttribute("number", String(fnNum));
        // Add a sub-paragraph with placeholder text
        const subPara = paraEl.ownerDocument.createElementNS(NS, "hp:subPara");
        const subRun = paraEl.ownerDocument.createElementNS(NS, "hp:run");
        const tEl = paraEl.ownerDocument.createElementNS(NS, "hp:t");
        tEl.textContent = `각주 ${fnNum}`;
        subRun.appendChild(tEl);
        subPara.appendChild(subRun);
        fnEl.appendChild(subPara);
        lastRun.appendChild(fnEl);
      }
      get().rebuild();
    } catch (e) {
      console.error("insertFootnote failed:", e);
    }
  },

  insertEndnote: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    try {
      get().pushUndo();
      const paraEl = para.element;
      const NS = "http://www.hancom.co.kr/hwpml/2011/paragraph";
      const runs = paraEl.getElementsByTagNameNS(NS, "run");
      const lastRun = runs.length > 0 ? runs[runs.length - 1]! : null;
      if (lastRun) {
        const enEl = paraEl.ownerDocument.createElementNS(NS, "hp:endNote");
        const existingEn = section.element.getElementsByTagNameNS(NS, "endNote");
        const enNum = existingEn.length + 1;
        enEl.setAttribute("number", String(enNum));
        const subPara = paraEl.ownerDocument.createElementNS(NS, "hp:subPara");
        const subRun = paraEl.ownerDocument.createElementNS(NS, "hp:run");
        const tEl = paraEl.ownerDocument.createElementNS(NS, "hp:t");
        tEl.textContent = `미주 ${enNum}`;
        subRun.appendChild(tEl);
        subPara.appendChild(subRun);
        enEl.appendChild(subPara);
        lastRun.appendChild(enEl);
      }
      get().rebuild();
    } catch (e) {
      console.error("insertEndnote failed:", e);
    }
  },

  setWatermarkText: (text) => {
    const vm = get().viewModel;
    if (!vm) return;
    // Watermark is a UI-only feature stored in the view model
    set({
      viewModel: { ...vm, watermarkText: text },
      revision: get().revision + 1,
    });
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

  // Table structure operations
  insertTableRow: (position) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.row == null) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      table.insertRow(selection.row, position === "above" ? "before" : "after");
      get().rebuild();
    } catch (e) {
      console.error("insertTableRow failed:", e);
    }
  },

  deleteTableRow: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.row == null) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      table.deleteRow(selection.row);
      set({ selection: null });
      get().rebuild();
    } catch (e) {
      console.error("deleteTableRow failed:", e);
    }
  },

  insertTableColumn: (position) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.col == null) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      table.insertColumn(selection.col, position === "left" ? "before" : "after");
      get().rebuild();
    } catch (e) {
      console.error("insertTableColumn failed:", e);
    }
  },

  deleteTableColumn: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.col == null) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      table.deleteColumn(selection.col);
      set({ selection: null });
      get().rebuild();
    } catch (e) {
      console.error("deleteTableColumn failed:", e);
    }
  },

  mergeTableCells: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    if (selection.row == null || selection.col == null) return;
    if (selection.endRow == null || selection.endCol == null) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      const r1 = Math.min(selection.row, selection.endRow);
      const c1 = Math.min(selection.col, selection.endCol);
      const r2 = Math.max(selection.row, selection.endRow);
      const c2 = Math.max(selection.col, selection.endCol);
      table.mergeCells(r1, c1, r2, c2);
      set({ selection: { ...selection, row: r1, col: c1, endRow: undefined, endCol: undefined } });
      get().rebuild();
    } catch (e) {
      console.error("mergeTableCells failed:", e);
    }
  },

  splitTableCell: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    if (selection.row == null || selection.col == null) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      table.splitCell(selection.row, selection.col);
      get().rebuild();
    } catch (e) {
      console.error("splitTableCell failed:", e);
    }
  },

  deleteTable: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    try {
      get().pushUndo();
      doc.removeParagraph(selection.sectionIndex, selection.paragraphIndex);
      set({ selection: null });
      get().rebuild();
    } catch (e) {
      console.error("deleteTable failed:", e);
    }
  },

  // File operations
  openFile: () => {
    window.dispatchEvent(new CustomEvent("hwpx-open-file"));
  },

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

  // Dialog open/close
  openCharFormatDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, charFormatDialogOpen: true } })),
  closeCharFormatDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, charFormatDialogOpen: false } })),
  openParaFormatDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, paraFormatDialogOpen: true } })),
  closeParaFormatDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, paraFormatDialogOpen: false } })),
  openBulletNumberDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, bulletNumberDialogOpen: true } })),
  closeBulletNumberDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, bulletNumberDialogOpen: false } })),
  openCharMapDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, charMapDialogOpen: true } })),
  closeCharMapDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, charMapDialogOpen: false } })),

  insertTextAtCursor: (text) => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      get().pushUndo();
      para.text = para.text + text;
      get().rebuild();
    } catch (e) {
      console.error("insertTextAtCursor failed:", e);
    }
  },

  // Template management (browser localStorage)
  loadTemplates: () => {
    try {
      const raw = localStorage.getItem("hwpx-editor-templates");
      if (raw) {
        const templates = JSON.parse(raw);
        if (Array.isArray(templates)) set({ templates });
      }
    } catch { /* ignore parse errors */ }
  },
  saveTemplates: () => {
    try {
      localStorage.setItem("hwpx-editor-templates", JSON.stringify(get().templates));
    } catch { /* ignore storage errors */ }
  },
  addTemplate: (name, path, description) => {
    const template = { id: crypto.randomUUID(), name, path, description, createdAt: Date.now() };
    const templates = [...get().templates, template];
    set({ templates });
    try { localStorage.setItem("hwpx-editor-templates", JSON.stringify(templates)); } catch {}
  },
  removeTemplate: (id) => {
    const templates = get().templates.filter((t) => t.id !== id);
    set({ templates });
    try { localStorage.setItem("hwpx-editor-templates", JSON.stringify(templates)); } catch {}
  },
}));
