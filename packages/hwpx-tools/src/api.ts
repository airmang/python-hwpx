/**
 * High-level API for HWPX document operations.
 * Provides convenient file-based operations for CLI and other consumers.
 */

import { readFile } from "node:fs/promises";
import {
  HwpxPackage,
  HwpxOxmlDocument,
  TextExtractor,
} from "@ubermensch1218/hwpxcore";
import {
  exportToMarkdown as toMarkdown,
  exportToMarkdownBundle as toMarkdownBundle,
  exportToText as toText,
  exportAllText,
  exportSectionText,
  getAllParagraphs,
} from "./exporters/index.js";
import { convertHwpBytesToHwpxBytes } from "./converters/hwp-to-hwpx.js";

// Re-export from exporters for convenience
export {
  toMarkdown as exportToMarkdown,
  toMarkdownBundle as exportToMarkdownBundle,
  toText as exportToText,
  exportAllText,
  exportSectionText,
  getAllParagraphs,
};

export interface HwpxInfo {
  title?: string;
  author?: string;
  date?: string;
  sections: number;
  paragraphs: number;
  [key: string]: unknown;
}

/**
 * Open an HWPX file and return a HwpxPackage instance.
 */
export async function openHwpxFile(filePath: string): Promise<HwpxPackage> {
  const buffer = await readFile(filePath);
  return HwpxPackage.open(buffer);
}

/**
 * Convert an HWP (HWP 5.x binary) file to HWPX bytes.
 * Note: HWP parsing support is best-effort and may not preserve formatting.
 */
export async function convertHwpFileToHwpxBytes(filePath: string): Promise<Uint8Array> {
  const buffer = await readFile(filePath);
  return convertHwpBytesToHwpxBytes(new Uint8Array(buffer));
}

/**
 * Read text content from an HWPX file.
 * @param filePath - Path to the HWPX file
 * @param section - Optional section index (0-based). If not provided, reads all sections.
 */
export async function readHwpxFile(
  filePath: string,
  section?: number
): Promise<string> {
  const pkg = await openHwpxFile(filePath);
  const extractor = new TextExtractor(pkg);

  if (section !== undefined) {
    return extractor.extractParagraphs(section).map((p) => p.text).join("\n");
  }

  return extractor.extractText("\n");
}

/**
 * Export an HWPX file to Markdown format.
 * @param filePath - Path to the HWPX file
 */
export async function exportToMarkdownFile(filePath: string): Promise<string> {
  const pkg = await openHwpxFile(filePath);
  return toMarkdown(pkg);
}

/**
 * Export an HWPX file to Markdown with image manifest metadata.
 * @param filePath - Path to the HWPX file
 */
export async function exportToMarkdownBundleFile(
  filePath: string
): Promise<import("./exporters/index.js").MarkdownExportResult> {
  const pkg = await openHwpxFile(filePath);
  return toMarkdownBundle(pkg);
}

/**
 * Export an HWPX file to plain text format.
 * @param filePath - Path to the HWPX file
 */
export async function exportToTxtFile(filePath: string): Promise<string> {
  const pkg = await openHwpxFile(filePath);
  return toText(pkg);
}

/**
 * Extract a specific part from an HWPX file.
 * @param filePath - Path to the HWPX file
 * @param partName - Name of the part to extract (e.g., "Contents/section0.xml")
 */
export async function extractPart(
  filePath: string,
  partName: string
): Promise<string> {
  const pkg = await openHwpxFile(filePath);

  if (!pkg.hasPart(partName)) {
    throw new Error(`Part not found: ${partName}`);
  }

  return pkg.getText(partName);
}

/**
 * Get metadata and statistics from an HWPX file.
 * @param filePath - Path to the HWPX file
 */
export async function getHwpxInfo(filePath: string): Promise<HwpxInfo> {
  const pkg = await openHwpxFile(filePath);
  const extractor = new TextExtractor(pkg);
  const doc = HwpxOxmlDocument.fromPackage(pkg);

  const sections = extractor.sections();
  const allParagraphs = extractor.extractParagraphs();

  // Try to get metadata from manifest/document
  const info: HwpxInfo = {
    sections: sections.length,
    paragraphs: allParagraphs.length,
  };

  // Try to extract title, author, date from metadata
  try {
    const manifestText = pkg.getText(HwpxPackage.MANIFEST_PATH);

    // Parse metadata from manifest (simplified)
    const titleMatch = /<dc:title[^>]*>([^<]*)<\/dc:title>/i.exec(manifestText);
    if (titleMatch?.[1]) {
      info.title = titleMatch[1];
    }

    const authorMatch = /<dc:creator[^>]*>([^<]*)<\/dc:creator>/i.exec(manifestText);
    if (authorMatch?.[1]) {
      info.author = authorMatch[1];
    }

    const dateMatch = /<dc:date[^>]*>([^<]*)<\/dc:date>/i.exec(manifestText);
    if (dateMatch?.[1]) {
      info.date = dateMatch[1];
    }
  } catch {
    // Metadata extraction failed, continue with defaults
  }

  return info;
}

/**
 * List all parts in an HWPX file.
 * @param filePath - Path to the HWPX file
 */
export async function listParts(filePath: string): Promise<string[]> {
  const pkg = await openHwpxFile(filePath);
  return pkg.partNames();
}

/**
 * Get sections information from an HWPX file.
 * @param filePath - Path to the HWPX file
 */
export async function getSections(
  filePath: string
): Promise<Array<{ index: number; name: string; path: string }>> {
  const pkg = await openHwpxFile(filePath);
  const extractor = new TextExtractor(pkg);
  return extractor.sections();
}

// Alias for CLI compatibility (exportToMarkdown is provided by exporters/index.js)
export const exportToTxt = exportToTxtFile;

// Re-export types
export type {
  TextExportOptions,
  MarkdownExportOptions,
  MarkdownExportResult,
  MarkdownImageManifestItem,
  MarkdownExportStats,
  MarkdownImageMode,
  MarkdownTextFormatting,
} from "./exporters/index.js";
