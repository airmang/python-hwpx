/**
 * Plain text exporter for HWPX documents.
 * Extracts all text content from HWPX documents.
 */

import { HwpxPackage, TextExtractor, Paragraph } from "@ubermensch1218/hwpxcore";

export interface TextExportOptions {
  /** Separator between paragraphs (default: "\n") */
  paragraphSeparator?: string;
  /** Separator between sections (default: "\n\n") */
  sectionSeparator?: string;
  /** Include section breaks with markers (default: false) */
  includeSectionMarkers?: boolean;
  /** Section marker format (default: "--- Section {n} ---") */
  sectionMarkerFormat?: string;
}

/**
 * Export HWPX document content as plain text.
 */
export function exportToText(hwpxPackage: HwpxPackage, options?: TextExportOptions): string {
  const extractor = new TextExtractor(hwpxPackage);
  const paragraphSeparator = options?.paragraphSeparator ?? "\n";
  const sectionSeparator = options?.sectionSeparator ?? "\n\n";
  const includeSectionMarkers = options?.includeSectionMarkers ?? false;
  const sectionMarkerFormat = options?.sectionMarkerFormat ?? "--- Section {n} ---";

  const sections = extractor.sections();

  if (sections.length === 0) {
    return "";
  }

  const parts: string[] = [];

  for (const section of sections) {
    if (includeSectionMarkers) {
      const marker = sectionMarkerFormat.replace("{n}", String(section.index + 1));
      parts.push(marker);
    }

    const paragraphs = extractor.extractParagraphs(section.index);
    const text = paragraphs.map((p) => p.text).join(paragraphSeparator);
    parts.push(text);
  }

  return parts.join(sectionSeparator);
}

/**
 * Export all text from HWPX document as a single string.
 */
export function exportAllText(hwpxPackage: HwpxPackage, separator: string = "\n"): string {
  const extractor = new TextExtractor(hwpxPackage);
  return extractor.extractText(separator);
}

/**
 * Export text from a specific section.
 */
export function exportSectionText(
  hwpxPackage: HwpxPackage,
  sectionIndex: number,
  separator: string = "\n"
): string {
  const extractor = new TextExtractor(hwpxPackage);
  const paragraphs = extractor.extractParagraphs(sectionIndex);
  return paragraphs.map((p) => p.text).join(separator);
}

/**
 * Get all paragraphs from the document.
 */
export function getAllParagraphs(hwpxPackage: HwpxPackage): Array<{
  sectionIndex: number;
  paragraphIndex: number;
  text: string;
}> {
  const extractor = new TextExtractor(hwpxPackage);
  return extractor.extractParagraphs();
}
