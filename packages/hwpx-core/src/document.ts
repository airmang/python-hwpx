/**
 * High-level HwpxDocument API.
 * Ported from Python hwpx/document.py
 */

import { HwpxPackage } from "./package.js";
import {
  HwpxOxmlDocument,
  HwpxOxmlSection,
  HwpxOxmlParagraph,
  HwpxOxmlRun,
  HwpxOxmlTable,
  HwpxOxmlTableCell,
  HwpxOxmlMemo,
  HwpxOxmlHeader,
  RunStyle,
} from "./oxml/document.js";
import type { Paragraph, Run, Section } from "./oxml/body.js";
import type {
  Style,
  ParagraphProperty,
  Bullet,
  MemoShape,
  TrackChange,
  TrackChangeAuthor,
} from "./oxml/header.js";
import type { GenericElement } from "./oxml/common.js";
import { __version__ } from "./version.js";

export interface DocumentVersionInfo {
  path: string | null;
  targetApplication: string | null;
  major: number | null;
  minor: number | null;
  micro: number | null;
  buildNumber: number | null;
  os: number | null;
  xmlVersion: string | null;
  application: string | null;
  appVersion: string | null;
}

function parseNullableInt(value: string | null): number | null {
  if (value == null) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

export class HwpxDocument {
  private _package: HwpxPackage;
  private _oxml: HwpxOxmlDocument;
  private _closed = false;

  constructor(pkg: HwpxPackage, oxml: HwpxOxmlDocument) {
    this._package = pkg;
    this._oxml = oxml;
  }

  private _assertOpen(): void {
    if (this._closed) {
      throw new Error("HwpxDocument is closed");
    }
  }

  /** Open an HWPX document from a Uint8Array or ArrayBuffer. */
  static async open(source: Uint8Array | ArrayBuffer): Promise<HwpxDocument> {
    const pkg = await HwpxPackage.open(source);
    const oxml = HwpxOxmlDocument.fromPackage(pkg);
    return new HwpxDocument(pkg, oxml);
  }

  /** Return the underlying package. */
  get package(): HwpxPackage {
    this._assertOpen();
    return this._package;
  }

  /** Return the OXML document object model. */
  get oxml(): HwpxOxmlDocument {
    this._assertOpen();
    return this._oxml;
  }

  get closed(): boolean {
    return this._closed;
  }

  get libraryVersion(): string {
    return __version__;
  }

  get documentVersionInfo(): DocumentVersionInfo | null {
    this._assertOpen();
    const version = this._oxml.version;
    if (!version) return null;

    const element = version.element;
    const path = this._package.versionPath();

    return {
      path,
      targetApplication: element.getAttribute("tagetApplication") ?? element.getAttribute("targetApplication"),
      major: parseNullableInt(element.getAttribute("major")),
      minor: parseNullableInt(element.getAttribute("minor")),
      micro: parseNullableInt(element.getAttribute("micro")),
      buildNumber: parseNullableInt(element.getAttribute("buildNumber")),
      os: parseNullableInt(element.getAttribute("os")),
      xmlVersion: element.getAttribute("xmlVersion"),
      application: element.getAttribute("application"),
      appVersion: element.getAttribute("appVersion"),
    };
  }

  close(): void {
    if (this._closed) return;
    this._package.close();
    this._closed = true;
  }

  toJSON(): {
    sectionCount: number;
    paragraphCount: number;
    tableCount: number;
    memoCount: number;
    headerCount: number;
    textPreview: string;
  } {
    const text = this.text;
    return {
      sectionCount: this.sectionCount,
      paragraphCount: this.paragraphs.length,
      tableCount: this.tables.length,
      memoCount: this.memos.length,
      headerCount: this.headers.length,
      textPreview: text.slice(0, 120),
    };
  }

  toString(): string {
    const summary = this.toJSON();
    return `HwpxDocument(sections=${summary.sectionCount}, paragraphs=${summary.paragraphCount}, tables=${summary.tableCount}, memos=${summary.memoCount})`;
  }

  // ── Section access ──────────────────────────────────────────────────

  /** Return the sections in this document. */
  get sections(): HwpxOxmlSection[] {
    this._assertOpen();
    return this._oxml.sections;
  }

  /** Return the number of sections. */
  get sectionCount(): number {
    this._assertOpen();
    return this._oxml.sections.length;
  }

  /** Return a specific section by index. */
  section(index: number = 0): HwpxOxmlSection {
    this._assertOpen();
    const sections = this._oxml.sections;
    if (index < 0 || index >= sections.length) {
      throw new Error(`Section index ${index} out of range (0-${sections.length - 1})`);
    }
    return sections[index]!;
  }

  // ── Paragraph access ───────────────────────────────────────────────

  /** Return all paragraphs across all sections. */
  get paragraphs(): HwpxOxmlParagraph[] {
    this._assertOpen();
    return this._oxml.paragraphs;
  }

  /** Append a new paragraph to the last section (or specified section). */
  addParagraph(text: string = "", opts?: {
    sectionIndex?: number;
    paraPrIdRef?: string | number;
    styleIdRef?: string | number;
    charPrIdRef?: string | number;
  }): HwpxOxmlParagraph {
    this._assertOpen();
    return this._oxml.addParagraph(text, {
      sectionIndex: opts?.sectionIndex,
      paraPrIdRef: opts?.paraPrIdRef,
      styleIdRef: opts?.styleIdRef,
      charPrIdRef: opts?.charPrIdRef,
    });
  }

  /** Insert a new paragraph at a specific position within a section. */
  insertParagraphAt(sectionIndex: number, paragraphIndex: number, text: string = "", opts?: {
    paraPrIdRef?: string | number;
    styleIdRef?: string | number;
    charPrIdRef?: string | number;
  }): HwpxOxmlParagraph {
    this._assertOpen();
    return this._oxml.insertParagraphAt(sectionIndex, paragraphIndex, text, opts);
  }

  /** Remove a paragraph by section and paragraph index. */
  removeParagraph(sectionIndex: number, paragraphIndex: number): void {
    this._assertOpen();
    this._oxml.removeParagraph(sectionIndex, paragraphIndex);
  }

  // ── Text access ────────────────────────────────────────────────────

  /** Return the full text of the document (all paragraphs joined). */
  get text(): string {
    this._assertOpen();
    return this.paragraphs.map((p) => p.text).join("\n");
  }

  /** Replace text across all paragraphs. */
  replaceText(search: string, replacement: string, count?: number): number {
    this._assertOpen();
    let totalReplacements = 0;
    let remaining = count;

    for (const paragraph of this.paragraphs) {
      if (remaining != null && remaining <= 0) break;
      for (const run of paragraph.runs) {
        if (remaining != null && remaining <= 0) break;
        const replaced = run.replaceText(search, replacement, remaining);
        totalReplacements += replaced;
        if (remaining != null) remaining -= replaced;
      }
    }

    return totalReplacements;
  }

  // ── Table access ───────────────────────────────────────────────────

  /** Return all tables across all sections. */
  get tables(): HwpxOxmlTable[] {
    this._assertOpen();
    const tables: HwpxOxmlTable[] = [];
    for (const paragraph of this.paragraphs) {
      tables.push(...paragraph.tables);
    }
    return tables;
  }

  // ── Header/Footer access ──────────────────────────────────────────

  /** Return the OXML header objects. */
  get headers(): HwpxOxmlHeader[] {
    this._assertOpen();
    return this._oxml.headers;
  }

  // ── Style access ──────────────────────────────────────────────────

  /** Get character properties map. */
  get charProperties(): Record<string, RunStyle> {
    this._assertOpen();
    return this._oxml.charProperties;
  }

  /** Look up a character property by ID. */
  charProperty(charPrIdRef: string | number | null): RunStyle | null {
    this._assertOpen();
    return this._oxml.charProperty(charPrIdRef);
  }

  /** Resolve a numeric font ID to its face name. */
  fontFaceName(fontId: string | number | null, lang?: string): string | null {
    this._assertOpen();
    return this._oxml.fontFaceName(fontId, lang);
  }

  /** Ensure a run style with the given formatting exists. */
  ensureRunStyle(opts: {
    bold?: boolean;
    italic?: boolean;
    underline?: boolean;
    strikethrough?: boolean;
    fontFamily?: string;
    fontSize?: number;
    textColor?: string;
    highlightColor?: string;
    baseCharPrId?: string | number;
  }): string {
    this._assertOpen();
    return this._oxml.ensureRunStyle(opts);
  }

  /** Ensure a paragraph style with the given formatting exists. */
  ensureParaStyle(opts: {
    alignment?: string;
    lineSpacingValue?: number;
    marginLeft?: number;
    marginRight?: number;
    indent?: number;
    baseParaPrId?: string | number;
  }): string {
    this._assertOpen();
    return this._oxml.ensureParaStyle(opts);
  }

  /** Ensure a basic border fill exists and return its ID. */
  ensureBasicBorderFill(): string {
    this._assertOpen();
    return this._oxml.ensureBasicBorderFill();
  }

  // ── Image insertion ─────────────────────────────────────────────────

  /**
   * Add an image to the document.
   * @param imageData - The image binary data as Uint8Array
   * @param opts - mediaType, width/height in mm (or hwpUnits if useHwpUnits=true)
   * @returns The paragraph containing the image
   */
  addImage(imageData: Uint8Array, opts: {
    mediaType: string;
    widthMm: number;
    heightMm: number;
    sectionIndex?: number;
    textWrap?: string;
    treatAsChar?: boolean;
  }): HwpxOxmlParagraph {
    this._assertOpen();
    // Register binary in package
    const binaryItemId = this._package.addBinaryItem(imageData, {
      mediaType: opts.mediaType,
    });

    // Convert mm to hwpUnits (7200 hwpUnits = 1 inch = 25.4 mm)
    const width = Math.round(opts.widthMm * 7200 / 25.4);
    const height = Math.round(opts.heightMm * 7200 / 25.4);

    // Create a paragraph with the picture
    const para = this.addParagraph("", { sectionIndex: opts.sectionIndex });
    para.addPicture(binaryItemId, {
      width,
      height,
      textWrap: opts.textWrap,
      treatAsChar: opts.treatAsChar,
    });

    return para;
  }

  // ── Equation insertion ──────────────────────────────────────────────

  /**
   * Add an equation to the document using HWP equation script notation.
   *
   * Script examples (from Hancom equation spec):
   *   - "rmCH _{3} COOH"         → CH₃COOH (Roman chemistry)
   *   - "1 over 2"               → ½ (fraction)
   *   - "sqrt 2"                 → √2 (square root)
   *   - "E=mc^2"                 → E=mc² (superscript)
   *   - "rm 2H_2 O = 2H_2 + O_2" → 2H₂O = 2H₂ + O₂
   *   - "sum_{x=0} ^{inf}"       → Σ (summation with bounds)
   *   - "int _1 ^2 {3x^2}dx"    → integral
   *   - "alpha beta Gamma"       → Greek letters
   *
   * @param script - HWP equation script text
   * @param opts - Optional: sectionIndex, textColor, font, baseUnit, baseLine, width/height in hwpUnits
   * @returns The paragraph containing the equation
   */
  addEquation(script: string, opts?: {
    sectionIndex?: number;
    textColor?: string;
    font?: string;
    baseUnit?: number;
    baseLine?: number;
    width?: number;
    height?: number;
  }): HwpxOxmlParagraph {
    this._assertOpen();
    const para = this.addParagraph("", { sectionIndex: opts?.sectionIndex });
    para.addEquation(script, {
      textColor: opts?.textColor,
      font: opts?.font,
      baseUnit: opts?.baseUnit,
      baseLine: opts?.baseLine,
      width: opts?.width,
      height: opts?.height,
    });
    return para;
  }

  // ── Memo access ───────────────────────────────────────────────────

  /** Return all memos across all sections. */
  get memos(): HwpxOxmlMemo[] {
    this._assertOpen();
    const memos: HwpxOxmlMemo[] = [];
    for (const section of this.sections) {
      memos.push(...section.memos);
    }
    return memos;
  }

  // ── Save ──────────────────────────────────────────────────────────

  async saveToBuffer(): Promise<Uint8Array> {
    this._assertOpen();
    const updates = this._oxml.serialize();
    const result = await this._package.save(updates);
    this._oxml.resetDirty();
    return result;
  }

  async saveToBlob(): Promise<Blob> {
    this._assertOpen();
    const bytes = await this.saveToBuffer();
    const arrayBuffer = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(arrayBuffer).set(bytes);
    return new Blob([arrayBuffer], {
      type: "application/hwp+zip",
    });
  }

  async saveToPath(path: string): Promise<void> {
    this._assertOpen();
    const bytes = await this.saveToBuffer();
    const mod = await import("node:fs/promises");
    await mod.writeFile(path, bytes);
  }

  /** Save the document, returning the HWPX file as a Uint8Array. */
  async save(): Promise<Uint8Array> {
    this._assertOpen();
    return this.saveToBuffer();
  }
}
