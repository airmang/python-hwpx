/**
 * Table of Contents (TOC) generation utilities for HWPX documents.
 */

import { HP_NS, subElement, createNsElement } from "./xml-utils.js";
import type { HwpxOxmlDocument } from "./document.js";
import type { HwpxOxmlSection } from "./section.js";
import type { HwpxOxmlParagraph } from "./paragraph.js";

/** TOC entry representing a heading in the document */
export interface TocEntry {
  /** Heading text */
  text: string;
  /** Outline level (1-9) */
  level: number;
  /** Page number (estimated or actual) */
  pageNumber: number;
  /** Original paragraph reference */
  paragraph: HwpxOxmlParagraph;
}

/** Options for TOC generation */
export interface TocOptions {
  /** Section index where TOC should be inserted (default: 0 = beginning) */
  sectionIndex?: number;
  /** Paragraph index within section (default: 0 = beginning) */
  paragraphIndex?: number;
  /** Title for the TOC (default: "차례") */
  title?: string;
  /** Tab leader style (default: "DOT") */
  tabLeader?: "DOT" | "HYPHEN" | "UNDERLINE" | "NONE";
  /** Tab position in hwpUnit (default: 12000) */
  tabWidth?: number;
  /** Maximum outline level to include (default: 9 = all) */
  maxLevel?: number;
  /** Whether to show page numbers (default: true) */
  showPageNumbers?: boolean;
}

/**
 * Scan document for headings and return TOC entries
 */
export function scanForHeadings(document: HwpxOxmlDocument, maxLevel: number = 9): TocEntry[] {
  const entries: TocEntry[] = [];
  let currentPageNumber = 1;

  for (const section of document.sections) {
    for (const paragraph of section.paragraphs) {
      const level = paragraph.outlineLevel;
      if (level > 0 && level <= maxLevel) {
        const text = paragraph.text.trim();
        if (text) {
          entries.push({
            text,
            level,
            pageNumber: currentPageNumber,
            paragraph,
          });
        }
      }

      // Simple page number estimation (actual implementation would be more complex)
      // For now, we assume each section might start a new page
    }
  }

  return entries;
}

/**
 * Create a TOC paragraph entry with tab leader and page number
 */
function createTocEntryParagraph(
  doc: Document,
  entry: TocEntry,
  options: Required<TocOptions>
): Element {
  const { tabLeader, tabWidth, showPageNumbers } = options;

  // Calculate indent based on level
  const indent = (entry.level - 1) * 2000;

  const attrs: Record<string, string> = {
    id: paragraphId(),
    paraPrIDRef: "0",
    styleIDRef: "0",
    pageBreak: "0",
    columnBreak: "0",
    merged: "0",
  };

  const paragraph = createNsElement(doc, HP_NS, "p", attrs);

  // Create run with text
  const runElement = subElement(paragraph, HP_NS, "run", { charPrIDRef: "0" });
  const t = subElement(runElement, HP_NS, "t");
  t.textContent = entry.text;

  // Add tab with leader
  const tabAttrs: Record<string, string> = {};
  if (tabWidth) tabAttrs.width = String(tabWidth);
  if (tabLeader && tabLeader !== "NONE") tabAttrs.tabLeader = tabLeader;

  subElement(runElement, HP_NS, "tab", tabAttrs);

  // Add page number
  if (showPageNumbers) {
    const pageRun = subElement(paragraph, HP_NS, "run", { charPrIDRef: "0" });
    const pageT = subElement(pageRun, HP_NS, "t");
    pageT.textContent = String(entry.pageNumber);
  }

  return paragraph;
}

/**
 * Helper function (borrowed from xml-utils)
 */
function paragraphId(): string {
  const bytes = new Uint8Array(4);
  if (typeof globalThis.crypto !== "undefined" && globalThis.crypto.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 4; i++) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  const view = new DataView(bytes.buffer);
  return String(view.getUint32(0) >>> 0);
}

/**
 * Generate and insert a table of contents into the document
 */
export function generateTableOfContents(
  document: HwpxOxmlDocument,
  options: TocOptions = {}
): HwpxOxmlSection {
  const opts: Required<TocOptions> = {
    sectionIndex: 0,
    paragraphIndex: 0,
    title: "차례",
    tabLeader: "DOT",
    tabWidth: 12000,
    maxLevel: 9,
    showPageNumbers: true,
    ...options,
  };

  // Scan for headings
  const entries = scanForHeadings(document, opts.maxLevel);

  // Get the target section
  if (document.sections.length === 0) {
    throw new Error("Cannot generate TOC: document has no sections");
  }
  const targetSectionIndex = Math.min(opts.sectionIndex, document.sections.length - 1);
  const targetSection = document.sections[targetSectionIndex]!;

  // Create TOC entries
  const doc = targetSection.element.ownerDocument!;

  // Add title paragraph
  const titlePara = createNsElement(doc, HP_NS, "p", {
    id: paragraphId(),
    paraPrIDRef: "0",
    styleIDRef: "0",
    pageBreak: "0",
    columnBreak: "0",
    merged: "0",
  });

  const titleRun = subElement(titlePara, HP_NS, "run", { charPrIDRef: "0" });
  const titleT = subElement(titleRun, HP_NS, "t");
  titleT.textContent = opts.title;

  // Insert title at the beginning
  targetSection.insertParagraph(titlePara, opts.paragraphIndex);

  // Insert TOC entries after title
  for (const entry of entries) {
    const tocPara = createTocEntryParagraph(doc, entry, opts);
    targetSection.insertParagraph(tocPara, opts.paragraphIndex + entries.indexOf(entry) + 1);
  }

  // Mark section as dirty
  targetSection.markDirty();

  return targetSection;
}

/**
 * Get TOC entries as a plain array (for custom TOC rendering)
 */
export function getTocEntries(document: HwpxOxmlDocument, maxLevel: number = 9): TocEntry[] {
  return scanForHeadings(document, maxLevel);
}
