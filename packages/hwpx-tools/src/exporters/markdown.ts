/**
 * Markdown exporter for HWPX documents.
 * Converts HWPX content to Markdown format.
 */

import {
  HwpxPackage,
  HwpxOxmlDocument,
  HwpxOxmlParagraph,
  HwpxOxmlSection,
  HwpxOxmlTable,
  localName as domLocalName,
  childElements,
} from "@ubermensch1218/hwpxcore";
import { findAllDescendants, collectAllText } from "../helpers/xml-utils.js";

export interface MarkdownExportOptions {
  /** Heading level for title (default: 1) */
  titleHeadingLevel?: number;
  /** Include table of contents (default: false) */
  includeToc?: boolean;
  /** Convert paragraphs with heading styles to headings (default: true) */
  convertHeadingStyles?: boolean;
  /** Preserve line breaks within paragraphs (default: false) */
  preserveLineBreaks?: boolean;
  /** Include section separators (default: true) */
  includeSectionSeparators?: boolean;
  /** Section separator text (default: "---") */
  sectionSeparator?: string;
}

interface TableInfo {
  rows: number;
  cols: number;
  cells: string[][];
}

/**
 * Export HWPX document content as Markdown.
 */
export function exportToMarkdown(
  hwpxPackage: HwpxPackage,
  options?: MarkdownExportOptions
): string {
  const doc = HwpxOxmlDocument.fromPackage(hwpxPackage);
  const titleHeadingLevel = options?.titleHeadingLevel ?? 1;
  const includeSectionSeparators = options?.includeSectionSeparators ?? true;
  const sectionSeparator = options?.sectionSeparator ?? "---";

  const lines: string[] = [];
  const sections = doc.sections;

  for (let i = 0; i < sections.length; i++) {
    const section = sections[i]!;

    if (i > 0 && includeSectionSeparators) {
      lines.push("");
      lines.push(sectionSeparator);
      lines.push("");
    }

    const paragraphs = section.paragraphs;
    for (const paragraph of paragraphs) {
      const md = paragraphToMarkdown(paragraph, doc, options);
      if (md) {
        lines.push(md);
      }
    }
  }

  return lines.join("\n");
}

/**
 * Convert a paragraph element to Markdown.
 */
function paragraphToMarkdown(
  paragraph: HwpxOxmlParagraph,
  doc: HwpxOxmlDocument,
  options?: MarkdownExportOptions
): string {
  const element = paragraph.element;
  const styleIdRef = element.getAttribute("styleIDRef");

  // Check if this paragraph has a heading style
  const convertHeadingStyles = options?.convertHeadingStyles ?? true;
  let headingPrefix = "";

  if (convertHeadingStyles && styleIdRef) {
    // Style ID mapping for common heading styles
    // In HWPX, styles are numbered; typically 0-9 might be headings
    const styleNum = parseInt(styleIdRef, 10);
    if (styleNum >= 1 && styleNum <= 6) {
      headingPrefix = "#".repeat(styleNum) + " ";
    }
  }

  // Get text content with formatting
  const text = getParagraphTextWithFormatting(paragraph, options);

  if (!text.trim()) {
    return "";
  }

  // Check for list items
  const listMarker = getListMarker(paragraph);
  if (listMarker) {
    return listMarker + text;
  }

  return headingPrefix + text;
}

/**
 * Get text content from a paragraph with basic formatting preserved.
 */
function getParagraphTextWithFormatting(
  paragraph: HwpxOxmlParagraph,
  options?: MarkdownExportOptions
): string {
  const element = paragraph.element;
  const parts: string[] = [];
  const preserveLineBreaks = options?.preserveLineBreaks ?? false;

  // Walk through runs and text elements
  for (const run of childElements(element)) {
    if (domLocalName(run) !== "run") continue;

    // Check for bold/italic in run style
    const charPrIdRef = run.getAttribute("charPrIDRef");
    let isBold = false;
    let isItalic = false;

    // Get text from run
    for (const child of childElements(run)) {
      const name = domLocalName(child);

      if (name === "t") {
        let text = child.textContent ?? "";

        if (!preserveLineBreaks) {
          text = text.replace(/\n/g, " ");
        }

        // Apply formatting markers
        if (isBold && isItalic) {
          text = `***${text}***`;
        } else if (isBold) {
          text = `**${text}**`;
        } else if (isItalic) {
          text = `*${text}*`;
        }

        parts.push(text);
      } else if (name === "tbl") {
        // Handle inline table
        const tableMd = tableToMarkdown(child);
        if (tableMd) {
          parts.push("\n" + tableMd + "\n");
        }
      }
    }
  }

  return parts.join("");
}

/**
 * Get list marker if paragraph is part of a list.
 */
function getListMarker(paragraph: HwpxOxmlParagraph): string | null {
  const element = paragraph.element;

  // Check for bullet/numbering attributes
  // This is a simplified check - real implementation would need to
  // examine the paragraph properties and bullet styles
  const bulletId = element.getAttribute("bulletIDRef");
  if (bulletId) {
    return "- ";
  }

  const numberingId = element.getAttribute("numberingIDRef");
  if (numberingId) {
    return "1. ";
  }

  return null;
}

/**
 * Convert a table element to Markdown.
 */
function tableToMarkdown(tableElement: Element): string {
  const tableInfo = parseTable(tableElement);
  if (!tableInfo || tableInfo.rows === 0 || tableInfo.cols === 0) {
    return "";
  }

  const lines: string[] = [];

  // Header row
  const headerCells = tableInfo.cells[0] ?? [];
  lines.push("| " + headerCells.map((c) => c.replace(/\n/g, " ")).join(" | ") + " |");

  // Separator
  lines.push("| " + headerCells.map(() => "---").join(" | ") + " |");

  // Data rows
  for (let i = 1; i < tableInfo.rows; i++) {
    const rowCells = tableInfo.cells[i] ?? [];
    // Pad row if needed
    while (rowCells.length < tableInfo.cols) {
      rowCells.push("");
    }
    lines.push("| " + rowCells.map((c) => c.replace(/\n/g, " ")).join(" | ") + " |");
  }

  return lines.join("\n");
}

/**
 * Parse table structure from HWPX table element.
 */
function parseTable(tableElement: Element): TableInfo | null {
  const rows: string[][] = [];
  let maxCols = 0;

  // Find all tr elements
  for (const tr of childElements(tableElement)) {
    if (domLocalName(tr) !== "tr") continue;

    const rowCells: string[] = [];

    // Find all tc elements
    for (const tc of childElements(tr)) {
      if (domLocalName(tc) !== "tc") continue;

      // Get cell text from subList/p/t
      const cellText = getCellText(tc);
      rowCells.push(cellText);
    }

    if (rowCells.length > 0) {
      rows.push(rowCells);
      maxCols = Math.max(maxCols, rowCells.length);
    }
  }

  if (rows.length === 0) {
    return null;
  }

  return {
    rows: rows.length,
    cols: maxCols,
    cells: rows,
  };
}

/**
 * Get text content from a table cell.
 */
function getCellText(tcElement: Element): string {
  const parts: string[] = [];

  // Find subList element
  for (const subList of childElements(tcElement)) {
    if (domLocalName(subList) !== "subList") continue;

    // Find all paragraphs
    for (const p of childElements(subList)) {
      if (domLocalName(p) !== "p") continue;

      // Get text from p
      for (const run of childElements(p)) {
        if (domLocalName(run) !== "run") continue;

        for (const t of childElements(run)) {
          if (domLocalName(t) === "t") {
            const text = t.textContent ?? "";
            if (text) parts.push(text);
          }
        }
      }
    }
  }

  return parts.join(" ");
}

/**
 * Export document with table of contents.
 */
export function exportToMarkdownWithToc(
  hwpxPackage: HwpxPackage,
  options?: MarkdownExportOptions
): string {
  const doc = HwpxOxmlDocument.fromPackage(hwpxPackage);
  const lines: string[] = [];

  // Add title
  lines.push("# Document");
  lines.push("");

  // Generate TOC (simplified - would need heading extraction for full implementation)
  lines.push("## Table of Contents");
  lines.push("");
  lines.push("* [Section 1](#section-1)");
  lines.push("");

  // Add separator
  lines.push("---");
  lines.push("");

  // Add content
  const content = exportToMarkdown(hwpxPackage, { ...options, includeSectionSeparators: true });
  lines.push(content);

  return lines.join("\n");
}
