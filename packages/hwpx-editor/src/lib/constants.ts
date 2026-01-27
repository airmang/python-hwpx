/**
 * Constants for the HWPX editor UI — font lists, style presets, alignment/spacing options.
 */

// ── Korean font families ───────────────────────────────────────────────────

export const FONT_FAMILIES = [
  "맑은 고딕",
  "함초롬돋움",
  "함초롬바탕",
  "나눔고딕",
  "나눔명조",
  "나눔바른고딕",
  "바탕",
  "돋움",
  "굴림",
  "궁서",
  "Arial",
  "Times New Roman",
  "Courier New",
  "Verdana",
  "Georgia",
] as const;

export type FontFamily = (typeof FONT_FAMILIES)[number];

// ── Font sizes ─────────────────────────────────────────────────────────────

export const FONT_SIZES = [
  8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 48, 72,
] as const;

// ── Paragraph styles ───────────────────────────────────────────────────────

export interface StylePreset {
  id: string;
  name: string;
  engName: string;
}

export const STYLE_PRESETS: StylePreset[] = [
  { id: "0", name: "바탕글", engName: "Normal" },
  { id: "1", name: "본문", engName: "Body" },
  { id: "2", name: "개요 1", engName: "Outline 1" },
  { id: "3", name: "개요 2", engName: "Outline 2" },
  { id: "4", name: "개요 3", engName: "Outline 3" },
  { id: "5", name: "쪽 번호", engName: "Page Number" },
  { id: "6", name: "머리말", engName: "Header" },
  { id: "7", name: "꼬리말", engName: "Footer" },
  { id: "8", name: "각주", engName: "Footnote" },
  { id: "9", name: "미주", engName: "Endnote" },
];

// ── Alignment ──────────────────────────────────────────────────────────────

export type AlignmentType = "LEFT" | "CENTER" | "RIGHT" | "JUSTIFY" | "DISTRIBUTE";

export interface AlignmentOption {
  value: AlignmentType;
  label: string;
  shortcut?: string;
}

export const ALIGNMENT_OPTIONS: AlignmentOption[] = [
  { value: "LEFT", label: "왼쪽 정렬", shortcut: "Ctrl+L" },
  { value: "CENTER", label: "가운데 정렬", shortcut: "Ctrl+E" },
  { value: "RIGHT", label: "오른쪽 정렬", shortcut: "Ctrl+R" },
  { value: "JUSTIFY", label: "양쪽 정렬", shortcut: "Ctrl+J" },
  { value: "DISTRIBUTE", label: "배분 정렬" },
];

// ── Line spacing ───────────────────────────────────────────────────────────

export interface LineSpacingOption {
  value: number;
  label: string;
}

export const LINE_SPACING_OPTIONS: LineSpacingOption[] = [
  { value: 1.0, label: "1.0" },
  { value: 1.15, label: "1.15" },
  { value: 1.5, label: "1.5" },
  { value: 1.6, label: "1.6" },
  { value: 2.0, label: "2.0" },
  { value: 2.5, label: "2.5" },
  { value: 3.0, label: "3.0" },
];

// ── Underline types ────────────────────────────────────────────────────────

export const UNDERLINE_TYPES = [
  "NONE",
  "SOLID",
  "DASH",
  "DOT",
  "DASH_DOT",
  "DASH_DOT_DOT",
  "LONG_DASH",
  "DOUBLE",
  "WAVE",
  "HEAVY_WAVE",
  "DOUBLE_WAVE",
] as const;

// ── Color presets ──────────────────────────────────────────────────────────

export const COLOR_PRESETS = [
  // Row 1: Primary colors
  "#000000", "#333333", "#555555", "#777777", "#999999", "#BBBBBB", "#DDDDDD", "#FFFFFF",
  // Row 2: Vivid colors
  "#FF0000", "#FF6600", "#FFCC00", "#33CC33", "#0099FF", "#3366FF", "#6633CC", "#CC33CC",
  // Row 3: Pastel colors
  "#FF9999", "#FFCC99", "#FFFF99", "#CCFFCC", "#99CCFF", "#9999FF", "#CC99FF", "#FF99CC",
  // Row 4: Dark colors
  "#CC0000", "#CC6600", "#CC9900", "#009900", "#006699", "#003399", "#330099", "#990066",
] as const;

// ── Highlight colors ───────────────────────────────────────────────────────

export const HIGHLIGHT_COLORS = [
  { value: "#FFFF00", label: "노랑" },
  { value: "#00FF00", label: "연두" },
  { value: "#00FFFF", label: "하늘" },
  { value: "#FF00FF", label: "분홍" },
  { value: "#0000FF", label: "파랑" },
  { value: "#FF0000", label: "빨강" },
  { value: "#008000", label: "초록" },
  { value: "#800080", label: "보라" },
  { value: "#808080", label: "회색" },
  { value: "none", label: "없음" },
] as const;

// ── Sidebar tabs ───────────────────────────────────────────────────────────

export type SidebarTab = "char" | "para";
