/**
 * Store type definitions
 */

import type { HwpxDocument } from "@ubermensch1218/hwpxcore";
import type { EditorViewModel } from "../view-model";
import type { CharFormat, ParaFormat } from "../format-bridge";
import type { AlignmentType, OrientationType, SidebarTab } from "../constants";

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
  templateDialogOpen: boolean;
  headerFooterDialogOpen: boolean;
  findReplaceDialogOpen: boolean;
  wordCountDialogOpen: boolean;
  pageNumberDialogOpen: boolean;
  styleDialogOpen: boolean;
  autoCorrectDialogOpen: boolean;
  outlineDialogOpen: boolean;
  shapeDialogOpen: boolean;
  tocDialogOpen: boolean;
  zoomLevel: number;
}

export interface Template {
  id: string;
  name: string;
  path: string;
  description?: string;
  createdAt: number;
}

export interface TocOptions {
  title?: string;
  tabLeader?: "DOT" | "HYPHEN" | "UNDERLINE" | "NONE";
  tabWidth?: number;
  maxLevel?: number;
  showPageNumbers?: boolean;
}

export interface UndoEntry {
  sectionElements: Element[];
  headerElements: Element[];
  selection: SelectionState | null;
}

// Base state without actions
export interface EditorState {
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
  templates: Template[];
  serverDocumentId: string | null;
}

// Action interfaces by category
export interface DocumentActions {
  setDocument: (doc: HwpxDocument) => void;
  rebuild: () => void;
  setSelection: (sel: SelectionState | null) => void;
  setActiveFormat: (fmt: Partial<ActiveFormat>) => void;
  refreshExtendedFormat: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export interface UndoRedoActions {
  pushUndo: () => void;
  undo: () => void;
  redo: () => void;
}

export interface UIActions {
  toggleSidebar: () => void;
  setSidebarTab: (tab: SidebarTab) => void;
  openTemplateDialog: () => void;
  closeTemplateDialog: () => void;
  openHeaderFooterDialog: () => void;
  closeHeaderFooterDialog: () => void;
  openFindReplaceDialog: () => void;
  closeFindReplaceDialog: () => void;
  openWordCountDialog: () => void;
  closeWordCountDialog: () => void;
  openPageNumberDialog: () => void;
  closePageNumberDialog: () => void;
  openCharFormatDialog: () => void;
  closeCharFormatDialog: () => void;
  openParaFormatDialog: () => void;
  closeParaFormatDialog: () => void;
  openBulletNumberDialog: () => void;
  closeBulletNumberDialog: () => void;
  openCharMapDialog: () => void;
  closeCharMapDialog: () => void;
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
  openSaveDialog: () => void;
  closeSaveDialog: () => void;
  setZoom: (level: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
}

export interface FileActions {
  newDocument: () => Promise<void>;
  openDocument: (data: Uint8Array) => Promise<void>;
  saveDocument: () => Promise<void>;
  saveDocumentAs: (filename: string) => Promise<void>;
  saveDocumentToServer: (filename: string) => Promise<{
    ok: boolean;
    status: number;
    documentId?: string;
    error?: string;
  }>;
  printDocument: () => void;
  exportPDF: () => Promise<void>;
}

export interface FormattingActions {
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
  setFirstLineIndent: (valueHwp: number) => void;
  setLeftIndent: (valueHwp: number) => void;
  applyBullet: (bulletId: string | null) => void;
  applyNumbering: (level: number) => void;
  applyOutlineLevel: (level: number) => void;
  removeBulletNumbering: () => void;
  applyStyle: (styleId: string) => void;
  insertToc: (options: TocOptions) => void;
}

export type ShapeType = "rectangle" | "ellipse" | "line" | "arrow";

export interface ShapeActions {
  insertShape: (shapeType: ShapeType, widthMm: number, heightMm: number) => void;
}

export interface ChartActions {
  insertChart: (opts?: {
    title?: string;
    chartType?: "bar" | "line";
    categories?: string[];
    values?: number[];
  }) => void;
}

export interface TextEditingActions {
  updateParagraphText: (sectionIndex: number, paragraphIndex: number, text: string) => void;
  updateCellText: (sectionIndex: number, paragraphIndex: number, tableIndex: number, row: number, col: number, text: string) => void;
  splitParagraph: (sectionIndex: number, paragraphIndex: number, offset: number) => void;
  mergeParagraphWithPrevious: (sectionIndex: number, paragraphIndex: number) => void;
  deleteBlock: (sectionIndex: number, paragraphIndex: number) => void;
  insertBlockAt: (sectionIndex: number, paragraphIndex: number, text?: string) => void;
  addParagraph: (text?: string) => void;
  insertTextAtCursor: (text: string) => void;
  insertTab: () => void;
  findAndReplace: (search: string, replacement: string, count?: number) => number;
}

export interface TableActions {
  addTable: (sectionIndex: number, paragraphIndex: number, rows: number, cols: number) => void;
  setTablePageBreak: (mode: "CELL" | "NONE") => void;
  setTableRepeatHeader: (repeat: boolean) => void;
  setTableSize: (widthMm: number, heightMm: number) => void;
  setTableOutMargin: (margins: Partial<{ top: number; bottom: number; left: number; right: number }>) => void;
  setTableInMargin: (margins: Partial<{ top: number; bottom: number; left: number; right: number }>) => void;
  resizeTableColumn: (sectionIdx: number, paraIdx: number, tableIdx: number, colIdx: number, deltaHwp: number) => void;
  setSelectedCellsSize: (widthMm?: number, heightMm?: number) => void;
  mergeSelectedCells: () => void;
  unmergeSelectedCells: () => void;
  insertTableRow: (position: "above" | "below") => void;
  insertTableColumn: (position: "left" | "right") => void;
  deleteTableRow: () => void;
  deleteTableColumn: () => void;
  deleteTable: () => void;
}

export interface ImageActions {
  insertImage: (data: Uint8Array, mediaType: string, widthMm: number, heightMm: number) => void;
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
}

export interface PageActions {
  updatePageSize: (width: number, height: number) => void;
  updatePageMargins: (margins: Partial<{ left: number; right: number; top: number; bottom: number; header: number; footer: number; gutter: number }>) => void;
  updatePageOrientation: (orientation: OrientationType) => void;
  setColumnCount: (colCount: number, gapMm?: number) => void;
  setPageNumbering: (opts: { position: string; startNumber: number; format?: string }) => void;
  setHeaderFooter: (opts: {
    headerText?: string;
    footerText?: string;
    headerPosition?: "left" | "center" | "right";
    footerPosition?: "left" | "center" | "right";
  }) => void;
  insertColumnBreak: () => void;
  insertPageBreak: () => void;
  insertFootnote: () => void;
  insertEndnote: () => void;
  setWatermarkText: (text: string) => void;
  insertTextBox: (text: string, widthMm: number, heightMm: number) => void;
}

export interface TemplateActions {
  addTemplate: (name: string, path: string, description?: string) => void;
  removeTemplate: (id: string) => void;
  loadTemplates: () => void;
  saveTemplates: () => void;
}

// Combined store interface
export interface EditorStore extends
  EditorState,
  DocumentActions,
  UndoRedoActions,
  UIActions,
  FileActions,
  FormattingActions,
  TextEditingActions,
  TableActions,
  ImageActions,
  PageActions,
  TemplateActions,
  ChartActions,
  ShapeActions {}
