/**
 * Zustand store — manages HwpxDocument + EditorViewModel + actions.
 */

import { create } from "zustand";
import { HwpxDocument } from "@ubermensch1218/hwpxcore";
import { buildViewModel, type EditorViewModel } from "./view-model";
import {
  readFormatFromSelection,
  type CharFormat,
  type ParaFormat,
} from "./format-bridge";
import type { AlignmentType, OrientationType, SidebarTab } from "./constants";
import { mmToHwp, pxToHwp } from "./hwp-units";
import { createNewDocument } from "./skeleton-loader";

export interface SelectionState {
  sectionIndex: number;
  paragraphIndex: number;
  type: "paragraph" | "cell" | "table";
  tableIndex?: number;
  row?: number;
  col?: number;
  endRow?: number;
  endCol?: number;
  objectType?: "image" | "table" | "textBox";
  imageIndex?: number;
  textBoxIndex?: number;
  textStartOffset?: number;
  textEndOffset?: number;
  /** Collapsed caret offset within the paragraph text (0..length). */
  cursorOffset?: number;
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
  showRuler: boolean;
  saveDialogOpen: boolean;
  charFormatDialogOpen: boolean;
  paraFormatDialogOpen: boolean;
  bulletNumberDialogOpen: boolean;
  charMapDialogOpen: boolean;
  templateDialogOpen: boolean;
  headerFooterDialogOpen: boolean;
  findReplaceDialogOpen: boolean;
  wordCountDialogOpen: boolean;
  pageNumberDialogOpen: boolean;
  styleDialogOpen: boolean;
  clipboardDialogOpen: boolean;
  captionDialogOpen: boolean;
  autoCorrectDialogOpen: boolean;
  outlineDialogOpen: boolean;
  shapeDialogOpen: boolean;
  tocDialogOpen: boolean;
  zoomLevel: number;
}

interface UndoEntry {
  sectionElements: Element[];
  headerElements: Element[];
  selection: SelectionState | null;
}

interface Template {
  id: string;
  name: string;
  path: string;
  description?: string;
  createdAt: number;
}

interface Snippet {
  id: string;
  name: string;
  text: string;
  createdAt: number;
}

type FormatPainterMode = "char" | "para" | "both" | "cell";

interface FormatPainterState {
  active: boolean;
  locked: boolean;
  mode: FormatPainterMode;
  origin: SelectionState | null;
  snapshot: ExtendedFormat | null;
}

export interface NestedTableFocusState {
  sectionIndex: number;
  paragraphIndex: number;
  tableIndex: number;
  row: number;
  col: number;
  nestedIndex: number;
}

function replacementFromMatchTemplate(template: string, match: string, args: unknown[]): string {
  // args is [...groups, offset, input] for String.prototype.replace callback.
  const tailOffset = args.length >= 2 ? args.length - 2 : 0;
  const groups = args.slice(0, tailOffset).map((v) => (v == null ? "" : String(v)));
  const offset = typeof args[tailOffset] === "number" ? (args[tailOffset] as number) : 0;
  const input = typeof args[tailOffset + 1] === "string" ? (args[tailOffset + 1] as string) : "";

  return template.replace(/\$(\$|&|`|'|\d{1,2})/g, (_whole, token: string) => {
    if (token === "$") return "$";
    if (token === "&") return match;
    if (token === "`") return input.slice(0, offset);
    if (token === "'") return input.slice(offset + match.length);
    const n = parseInt(token, 10);
    if (Number.isFinite(n) && n > 0) return groups[n - 1] ?? "";
    return "";
  });
}

function elementLocalName(element: Element): string {
  return element.localName ?? element.nodeName.split(":").pop() ?? "";
}

function findDirectChildByLocalName(parent: Element, localName: string): Element | null {
  const children = parent.childNodes;
  for (let i = 0; i < children.length; i += 1) {
    const node = children.item(i);
    if (!node || node.nodeType !== 1) continue;
    const child = node as Element;
    if (elementLocalName(child) === localName) return child;
  }
  return null;
}

function ensureDirectChildByLocalName(parent: Element, localName: string): Element {
  const existing = findDirectChildByLocalName(parent, localName);
  if (existing) return existing;
  const ns = parent.namespaceURI;
  const prefix = parent.prefix;
  const qualifiedName = prefix ? `${prefix}:${localName}` : localName;
  const created = ns
    ? parent.ownerDocument.createElementNS(ns, qualifiedName)
    : parent.ownerDocument.createElement(localName);
  parent.appendChild(created);
  return created;
}

function findDescendantByLocalName(parent: Element, localName: string): Element | null {
  const all = parent.getElementsByTagName("*");
  for (let i = 0; i < all.length; i += 1) {
    const el = all.item(i);
    if (!el) continue;
    if (elementLocalName(el) === localName) return el;
  }
  return null;
}

function getPictureElement(para: unknown, index: number): Element | null {
  const paraAny = para as { pictures?: Element[] };
  const pics = paraAny.pictures;
  if (pics && Array.isArray(pics) && pics[index]) {
    return pics[index]!;
  }

  // Fallback: some documents place pic in nested descendants not surfaced by pictures getter.
  const paragraphElement = (para as { element?: Element }).element;
  if (!paragraphElement) return null;
  const found: Element[] = [];
  const all = paragraphElement.getElementsByTagName("*");
  for (let i = 0; i < all.length; i += 1) {
    const el = all.item(i);
    if (!el) continue;
    if (elementLocalName(el) === "pic") found.push(el);
  }
  return found[index] ?? null;
}

function markSectionDirty(para: unknown): void {
  const section = (para as { section?: { markDirty?: () => void } }).section;
  section?.markDirty?.();
}

function countDescendantTables(element: Element | null | undefined): number {
  if (!element) return 0;
  const descendants = element.getElementsByTagName("*");
  let count = 0;
  for (let i = 0; i < descendants.length; i += 1) {
    const el = descendants.item(i);
    if (!el) continue;
    if (elementLocalName(el) === "tbl") count += 1;
  }
  return count;
}

function listTopLevelNestedTables(cellElement: Element): Element[] {
  const descendants = cellElement.getElementsByTagName("*");
  const nested: Element[] = [];
  for (let i = 0; i < descendants.length; i += 1) {
    const el = descendants.item(i);
    if (!el || elementLocalName(el) !== "tbl") continue;
    let hasAncestorTable = false;
    let parent: Element | null = el.parentElement;
    while (parent && parent !== cellElement) {
      if (elementLocalName(parent) === "tbl") {
        hasAncestorTable = true;
        break;
      }
      parent = parent.parentElement;
    }
    if (!hasAncestorTable) nested.push(el);
  }
  return nested;
}

function findTableCellElementAt(tableElement: Element, row: number, col: number): Element | null {
  const all = tableElement.getElementsByTagName("*");
  for (let i = 0; i < all.length; i += 1) {
    const el = all.item(i);
    if (!el || elementLocalName(el) !== "tc") continue;

    const addr = findDirectChildByLocalName(el, "cellAddr");
    const span = findDirectChildByLocalName(el, "cellSpan");
    const rowAddr = parseInt(addr?.getAttribute("rowAddr") ?? "0", 10);
    const colAddr = parseInt(addr?.getAttribute("colAddr") ?? "0", 10);
    const rowSpan = parseInt(span?.getAttribute("rowSpan") ?? "1", 10);
    const colSpan = parseInt(span?.getAttribute("colSpan") ?? "1", 10);

    if (
      Number.isFinite(rowAddr) &&
      Number.isFinite(colAddr) &&
      row >= rowAddr &&
      row < rowAddr + Math.max(1, rowSpan) &&
      col >= colAddr &&
      col < colAddr + Math.max(1, colSpan)
    ) {
      return el;
    }
  }
  return null;
}

function setTableCellElementText(cellElement: Element, text: string): void {
  const subList = ensureDirectChildByLocalName(cellElement, "subList");
  if (!subList.getAttribute("vertAlign")) {
    subList.setAttribute("vertAlign", "CENTER");
  }
  const paragraph = ensureDirectChildByLocalName(subList, "p");
  if (!paragraph.getAttribute("charPrIDRef") && !paragraph.getAttribute("charPrIdRef")) {
    paragraph.setAttribute("charPrIDRef", "0");
  }
  const run = ensureDirectChildByLocalName(paragraph, "run");
  if (!run.getAttribute("charPrIDRef") && !run.getAttribute("charPrIdRef")) {
    const charRef =
      paragraph.getAttribute("charPrIDRef") ??
      paragraph.getAttribute("charPrIdRef") ??
      "0";
    run.setAttribute("charPrIDRef", charRef);
  }
  const textElement = ensureDirectChildByLocalName(run, "t");
  textElement.textContent = text;
}

function setTableCellElementBackground(
  doc: HwpxDocument,
  tableElement: Element,
  row: number,
  col: number,
  color: string | null,
): boolean {
  const cellElement = findTableCellElementAt(tableElement, row, col);
  if (!cellElement) return false;
  const baseBorderFillId =
    cellElement.getAttribute("borderFillIDRef")
    ?? tableElement.getAttribute("borderFillIDRef")
    ?? undefined;
  const newId = doc.oxml.ensureBorderFillStyle({
    baseBorderFillId,
    backgroundColor: color,
  });
  cellElement.setAttribute("borderFillIDRef", newId);
  return true;
}

export interface EditorStore {
  doc: HwpxDocument | null;
  viewModel: EditorViewModel | null;
  revision: number;
  selection: SelectionState | null;
  nestedTableFocus: NestedTableFocusState | null;
  activeFormat: ActiveFormat;
  extendedFormat: ExtendedFormat;
  uiState: UIState;
  loading: boolean;
  error: string | null;
  undoStack: UndoEntry[];
  redoStack: UndoEntry[];
  templates: Template[];
  clipboardHistory: string[];
  snippets: Snippet[];
  formatPainter: FormatPainterState;
  serverDocumentId: string | null;

  // Actions
  setDocument: (doc: HwpxDocument) => void;
  rebuild: () => void;
  setSelection: (sel: SelectionState | null) => void;
  focusNestedTableInCell: (nestedIndex?: number) => void;
  focusParentTable: () => void;
  setActiveFormat: (fmt: Partial<ActiveFormat>) => void;
  refreshExtendedFormat: () => void;

  // UI actions
  toggleSidebar: () => void;
  setSidebarTab: (tab: SidebarTab) => void;
  toggleRuler: () => void;

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
  updateNestedTableCellText: (
    sectionIndex: number,
    paragraphIndex: number,
    tableIndex: number,
    row: number,
    col: number,
    nestedIndex: number,
    nestedRow: number,
    nestedCol: number,
    text: string,
  ) => void;
  updateNestedTableCellBackground: (
    sectionIndex: number,
    paragraphIndex: number,
    tableIndex: number,
    row: number,
    col: number,
    nestedIndex: number,
    startRow: number,
    startCol: number,
    endRow: number,
    endCol: number,
    color: string | null,
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
  insertChart: (opts?: {
    title?: string;
    chartType?: "bar" | "line";
    categories?: string[];
    values?: number[];
  }) => void;
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
  setImageTextWrap: (textWrap: string) => void;
  setImageTreatAsChar: (treatAsChar: boolean) => void;
  setImageOffsets: (offsets: Partial<{ horzMm: number; vertMm: number }>) => void;
  setImageOffsetRelTo: (relTo: Partial<{ horzRelTo: string; vertRelTo: string }>) => void;
  setImageSizeProtect: (protect: boolean) => void;
  setImageScale: (scaleXPercent: number, scaleYPercent: number) => void;
  setImageCrop: (crop: Partial<{ leftMm: number; rightMm: number; topMm: number; bottomMm: number }>) => void;
  setImageAdjustment: (adjust: Partial<{ brightness: number; contrast: number; effect: string; alpha: number }>) => void;
  setImageRotation: (angle: number) => void;
  setImageLock: (locked: boolean) => void;
  deleteSelectedObject: () => void;

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
  setRightIndent: (valueHwp: number) => void;
  setParagraphSpacingBefore: (valueHwp: number) => void;
  setParagraphSpacingAfter: (valueHwp: number) => void;

  // Page numbering
  setPageNumbering: (opts: { position: string; startNumber: number; format?: string }) => void;

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
  openFindReplaceDialog: () => void;
  closeFindReplaceDialog: () => void;
  openWordCountDialog: () => void;
  closeWordCountDialog: () => void;
  openTemplateDialog: () => void;
  closeTemplateDialog: () => void;
  openClipboardDialog: () => void;
  closeClipboardDialog: () => void;
  openCaptionDialog: () => void;
  closeCaptionDialog: () => void;
  openHeaderFooterDialog: () => void;
  closeHeaderFooterDialog: () => void;
  openPageNumberDialog: () => void;
  closePageNumberDialog: () => void;
  openStyleDialog: () => void;
  closeStyleDialog: () => void;
  openAutoCorrectDialog: () => void;
  closeAutoCorrectDialog: () => void;
  openOutlineDialog: () => void;
  closeOutlineDialog: () => void;
  openShapeDialog: () => void;
  closeShapeDialog: () => void;
  openTocDialog: () => void;
  closeTocDialog: () => void;
  setZoom: (level: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;

  // Text insertion at cursor
  insertTextAtCursor: (text: string) => void;
  insertTab: () => void;

  // Selection helpers
  selectWordAtCursor: () => void;
  selectSentenceAtCursor: () => void;
  selectParagraphAll: () => void;

  // Clipboard/snippets
  pushClipboardHistory: (text: string) => void;
  clearClipboardHistory: () => void;
  addSnippet: (name: string, text: string) => void;
  removeSnippet: (id: string) => void;
  loadSnippets: () => void;
  saveSnippets: () => void;

  // Format painter
  startFormatPainter: (mode?: FormatPainterMode, opts?: { locked?: boolean }) => void;
  cancelFormatPainter: () => void;
  maybeApplyFormatPainter: (nextSelection: SelectionState | null) => void;

  // Page setup
  updatePageSize: (width: number, height: number) => void;
  updatePageMargins: (margins: Partial<{ left: number; right: number; top: number; bottom: number; header: number; footer: number; gutter: number }>) => void;
  updatePageOrientation: (orientation: OrientationType) => void;
  setColumnCount: (colCount: number, gapMm?: number) => void;
  setHeaderFooter: (opts: {
    headerText?: string;
    footerText?: string;
    headerPosition?: "left" | "center" | "right";
    footerPosition?: "left" | "center" | "right";
  }) => void;

  // Cell style operations
  setCellBorder: (sides: ("left"|"right"|"top"|"bottom")[], style: { type?: string; width?: string; color?: string }) => void;
  setCellBackground: (color: string | null) => void;
  setCellVertAlign: (align: "TOP" | "CENTER" | "BOTTOM") => void;

  // Table-wide border/background
  setTableBorder: (sides: ("left"|"right"|"top"|"bottom")[], style: { type?: string; width?: string; color?: string }) => void;
  setTableBackground: (color: string | null) => void;

  // Table structure operations
  insertNestedTableInCell: (rows: number, cols: number) => void;
  insertTableRow: (position: "above" | "below") => void;
  deleteTableRow: () => void;
  insertTableColumn: (position: "left" | "right") => void;
  deleteTableColumn: () => void;
  moveTableRow: (direction: "up" | "down") => void;
  moveTableColumn: (direction: "left" | "right") => void;
  distributeTableColumns: () => void;
  distributeTableRows: () => void;
  mergeTableCells: () => void;
  splitTableCell: () => void;
  deleteTable: () => void;

  // File operations
  newDocument: () => Promise<void>;
  openDocument: (data: Uint8Array) => Promise<void>;
  printDocument: () => void;
  exportPDF: () => Promise<void>;
  openFile: () => void;
  saveDocument: () => Promise<void>;
  saveDocumentAs: (filename: string) => Promise<void>;
  saveDocumentToServer: (
    filename: string,
  ) => Promise<{ ok: boolean; status: number; documentId?: string; error?: string }>;
  openSaveDialog: () => void;
  closeSaveDialog: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  applyBullet: (bulletId: string | null) => void;
  applyNumbering: (level: number) => void;
  applyOutlineLevel: (level: number) => void;
  removeBulletNumbering: () => void;
  applyStyle: (styleId: string) => void;
  applyStyleToDocument: (styleId: string) => void;
  insertToc: (opts: {
    title?: string;
    tabLeader?: "DOT" | "HYPHEN" | "UNDERLINE" | "NONE";
    tabWidth?: number;
    maxLevel?: number;
    showPageNumbers?: boolean;
  }) => void;
  insertCaption: (opts: { kind: "figure" | "table"; text: string }) => void;
  insertCaptionList: (opts: { kind: "figure" | "table"; title?: string }) => void;
  insertShape: (shapeType: "rectangle" | "ellipse" | "line" | "arrow", widthMm: number, heightMm: number) => void;
  findAndReplace: (search: string, replacement: string, count?: number) => number;
  findAndReplaceAdvanced: (opts: {
    search: string;
    replacement: string;
    count?: number;
    matchCase?: boolean;
    useRegex?: boolean;
    wholeWord?: boolean;
    scope?: "document" | "paragraph" | "selection";
  }) => number;
  findNextMatch: (opts: {
    search: string;
    matchCase?: boolean;
    useRegex?: boolean;
    wholeWord?: boolean;
    scope?: "document" | "paragraph";
  }) => { found: boolean; matchCount: number };
  addTemplate: (name: string, path: string, description?: string) => void;
  removeTemplate: (id: string) => void;
  loadTemplates: () => void;
  saveTemplates: () => void;
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

function applyCharStyleToParagraph(
  paragraph: {
    charPrIdRef: string | null;
    runs: Array<{ charPrIdRef: string | null }>;
    applyCharFormatToRange: (startOffset: number, endOffset: number, charPrIdRef: string | number) => void;
  },
  selection: SelectionState,
  charPrIdRef: string | number,
): void {
  const start = selection.textStartOffset;
  const end = selection.textEndOffset;
  const hasRange =
    typeof start === "number" &&
    typeof end === "number" &&
    start !== end;

  if (hasRange) {
    paragraph.applyCharFormatToRange(
      Math.min(start, end),
      Math.max(start, end),
      charPrIdRef,
    );
    return;
  }

  // Apply to paragraph default and existing runs so already-written text updates immediately.
  paragraph.charPrIdRef = String(charPrIdRef);
  for (const run of paragraph.runs) {
    run.charPrIdRef = String(charPrIdRef);
  }
}

function applyCharStyleToCell(cell: { element: Element }, charPrIdRef: string | number): void {
  const charPr = String(charPrIdRef);
  const stack: Element[] = [cell.element];
  let paragraphFound = false;
  let runFound = false;
  let firstParagraph: Element | null = null;

  while (stack.length > 0) {
    const current = stack.shift()!;
    const local = current.localName ?? current.nodeName.split(":").pop() ?? "";
    if (local === "p") {
      paragraphFound = true;
      if (!firstParagraph) firstParagraph = current;
      current.setAttribute("charPrIDRef", charPr);
      current.setAttribute("charPrIdRef", charPr);
    } else if (local === "run") {
      runFound = true;
      current.setAttribute("charPrIDRef", charPr);
      current.setAttribute("charPrIdRef", charPr);
    }
    for (const child of Array.from(current.childNodes)) {
      if (child.nodeType === 1) stack.push(child as Element);
    }
  }

  if (paragraphFound && !runFound && firstParagraph) {
    const ns = firstParagraph.namespaceURI;
    const prefix = firstParagraph.prefix;
    const runName = prefix ? `${prefix}:run` : "run";
    const tName = prefix ? `${prefix}:t` : "t";
    const run = firstParagraph.ownerDocument.createElementNS(ns, runName);
    run.setAttribute("charPrIDRef", charPr);
    run.setAttribute("charPrIdRef", charPr);
    const text = firstParagraph.ownerDocument.createElementNS(ns, tName);
    run.appendChild(text);
    firstParagraph.appendChild(run);
  }
}

function applyCharStyleToTableSelection(
  table: {
    getCellMap: () => Array<Array<{ anchor: [number, number] } | undefined>>;
    iterGrid: () => Iterable<{ anchor: [number, number] }>;
    cell: (row: number, col: number) => { element: Element };
  },
  selection: SelectionState,
  charPrIdRef: string | number,
): void {
  const processed = new Set<string>();

  if (selection.type === "table") {
    for (const pos of table.iterGrid()) {
      const [ar, ac] = pos.anchor;
      const key = `${ar},${ac}`;
      if (processed.has(key)) continue;
      processed.add(key);
      applyCharStyleToCell(table.cell(ar, ac), charPrIdRef);
    }
    return;
  }

  if (selection.row == null || selection.col == null) return;
  const endRow = selection.endRow ?? selection.row;
  const endCol = selection.endCol ?? selection.col;
  const minRow = Math.min(selection.row, endRow);
  const maxRow = Math.max(selection.row, endRow);
  const minCol = Math.min(selection.col, endCol);
  const maxCol = Math.max(selection.col, endCol);
  const map = table.getCellMap();
  for (let r = minRow; r <= maxRow; r += 1) {
    for (let c = minCol; c <= maxCol; c += 1) {
      const pos = map[r]?.[c];
      if (!pos) continue;
      const [ar, ac] = pos.anchor;
      const key = `${ar},${ac}`;
      if (processed.has(key)) continue;
      processed.add(key);
      applyCharStyleToCell(table.cell(ar, ac), charPrIdRef);
    }
  }
}

function applyCharStyleToSelection(
  section: {
    paragraphs: Array<{
      charPrIdRef: string | null;
      runs: Array<{ charPrIdRef: string | null }>;
      applyCharFormatToRange: (startOffset: number, endOffset: number, charPrIdRef: string | number) => void;
      tables: Array<{
        getCellMap: () => Array<Array<{ anchor: [number, number] } | undefined>>;
        iterGrid: () => Iterable<{ anchor: [number, number] }>;
        cell: (row: number, col: number) => { element: Element };
      }>;
    }>;
  },
  selection: SelectionState,
  charPrIdRef: string | number,
): void {
  const para = section.paragraphs[selection.paragraphIndex];
  if (!para) return;

  if ((selection.type === "cell" || selection.type === "table") && selection.tableIndex != null) {
    const table = para.tables[selection.tableIndex];
    if (!table) return;
    applyCharStyleToTableSelection(table, selection, charPrIdRef);
    return;
  }

  applyCharStyleToParagraph(para, selection, charPrIdRef);
}

function redistributeTableColumns(
  table: {
    columnCount: number;
    getCellMap: () => Array<Array<{ cell: { width: number } } | undefined>>;
    setColumnWidth: (colIdx: number, width: number) => void;
  },
  targetWidth: number,
): void {
  const colCount = table.columnCount;
  if (colCount <= 0 || targetWidth <= 0) return;

  let currentWidths: number[] = [];
  try {
    const grid = table.getCellMap();
    for (let c = 0; c < colCount; c += 1) {
      const pos = grid[0]?.[c];
      currentWidths.push(pos ? Math.max(pos.cell.width, 0) : 0);
    }
  } catch {
    currentWidths = [];
  }

  let nextWidths: number[];
  const sum = currentWidths.reduce((a, b) => a + b, 0);
  if (sum > 0 && currentWidths.length === colCount) {
    nextWidths = currentWidths.map((w) => Math.max(Math.round((w / sum) * targetWidth), 1));
  } else {
    const base = Math.floor(targetWidth / colCount);
    let remainder = targetWidth - base * colCount;
    nextWidths = Array.from({ length: colCount }, () => {
      if (remainder > 0) {
        remainder -= 1;
        return base + 1;
      }
      return base;
    });
  }

  const allocated = nextWidths.reduce((a, b) => a + b, 0);
  const diff = targetWidth - allocated;
  if (nextWidths.length > 0 && diff !== 0) {
    nextWidths[nextWidths.length - 1] = Math.max(1, (nextWidths[nextWidths.length - 1] ?? 1) + diff);
  }

  for (let c = 0; c < colCount; c += 1) {
    table.setColumnWidth(c, nextWidths[c] ?? 1);
  }
}

type HeaderFooterPosition = "left" | "center" | "right";

type PageNumberPosition =
  | "none"
  | "header-left"
  | "header-center"
  | "header-right"
  | "footer-left"
  | "footer-center"
  | "footer-right";

const PARAGRAPH_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph";

function findFirstParagraphElement(root: Element): Element | null {
  const all = root.getElementsByTagName("*");
  for (let i = 0; i < all.length; i += 1) {
    const el = all.item(i);
    if (!el) continue;
    const localName = el.localName ?? el.nodeName.split(":").pop() ?? "";
    if (localName === "p") return el;
  }
  return null;
}

function applyHeaderFooterAlignment(
  doc: HwpxDocument,
  headerFooterElement: Element | null,
  position?: HeaderFooterPosition,
): void {
  if (!headerFooterElement || !position) return;
  const paragraph = findFirstParagraphElement(headerFooterElement);
  if (!paragraph) return;

  const alignment = position === "left" ? "LEFT" : position === "right" ? "RIGHT" : "CENTER";
  const baseParaPrId =
    paragraph.getAttribute("paraPrIDRef") ??
    paragraph.getAttribute("paraPrIdRef") ??
    paragraph.getAttribute("paraPrRef") ??
    undefined;
  const paraPrIdRef = doc.ensureParaStyle({
    alignment,
    baseParaPrId,
  });
  paragraph.setAttribute("paraPrIDRef", paraPrIdRef);
}

function pageNumPosFromUi(position: string): string {
  switch (position as PageNumberPosition) {
    case "header-left":
      return "TOP_LEFT";
    case "header-right":
      return "TOP_RIGHT";
    case "footer-left":
      return "BOTTOM_LEFT";
    case "footer-right":
      return "BOTTOM_RIGHT";
    case "footer-center":
      return "BOTTOM_CENTER";
    case "header-center":
    default:
      return "TOP_CENTER";
  }
}

function pageNumFormatFromUi(format?: string): string {
  switch (format) {
    case "roman-lower":
      return "ROMAN_LOWER";
    case "roman-upper":
      return "ROMAN";
    case "alpha-lower":
      return "ALPHA_LOWER";
    case "alpha-upper":
      return "ALPHA_UPPER";
    case "korean":
      return "KOREAN";
    case "hanja":
      return "HANJA";
    case "arabic":
    default:
      return "DIGIT";
  }
}

function findPageNumElement(sectionEl: Element): Element | null {
  const all = sectionEl.getElementsByTagName("*");
  for (let i = 0; i < all.length; i += 1) {
    const el = all.item(i);
    if (!el) continue;
    const localName = el.localName ?? el.nodeName.split(":").pop() ?? "";
    if (localName === "pageNum") return el;
  }
  return null;
}

function removePageNumElement(sectionEl: Element): boolean {
  const pageNumEl = findPageNumElement(sectionEl);
  if (!pageNumEl?.parentNode) return false;
  pageNumEl.parentNode.removeChild(pageNumEl);
  return true;
}

function ensurePageNumElement(sectionEl: Element): Element {
  const existing = findPageNumElement(sectionEl);
  if (existing) return existing;
  const created = sectionEl.ownerDocument.createElementNS(PARAGRAPH_NS, "hp:pageNum");
  sectionEl.appendChild(created);
  return created;
}

export const useEditorStore = create<EditorStore>((set, get) => ({
  doc: null,
  viewModel: null,
  revision: 0,
  selection: null,
  nestedTableFocus: null,
  activeFormat: { bold: false, italic: false, underline: false, strikethrough: false },
  undoStack: [],
  redoStack: [],
  templates: [],
  clipboardHistory: [],
  snippets: [],
  formatPainter: { active: false, locked: false, mode: "both", origin: null, snapshot: null },
  serverDocumentId: null,
  extendedFormat: { char: defaultCharFormat, para: defaultParaFormat },
  uiState: {
    sidebarOpen: true,
    sidebarTab: "char",
    showRuler: true,
    saveDialogOpen: false,
    charFormatDialogOpen: false,
    paraFormatDialogOpen: false,
    bulletNumberDialogOpen: false,
    charMapDialogOpen: false,
    templateDialogOpen: false,
    headerFooterDialogOpen: false,
    findReplaceDialogOpen: false,
    wordCountDialogOpen: false,
    pageNumberDialogOpen: false,
    styleDialogOpen: false,
    clipboardDialogOpen: false,
    captionDialogOpen: false,
    autoCorrectDialogOpen: false,
    outlineDialogOpen: false,
    shapeDialogOpen: false,
    tocDialogOpen: false,
    zoomLevel: 100,
  },
  loading: false,
  error: null,

  setDocument: (doc) => {
    const viewModel = buildViewModel(doc);
    set({
      doc,
      viewModel,
      revision: get().revision + 1,
      error: null,
      serverDocumentId: null,
    });
  },

  rebuild: () => {
    const { doc } = get();
    if (!doc) return;
    const viewModel = buildViewModel(doc);
    set({ viewModel, revision: get().revision + 1 });
  },

  setSelection: (selection) => {
    set((state) => {
      const focus = state.nestedTableFocus;
      const keepNestedFocus =
        selection != null &&
        focus != null &&
        selection.type === "cell" &&
        selection.sectionIndex === focus.sectionIndex &&
        selection.paragraphIndex === focus.paragraphIndex &&
        selection.tableIndex === focus.tableIndex &&
        selection.row === focus.row &&
        selection.col === focus.col;
      return {
        selection,
        nestedTableFocus: keepNestedFocus ? focus : null,
      };
    });
    get().maybeApplyFormatPainter(selection);
    // Auto-refresh extended format when selection changes
    if (selection) {
      // Use setTimeout to avoid synchronous read during render
      setTimeout(() => get().refreshExtendedFormat(), 0);
    }
  },

  focusNestedTableInCell: (nestedIndex = 0) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.type !== "cell") return;
    if (selection.tableIndex == null || selection.row == null || selection.col == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      const cell = table.cell(selection.row, selection.col);
      const nestedCount = countDescendantTables(cell.element);
      if (nestedCount <= 0) return;
      const normalizedIndex = Math.max(0, Math.min(nestedCount - 1, Math.floor(nestedIndex)));
      set({
        nestedTableFocus: {
          sectionIndex: selection.sectionIndex,
          paragraphIndex: selection.paragraphIndex,
          tableIndex: selection.tableIndex,
          row: selection.row,
          col: selection.col,
          nestedIndex: normalizedIndex,
        },
      });
    } catch (e) {
      console.error("focusNestedTableInCell failed:", e);
    }
  },

  focusParentTable: () => {
    const focus = get().nestedTableFocus;
    if (!focus) return;
    set({
      nestedTableFocus: null,
      selection: {
        sectionIndex: focus.sectionIndex,
        paragraphIndex: focus.paragraphIndex,
        type: "table",
        tableIndex: focus.tableIndex,
        objectType: "table",
      },
    });
  },

  setActiveFormat: (fmt) =>
    set((s) => ({ activeFormat: { ...s.activeFormat, ...fmt } })),

  refreshExtendedFormat: () => {
    const { doc, selection, viewModel } = get();
    if (!doc || !selection) return;
    try {
      const fmt = readFormatFromSelection(
        doc,
        selection.sectionIndex,
        selection.paragraphIndex,
      );

      if ((selection.type === "cell" || selection.type === "table") && selection.tableIndex != null) {
        const tableVm = viewModel?.sections[selection.sectionIndex]?.paragraphs[selection.paragraphIndex]?.tables[selection.tableIndex];
        if (tableVm) {
          let selectedCell =
            selection.row != null && selection.col != null
              ? tableVm.cells[selection.row]?.[selection.col]
              : null;
          if (!selectedCell || !selectedCell.isAnchor) {
            selectedCell = tableVm.cells.flat().find((cell) => cell.isAnchor) ?? null;
          }
          if (selectedCell) {
            fmt.char = {
              ...fmt.char,
              bold: selectedCell.bold,
              italic: selectedCell.italic,
              underline: selectedCell.underline,
              strikethrough: selectedCell.strikethrough,
              fontFamily: selectedCell.fontFamily ?? fmt.char.fontFamily,
              fontSize: selectedCell.fontSize ?? fmt.char.fontSize,
              textColor: selectedCell.textColor ?? fmt.char.textColor,
            };
          }
        }
      }

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

  toggleRuler: () =>
    set((s) => ({
      uiState: { ...s.uiState, showRuler: !s.uiState.showRuler },
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

  updateNestedTableCellText: (
    sectionIndex,
    paragraphIndex,
    tableIndex,
    row,
    col,
    nestedIndex,
    nestedRow,
    nestedCol,
    text,
  ) => {
    const { doc } = get();
    if (!doc) return;
    try {
      const section = doc.sections[sectionIndex];
      if (!section) return;
      const para = section.paragraphs[paragraphIndex];
      if (!para) return;
      const table = para.tables[tableIndex];
      if (!table) return;
      const targetCell = table.cell(row, col);
      const nestedTables = listTopLevelNestedTables(targetCell.element);
      const nestedTableElement = nestedTables[nestedIndex];
      if (!nestedTableElement) return;
      const nestedCellElement = findTableCellElementAt(nestedTableElement, nestedRow, nestedCol);
      if (!nestedCellElement) return;
      setTableCellElementText(nestedCellElement, text);
      markSectionDirty(para);
      get().rebuild();
    } catch (e) {
      console.error("updateNestedTableCellText failed:", e);
    }
  },

  updateNestedTableCellBackground: (
    sectionIndex,
    paragraphIndex,
    tableIndex,
    row,
    col,
    nestedIndex,
    startRow,
    startCol,
    endRow,
    endCol,
    color,
  ) => {
    const { doc } = get();
    if (!doc) return;
    try {
      const section = doc.sections[sectionIndex];
      if (!section) return;
      const para = section.paragraphs[paragraphIndex];
      if (!para) return;
      const table = para.tables[tableIndex];
      if (!table) return;
      const targetCell = table.cell(row, col);
      const nestedTables = listTopLevelNestedTables(targetCell.element);
      const nestedTableElement = nestedTables[nestedIndex];
      if (!nestedTableElement) return;

      get().pushUndo();

      const minRow = Math.min(startRow, endRow);
      const maxRow = Math.max(startRow, endRow);
      const minCol = Math.min(startCol, endCol);
      const maxCol = Math.max(startCol, endCol);
      const processed = new Set<Element>();
      let changed = false;

      for (let nestedRow = minRow; nestedRow <= maxRow; nestedRow += 1) {
        for (let nestedCol = minCol; nestedCol <= maxCol; nestedCol += 1) {
          const nestedCellElement = findTableCellElementAt(nestedTableElement, nestedRow, nestedCol);
          if (!nestedCellElement || processed.has(nestedCellElement)) continue;
          processed.add(nestedCellElement);
          changed =
            setTableCellElementBackground(doc, nestedTableElement, nestedRow, nestedCol, color)
            || changed;
        }
      }

      if (!changed) return;
      markSectionDirty(para);
      get().rebuild();
    } catch (e) {
      console.error("updateNestedTableCellBackground failed:", e);
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
      applyCharStyleToSelection(section, selection, charPrIdRef);
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
      applyCharStyleToSelection(section, selection, charPrIdRef);
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
      applyCharStyleToSelection(section, selection, charPrIdRef);
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
      applyCharStyleToSelection(section, selection, charPrIdRef);
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
      applyCharStyleToSelection(section, selection, charPrIdRef);
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
      applyCharStyleToSelection(section, selection, charPrIdRef);
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
      applyCharStyleToSelection(section, selection, charPrIdRef);
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
      applyCharStyleToSelection(section, selection, charPrIdRef);
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
      if (bulletId) para.outlineLevel = 1;
      get().rebuild();
      get().refreshExtendedFormat();
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
      para.bulletIdRef = null;
      para.outlineLevel = Math.max(1, Math.min(9, level));
      get().rebuild();
      get().refreshExtendedFormat();
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
      para.outlineLevel = Math.max(0, Math.min(9, level));
      if (level > 0) {
        // Keep hierarchy readable by increasing left margin per level.
        const marginLeft = (level - 1) * 2000;
        const paraPrIdRef = doc.ensureParaStyle({
          marginLeft,
          indent: 0,
          baseParaPrId: para.paraPrIdRef ?? undefined,
        });
        para.paraPrIdRef = paraPrIdRef;
      }
      get().rebuild();
      get().refreshExtendedFormat();
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
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("removeBulletNumbering failed:", e);
    }
  },

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
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("applyStyle failed:", e);
    }
  },

  applyStyleToDocument: (styleId) => {
    const { doc } = get();
    if (!doc) return;
    try {
      get().pushUndo();
      for (const section of doc.sections) {
        for (const para of section.paragraphs) {
          if (!para) continue;
          para.styleIdRef = styleId;
        }
      }
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("applyStyleToDocument failed:", e);
    }
  },

  insertToc: (opts) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sectionIndex = selection?.sectionIndex ?? 0;
    const paragraphIndex = selection?.paragraphIndex ?? 0;
    const targetSection = doc.sections[sectionIndex];
    if (!targetSection) return;

    try {
      get().pushUndo();

      const options = {
        title: opts.title ?? "차례",
        tabLeader: opts.tabLeader ?? "DOT",
        tabWidth: opts.tabWidth ?? 12000,
        maxLevel: opts.maxLevel ?? 9,
        showPageNumbers: opts.showPageNumbers ?? true,
      };

      const entries: Array<{ text: string; level: number; pageNumber: number }> = [];
      doc.sections.forEach((section, sIdx) => {
        section.paragraphs.forEach((para) => {
          const level = para.outlineLevel;
          const text = para.text.trim();
          if (level > 0 && level <= options.maxLevel && text) {
            entries.push({ text, level, pageNumber: sIdx + 1 });
          }
        });
      });

      doc.insertParagraphAt(sectionIndex, paragraphIndex, options.title);
      entries.forEach((entry, idx) => {
        const p = doc.insertParagraphAt(sectionIndex, paragraphIndex + idx + 1, entry.text);
        const paraPrIdRef = doc.ensureParaStyle({
          marginLeft: Math.max(0, (entry.level - 1) * 2000),
          indent: 0,
          baseParaPrId: p.paraPrIdRef ?? undefined,
        });
        p.paraPrIdRef = paraPrIdRef;
        if (options.showPageNumbers) {
          p.addTab({ width: options.tabWidth, tabLeader: options.tabLeader });
          p.addRun(String(entry.pageNumber));
        }
      });
      get().rebuild();
    } catch (e) {
      console.error("insertToc failed:", e);
    }
  },

  insertCaption: (opts) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sectionIndex = selection?.sectionIndex ?? 0;
    const paragraphIndex = selection?.paragraphIndex ?? 0;
    const section = doc.sections[sectionIndex];
    if (!section) return;

    try {
      get().pushUndo();
      const prefix = opts.kind === "table" ? "표" : "그림";
      const pattern = new RegExp(`^${prefix}\\s*(\\d+)\\b`);
      let max = 0;
      for (const para of doc.paragraphs) {
        const m = String(para.text ?? "").trim().match(pattern);
        if (!m) continue;
        const n = parseInt(m[1] ?? "0", 10);
        if (Number.isFinite(n)) max = Math.max(max, n);
      }
      const nextNumber = max + 1;
      const captionText = `${prefix} ${nextNumber}. ${String(opts.text ?? "").trim()}`.trim();
      doc.insertParagraphAt(sectionIndex, Math.min(section.paragraphs.length, paragraphIndex + 1), captionText);
      get().rebuild();
    } catch (e) {
      console.error("insertCaption failed:", e);
    }
  },

  insertCaptionList: (opts) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sectionIndex = selection?.sectionIndex ?? 0;
    const paragraphIndex = selection?.paragraphIndex ?? 0;
    const section = doc.sections[sectionIndex];
    if (!section) return;

    try {
      get().pushUndo();
      const prefix = opts.kind === "table" ? "표" : "그림";
      const title = opts.title ?? (opts.kind === "table" ? "표 목차" : "그림 목차");
      const pattern = new RegExp(`^${prefix}\\s*(\\d+)\\b`);
      const captions: string[] = [];
      for (const para of doc.paragraphs) {
        const t = String(para.text ?? "").trim();
        if (!t) continue;
        if (pattern.test(t)) captions.push(t);
      }

      doc.insertParagraphAt(sectionIndex, paragraphIndex, title);
      captions.forEach((cap, idx) => {
        doc.insertParagraphAt(sectionIndex, paragraphIndex + idx + 1, cap);
      });
      get().rebuild();
    } catch (e) {
      console.error("insertCaptionList failed:", e);
    }
  },

  findAndReplace: (search, replacement, count) => {
    const { doc } = get();
    if (!doc || !search) return 0;
    try {
      get().pushUndo();
      const replaced = doc.replaceText(search, replacement, count);
      if (replaced > 0) get().rebuild();
      return replaced;
    } catch (e) {
      console.error("findAndReplace failed:", e);
      return 0;
    }
  },

  findAndReplaceAdvanced: (opts) => {
    const { doc, selection } = get();
    if (!doc) return 0;
    const search = String(opts.search ?? "");
    if (!search) return 0;

    const scope = opts.scope ?? "document";
    const matchCase = Boolean(opts.matchCase);
    const useRegex = Boolean(opts.useRegex);
    const wholeWord = Boolean(opts.wholeWord);
    let remaining = opts.count ?? Infinity;
    let total = 0;

    const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const source = useRegex ? search : escape(search);
    const wrapped = wholeWord ? `\\b(?:${source})\\b` : source;
    const flags = `${matchCase ? "" : "i"}g`;
    const pattern = new RegExp(wrapped, flags);
    const replacement = String(opts.replacement ?? "");

    try {
      get().pushUndo();

      const paragraphsByScope = (() => {
        if (!selection) return doc.paragraphs;
        if (scope === "paragraph" || scope === "selection") {
          const section = doc.sections[selection.sectionIndex];
          const para = section?.paragraphs[selection.paragraphIndex];
          return para ? [para] : [];
        }
        return doc.paragraphs;
      })();

      for (const para of paragraphsByScope as any[]) {
        if (remaining <= 0) break;

        if (scope === "selection" && selection?.type === "paragraph") {
          const full = String(para.text ?? "");
          const start = selection.textStartOffset;
          const end = selection.textEndOffset;
          if (typeof start !== "number" || typeof end !== "number" || start === end) continue;
          const a = Math.max(0, Math.min(full.length, Math.min(start, end)));
          const b = Math.max(0, Math.min(full.length, Math.max(start, end)));
          const before = full.slice(0, a);
          const mid = full.slice(a, b);
          const after = full.slice(b);

          pattern.lastIndex = 0;
          let replacedLocal = 0;
          const replacedMid = mid.replace(pattern, (m, ...args) => {
            if (remaining <= 0) return m;
            remaining -= 1;
            replacedLocal += 1;
            total += 1;
            return replacementFromMatchTemplate(replacement, m, args);
          });
          if (replacedLocal > 0) {
            para.text = before + replacedMid + after;
          }
          continue;
        }

        for (const run of para.runs as any[]) {
          if (remaining <= 0) break;
          if (useRegex || wholeWord || !matchCase) {
            if (typeof run.replaceTextRegex === "function") {
              const n = run.replaceTextRegex(pattern, replacement, remaining);
              total += n;
              remaining -= n;
            } else {
              // Fallback: treat run.text as the only text node.
              const text = String(run.text ?? "");
              pattern.lastIndex = 0;
              let local = 0;
              const next = text.replace(pattern, (m, ...args) => {
                if (remaining <= 0) return m;
                remaining -= 1;
                local += 1;
                total += 1;
                return replacementFromMatchTemplate(replacement, m, args);
              });
              if (local > 0) run.text = next;
            }
          } else if (typeof run.replaceText === "function") {
            const n = run.replaceText(search, replacement, remaining);
            total += n;
            remaining -= n;
          }
        }
      }

      if (total > 0) get().rebuild();
      return total;
    } catch (e) {
      console.error("findAndReplaceAdvanced failed:", e);
      return total;
    }
  },

  findNextMatch: (opts) => {
    const { doc, selection } = get();
    if (!doc || !selection) return { found: false, matchCount: 0 };
    const search = String(opts.search ?? "");
    if (!search) return { found: false, matchCount: 0 };

    const scope = opts.scope ?? "document";
    const matchCase = Boolean(opts.matchCase);
    const useRegex = Boolean(opts.useRegex);
    const wholeWord = Boolean(opts.wholeWord);
    const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const source = useRegex ? search : escape(search);
    const wrapped = wholeWord ? `\\b(?:${source})\\b` : source;
    const flags = `${matchCase ? "" : "i"}g`;
    const pattern = new RegExp(wrapped, flags);

    const section = doc.sections[selection.sectionIndex];
    if (!section) return { found: false, matchCount: 0 };

    const paragraphIndices =
      scope === "paragraph"
        ? [selection.paragraphIndex]
        : Array.from({ length: section.paragraphs.length }, (_, i) => i);

    const countMatches = (text: string) => {
      let count = 0;
      pattern.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = pattern.exec(text))) {
        count += 1;
        if (m[0].length === 0) pattern.lastIndex += 1;
      }
      return count;
    };
    const matchCount = paragraphIndices.reduce((sum, idx) => {
      const t = String(section.paragraphs[idx]?.text ?? "");
      return sum + countMatches(t);
    }, 0);

    const startOffset = selection.cursorOffset ?? selection.textEndOffset ?? 0;

    const findInParagraph = (text: string, from: number) => {
      pattern.lastIndex = Math.max(0, Math.min(text.length, from));
      const m = pattern.exec(text);
      if (!m) return null;
      return { start: m.index, end: m.index + m[0].length };
    };

    const startIndexInList = paragraphIndices.indexOf(selection.paragraphIndex);
    const ordered = startIndexInList >= 0
      ? paragraphIndices.slice(startIndexInList).concat(paragraphIndices.slice(0, startIndexInList))
      : paragraphIndices;

    for (let pass = 0; pass < 2; pass += 1) {
      for (const idx of ordered) {
        const text = String(section.paragraphs[idx]?.text ?? "");
        const from = pass === 0 && idx === selection.paragraphIndex ? startOffset + 1 : 0;
        const m = findInParagraph(text, from);
        if (!m) continue;
        get().setSelection({
          sectionIndex: selection.sectionIndex,
          paragraphIndex: idx,
          type: "paragraph",
          textStartOffset: m.start,
          textEndOffset: m.end,
          cursorOffset: m.end,
        });
        return { found: true, matchCount };
      }
    }
    return { found: false, matchCount };
  },

  insertShape: (shapeType, widthMm, heightMm) => {
    const { doc, selection } = get();
    if (!doc) return;
    try {
      get().pushUndo();
      const sectionIndex = selection?.sectionIndex ?? 0;
      const para = doc.addParagraph("", { sectionIndex });
      const width = mmToHwp(Math.max(5, widthMm));
      const height = mmToHwp(Math.max(5, heightMm));
      // NOTE: hwpx-core currently exposes text box drawing, so shape insertion
      // is represented as a text-box based primitive for now.
      if (shapeType === "line") {
        para.addTextBox("─", { width, height: mmToHwp(5), borderColor: "#000000", fillColor: "#FFFFFF" });
      } else if (shapeType === "arrow") {
        para.addTextBox("→", { width, height: mmToHwp(8), borderColor: "#000000", fillColor: "#FFFFFF" });
      } else if (shapeType === "ellipse") {
        para.addTextBox("◯", { width, height, borderColor: "#000000", fillColor: "#FFFFFF" });
      } else {
        para.addTextBox("", { width, height, borderColor: "#000000", fillColor: "#FFFFFF" });
      }
      get().rebuild();
    } catch (e) {
      console.error("insertShape failed:", e);
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

  insertChart: (opts) => {
    const { doc, selection } = get();
    if (!doc) return;
    try {
      get().pushUndo();

      const sectionIndex = selection?.sectionIndex ?? 0;
      const section = doc.sections[sectionIndex];
      if (!section) return;

      const baseParagraphIndex =
        selection?.paragraphIndex ?? (section.paragraphs.length > 0 ? section.paragraphs.length - 1 : -1);
      const safeBaseParagraphIndex = Math.max(-1, Math.min(section.paragraphs.length - 1, baseParagraphIndex));
      const insertAt = safeBaseParagraphIndex + 1;

      const title = String(opts?.title ?? "").trim() || "차트";
      const chartType = opts?.chartType === "line" ? "line" : "bar";
      const rawCategories = (opts?.categories ?? []).map((v) => String(v ?? "").trim()).filter(Boolean);
      const rawValues = (opts?.values ?? [])
        .map((v) => (Number.isFinite(v) ? Number(v) : NaN))
        .filter((v) => Number.isFinite(v)) as number[];

      const defaultCategories = ["항목 1", "항목 2", "항목 3"];
      const defaultValues = [100, 80, 60];

      const rowCount = Math.max(
        1,
        Math.min(
          12,
          Math.max(
            rawCategories.length,
            rawValues.length,
            3,
          ),
        ),
      );

      const categories = Array.from({ length: rowCount }, (_v, idx) => rawCategories[idx] ?? defaultCategories[idx] ?? `항목 ${idx + 1}`);
      const values = Array.from({ length: rowCount }, (_v, idx) => rawValues[idx] ?? defaultValues[idx] ?? 0);

      const chartParagraph = doc.insertParagraphAt(sectionIndex, insertAt, `[차트:${chartType}] ${title}`);
      chartParagraph.addTable(rowCount + 1, 2);
      const tableIndex = Math.max(0, chartParagraph.tables.length - 1);
      const table = chartParagraph.tables[tableIndex];
      if (!table) {
        get().rebuild();
        return;
      }

      table.setCellText(0, 0, "항목");
      table.setCellText(0, 1, "값");
      for (let i = 0; i < rowCount; i += 1) {
        table.setCellText(i + 1, 0, categories[i]!);
        table.setCellText(i + 1, 1, String(values[i]!));
      }

      set({
        selection: {
          sectionIndex,
          paragraphIndex: insertAt,
          type: "cell",
          tableIndex,
          row: 1,
          col: 1,
          objectType: "table",
        },
      });

      get().rebuild();
    } catch (e) {
      console.error("insertChart failed:", e);
    }
  },

  insertImage: (data, mediaType, widthMm, heightMm) => {
    const { doc, selection } = get();
    if (!doc) return;
    try {
      const sectionIndex = selection?.sectionIndex ?? 0;
      const imageParagraph = doc.addImage(data, { mediaType, widthMm, heightMm, sectionIndex });
      const section = doc.sections[sectionIndex];
      const paragraphIndex = section?.paragraphs.findIndex((p) => p.element === imageParagraph.element) ?? -1;
      if (paragraphIndex >= 0) {
        set({
          selection: {
            sectionIndex,
            paragraphIndex,
            type: "paragraph",
            objectType: "image",
            imageIndex: 0,
          },
        });
      }
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

  setImageTextWrap: (textWrap) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      para.setPictureTextWrap(imgIdx, textWrap);
      get().rebuild();
    } catch (e) {
      console.error("setImageTextWrap failed:", e);
    }
  },

  setImageTreatAsChar: (treatAsChar) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      para.setPicturePosition(imgIdx, { treatAsChar });
      get().rebuild();
    } catch (e) {
      console.error("setImageTreatAsChar failed:", e);
    }
  },

  setImageOffsets: (offsets) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      para.setPicturePosition(imgIdx, {
        horzOffset: offsets.horzMm != null ? mmToHwp(offsets.horzMm) : undefined,
        vertOffset: offsets.vertMm != null ? mmToHwp(offsets.vertMm) : undefined,
      });
      get().rebuild();
    } catch (e) {
      console.error("setImageOffsets failed:", e);
    }
  },

  setImageOffsetRelTo: (relTo) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      para.setPicturePosition(imgIdx, {
        horzRelTo: relTo.horzRelTo,
        vertRelTo: relTo.vertRelTo,
      });
      get().rebuild();
    } catch (e) {
      console.error("setImageOffsetRelTo failed:", e);
    }
  },

  setImageSizeProtect: (protect) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      const paraAny = para as unknown as {
        setPictureSizeProtected?: (index: number, value: boolean) => void;
      };
      paraAny.setPictureSizeProtected?.(imgIdx, protect);

      // Fallback path when runtime core build does not expose setPictureSizeProtected.
      const pic = getPictureElement(para, imgIdx);
      if (pic) {
        const sz = ensureDirectChildByLocalName(pic, "sz");
        if (!sz.hasAttribute("width")) {
          const curSz = findDirectChildByLocalName(pic, "curSz");
          sz.setAttribute("width", curSz?.getAttribute("width") ?? "1");
          sz.setAttribute("height", curSz?.getAttribute("height") ?? "1");
          sz.setAttribute("widthRelTo", "ABSOLUTE");
          sz.setAttribute("heightRelTo", "ABSOLUTE");
        }
        sz.setAttribute("protect", protect ? "1" : "0");
        markSectionDirty(para);
      }
      get().rebuild();
    } catch (e) {
      console.error("setImageSizeProtect failed:", e);
    }
  },

  setImageScale: (scaleXPercent, scaleYPercent) => {
    const { doc, selection, viewModel } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    const image = viewModel?.sections[selection.sectionIndex]?.paragraphs[selection.paragraphIndex]?.images[imgIdx];
    if (!image) return;
    try {
      const baseWidth = image.originalWidthHwp > 0 ? image.originalWidthHwp : image.widthHwp;
      const baseHeight = image.originalHeightHwp > 0 ? image.originalHeightHwp : image.heightHwp;
      const nextWidth = Math.max(Math.round(baseWidth * (Math.max(scaleXPercent, 1) / 100)), 1);
      const nextHeight = Math.max(Math.round(baseHeight * (Math.max(scaleYPercent, 1) / 100)), 1);
      get().pushUndo();
      para.setPictureSize(imgIdx, nextWidth, nextHeight);
      get().rebuild();
    } catch (e) {
      console.error("setImageScale failed:", e);
    }
  },

  setImageCrop: (crop) => {
    const { doc, selection, viewModel } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    const image = viewModel?.sections[selection.sectionIndex]?.paragraphs[selection.paragraphIndex]?.images[imgIdx];
    if (!image) return;
    try {
      const width = Math.max(image.widthHwp, 1);
      const height = Math.max(image.heightHwp, 1);
      const left = crop.leftMm != null ? mmToHwp(crop.leftMm) : image.cropLeftHwp;
      const right = crop.rightMm != null ? mmToHwp(crop.rightMm) : image.cropRightHwp;
      const top = crop.topMm != null ? mmToHwp(crop.topMm) : image.cropTopHwp;
      const bottom = crop.bottomMm != null ? mmToHwp(crop.bottomMm) : image.cropBottomHwp;

      const clipLeft = Math.max(0, Math.min(left, width - 1));
      const clipRight = Math.max(clipLeft + 1, Math.min(width - right, width));
      const clipTop = Math.max(0, Math.min(top, height - 1));
      const clipBottom = Math.max(clipTop + 1, Math.min(height - bottom, height));

      get().pushUndo();
      const nextClip = {
        left: clipLeft,
        right: clipRight,
        top: clipTop,
        bottom: clipBottom,
      };
      const paraAny = para as unknown as {
        setPictureClip?: (
          index: number,
          clip: { left: number; right: number; top: number; bottom: number },
        ) => void;
      };
      paraAny.setPictureClip?.(imgIdx, nextClip);

      const pic = getPictureElement(para, imgIdx);
      if (pic) {
        const clip = ensureDirectChildByLocalName(pic, "imgClip");
        clip.setAttribute("left", String(nextClip.left));
        clip.setAttribute("right", String(nextClip.right));
        clip.setAttribute("top", String(nextClip.top));
        clip.setAttribute("bottom", String(nextClip.bottom));
        markSectionDirty(para);
      }
      get().rebuild();
    } catch (e) {
      console.error("setImageCrop failed:", e);
    }
  },

  setImageAdjustment: (adjust) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      const normalized = {
        bright: adjust.brightness,
        contrast: adjust.contrast,
        effect: adjust.effect,
        alpha: adjust.alpha,
      };
      const paraAny = para as unknown as {
        setPictureImageAdjust?: (
          index: number,
          adjust: {
            bright?: number;
            contrast?: number;
            effect?: string;
            alpha?: number;
          },
        ) => void;
      };
      paraAny.setPictureImageAdjust?.(imgIdx, normalized);

      const pic = getPictureElement(para, imgIdx);
      const img = pic ? findDescendantByLocalName(pic, "img") : null;
      if (img) {
        if (normalized.bright != null) img.setAttribute("bright", String(Math.round(normalized.bright)));
        if (normalized.contrast != null) img.setAttribute("contrast", String(Math.round(normalized.contrast)));
        if (normalized.effect != null) img.setAttribute("effect", normalized.effect);
        if (normalized.alpha != null) img.setAttribute("alpha", String(Math.round(normalized.alpha)));
        markSectionDirty(para);
      }
      get().rebuild();
    } catch (e) {
      console.error("setImageAdjustment failed:", e);
    }
  },

  setImageRotation: (angle) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      const paraAny = para as unknown as {
        setPictureRotationAngle?: (index: number, value: number) => void;
      };
      paraAny.setPictureRotationAngle?.(imgIdx, angle);

      const pic = getPictureElement(para, imgIdx);
      if (pic) {
        const rot = ensureDirectChildByLocalName(pic, "rotationInfo");
        rot.setAttribute("angle", String(Math.round(angle)));
        if (!rot.hasAttribute("centerX") || !rot.hasAttribute("centerY")) {
          const curSz = findDirectChildByLocalName(pic, "curSz");
          const width = parseInt(curSz?.getAttribute("width") ?? "1", 10);
          const height = parseInt(curSz?.getAttribute("height") ?? "1", 10);
          rot.setAttribute("centerX", String(Math.floor(width / 2)));
          rot.setAttribute("centerY", String(Math.floor(height / 2)));
          if (!rot.hasAttribute("rotateimage")) rot.setAttribute("rotateimage", "1");
        }
        markSectionDirty(para);
      }
      get().rebuild();
    } catch (e) {
      console.error("setImageRotation failed:", e);
    }
  },

  setImageLock: (locked) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.objectType !== "image") return;
    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const imgIdx = selection.imageIndex ?? 0;
    try {
      get().pushUndo();
      const paraAny = para as unknown as {
        setPictureLock?: (index: number, value: boolean) => void;
      };
      paraAny.setPictureLock?.(imgIdx, locked);

      const pic = getPictureElement(para, imgIdx);
      if (pic) {
        pic.setAttribute("lock", locked ? "1" : "0");
        markSectionDirty(para);
      }
      get().rebuild();
    } catch (e) {
      console.error("setImageLock failed:", e);
    }
  },

  deleteSelectedObject: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;

    // Selected table object
    if (selection.type === "table") {
      get().deleteTable();
      return;
    }

    const section = doc.sections[selection.sectionIndex];
    if (!section) return;
    const para = section.paragraphs[selection.paragraphIndex];
    if (!para) return;

    try {
      if (selection.objectType === "image") {
        const imgIdx = selection.imageIndex ?? 0;
        get().pushUndo();
        para.removePicture(imgIdx);
        set({
          selection: {
            sectionIndex: selection.sectionIndex,
            paragraphIndex: selection.paragraphIndex,
            type: "paragraph",
          },
        });
        get().rebuild();
        return;
      }

      if (selection.objectType === "textBox") {
        const textBoxIdx = selection.textBoxIndex ?? 0;
        get().pushUndo();
        para.removeTextBox(textBoxIdx);
        set({
          selection: {
            sectionIndex: selection.sectionIndex,
            paragraphIndex: selection.paragraphIndex,
            type: "paragraph",
          },
        });
        get().rebuild();
      }
    } catch (e) {
      console.error("deleteSelectedObject failed:", e);
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
      const targetWidth = mmToHwp(widthMm);
      const targetHeight = mmToHwp(heightMm);
      table.setSize(targetWidth, targetHeight);
      redistributeTableColumns(table, targetWidth);

      get().rebuild();
    } catch (e) {
      console.error("setTableSize failed:", e);
    }
  },

  setTableOutMargin: (margins) => {
    const { doc, selection, viewModel } = get();
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

      // Keep table within body width when horizontal outer margins increase.
      // This prevents right-side clipping and keeps all columns visible by
      // compressing column widths proportionally.
      const sectionVm = viewModel?.sections[selection.sectionIndex];
      if (sectionVm) {
        const bodyWidthPx = sectionVm.pageWidthPx - sectionVm.marginLeftPx - sectionVm.marginRightPx;
        const bodyWidthHwp = pxToHwp(Math.max(bodyWidthPx, 0));
        const nextOut = table.getOutMargin();
        const maxTableWidth = Math.max(bodyWidthHwp - nextOut.left - nextOut.right, 200);
        if (table.width > maxTableWidth) {
          table.setSize(maxTableWidth, table.height);
          redistributeTableColumns(table, maxTableWidth);
        }
      }
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
        marginRight: pf.indentRight,
        marginBefore: pf.spacingBefore,
        marginAfter: pf.spacingAfter,
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
        marginRight: pf.indentRight,
        indent: pf.firstLineIndent,
        marginBefore: pf.spacingBefore,
        marginAfter: pf.spacingAfter,
        baseParaPrId: para.paraPrIdRef ?? undefined,
      });
      para.paraPrIdRef = paraPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setLeftIndent failed:", e);
    }
  },

  setRightIndent: (valueHwp) => {
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
        marginLeft: pf.indentLeft,
        marginRight: valueHwp,
        indent: pf.firstLineIndent,
        marginBefore: pf.spacingBefore,
        marginAfter: pf.spacingAfter,
        baseParaPrId: para.paraPrIdRef ?? undefined,
      });
      para.paraPrIdRef = paraPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setRightIndent failed:", e);
    }
  },

  setParagraphSpacingBefore: (valueHwp) => {
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
        marginLeft: pf.indentLeft,
        marginRight: pf.indentRight,
        indent: pf.firstLineIndent,
        marginBefore: valueHwp,
        marginAfter: pf.spacingAfter,
        baseParaPrId: para.paraPrIdRef ?? undefined,
      });
      para.paraPrIdRef = paraPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setParagraphSpacingBefore failed:", e);
    }
  },

  setParagraphSpacingAfter: (valueHwp) => {
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
        marginLeft: pf.indentLeft,
        marginRight: pf.indentRight,
        indent: pf.firstLineIndent,
        marginBefore: pf.spacingBefore,
        marginAfter: valueHwp,
        baseParaPrId: para.paraPrIdRef ?? undefined,
      });
      para.paraPrIdRef = paraPrIdRef;
      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("setParagraphSpacingAfter failed:", e);
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
        const removed = removePageNumElement(section.element);
        if (removed) section.markDirty();
        // Remove page number text fallback.
        props.setHeaderText("");
        props.setFooterText("");
      } else {
        // pageNum node drives position/format; clear text fallback to avoid double rendering.
        props.setHeaderText("");
        props.setFooterText("");
        const pageNumEl = ensurePageNumElement(section.element);
        pageNumEl.setAttribute("pos", pageNumPosFromUi(opts.position));
        pageNumEl.setAttribute("formatType", pageNumFormatFromUi(opts.format));
        pageNumEl.setAttribute("sideChar", "-");
        section.markDirty();
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
        // Add a sub-paragraph with default text
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

  setColumnCount: (colCount, gapMm = 8) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sIdx = selection?.sectionIndex ?? 0;
    const section = doc.sections[sIdx];
    if (!section) return;
    try {
      get().pushUndo();
      section.properties.setColumnLayout({
        colCount: Math.max(1, Math.min(12, colCount)),
        sameGap: mmToHwp(Math.max(0, gapMm)),
      });
      get().rebuild();
    } catch (e) {
      console.error("setColumnCount failed:", e);
    }
  },

  setHeaderFooter: ({ headerText, footerText, headerPosition, footerPosition }) => {
    const { doc, selection } = get();
    if (!doc) return;
    const sIdx = selection?.sectionIndex ?? 0;
    const section = doc.sections[sIdx];
    if (!section) return;
    try {
      get().pushUndo();
      if (headerText != null) {
        const header = section.properties.setHeaderText(headerText);
        applyHeaderFooterAlignment(doc, header.element, headerPosition);
      } else if (headerPosition) {
        const existing = section.properties.getHeader("BOTH");
        applyHeaderFooterAlignment(doc, existing?.element ?? null, headerPosition);
      }
      if (footerText != null) {
        const footer = section.properties.setFooterText(footerText);
        applyHeaderFooterAlignment(doc, footer.element, footerPosition);
      } else if (footerPosition) {
        const existing = section.properties.getFooter("BOTH");
        applyHeaderFooterAlignment(doc, existing?.element ?? null, footerPosition);
      }
      get().rebuild();
    } catch (e) {
      console.error("setHeaderFooter failed:", e);
    }
  },

  // Table structure operations
  insertNestedTableInCell: (rows, cols) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.row == null || selection.col == null) return;
    try {
      const safeRows = Math.max(1, Math.min(20, Math.floor(rows)));
      const safeCols = Math.max(1, Math.min(20, Math.floor(cols)));
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      const targetCell = table.cell(selection.row, selection.col);
      const borderFillIdRef =
        targetCell.borderFillIDRef
        ?? table.borderFillIDRef
        ?? doc.ensureBasicBorderFill();
      targetCell.addTable(safeRows, safeCols, { borderFillIdRef });
      set({
        selection: {
          ...selection,
          type: "cell",
          endRow: undefined,
          endCol: undefined,
          objectType: "table",
        },
      });
      get().rebuild();
    } catch (e) {
      console.error("insertNestedTableInCell failed:", e);
    }
  },

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

  moveTableRow: (direction) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.row == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      const para = section?.paragraphs[selection.paragraphIndex];
      const table = para?.tables[selection.tableIndex];
      if (!table) return;

      const rowCount = table.rowCount;
      const src = selection.row;
      const dst = direction === "up" ? src - 1 : src + 1;
      if (dst < 0 || dst >= rowCount) return;

      // Restrict to non-merged tables (rowSpan/colSpan 모두 1)
      for (const pos of table.iterGrid()) {
        if (pos.span[0] !== 1 || pos.span[1] !== 1) {
          throw new Error("moveTableRow currently supports non-merged tables only");
        }
      }

      get().pushUndo();

      const trEls = Array.from(table.element.childNodes).filter(
        (n): n is Element => n.nodeType === 1 && elementLocalName(n as Element) === "tr",
      );
      const trA = trEls[src];
      const trB = trEls[dst];
      if (!trA || !trB) return;

      const parent = trA.parentNode;
      if (!parent) return;
      const marker = table.element.ownerDocument.createElement("hwpx-row-marker");
      parent.insertBefore(marker, trA);
      parent.replaceChild(trA, trB);
      parent.replaceChild(trB, marker);

      // Re-index rowAddr based on DOM row order
      const nextTrEls = Array.from(table.element.childNodes).filter(
        (n): n is Element => n.nodeType === 1 && elementLocalName(n as Element) === "tr",
      );
      for (let r = 0; r < nextTrEls.length; r += 1) {
        const tr = nextTrEls[r]!;
        const tcs = Array.from(tr.childNodes).filter(
          (n): n is Element => n.nodeType === 1 && elementLocalName(n as Element) === "tc",
        );
        for (const tc of tcs) {
          const addr = findDescendantByLocalName(tc, "cellAddr");
          if (!addr) continue;
          addr.setAttribute("rowAddr", String(r));
        }
      }

      set({
        selection: { ...selection, row: dst, endRow: undefined, endCol: undefined },
      });
      get().rebuild();
    } catch (e) {
      console.error("moveTableRow failed:", e);
    }
  },

  moveTableColumn: (direction) => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null || selection.col == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      const para = section?.paragraphs[selection.paragraphIndex];
      const table = para?.tables[selection.tableIndex];
      if (!table) return;

      const colCount = table.columnCount;
      const src = selection.col;
      const dst = direction === "left" ? src - 1 : src + 1;
      if (dst < 0 || dst >= colCount) return;

      for (const pos of table.iterGrid()) {
        if (pos.span[0] !== 1 || pos.span[1] !== 1) {
          throw new Error("moveTableColumn currently supports non-merged tables only");
        }
      }

      get().pushUndo();

      // Swap colAddr for all cells, then reorder <tc> nodes in each <tr>.
      const trEls = Array.from(table.element.childNodes).filter(
        (n): n is Element => n.nodeType === 1 && elementLocalName(n as Element) === "tr",
      );
      for (const tr of trEls) {
        const tcs = Array.from(tr.childNodes).filter(
          (n): n is Element => n.nodeType === 1 && elementLocalName(n as Element) === "tc",
        );

        for (const tc of tcs) {
          const addr = findDescendantByLocalName(tc, "cellAddr");
          if (!addr) continue;
          const c = parseInt(addr.getAttribute("colAddr") ?? "0", 10);
          if (c === src) addr.setAttribute("colAddr", String(dst));
          else if (c === dst) addr.setAttribute("colAddr", String(src));
        }

        const sorted = tcs
          .slice()
          .sort((a, b) => {
            const aAddr = findDescendantByLocalName(a, "cellAddr");
            const bAddr = findDescendantByLocalName(b, "cellAddr");
            const ac = parseInt(aAddr?.getAttribute("colAddr") ?? "0", 10);
            const bc = parseInt(bAddr?.getAttribute("colAddr") ?? "0", 10);
            return ac - bc;
          });

        for (const tc of sorted) {
          tr.appendChild(tc);
        }
      }

      set({
        selection: { ...selection, col: dst, endRow: undefined, endCol: undefined },
      });
      get().rebuild();
    } catch (e) {
      console.error("moveTableColumn failed:", e);
    }
  },

  distributeTableColumns: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      const para = section?.paragraphs[selection.paragraphIndex];
      const table = para?.tables[selection.tableIndex];
      if (!table) return;

      for (const pos of table.iterGrid()) {
        if (pos.span[0] !== 1 || pos.span[1] !== 1) {
          throw new Error("distributeTableColumns currently supports non-merged tables only");
        }
      }

      const colCount = table.columnCount;
      if (colCount <= 0) return;

      get().pushUndo();

      const totalWidth = table.width > 0
        ? table.width
        : (() => {
            let sum = 0;
            for (let colIdx = 0; colIdx < colCount; colIdx += 1) {
              try {
                sum += table.cell(0, colIdx).width;
              } catch {
                // ignore invalid cells
              }
            }
            return sum;
          })();
      const each = Math.floor(Math.max(totalWidth, 0) / colCount);

      for (let c = 0; c < colCount; c += 1) {
        table.setColumnWidth(c, each);
      }
      get().rebuild();
    } catch (e) {
      console.error("distributeTableColumns failed:", e);
    }
  },

  distributeTableRows: () => {
    const { doc, selection } = get();
    if (!doc || !selection || selection.tableIndex == null) return;
    try {
      const section = doc.sections[selection.sectionIndex];
      const para = section?.paragraphs[selection.paragraphIndex];
      const table = para?.tables[selection.tableIndex];
      if (!table) return;

      for (const pos of table.iterGrid()) {
        if (pos.span[0] !== 1 || pos.span[1] !== 1) {
          throw new Error("distributeTableRows currently supports non-merged tables only");
        }
      }

      const rowCount = table.rowCount;
      const colCount = table.columnCount;
      if (rowCount <= 0 || colCount <= 0) return;

      get().pushUndo();

      const totalHeight = table.height > 0
        ? table.height
        : (() => {
            let sum = 0;
            for (let rowIdx = 0; rowIdx < rowCount; rowIdx += 1) {
              try {
                sum += table.cell(rowIdx, 0).height;
              } catch {
                // ignore invalid cells
              }
            }
            return sum;
          })();
      const each = Math.floor(Math.max(totalHeight, 0) / rowCount);

      for (let r = 0; r < rowCount; r += 1) {
        for (let c = 0; c < colCount; c += 1) {
          table.cell(r, c).setSize(undefined, each);
        }
      }
      get().rebuild();
    } catch (e) {
      console.error("distributeTableRows failed:", e);
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
    try {
      get().pushUndo();
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;
      const table = para.tables[selection.tableIndex];
      if (!table) return;
      let targetRow = selection.row ?? selection.endRow ?? null;
      let targetCol = selection.col ?? selection.endCol ?? null;

      if (targetRow == null || targetCol == null) {
        const map = table.getCellMap();
        outer: for (let r = 0; r < map.length; r += 1) {
          const row = map[r];
          if (!row) continue;
          for (let c = 0; c < row.length; c += 1) {
            const pos = row[c];
            if (!pos) continue;
            const [ar, ac] = pos.anchor;
            const [sr, sc] = pos.span;
            if (ar === r && ac === c && (sr > 1 || sc > 1)) {
              targetRow = ar;
              targetCol = ac;
              break outer;
            }
          }
        }
      }

      if (targetRow == null || targetCol == null) return;
      const anchorPos = table.getCellMap()[targetRow]?.[targetCol];
      if (anchorPos) {
        targetRow = anchorPos.anchor[0];
        targetCol = anchorPos.anchor[1];
      }
      table.splitCell(targetRow, targetCol);
      set({
        selection: {
          ...selection,
          type: "cell",
          row: targetRow,
          col: targetCol,
          endRow: undefined,
          endCol: undefined,
        },
      });
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
      const section = doc.sections[selection.sectionIndex];
      if (!section) return;
      const para = section.paragraphs[selection.paragraphIndex];
      if (!para) return;

      const table = para.tables[selection.tableIndex];
      if (!table) return;
      table.remove();

      const remainingTables = para.tables;
      if (remainingTables.length > 0) {
        const nextTableIndex = Math.min(selection.tableIndex, remainingTables.length - 1);
        set({
          selection: {
            sectionIndex: selection.sectionIndex,
            paragraphIndex: selection.paragraphIndex,
            type: "table",
            tableIndex: nextTableIndex,
            objectType: "table",
          },
        });
      } else {
        set({
          selection: {
            sectionIndex: selection.sectionIndex,
            paragraphIndex: selection.paragraphIndex,
            type: "paragraph",
          },
        });
      }
      get().rebuild();
    } catch (e) {
      console.error("deleteTable failed:", e);
    }
  },

  // File operations
  newDocument: async () => {
    try {
      set({ loading: true, error: null });
      const doc = await createNewDocument();
      get().setDocument(doc);
      set({ selection: { sectionIndex: 0, paragraphIndex: 0, type: "paragraph" } });
    } catch (e) {
      console.error("newDocument failed:", e);
      set({ error: "새 문서를 생성하지 못했습니다." });
    } finally {
      set({ loading: false });
    }
  },

  openDocument: async (data) => {
    try {
      set({ loading: true, error: null });
      const doc = await HwpxDocument.open(data);
      get().setDocument(doc);
      set({ selection: { sectionIndex: 0, paragraphIndex: 0, type: "paragraph" } });
    } catch (e) {
      console.error("openDocument failed:", e);
      set({ error: "문서를 열지 못했습니다." });
    } finally {
      set({ loading: false });
    }
  },

  openFile: () => {
    window.dispatchEvent(new CustomEvent("hwpx-open-file"));
  },

  printDocument: () => {
    window.print();
  },

  exportPDF: async () => {
    // Browser fallback: leverage print-to-PDF.
    window.print();
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

  saveDocumentToServer: async (filename) => {
    const { doc, serverDocumentId } = get();
    if (!doc) {
      return { ok: false, status: 400, error: "문서가 없습니다." };
    }

    try {
      set({ loading: true, error: null });
      const bytes = await doc.save();
      const response = await fetch("/api/hwpx-documents", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "x-filename": filename,
          ...(serverDocumentId ? { "x-document-id": serverDocumentId } : {}),
        },
        body: bytes as unknown as BodyInit,
      });

      const payload = (await response.json().catch(() => null)) as
        | { error?: string; document?: { id?: string } }
        | null;

      if (!response.ok) {
        const fallback = response.status === 401
          ? "로그인 후 서버 저장이 가능합니다."
          : "서버 저장에 실패했습니다.";
        const error = response.status === 401 ? fallback : (payload?.error || fallback);
        set({ error });
        return { ok: false, status: response.status, error };
      }

      const newId = payload?.document?.id;
      if (newId) {
        set({ serverDocumentId: newId });
      }
      get().closeSaveDialog();
      return { ok: true, status: response.status, documentId: newId };
    } catch (e) {
      console.error("saveDocumentToServer failed:", e);
      const error = "서버 저장에 실패했습니다.";
      set({ error });
      return { ok: false, status: 500, error };
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
  openFindReplaceDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, findReplaceDialogOpen: true } })),
  closeFindReplaceDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, findReplaceDialogOpen: false } })),
  openWordCountDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, wordCountDialogOpen: true } })),
  closeWordCountDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, wordCountDialogOpen: false } })),
  openTemplateDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, templateDialogOpen: true } })),
  closeTemplateDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, templateDialogOpen: false } })),
  openClipboardDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, clipboardDialogOpen: true } })),
  closeClipboardDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, clipboardDialogOpen: false } })),
  openCaptionDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, captionDialogOpen: true } })),
  closeCaptionDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, captionDialogOpen: false } })),
  openHeaderFooterDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, headerFooterDialogOpen: true } })),
  closeHeaderFooterDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, headerFooterDialogOpen: false } })),
  openPageNumberDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, pageNumberDialogOpen: true } })),
  closePageNumberDialog: () =>
    set((s) => ({ uiState: { ...s.uiState, pageNumberDialogOpen: false } })),
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
  setZoom: (level) =>
    set((s) => ({
      uiState: {
        ...s.uiState,
        zoomLevel: Math.max(10, Math.min(500, Math.round(level))),
      },
    })),
  zoomIn: () =>
    set((s) => ({
      uiState: {
        ...s.uiState,
        zoomLevel: Math.max(10, Math.min(500, s.uiState.zoomLevel + 10)),
      },
    })),
  zoomOut: () =>
    set((s) => ({
      uiState: {
        ...s.uiState,
        zoomLevel: Math.max(10, Math.min(500, s.uiState.zoomLevel - 10)),
      },
    })),

  addTemplate: (name, path, description) => {
    const template: Template = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
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
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("hwpx-editor-templates");
      if (!raw) return;
      const parsed = JSON.parse(raw) as Template[];
      if (Array.isArray(parsed)) {
        set({ templates: parsed });
      }
    } catch (e) {
      console.error("loadTemplates failed:", e);
    }
  },

  saveTemplates: () => {
    if (typeof window === "undefined") return;
    try {
      const templates = get().templates;
      window.localStorage.setItem("hwpx-editor-templates", JSON.stringify(templates));
    } catch (e) {
      console.error("saveTemplates failed:", e);
    }
  },

  pushClipboardHistory: (text) => {
    const trimmed = String(text ?? "").replace(/\s+/g, " ").trim();
    if (!trimmed) return;
    set((s) => {
      const prev = s.clipboardHistory ?? [];
      const next = [trimmed, ...prev.filter((t) => t !== trimmed)].slice(0, 20);
      return { clipboardHistory: next };
    });
  },

  clearClipboardHistory: () => set({ clipboardHistory: [] }),

  addSnippet: (name, text) => {
    const snippet: Snippet = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: (name ?? "").trim() || "스니펫",
      text: String(text ?? ""),
      createdAt: Date.now(),
    };
    set((s) => ({ snippets: [...(s.snippets ?? []), snippet] }));
    get().saveSnippets();
  },

  removeSnippet: (id) => {
    set((s) => ({ snippets: (s.snippets ?? []).filter((snip) => snip.id !== id) }));
    get().saveSnippets();
  },

  loadSnippets: () => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("hwpx-editor-snippets");
      if (!raw) return;
      const parsed = JSON.parse(raw) as Snippet[];
      if (Array.isArray(parsed)) set({ snippets: parsed });
    } catch (e) {
      console.error("loadSnippets failed:", e);
    }
  },

  saveSnippets: () => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem("hwpx-editor-snippets", JSON.stringify(get().snippets ?? []));
    } catch (e) {
      console.error("saveSnippets failed:", e);
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
      const fullText = para.text ?? "";
      const start =
        selection.textStartOffset ??
        selection.cursorOffset ??
        fullText.length;
      const end = selection.textEndOffset ?? start;
      const safeStart = Math.max(0, Math.min(fullText.length, start));
      const safeEnd = Math.max(safeStart, Math.min(fullText.length, end));
      para.text = fullText.slice(0, safeStart) + text + fullText.slice(safeEnd);
      get().rebuild();
      // Update caret position to after inserted text.
      const nextOffset = safeStart + text.length;
      set({
        selection: {
          ...selection,
          type: "paragraph",
          textStartOffset: undefined,
          textEndOffset: undefined,
          cursorOffset: nextOffset,
        },
      });
    } catch (e) {
      console.error("insertTextAtCursor failed:", e);
    }
  },

  insertTab: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    try {
      get().insertTextAtCursor("\t");
    } catch (e) {
      console.error("insertTab failed:", e);
    }
  },

  selectParagraphAll: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    if (selection.type !== "paragraph") return;
    const section = doc.sections[selection.sectionIndex];
    const para = section?.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const len = (para.text ?? "").length;
    get().setSelection({
      ...selection,
      type: "paragraph",
      textStartOffset: 0,
      textEndOffset: len,
      cursorOffset: len,
    });
  },

  selectWordAtCursor: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    if (selection.type !== "paragraph") return;
    const section = doc.sections[selection.sectionIndex];
    const para = section?.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const text = para.text ?? "";
    const caret = Math.max(0, Math.min(text.length, selection.cursorOffset ?? selection.textEndOffset ?? 0));
    const isWs = (ch: string) => /\s/.test(ch);
    let start = caret;
    let end = caret;
    while (start > 0 && !isWs(text[start - 1]!)) start -= 1;
    while (end < text.length && !isWs(text[end]!)) end += 1;
    if (start === end && text.length > 0) {
      // Fallback: expand by 1 char if caret is on whitespace.
      if (caret < text.length) end = Math.min(text.length, caret + 1);
      else start = Math.max(0, caret - 1);
    }
    get().setSelection({
      ...selection,
      type: "paragraph",
      textStartOffset: start,
      textEndOffset: end,
      cursorOffset: end,
    });
  },

  selectSentenceAtCursor: () => {
    const { doc, selection } = get();
    if (!doc || !selection) return;
    if (selection.type !== "paragraph") return;
    const section = doc.sections[selection.sectionIndex];
    const para = section?.paragraphs[selection.paragraphIndex];
    if (!para) return;
    const text = para.text ?? "";
    const caret = Math.max(0, Math.min(text.length, selection.cursorOffset ?? selection.textEndOffset ?? 0));
    const stops = new Set([".", "!", "?", "。", "！", "？", "\n"]);
    let start = caret;
    let end = caret;
    for (let i = caret - 1; i >= 0; i -= 1) {
      if (stops.has(text[i]!)) {
        start = i + 1;
        break;
      }
      if (i === 0) start = 0;
    }
    for (let i = caret; i < text.length; i += 1) {
      if (stops.has(text[i]!)) {
        end = i + 1;
        break;
      }
      if (i === text.length - 1) end = text.length;
    }
    get().setSelection({
      ...selection,
      type: "paragraph",
      textStartOffset: start,
      textEndOffset: end,
      cursorOffset: end,
    });
  },

  startFormatPainter: (mode, opts) => {
    const { doc, selection, extendedFormat } = get();
    if (!doc || !selection) return;
    const nextMode: FormatPainterMode =
      mode ??
      ((selection.type === "cell" || selection.type === "table") ? "cell" : "both");
    const snapshot: ExtendedFormat = {
      char: { ...extendedFormat.char },
      para: { ...extendedFormat.para },
    };
    set({
      formatPainter: {
        active: true,
        locked: Boolean(opts?.locked),
        mode: nextMode,
        origin: { ...selection },
        snapshot,
      },
    });
  },

  cancelFormatPainter: () => {
    set({
      formatPainter: {
        active: false,
        locked: false,
        mode: "both",
        origin: null,
        snapshot: null,
      },
    });
  },

  maybeApplyFormatPainter: (nextSelection) => {
    const { doc, formatPainter } = get();
    if (!doc) return;
    if (!formatPainter.active || !formatPainter.snapshot || !formatPainter.origin) return;
    if (!nextSelection) return;

    const key = (s: SelectionState) =>
      `${s.sectionIndex}:${s.paragraphIndex}:${s.type}:${s.tableIndex ?? ""}:${s.row ?? ""}:${s.col ?? ""}`;
    if (key(nextSelection) === key(formatPainter.origin)) return;

    try {
      get().pushUndo();

      const snap = formatPainter.snapshot;
      const section = doc.sections[nextSelection.sectionIndex];
      if (!section) return;

      if (formatPainter.mode === "char" || formatPainter.mode === "both" || formatPainter.mode === "cell") {
        const cf = snap.char;
        const charPrIdRef = doc.ensureRunStyle({
          bold: cf.bold,
          italic: cf.italic,
          underline: cf.underline,
          strikethrough: cf.strikethrough,
          fontFamily: cf.fontFamily ?? undefined,
          fontSize: cf.fontSize ?? undefined,
          textColor: cf.textColor ?? undefined,
          highlightColor: cf.highlightColor ?? undefined,
        });
        applyCharStyleToSelection(section, nextSelection, charPrIdRef);
      }

      if (formatPainter.mode === "para" || formatPainter.mode === "both") {
        if (nextSelection.type === "paragraph" && !nextSelection.objectType) {
          const para = section.paragraphs[nextSelection.paragraphIndex];
          if (para) {
            const pf = snap.para;
            const paraPrIdRef = doc.ensureParaStyle({
              alignment: pf.alignment,
              lineSpacingValue: Math.round(pf.lineSpacing * 100),
              indent: pf.firstLineIndent,
              marginLeft: pf.indentLeft,
              marginRight: pf.indentRight,
              marginBefore: pf.spacingBefore,
              marginAfter: pf.spacingAfter,
              baseParaPrId: para.paraPrIdRef ?? undefined,
            });
            para.paraPrIdRef = paraPrIdRef;
          }
        }
      }

      get().rebuild();
      get().refreshExtendedFormat();
    } catch (e) {
      console.error("applyFormatPainter failed:", e);
    } finally {
      if (formatPainter.locked) {
        set({ formatPainter: { ...formatPainter, origin: nextSelection ? { ...nextSelection } : formatPainter.origin } });
      } else {
        get().cancelFormatPainter();
      }
    }
  },
}));
