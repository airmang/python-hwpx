/**
 * @hwpx/editor — React editor components for HWPX documents.
 *
 * Provides a Korean word processor-style UI with ribbon toolbar,
 * format sidebar, ruler, and full page editing.
 */

// ── Editor components ─────────────────────────────────────────────────────
export { Editor } from "./components/editor/Editor";
export { PageView } from "./components/editor/PageView";
export { Page } from "./components/editor/Page";
export { ParagraphBlock } from "./components/editor/ParagraphBlock";
export { RunSpan } from "./components/editor/RunSpan";
export { ImageBlock } from "./components/editor/ImageBlock";
export { TableBlock } from "./components/editor/TableBlock";
export { TableCell } from "./components/editor/TableCell";

// ── Toolbar components ────────────────────────────────────────────────────
export { RibbonToolbar } from "./components/toolbar/RibbonToolbar";
export { SecondaryToolbar } from "./components/toolbar/SecondaryToolbar";
export { ToolbarButton } from "./components/toolbar/ToolbarButton";
export { ToolbarDropdown } from "./components/toolbar/ToolbarDropdown";
export { ToolbarDivider } from "./components/toolbar/ToolbarDivider";
export { ColorPicker } from "./components/toolbar/ColorPicker";
export { RibbonGroup } from "./components/toolbar/RibbonGroup";
export { ClipboardGroup } from "./components/toolbar/ClipboardGroup";
export { InsertGroup } from "./components/toolbar/InsertGroup";
export { StyleSelector } from "./components/toolbar/StyleSelector";
export { FontSelector } from "./components/toolbar/FontSelector";
export { FontSizeInput } from "./components/toolbar/FontSizeInput";
export { CharFormatButtons } from "./components/toolbar/CharFormatButtons";
export { AlignmentButtons } from "./components/toolbar/AlignmentButtons";
export { LineSpacingControl } from "./components/toolbar/LineSpacingControl";

// ── Sidebar components ────────────────────────────────────────────────────
export { FormatSidebar } from "./components/sidebar/FormatSidebar";
export { SidebarSection } from "./components/sidebar/SidebarSection";
export { SidebarField } from "./components/sidebar/SidebarField";
export { CharFormatPanel } from "./components/sidebar/CharFormatPanel";
export { ParaFormatPanel } from "./components/sidebar/ParaFormatPanel";
export { BorderSettings } from "./components/sidebar/BorderSettings";
export { BackgroundSettings } from "./components/sidebar/BackgroundSettings";

// ── Ruler ─────────────────────────────────────────────────────────────────
export { HorizontalRuler } from "./components/ruler/HorizontalRuler";

// ── Upload components ─────────────────────────────────────────────────────
export { FileUpload } from "./components/upload/FileUpload";
export { NewDocumentButton } from "./components/upload/NewDocumentButton";

// ── Store ─────────────────────────────────────────────────────────────────
export { useEditorStore } from "./lib/store";
export type {
  SelectionState,
  ActiveFormat,
  ExtendedFormat,
  UIState,
  EditorStore,
} from "./lib/store";

// ── Constants ─────────────────────────────────────────────────────────────
export {
  FONT_FAMILIES,
  FONT_SIZES,
  STYLE_PRESETS,
  ALIGNMENT_OPTIONS,
  LINE_SPACING_OPTIONS,
  UNDERLINE_TYPES,
  COLOR_PRESETS,
  HIGHLIGHT_COLORS,
} from "./lib/constants";
export type {
  FontFamily,
  StylePreset,
  AlignmentType,
  AlignmentOption,
  LineSpacingOption,
  SidebarTab,
} from "./lib/constants";

// ── Format bridge ─────────────────────────────────────────────────────────
export {
  readCharFormat,
  readParaFormat,
  readStyleInfo,
  getDocumentStyles,
  readFormatFromSelection,
} from "./lib/format-bridge";
export type { CharFormat, ParaFormat } from "./lib/format-bridge";

// ── View model ────────────────────────────────────────────────────────────
export { buildViewModel } from "./lib/view-model";
export type {
  RunVM,
  TableCellVM,
  TableVM,
  ImageVM,
  ParagraphVM,
  SectionVM,
  EditorViewModel,
} from "./lib/view-model";

// ── Utilities ─────────────────────────────────────────────────────────────
export { hwpToPx, pxToHwp, hwpToMm, mmToHwp } from "./lib/hwp-units";
export { extractImages } from "./lib/image-extractor";
export { ensureSkeletonLoaded, createNewDocument } from "./lib/skeleton-loader";
