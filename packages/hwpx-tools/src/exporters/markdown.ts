/**
 * Markdown exporter for HWPX documents.
 * Converts HWPX content to Markdown format with optional token-efficient normalization.
 */

import {
  HwpxPackage,
  HwpxOxmlDocument,
  HwpxOxmlParagraph,
  localName as domLocalName,
  childElements,
} from "@ubermensch1218/hwpxcore";

export type MarkdownImageMode = "markdown" | "placeholder" | "omit";
export type MarkdownTextFormatting = "none" | "basic";

export interface MarkdownExportOptions {
  /** Heading level for title (reserved for future use; default: 1) */
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
  /** Token-efficient mode for AI use (default: false) */
  tokenEfficient?: boolean;
  /** Collapse extra inline whitespace (default: tokenEfficient) */
  collapseWhitespace?: boolean;
  /** Text formatting level (default: tokenEfficient ? "none" : "basic") */
  textFormatting?: MarkdownTextFormatting;
  /** How to render image objects (default: tokenEfficient ? "placeholder" : "markdown") */
  imageMode?: MarkdownImageMode;
  /** Base path used for markdown image links (default: "images") */
  imageBasePath?: string;
  /** Placeholder template for imageMode="placeholder" */
  imagePlaceholderFormat?: string;
}

interface BinaryManifestItem {
  id: string;
  href: string;
  mediaType: string | null;
}

interface TableInfo {
  rows: number;
  cols: number;
  cells: string[][];
}

export interface MarkdownImageManifestItem {
  index: number;
  binaryItemId: string;
  href: string | null;
  mediaType: string | null;
  markdownPath: string | null;
  sectionIndex: number;
  paragraphIndex: number;
  width: number | null;
  height: number | null;
  missingPart: boolean;
}

export interface MarkdownExportStats {
  sections: number;
  paragraphs: number;
  tables: number;
  images: number;
}

export interface MarkdownExportResult {
  markdown: string;
  images: MarkdownImageManifestItem[];
  stats: MarkdownExportStats;
}

interface MarkdownParagraphResult {
  markdown: string;
  images: MarkdownImageManifestItem[];
  tableCount: number;
}

interface MarkdownBuildContext {
  packageRef: HwpxPackage;
  document: HwpxOxmlDocument;
  options: RequiredMarkdownOptions;
  manifestById: Map<string, BinaryManifestItem>;
  globalImageIndex: number;
}

interface RequiredMarkdownOptions {
  includeSectionSeparators: boolean;
  sectionSeparator: string;
  convertHeadingStyles: boolean;
  preserveLineBreaks: boolean;
  tokenEfficient: boolean;
  collapseWhitespace: boolean;
  textFormatting: MarkdownTextFormatting;
  imageMode: MarkdownImageMode;
  imageBasePath: string;
  imagePlaceholderFormat: string;
}

const DEFAULT_IMAGE_PLACEHOLDER = '[IMAGE:{index} id="{binaryItemId}" src="{href}"]';

/**
 * Export HWPX document content as Markdown.
 */
export function exportToMarkdown(
  hwpxPackage: HwpxPackage,
  options?: MarkdownExportOptions
): string {
  return exportToMarkdownBundle(hwpxPackage, options).markdown;
}

/**
 * Export HWPX document content as Markdown plus image manifest metadata.
 */
export function exportToMarkdownBundle(
  hwpxPackage: HwpxPackage,
  options?: MarkdownExportOptions
): MarkdownExportResult {
  const doc = HwpxOxmlDocument.fromPackage(hwpxPackage);
  const resolved = resolveOptions(options);

  const lines: string[] = [];
  const images: MarkdownImageManifestItem[] = [];
  let tableCount = 0;

  const context: MarkdownBuildContext = {
    packageRef: hwpxPackage,
    document: doc,
    options: resolved,
    manifestById: buildBinaryManifestById(doc.manifest),
    globalImageIndex: 0,
  };

  const sections = doc.sections;

  for (let sectionIndex = 0; sectionIndex < sections.length; sectionIndex++) {
    const section = sections[sectionIndex]!;

    if (sectionIndex > 0 && resolved.includeSectionSeparators) {
      lines.push("");
      lines.push(resolved.sectionSeparator);
      lines.push("");
    }

    const paragraphs = section.paragraphs;
    for (let paragraphIndex = 0; paragraphIndex < paragraphs.length; paragraphIndex++) {
      const paragraph = paragraphs[paragraphIndex]!;
      const paragraphResult = paragraphToMarkdown(paragraph, context, sectionIndex, paragraphIndex);

      if (paragraphResult.markdown) {
        lines.push(paragraphResult.markdown);
      }

      if (paragraphResult.images.length > 0) {
        images.push(...paragraphResult.images);
      }

      tableCount += paragraphResult.tableCount;
    }
  }

  const markdown = finalizeMarkdown(lines, resolved);

  return {
    markdown,
    images,
    stats: {
      sections: sections.length,
      paragraphs: doc.paragraphs.length,
      tables: tableCount,
      images: images.length,
    },
  };
}

/**
 * Convert a paragraph element to Markdown.
 */
function paragraphToMarkdown(
  paragraph: HwpxOxmlParagraph,
  context: MarkdownBuildContext,
  sectionIndex: number,
  paragraphIndex: number
): MarkdownParagraphResult {
  const element = paragraph.element;
  const styleIdRef = element.getAttribute("styleIDRef");

  const parts: string[] = [];
  const paragraphImages: MarkdownImageManifestItem[] = [];
  let tableCount = 0;

  for (const run of childElements(element)) {
    if (domLocalName(run) !== "run") continue;

    const style = context.document.charProperty(run.getAttribute("charPrIDRef"));

    for (const child of childElements(run)) {
      const name = domLocalName(child);

      if (name === "t") {
        const text = normalizeTextNode(child.textContent ?? "", context.options);
        if (!text) continue;

        parts.push(applyTextFormatting(text, style, context.options.textFormatting));
        continue;
      }

      if (name === "tbl") {
        const tableMd = tableToMarkdown(child, context.options);
        if (tableMd) {
          parts.push(`\n${tableMd}\n`);
          tableCount += 1;
        }
        continue;
      }

      const imageResult = imageElementToToken(child, context, sectionIndex, paragraphIndex);
      if (imageResult == null) {
        continue;
      }

      if (imageResult.token) {
        parts.push(imageResult.token);
      }
      paragraphImages.push(imageResult.image);
    }
  }

  let text = normalizeParagraphText(parts.join(""), context.options);
  if (!text) {
    return { markdown: "", images: paragraphImages, tableCount };
  }

  const listMarker = getListMarker(paragraph);
  const headingPrefix = getHeadingPrefix(styleIdRef, context.options);

  if (listMarker) {
    text = listMarker + text;
  } else if (headingPrefix) {
    text = headingPrefix + text;
  }

  return {
    markdown: text,
    images: paragraphImages,
    tableCount,
  };
}

function getHeadingPrefix(
  styleIdRef: string | null,
  options: RequiredMarkdownOptions
): string {
  if (!options.convertHeadingStyles || !styleIdRef) {
    return "";
  }

  const styleNum = parseInt(styleIdRef, 10);
  if (!Number.isFinite(styleNum) || styleNum < 1 || styleNum > 6) {
    return "";
  }

  return `${"#".repeat(styleNum)} `;
}

function normalizeTextNode(text: string, options: RequiredMarkdownOptions): string {
  if (!text) return "";

  let result = text.replace(/\r\n?/g, "\n");

  if (!options.preserveLineBreaks) {
    result = result.replace(/\n+/g, " ");
  }

  if (options.collapseWhitespace) {
    result = result.replace(/[\t ]+/g, " ");
  }

  return result;
}

function normalizeParagraphText(text: string, options: RequiredMarkdownOptions): string {
  if (!text) return "";

  let result = text;

  if (options.collapseWhitespace) {
    result = result
      .replace(/[\t ]+\n/g, "\n")
      .replace(/\n[\t ]+/g, "\n")
      .replace(/[\t ]{2,}/g, " ");
  }

  result = result.trim();
  return result;
}

function applyTextFormatting(
  text: string,
  style: { childAttributes?: Record<string, Record<string, string>> } | null,
  mode: MarkdownTextFormatting
): string {
  if (mode === "none" || !style?.childAttributes || !text.trim()) {
    return text;
  }

  const childAttrs = style.childAttributes;
  const hasBold = childAttrs["bold"] != null;
  const hasItalic = childAttrs["italic"] != null;
  const underlineType = childAttrs["underline"]?.["type"] ?? null;
  const strikeType = childAttrs["strikeout"]?.["type"] ?? null;
  const hasUnderline = underlineType != null && underlineType.toUpperCase() !== "NONE";
  const hasStrike = strikeType != null && strikeType.toUpperCase() !== "NONE";

  let result = text;

  if (hasBold && hasItalic) {
    result = `***${result}***`;
  } else if (hasBold) {
    result = `**${result}**`;
  } else if (hasItalic) {
    result = `*${result}*`;
  }

  if (hasStrike) {
    result = `~~${result}~~`;
  }

  if (hasUnderline) {
    result = `<u>${result}</u>`;
  }

  return result;
}

function imageElementToToken(
  element: Element,
  context: MarkdownBuildContext,
  sectionIndex: number,
  paragraphIndex: number
): { token: string; image: MarkdownImageManifestItem } | null {
  const img = findDescendantByLocalName(element, "img");
  if (!img) {
    return null;
  }

  const binaryItemId = (img.getAttribute("binaryItemIDRef") ?? "").trim();
  if (!binaryItemId) {
    return null;
  }

  context.globalImageIndex += 1;

  const manifestItem = context.manifestById.get(binaryItemId) ?? null;
  const href = manifestItem?.href ?? null;
  const mediaType = manifestItem?.mediaType ?? null;
  const markdownPath = href
    ? buildMarkdownImagePath(pathBaseName(href), context.options.imageBasePath)
    : null;

  const curSize = findDescendantByLocalName(element, "curSz");
  const width = parseInteger(curSize?.getAttribute("width") ?? null);
  const height = parseInteger(curSize?.getAttribute("height") ?? null);

  const imageItem: MarkdownImageManifestItem = {
    index: context.globalImageIndex,
    binaryItemId,
    href,
    mediaType,
    markdownPath,
    sectionIndex,
    paragraphIndex,
    width,
    height,
    missingPart: href ? !context.packageRef.hasPart(href) : true,
  };

  const token = renderImageToken(imageItem, context.options);
  return { token, image: imageItem };
}

function renderImageToken(
  image: MarkdownImageManifestItem,
  options: RequiredMarkdownOptions
): string {
  if (options.imageMode === "omit") {
    return "";
  }

  if (options.imageMode === "markdown") {
    const alt = `image ${image.index}`;
    const source = image.markdownPath ?? image.href ?? image.binaryItemId;
    return `![${alt}](${source})`;
  }

  const href = image.href ?? "";
  return options.imagePlaceholderFormat
    .replaceAll("{index}", String(image.index))
    .replaceAll("{binaryItemId}", image.binaryItemId)
    .replaceAll("{href}", href);
}

function buildBinaryManifestById(manifestRoot: Element): Map<string, BinaryManifestItem> {
  const manifestById = new Map<string, BinaryManifestItem>();

  const walk = (node: Element): void => {
    if (domLocalName(node) === "item") {
      const id = (node.getAttribute("id") ?? "").trim();
      const href = (node.getAttribute("href") ?? "").trim();
      const mediaType = (node.getAttribute("media-type") ?? "").trim() || null;

      if (id && href) {
        manifestById.set(id, { id, href, mediaType });
      }
    }

    for (const child of childElements(node)) {
      walk(child);
    }
  };

  walk(manifestRoot);
  return manifestById;
}

function buildMarkdownImagePath(fileName: string, imageBasePath: string): string {
  const base = trimSlashes(imageBasePath);
  if (!base || base === ".") {
    return fileName;
  }
  return `${base}/${fileName}`;
}

function trimSlashes(value: string): string {
  return value.replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
}

function pathBaseName(pathValue: string): string {
  const normalized = pathValue.replace(/\\/g, "/");
  const idx = normalized.lastIndexOf("/");
  return idx >= 0 ? normalized.substring(idx + 1) : normalized;
}

function parseInteger(value: string | null): number | null {
  if (value == null || value.trim() === "") return null;
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function findDescendantByLocalName(parent: Element, localName: string): Element | null {
  const walk = (node: Element): Element | null => {
    for (const child of childElements(node)) {
      if (domLocalName(child) === localName) {
        return child;
      }
      const nested = walk(child);
      if (nested) return nested;
    }
    return null;
  };

  return walk(parent);
}

/**
 * Get list marker if paragraph is part of a list.
 */
function getListMarker(paragraph: HwpxOxmlParagraph): string | null {
  const element = paragraph.element;

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
function tableToMarkdown(tableElement: Element, options: RequiredMarkdownOptions): string {
  const tableInfo = parseTable(tableElement, options);
  if (!tableInfo || tableInfo.rows === 0 || tableInfo.cols === 0) {
    return "";
  }

  const lines: string[] = [];

  const headerCells = fillRowCells(tableInfo.cells[0] ?? [], tableInfo.cols);
  lines.push("| " + headerCells.map((c) => escapeTableCell(c)).join(" | ") + " |");

  lines.push("| " + headerCells.map(() => "---").join(" | ") + " |");

  for (let i = 1; i < tableInfo.rows; i++) {
    const rowCells = fillRowCells(tableInfo.cells[i] ?? [], tableInfo.cols);
    lines.push("| " + rowCells.map((c) => escapeTableCell(c)).join(" | ") + " |");
  }

  return lines.join("\n");
}

function fillRowCells(rowCells: string[], expectedLength: number): string[] {
  if (rowCells.length >= expectedLength) {
    return rowCells;
  }

  const filled = [...rowCells];
  while (filled.length < expectedLength) {
    filled.push("");
  }
  return filled;
}

function escapeTableCell(value: string): string {
  return value.replace(/\n/g, " ").replace(/\|/g, "\\|").trim();
}

/**
 * Parse table structure from HWPX table element.
 */
function parseTable(tableElement: Element, options: RequiredMarkdownOptions): TableInfo | null {
  const rows: string[][] = [];
  let maxCols = 0;

  for (const tr of childElements(tableElement)) {
    if (domLocalName(tr) !== "tr") continue;

    const rowCells: string[] = [];

    for (const tc of childElements(tr)) {
      if (domLocalName(tc) !== "tc") continue;

      const cellText = getCellText(tc, options);
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
function getCellText(tcElement: Element, options: RequiredMarkdownOptions): string {
  const parts: string[] = [];

  const walk = (node: Element): void => {
    for (const child of childElements(node)) {
      const name = domLocalName(child);
      if (name === "t") {
        const text = normalizeTextNode(child.textContent ?? "", options);
        if (text) parts.push(text);
      } else {
        walk(child);
      }
    }
  };

  walk(tcElement);

  const text = parts.join(" ");
  return options.collapseWhitespace ? text.replace(/[\t ]{2,}/g, " ").trim() : text;
}

function finalizeMarkdown(lines: string[], options: RequiredMarkdownOptions): string {
  if (lines.length === 0) {
    return "";
  }

  let markdown = lines.join("\n");

  if (options.tokenEfficient) {
    markdown = markdown
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[\t ]+$/gm, "")
      .trim();
  }

  return markdown;
}

function resolveOptions(options?: MarkdownExportOptions): RequiredMarkdownOptions {
  const tokenEfficient = options?.tokenEfficient ?? false;

  return {
    includeSectionSeparators: options?.includeSectionSeparators ?? true,
    sectionSeparator: options?.sectionSeparator ?? "---",
    convertHeadingStyles: options?.convertHeadingStyles ?? true,
    preserveLineBreaks: options?.preserveLineBreaks ?? false,
    tokenEfficient,
    collapseWhitespace: options?.collapseWhitespace ?? tokenEfficient,
    textFormatting: options?.textFormatting ?? (tokenEfficient ? "none" : "basic"),
    imageMode: options?.imageMode ?? (tokenEfficient ? "placeholder" : "markdown"),
    imageBasePath: options?.imageBasePath ?? "images",
    imagePlaceholderFormat: options?.imagePlaceholderFormat ?? DEFAULT_IMAGE_PLACEHOLDER,
  };
}

/**
 * Export document with table of contents.
 */
export function exportToMarkdownWithToc(
  hwpxPackage: HwpxPackage,
  options?: MarkdownExportOptions
): string {
  const lines: string[] = [];

  lines.push("# Document");
  lines.push("");
  lines.push("## Table of Contents");
  lines.push("");
  lines.push("* [Section 1](#section-1)");
  lines.push("");
  lines.push("---");
  lines.push("");

  const content = exportToMarkdown(hwpxPackage, {
    ...options,
    includeSectionSeparators: true,
  });

  lines.push(content);
  return lines.join("\n");
}
