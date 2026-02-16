/**
 * format-bridge.ts — Bridge between UI and @ubermensch1218/hwpxcore formatting APIs.
 *
 * Reads charPr / paraPr from the document and converts to UI-friendly formats.
 * Also provides methods to apply format changes back to the document.
 */

import type {
  HwpxDocument,
  HwpxOxmlParagraph,
  RunStyle,
  ParagraphProperty,
  Header,
  Style,
} from "@ubermensch1218/hwpxcore";
import {
  parseHeaderXml,
} from "@ubermensch1218/hwpxcore";
import { serializeXml } from "@ubermensch1218/hwpxcore";
import type { AlignmentType } from "./constants";

// ── Read format types ──────────────────────────────────────────────────────

export interface CharFormat {
  bold: boolean;
  italic: boolean;
  underline: boolean;
  strikethrough: boolean;
  fontFamily: string | null;
  fontSize: number | null;
  textColor: string | null;
  highlightColor: string | null;
  letterSpacing: number | null;
}

export interface ParaFormat {
  alignment: AlignmentType;
  lineSpacing: number;
  spacingBefore: number;
  spacingAfter: number;
  indentLeft: number;
  indentRight: number;
  firstLineIndent: number;
}

// ── Parse header to get paragraph properties ───────────────────────────────

function getParsedHeader(doc: HwpxDocument): Header | null {
  const headers = doc.headers;
  if (headers.length === 0) return null;
  const headerEl = headers[0]!.element;
  try {
    const xml = serializeXml(headerEl);
    return parseHeaderXml(xml);
  } catch {
    return null;
  }
}

// ── Read character formatting from a run style ─────────────────────────────

export function readCharFormat(style: RunStyle | null, doc?: HwpxDocument | null): CharFormat {
  const result: CharFormat = {
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

  if (!style) return result;

  const normalizeFlag = (value?: string | null): boolean =>
    value === "1" || value?.toLowerCase() === "true";

  // HWPX charPr often stores bold/italic as child tags (<hh:bold />, <hh:italic />)
  // instead of root attributes.
  result.bold =
    normalizeFlag(style.attributes["bold"]) ||
    style.childAttributes["bold"] != null;
  result.italic =
    normalizeFlag(style.attributes["italic"]) ||
    style.childAttributes["italic"] != null;

  // Underline
  const underlineChild = style.childAttributes["underline"];
  result.underline =
    underlineChild != null &&
    ((underlineChild["type"] == null) ||
      underlineChild["type"].toUpperCase() !== "NONE");

  // Strikethrough
  const strikeChild = style.childAttributes["strikeout"];
  result.strikethrough =
    strikeChild != null &&
    ((strikeChild["type"] == null) ||
      strikeChild["type"].toUpperCase() !== "NONE");

  // Text color
  result.textColor = style.attributes["textColor"] ?? null;

  // Highlight color
  result.highlightColor = style.attributes["shadeColor"] ?? null;

  // Letter spacing
  const spacing = style.attributes["spacing"];
  if (spacing) {
    const val = parseInt(spacing, 10);
    if (!isNaN(val)) result.letterSpacing = val;
  }

  // Font family — look in fontRef child, resolve numeric ID to face name
  const fontRef = style.childAttributes["fontRef"];
  if (fontRef) {
    const hangulId = fontRef["hangul"] ?? fontRef["latin"] ?? null;
    if (hangulId != null && doc) {
      result.fontFamily = doc.fontFaceName(hangulId) ?? hangulId;
    } else {
      result.fontFamily = hangulId;
    }
  }

  // Font size
  const sizeStr = style.attributes["height"];
  if (sizeStr) {
    // Height is in hwp units (1/7200 inch), convert to pt: hwpUnit / 100
    const hwpVal = parseInt(sizeStr, 10);
    if (!isNaN(hwpVal)) result.fontSize = hwpVal / 100;
  }

  return result;
}

// ── Read paragraph formatting ──────────────────────────────────────────────

export function readParaFormat(
  doc: HwpxDocument,
  paragraph: HwpxOxmlParagraph,
): ParaFormat {
  const result: ParaFormat = {
    alignment: "LEFT",
    lineSpacing: 1.6,
    spacingBefore: 0,
    spacingAfter: 0,
    indentLeft: 0,
    indentRight: 0,
    firstLineIndent: 0,
  };

  const paraPrIdRef = paragraph.paraPrIdRef;
  if (!paraPrIdRef) return result;

  const header = getParsedHeader(doc);
  if (!header) return result;

  // Look up the paragraph property
  const paraPr = findParaPr(header, paraPrIdRef);
  if (!paraPr) return result;

  // Alignment
  if (paraPr.align?.horizontal) {
    const h = paraPr.align.horizontal.toUpperCase();
    if (
      h === "LEFT" || h === "CENTER" || h === "RIGHT" ||
      h === "JUSTIFY" || h === "DISTRIBUTE"
    ) {
      result.alignment = h as AlignmentType;
    }
  }

  // Line spacing
  if (paraPr.lineSpacing?.value != null) {
    const spacingType = paraPr.lineSpacing.spacingType?.toUpperCase();
    if (spacingType === "PERCENT" || spacingType === "PROPORTIONAL") {
      // Value is in percent (e.g., 160 = 1.6x)
      result.lineSpacing = paraPr.lineSpacing.value / 100;
    } else {
      // Fixed value in hwp units
      result.lineSpacing = paraPr.lineSpacing.value / 100;
    }
  }

  // Margins / indentation
  if (paraPr.margin) {
    if (paraPr.margin.left) {
      result.indentLeft = parseInt(paraPr.margin.left, 10) || 0;
    }
    if (paraPr.margin.right) {
      result.indentRight = parseInt(paraPr.margin.right, 10) || 0;
    }
    if (paraPr.margin.intent) {
      result.firstLineIndent = parseInt(paraPr.margin.intent, 10) || 0;
    }
    if (paraPr.margin.prev) {
      result.spacingBefore = parseInt(paraPr.margin.prev, 10) || 0;
    }
    if (paraPr.margin.next) {
      result.spacingAfter = parseInt(paraPr.margin.next, 10) || 0;
    }
  }

  return result;
}

// ── Helper: find paragraph property by ID ──────────────────────────────────

function findParaPr(header: Header, paraPrIdRef: string): ParagraphProperty | null {
  if (!header.refList?.paraProperties) return null;
  for (const prop of header.refList.paraProperties.properties) {
    if (prop.rawId === paraPrIdRef) return prop;
    if (prop.id != null && String(prop.id) === paraPrIdRef) return prop;
  }
  return null;
}

// ── Read style info ────────────────────────────────────────────────────────

export function readStyleInfo(
  doc: HwpxDocument,
  paragraph: HwpxOxmlParagraph,
): { styleName: string | null; styleId: string | null } {
  const styleIdRef = paragraph.styleIdRef;
  if (!styleIdRef) return { styleName: null, styleId: null };

  const header = getParsedHeader(doc);
  if (!header?.refList?.styles) return { styleName: null, styleId: null };

  for (const style of header.refList.styles.styles) {
    if (style.rawId === styleIdRef || (style.id != null && String(style.id) === styleIdRef)) {
      return { styleName: style.name, styleId: styleIdRef };
    }
  }

  return { styleName: null, styleId: styleIdRef };
}

// ── Get available styles from document ─────────────────────────────────────

export function getDocumentStyles(doc: HwpxDocument): Style[] {
  const header = getParsedHeader(doc);
  if (!header?.refList?.styles) return [];
  return header.refList.styles.styles;
}

// ── Read format from current selection ─────────────────────────────────────

export function readFormatFromSelection(
  doc: HwpxDocument,
  sectionIndex: number,
  paragraphIndex: number,
): { char: CharFormat; para: ParaFormat } {
  const section = doc.sections[sectionIndex];
  if (!section) {
    return {
      char: readCharFormat(null),
      para: {
        alignment: "LEFT",
        lineSpacing: 1.6,
        spacingBefore: 0,
        spacingAfter: 0,
        indentLeft: 0,
        indentRight: 0,
        firstLineIndent: 0,
      },
    };
  }

  const paras = section.paragraphs;
  const para = paras[paragraphIndex];
  if (!para) {
    return {
      char: readCharFormat(null),
      para: {
        alignment: "LEFT",
        lineSpacing: 1.6,
        spacingBefore: 0,
        spacingAfter: 0,
        indentLeft: 0,
        indentRight: 0,
        firstLineIndent: 0,
      },
    };
  }

  // Character format: use the first run's style or the paragraph's charPrIdRef
  const runs = para.runs;
  let charStyle: RunStyle | null = null;
  if (runs.length > 0) {
    charStyle = runs[0]!.style;
  } else {
    const charPrIdRef = para.charPrIdRef;
    if (charPrIdRef) {
      charStyle = doc.charProperty(charPrIdRef);
    }
  }

  return {
    char: readCharFormat(charStyle, doc),
    para: readParaFormat(doc, para),
  };
}
