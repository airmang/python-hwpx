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

export class HwpxDocument {
  private _package: HwpxPackage;
  private _oxml: HwpxOxmlDocument;

  constructor(pkg: HwpxPackage, oxml: HwpxOxmlDocument) {
    this._package = pkg;
    this._oxml = oxml;
  }

  /** Open an HWPX document from a Uint8Array or ArrayBuffer. */
  static async open(source: Uint8Array | ArrayBuffer): Promise<HwpxDocument> {
    const pkg = await HwpxPackage.open(source);
    const oxml = HwpxOxmlDocument.fromPackage(pkg);
    return new HwpxDocument(pkg, oxml);
  }

  /** Return the underlying package. */
  get package(): HwpxPackage {
    return this._package;
  }

  /** Return the OXML document object model. */
  get oxml(): HwpxOxmlDocument {
    return this._oxml;
  }

  // ── Section access ──────────────────────────────────────────────────

  /** Return the sections in this document. */
  get sections(): HwpxOxmlSection[] {
    return this._oxml.sections;
  }

  /** Return the number of sections. */
  get sectionCount(): number {
    return this._oxml.sections.length;
  }

  /** Return a specific section by index. */
  section(index: number = 0): HwpxOxmlSection {
    const sections = this._oxml.sections;
    if (index < 0 || index >= sections.length) {
      throw new Error(`Section index ${index} out of range (0-${sections.length - 1})`);
    }
    return sections[index]!;
  }

  // ── Paragraph access ───────────────────────────────────────────────

  /** Return all paragraphs across all sections. */
  get paragraphs(): HwpxOxmlParagraph[] {
    return this._oxml.paragraphs;
  }

  /** Append a new paragraph to the last section (or specified section). */
  addParagraph(text: string = "", opts?: {
    sectionIndex?: number;
    paraPrIdRef?: string | number;
    styleIdRef?: string | number;
    charPrIdRef?: string | number;
  }): HwpxOxmlParagraph {
    return this._oxml.addParagraph(text, {
      sectionIndex: opts?.sectionIndex,
      paraPrIdRef: opts?.paraPrIdRef,
      styleIdRef: opts?.styleIdRef,
      charPrIdRef: opts?.charPrIdRef,
    });
  }

  // ── Text access ────────────────────────────────────────────────────

  /** Return the full text of the document (all paragraphs joined). */
  get text(): string {
    return this.paragraphs.map((p) => p.text).join("\n");
  }

  /** Replace text across all paragraphs. */
  replaceText(search: string, replacement: string, count?: number): number {
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
    const tables: HwpxOxmlTable[] = [];
    for (const paragraph of this.paragraphs) {
      tables.push(...paragraph.tables);
    }
    return tables;
  }

  // ── Header/Footer access ──────────────────────────────────────────

  /** Return the OXML header objects. */
  get headers(): HwpxOxmlHeader[] {
    return this._oxml.headers;
  }

  // ── Style access ──────────────────────────────────────────────────

  /** Get character properties map. */
  get charProperties(): Record<string, RunStyle> {
    return this._oxml.charProperties;
  }

  /** Look up a character property by ID. */
  charProperty(charPrIdRef: string | number | null): RunStyle | null {
    return this._oxml.charProperty(charPrIdRef);
  }

  /** Ensure a run style with the given formatting exists. */
  ensureRunStyle(opts: { bold?: boolean; italic?: boolean; underline?: boolean }): string {
    return this._oxml.ensureRunStyle(opts);
  }

  /** Ensure a basic border fill exists and return its ID. */
  ensureBasicBorderFill(): string {
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

  // ── Memo access ───────────────────────────────────────────────────

  /** Return all memos across all sections. */
  get memos(): HwpxOxmlMemo[] {
    const memos: HwpxOxmlMemo[] = [];
    for (const section of this.sections) {
      memos.push(...section.memos);
    }
    return memos;
  }

  // ── Save ──────────────────────────────────────────────────────────

  /** Save the document, returning the HWPX file as a Uint8Array. */
  async save(): Promise<Uint8Array> {
    const updates = this._oxml.serialize();
    const result = await this._package.save(updates);
    this._oxml.resetDirty();
    return result;
  }
}
