/**
 * Zustand store — manages HwpxDocument + EditorViewModel + actions.
 */

import { create } from "zustand";
import type { HwpxDocument } from "@ubermensch1218/hwpxcore";
import { buildViewModel } from "./view-model";
import { readFormatFromSelection, type CharFormat, type ParaFormat } from "./format-bridge";
import { mmToHwp } from "./hwp-units";

// Re-export types from store/types
export type {
  SelectionState,
  ActiveFormat,
  ExtendedFormat,
  UIState,
  Template,
  UndoEntry,
  EditorStore,
} from "./store/types";

import type {
  SelectionState,
  ActiveFormat,
  ExtendedFormat,
  UIState,
  Template,
  UndoEntry,
  EditorStore,
} from "./store/types";

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
  uiState: { sidebarOpen: true, sidebarTab: "char", saveDialogOpen: false, charFormatDialogOpen: false, paraFormatDialogOpen: false, bulletNumberDialogOpen: false, charMapDialogOpen: false, templateDialogOpen: false, headerFooterDialogOpen: false, findReplaceDialogOpen: false, wordCountDialogOpen: false, pageNumberDialogOpen: false, styleDialogOpen: false, autoCorrectDialogOpen: false, outlineDialogOpen: false, shapeDialogOpen: false, tocDialogOpen: false, zoomLevel: 100 },
  loading: false,
  error: null,
  templates: [],

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

  openTemplateDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, templateDialogOpen: true } })),

  closeTemplateDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, templateDialogOpen: false } })),

  openHeaderFooterDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, headerFooterDialogOpen: true } })),

  closeHeaderFooterDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, headerFooterDialogOpen: false } })),

  setHeaderFooter: ({ headerText, footerText }) => {
    const { doc, selection } = get();
    if (!doc) return;
    try {
      get().pushUndo();
      const sIdx = selection?.sectionIndex ?? 0;
      const section = doc.sections[sIdx];
      if (!section) return;
      const props = section.properties;
      if (headerText != null) props.setHeaderText(headerText);
      if (footerText != null) props.setFooterText(footerText);
      get().rebuild();
    } catch (e) {
      console.error("setHeaderFooter failed:", e);
    }
  },

  openFindReplaceDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, findReplaceDialogOpen: true } })),

  closeFindReplaceDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, findReplaceDialogOpen: false } })),

  findAndReplace: (search, replacement, count) => {
    const { doc } = get();
    if (!doc) return 0;
    try {
      get().pushUndo();
      const replaced = doc.replaceText(search, replacement, count);
      get().rebuild();
      return replaced;
    } catch (e) {
      console.error("findAndReplace failed:", e);
      return 0;
    }
  },

  openWordCountDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, wordCountDialogOpen: true } })),

  closeWordCountDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, wordCountDialogOpen: false } })),

  addTemplate: (name, path, description) => {
    const template: Template = {
      id: `tpl-${Date.now()}`,
      name,
      path,
      description,
      createdAt: Date.now(),
    };
    set((s) => ({ templates: [...s.templates, template] }));
    get().saveTemplates();
  },

  removeTemplate: (id) => {
    set((s) => ({ templates: s.templates.filter((t) => t.id !== id) }));
    get().saveTemplates();
  },

  loadTemplates: () => {
    try {
      const stored = localStorage.getItem("hwpx-templates");
      if (stored) {
        const templates = JSON.parse(stored) as Template[];
        set({ templates });
      }
    } catch (e) {
      console.error("loadTemplates failed:", e);
    }
  },

  saveTemplates: () => {
    try {
      const { templates } = get();
      localStorage.setItem("hwpx-templates", JSON.stringify(templates));
    } catch (e) {
      console.error("saveTemplates failed:", e);
    }
  },

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

      // Check if there's a text range selection
      const hasTextRange =
        selection.textStartOffset != null &&
        selection.textEndOffset != null &&
        selection.textStartOffset < selection.textEndOffset;

      if (hasTextRange) {
        para.applyCharFormatToRange(selection.textStartOffset!, selection.textEndOffset!, charPrIdRef);
      } else {
        para.charPrIdRef = charPrIdRef;
      }
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

      const hasTextRange =
        selection.textStartOffset != null &&
        selection.textEndOffset != null &&
        selection.textStartOffset < selection.textEndOffset;

      if (hasTextRange) {
        para.applyCharFormatToRange(selection.textStartOffset!, selection.textEndOffset!, charPrIdRef);
      } else {
        para.charPrIdRef = charPrIdRef;
      }
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

      const hasTextRange =
        selection.textStartOffset != null &&
        selection.textEndOffset != null &&
        selection.textStartOffset < selection.textEndOffset;

      if (hasTextRange) {
        para.applyCharFormatToRange(selection.textStartOffset!, selection.textEndOffset!, charPrIdRef);
      } else {
        para.charPrIdRef = charPrIdRef;
      }
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

      const hasTextRange =
        selection.textStartOffset != null &&
        selection.textEndOffset != null &&
        selection.textStartOffset < selection.textEndOffset;

      if (hasTextRange) {
        para.applyCharFormatToRange(selection.textStartOffset!, selection.textEndOffset!, charPrIdRef);
      } else {
        para.charPrIdRef = charPrIdRef;
      }
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
      get().pushUndo();
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

      const hasTextRange =
        selection.textStartOffset != null &&
        selection.textEndOffset != null &&
        selection.textStartOffset < selection.textEndOffset;

      if (hasTextRange) {
        para.applyCharFormatToRange(selection.textStartOffset!, selection.textEndOffset!, charPrIdRef);
      } else {
        para.charPrIdRef = charPrIdRef;
      }
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
      get().pushUndo();
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

      const hasTextRange =
        selection.textStartOffset != null &&
        selection.textEndOffset != null &&
        selection.textStartOffset < selection.textEndOffset;

      if (hasTextRange) {
        para.applyCharFormatToRange(selection.textStartOffset!, selection.textEndOffset!, charPrIdRef);
      } else {
        para.charPrIdRef = charPrIdRef;
      }
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
      get().pushUndo();
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

      const hasTextRange =
        selection.textStartOffset != null &&
        selection.textEndOffset != null &&
        selection.textStartOffset < selection.textEndOffset;

      if (hasTextRange) {
        para.applyCharFormatToRange(selection.textStartOffset!, selection.textEndOffset!, charPrIdRef);
      } else {
        para.charPrIdRef = charPrIdRef;
      }
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
      get().pushUndo();
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

      const hasTextRange =
        selection.textStartOffset != null &&
        selection.textEndOffset != null &&
        selection.textStartOffset < selection.textEndOffset;

      if (hasTextRange) {
        para.applyCharFormatToRange(selection.textStartOffset!, selection.textEndOffset!, charPrIdRef);
      } else {
        para.charPrIdRef = charPrIdRef;
      }
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

  setSelectedCellsSize: (widthMm, heightMm) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.type !== "cell" || selection.tableIndex == null) return;

    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const table = para.tables[selection.tableIndex];
    if (!table) return;

    try {
      get().pushUndo();

      // Determine the selected range
      const startRow = Math.min(selection.row ?? 0, selection.endRow ?? selection.row ?? 0);
      const endRow = Math.max(selection.row ?? 0, selection.endRow ?? selection.row ?? 0);
      const startCol = Math.min(selection.col ?? 0, selection.endCol ?? selection.col ?? 0);
      const endCol = Math.max(selection.col ?? 0, selection.endCol ?? selection.col ?? 0);

      const grid = table.getCellMap();

      // Set width for selected columns
      if (widthMm != null) {
        const widthHwp = mmToHwp(widthMm);
        const processedCols = new Set<number>();
        for (let c = startCol; c <= endCol; c++) {
          if (!processedCols.has(c)) {
            table.setColumnWidth(c, widthHwp);
            processedCols.add(c);
          }
        }
      }

      // Set height for selected rows (update each cell's height)
      if (heightMm != null) {
        const heightHwp = mmToHwp(heightMm);
        const processedCells = new Set<Element>();
        for (let r = startRow; r <= endRow; r++) {
          for (let c = startCol; c <= endCol; c++) {
            const pos = grid[r]?.[c];
            if (pos && !processedCells.has(pos.cell.element)) {
              pos.cell.setSize(undefined, heightHwp);
              processedCells.add(pos.cell.element);
            }
          }
        }
      }

      get().rebuild();
    } catch (e) {
      console.error("setSelectedCellsSize failed:", e);
    }
  },

  mergeSelectedCells: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.type !== "cell") return;
    if (selection.row == null || selection.col == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const tbl = para.tables[selection.tableIndex ?? 0];
      if (!tbl) return;

      const startRow = Math.min(selection.row, selection.endRow ?? selection.row);
      const endRow = Math.max(selection.row, selection.endRow ?? selection.row);
      const startCol = Math.min(selection.col, selection.endCol ?? selection.col);
      const endCol = Math.max(selection.col, selection.endCol ?? selection.col);
      if (startRow === endRow && startCol === endCol) return; // Single cell, nothing to merge

      get().pushUndo();
      tbl.mergeCells(startRow, startCol, endRow, endCol);
      // Update selection to just the merged cell
      set({
        selection: { ...selection, row: startRow, col: startCol, endRow: startRow, endCol: startCol },
      });
      get().rebuild();
    } catch (e) {
      console.error("mergeSelectedCells failed:", e);
    }
  },

  unmergeSelectedCells: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.type !== "cell") return;
    if (selection.row == null || selection.col == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const tbl = para.tables[selection.tableIndex ?? 0];
      if (!tbl) return;

      const cell = tbl.cell(selection.row, selection.col);
      if (!cell) return;
      const [rowSpan, colSpan] = cell.span;
      if (rowSpan === 1 && colSpan === 1) return; // Not merged

      get().pushUndo();
      tbl.unmergeCells(selection.row, selection.col);
      // Expand selection to cover all unmerged cells
      set({
        selection: {
          ...selection,
          endRow: selection.row + rowSpan - 1,
          endCol: selection.col + colSpan - 1,
        },
      });
      get().rebuild();
    } catch (e) {
      console.error("unmergeSelectedCells failed:", e);
    }
  },

  insertTableRow: (position) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.type !== "cell") return;
    if (selection.row == null || selection.tableIndex == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const tbl = para.tables[selection.tableIndex];
      if (!tbl) return;

      get().pushUndo();
      tbl.insertRow(selection.row, position);
      // Update selection to new row if inserted above
      if (position === "above") {
        set({ selection: { ...selection, row: selection.row + 1 } });
      }
      get().rebuild();
    } catch (e) {
      console.error("insertTableRow failed:", e);
    }
  },

  insertTableColumn: (position) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.type !== "cell") return;
    if (selection.col == null || selection.tableIndex == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const tbl = para.tables[selection.tableIndex];
      if (!tbl) return;

      get().pushUndo();
      tbl.insertColumn(selection.col, position);
      // Update selection to new column if inserted left
      if (position === "left") {
        set({ selection: { ...selection, col: selection.col + 1 } });
      }
      get().rebuild();
    } catch (e) {
      console.error("insertTableColumn failed:", e);
    }
  },

  deleteTableRow: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.type !== "cell") return;
    if (selection.row == null || selection.tableIndex == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const tbl = para.tables[selection.tableIndex];
      if (!tbl) return;

      if (tbl.rowCount <= 1) return; // Can't delete last row

      get().pushUndo();
      tbl.deleteRow(selection.row);
      // Adjust selection if needed
      const newRow = Math.min(selection.row, tbl.rowCount - 1);
      set({ selection: { ...selection, row: newRow } });
      get().rebuild();
    } catch (e) {
      console.error("deleteTableRow failed:", e);
    }
  },

  deleteTableColumn: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.type !== "cell") return;
    if (selection.col == null || selection.tableIndex == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const tbl = para.tables[selection.tableIndex];
      if (!tbl) return;

      if (tbl.columnCount <= 1) return; // Can't delete last column

      get().pushUndo();
      tbl.deleteColumn(selection.col);
      // Adjust selection if needed
      const newCol = Math.min(selection.col, tbl.columnCount - 1);
      set({ selection: { ...selection, col: newCol } });
      get().rebuild();
    } catch (e) {
      console.error("deleteTableColumn failed:", e);
    }
  },

  deleteTable: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;

      get().pushUndo();
      // Remove the table from the paragraph
      const tables = para.tables;
      if (selection.tableIndex < tables.length) {
        const tbl = tables[selection.tableIndex];
        if (tbl && tbl.element.parentNode) {
          tbl.element.parentNode.removeChild(tbl.element);
        }
      }
      // Clear table selection
      set({ selection: { ...selection, type: "paragraph", tableIndex: undefined, row: undefined, col: undefined } });
      get().rebuild();
    } catch (e) {
      console.error("deleteTable failed:", e);
    }
  },

  // Zoom actions
  setZoom: (level) => {
    const clampedLevel = Math.max(25, Math.min(400, level));
    set((s) => ({ uiState: { ...s.uiState, zoomLevel: clampedLevel } }));
  },

  zoomIn: () => {
    const { uiState } = get();
    const newLevel = Math.min(uiState.zoomLevel + 10, 400);
    set((s) => ({ uiState: { ...s.uiState, zoomLevel: newLevel } }));
  },

  zoomOut: () => {
    const { uiState } = get();
    const newLevel = Math.max(uiState.zoomLevel - 10, 25);
    set((s) => ({ uiState: { ...s.uiState, zoomLevel: newLevel } }));
  },

  // Page number dialog
  openPageNumberDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, pageNumberDialogOpen: true } })),

  closePageNumberDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, pageNumberDialogOpen: false } })),

  // New document / Open file
  newDocument: async () => {
    try {
      set({ loading: true, error: null });
      // Fetch skeleton template
      const response = await fetch("/Skeleton.hwpx");
      if (!response.ok) {
        throw new Error("Failed to load template");
      }
      const buffer = await response.arrayBuffer();
      const { HwpxDocument } = await import("@ubermensch1218/hwpxcore");
      const newDoc = await HwpxDocument.open(new Uint8Array(buffer));
      get().setDocument(newDoc);
      set({ selection: null, undoStack: [], redoStack: [] });
    } catch (e) {
      console.error("newDocument failed:", e);
      set({ error: "새 문서 생성에 실패했습니다." });
    } finally {
      set({ loading: false });
    }
  },

  openDocument: async (data) => {
    try {
      set({ loading: true, error: null });
      const { HwpxDocument } = await import("@ubermensch1218/hwpxcore");
      const newDoc = await HwpxDocument.open(data);
      get().setDocument(newDoc);
      set({ selection: null, undoStack: [], redoStack: [] });
    } catch (e) {
      console.error("openDocument failed:", e);
      set({ error: "문서 열기에 실패했습니다." });
    } finally {
      set({ loading: false });
    }
  },

  printDocument: () => {
    window.print();
  },

  exportPDF: async () => {
    // Use browser print to PDF functionality
    // In future, can integrate with libraries like html2pdf or jspdf
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      console.error("Failed to open print window");
      return;
    }

    const pageView = document.querySelector("[data-page-view]");
    if (!pageView) {
      printWindow.close();
      return;
    }

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>문서 출력</title>
        <style>
          @media print {
            body { margin: 0; padding: 0; }
            @page { margin: 20mm; }
          }
          body { font-family: 'Malgun Gothic', sans-serif; }
        </style>
      </head>
      <body>
        ${pageView.innerHTML}
      </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();

    setTimeout(() => {
      printWindow.print();
      printWindow.close();
    }, 250);
  },

  applyBullet: (bulletId) => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.bulletIdRef = bulletId;
      get().rebuild();
    } catch (e) {
      console.error("applyBullet failed:", e);
    }
  },

  applyNumbering: (level) => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.outlineLevel = level;
      get().rebuild();
    } catch (e) {
      console.error("applyNumbering failed:", e);
    }
  },

  applyOutlineLevel: (level) => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.outlineLevel = level;
      get().rebuild();
    } catch (e) {
      console.error("applyOutlineLevel failed:", e);
    }
  },

  removeBulletNumbering: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.bulletIdRef = null;
      para.outlineLevel = 0;
      get().rebuild();
    } catch (e) {
      console.error("removeBulletNumbering failed:", e);
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

  setColumnCount: (colCount, gapMm) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sIdx = selection?.sectionIndex ?? 0;
    const section = doc.sections[sIdx];
    if (!section) return;
    try {
      get().pushUndo();
      section.properties.setColumnLayout({
        colCount: Math.max(1, colCount),
        sameGap: gapMm != null ? mmToHwp(gapMm) : undefined,
      });
      get().rebuild();
    } catch (e) {
      console.error("setColumnCount failed:", e);
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

  openStyleDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, styleDialogOpen: true } })),

  closeStyleDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, styleDialogOpen: false } })),

  openAutoCorrectDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, autoCorrectDialogOpen: true } })),

  closeAutoCorrectDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, autoCorrectDialogOpen: false } })),

  openOutlineDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, outlineDialogOpen: true } })),

  closeOutlineDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, outlineDialogOpen: false } })),

  openShapeDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, shapeDialogOpen: true } })),

  closeShapeDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, shapeDialogOpen: false } })),

  openTocDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, tocDialogOpen: true } })),

  closeTocDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, tocDialogOpen: false } })),

  applyStyle: (styleId) => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      para.styleIdRef = styleId;
      get().rebuild();
    } catch (e) {
      console.error("applyStyle failed:", e);
    }
  },

  insertToc: (options) => {
    const { doc } = get();
    if (!doc) return;
    try {
      get().pushUndo();
      // Import dynamically to avoid circular dependencies
      import("@ubermensch1218/hwpxcore").then(({ generateTableOfContents }) => {
        generateTableOfContents(doc.oxml, options);
        get().rebuild();
      }).catch((e) => {
        console.error("insertToc import failed:", e);
      });
    } catch (e) {
      console.error("insertToc failed:", e);
    }
  },

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

  insertTab: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      get().pushUndo();
      para.addTab({ charPrIdRef: para.charPrIdRef ?? undefined });
      get().rebuild();
    } catch (e) {
      console.error("insertTab failed:", e);
    }
  },

  insertTextBox: (text, widthMm, heightMm) => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      get().pushUndo();
      para.addTextBox(text, {
        width: mmToHwp(widthMm),
        height: mmToHwp(heightMm),
        charPrIdRef: para.charPrIdRef ?? undefined,
      });
      get().rebuild();
    } catch (e) {
      console.error("insertTextBox failed:", e);
    }
  },

  insertShape: (shapeType, widthMm, heightMm) => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      get().pushUndo();

      const paraEl = para.element;
      const HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph";
      const HCNS = "http://www.hancom.co.kr/hwpml/2011/HwpUnitChar";

      // Find or create a run element
      const runs = paraEl.getElementsByTagNameNS(HP_NS, "run");
      let run: Element;
      if (runs.length > 0) {
        run = runs[runs.length - 1]!;
      } else {
        run = paraEl.ownerDocument.createElementNS(HP_NS, "hp:run");
        paraEl.appendChild(run);
      }

      // Create shape element (using drawingObject as container)
      const drawObj = paraEl.ownerDocument.createElementNS(HP_NS, "hp:drawingObject");

      // Set size in HWP units
      const widthHwp = mmToHwp(widthMm);
      const heightHwp = mmToHwp(heightMm);

      // Create curSz for size
      const curSz = paraEl.ownerDocument.createElementNS(HCNS, "hc:curSz");
      curSz.setAttribute("width", String(widthHwp));
      curSz.setAttribute("height", String(heightHwp));
      drawObj.appendChild(curSz);

      // Create shape-specific element
      const shapeEl = paraEl.ownerDocument.createElementNS(HP_NS, "hp:shape");
      shapeEl.setAttribute("type", shapeType);

      // Set shape properties based on type
      if (shapeType === "rectangle") {
        shapeEl.setAttribute("fill", "#ffffff");
        shapeEl.setAttribute("stroke", "#000000");
        shapeEl.setAttribute("strokeWidth", "1");
      } else if (shapeType === "ellipse") {
        shapeEl.setAttribute("fill", "#ffffff");
        shapeEl.setAttribute("stroke", "#000000");
        shapeEl.setAttribute("strokeWidth", "1");
      } else if (shapeType === "line" || shapeType === "arrow") {
        shapeEl.setAttribute("stroke", "#000000");
        shapeEl.setAttribute("strokeWidth", "1");
        if (shapeType === "arrow") {
          shapeEl.setAttribute("endArrow", "true");
        }
      }

      drawObj.appendChild(shapeEl);
      run.appendChild(drawObj);

      get().rebuild();
    } catch (e) {
      console.error("insertShape failed:", e);
    }
  },
}));
