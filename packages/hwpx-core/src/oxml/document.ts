/**
 * Object model mapping for XML parts of an HWPX document.
 *
 * HwpxOxmlDocument is the top-level entry point.
 * All sub-module exports are re-exported here so that existing
 * imports from "./oxml/document.js" continue to work unchanged.
 */

import { getAttributes } from "../xml/dom.js";
import { HwpxPackage } from "../package.js";
import type { RunStyle } from "./types.js";
import { charPropertiesFromHeader } from "./types.js";
import { HwpxOxmlSection } from "./section.js";
import { HwpxOxmlHeader } from "./header-part.js";
import { HwpxOxmlParagraph } from "./paragraph.js";
import {
  HwpxOxmlSimplePart,
  HwpxOxmlMasterPage,
  HwpxOxmlHistory,
  HwpxOxmlVersion,
} from "./simple-parts.js";
import {
  HH_NS,
  findChild,
  findAllChildren,
  subElement,
} from "./xml-utils.js";

// -- Re-export all public types and classes from sub-modules --

export * from "./xml-utils.js";
export * from "./types.js";
export * from "./simple-parts.js";
export * from "./table.js";
export * from "./paragraph.js";
export * from "./header-part.js";
export * from "./memo.js";
export * from "./section.js";
export * from "./toc.js";

// -- HwpxOxmlDocument --

export class HwpxOxmlDocument {
  private _manifest: Element;
  private _sections: HwpxOxmlSection[];
  private _headers: HwpxOxmlHeader[];
  private _masterPages: HwpxOxmlMasterPage[];
  private _histories: HwpxOxmlHistory[];
  private _version: HwpxOxmlVersion | null;
  private _charPropertyCache: Record<string, RunStyle> | null = null;

  constructor(
    manifest: Element,
    sections: HwpxOxmlSection[],
    headers: HwpxOxmlHeader[],
    opts?: {
      masterPages?: HwpxOxmlMasterPage[];
      histories?: HwpxOxmlHistory[];
      version?: HwpxOxmlVersion | null;
    },
  ) {
    this._manifest = manifest;
    this._sections = [...sections];
    this._headers = [...headers];
    this._masterPages = [...(opts?.masterPages ?? [])];
    this._histories = [...(opts?.histories ?? [])];
    this._version = opts?.version ?? null;

    for (const s of this._sections) s.attachDocument(this);
    for (const h of this._headers) h.attachDocument(this);
    for (const m of this._masterPages) m.attachDocument(this);
    for (const h of this._histories) h.attachDocument(this);
    if (this._version) this._version.attachDocument(this);
  }

  static fromPackage(pkg: HwpxPackage): HwpxOxmlDocument {
    const manifest = pkg.getXml(HwpxPackage.MANIFEST_PATH);
    const sectionPaths = pkg.sectionPaths();
    const headerPaths = pkg.headerPaths();
    const masterPagePaths = pkg.masterPagePaths();
    const historyPaths = pkg.historyPaths();
    const versionPath = pkg.versionPath();

    const sections = sectionPaths.map((path) => new HwpxOxmlSection(path, pkg.getXml(path)));
    const headers = headerPaths.map((path) => new HwpxOxmlHeader(path, pkg.getXml(path)));
    const masterPages = masterPagePaths
      .filter((path) => pkg.hasPart(path))
      .map((path) => new HwpxOxmlMasterPage(path, pkg.getXml(path)));
    const histories = historyPaths
      .filter((path) => pkg.hasPart(path))
      .map((path) => new HwpxOxmlHistory(path, pkg.getXml(path)));
    let version: HwpxOxmlVersion | null = null;
    if (versionPath && pkg.hasPart(versionPath)) {
      version = new HwpxOxmlVersion(versionPath, pkg.getXml(versionPath));
    }

    return new HwpxOxmlDocument(manifest, sections, headers, { masterPages, histories, version });
  }

  get manifest(): Element { return this._manifest; }
  get sections(): HwpxOxmlSection[] { return [...this._sections]; }
  get headers(): HwpxOxmlHeader[] { return [...this._headers]; }
  get masterPages(): HwpxOxmlMasterPage[] { return [...this._masterPages]; }
  get histories(): HwpxOxmlHistory[] { return [...this._histories]; }
  get version(): HwpxOxmlVersion | null { return this._version; }

  // -- Char property cache --

  private _ensureCharPropertyCache(): Record<string, RunStyle> {
    if (this._charPropertyCache == null) {
      const mapping: Record<string, RunStyle> = {};
      for (const header of this._headers) {
        Object.assign(mapping, charPropertiesFromHeader(header.element));
      }
      this._charPropertyCache = mapping;
    }
    return this._charPropertyCache;
  }

  invalidateCharPropertyCache(): void { this._charPropertyCache = null; }

  /**
   * Resolve a numeric font ID to a font face name.
   * @param fontId - numeric font ID string (e.g. "7")
   * @param lang - language group (default "HANGUL")
   * @returns font face name or null
   */
  fontFaceName(fontId: string | number | null, lang: string = "HANGUL"): string | null {
    if (fontId == null) return null;
    const id = String(fontId);
    for (const header of this._headers) {
      const fontfaces = findChild(
        findChild(header.element, HH_NS, "refList") ?? header.element,
        HH_NS, "fontfaces",
      );
      if (!fontfaces) continue;
      for (const langGroup of findAllChildren(fontfaces, HH_NS, "fontface")) {
        if (langGroup.getAttribute("lang") !== lang) continue;
        for (const font of findAllChildren(langGroup, HH_NS, "font")) {
          if (font.getAttribute("id") === id) {
            return font.getAttribute("face");
          }
        }
      }
    }
    return null;
  }

  get charProperties(): Record<string, RunStyle> {
    return { ...this._ensureCharPropertyCache() };
  }

  charProperty(charPrIdRef: string | number | null): RunStyle | null {
    if (charPrIdRef == null) return null;
    const key = String(charPrIdRef).trim();
    if (!key) return null;
    const cache = this._ensureCharPropertyCache();
    const style = cache[key];
    if (style) return style;
    try {
      const normalized = String(parseInt(key, 10));
      return cache[normalized] ?? null;
    } catch { return null; }
  }

  ensureRunStyle(opts: {
    bold?: boolean;
    italic?: boolean;
    underline?: boolean;
    strikethrough?: boolean;
    fontFamily?: string;
    fontSize?: number;      // in pt
    textColor?: string;     // hex color e.g. "#FF0000"
    highlightColor?: string; // hex color or "none"
    baseCharPrId?: string | number;
  }): string {
    if (this._headers.length === 0) throw new Error("document does not contain any headers");
    const header = this._headers[0]!;

    // Resolve font ID if fontFamily is specified
    let fontId: string | null = null;
    if (opts.fontFamily) {
      fontId = header.ensureFontFace(opts.fontFamily);
    }

    const targetBold = !!opts.bold;
    const targetItalic = !!opts.italic;
    const targetUnderline = !!opts.underline;
    const targetStrikethrough = !!opts.strikethrough;
    const targetHeight = opts.fontSize != null ? String(Math.round(opts.fontSize * 100)) : null;
    const targetTextColor = opts.textColor ?? null;
    const targetShadeColor = opts.highlightColor ?? null;

    const predicate = (element: Element): boolean => {
      // Check bold
      const boldPresent = findChild(element, HH_NS, "bold") != null;
      if (boldPresent !== targetBold) return false;
      // Check italic
      const italicPresent = findChild(element, HH_NS, "italic") != null;
      if (italicPresent !== targetItalic) return false;
      // Check underline
      const underlineEl = findChild(element, HH_NS, "underline");
      const underlinePresent = underlineEl != null && (underlineEl.getAttribute("type") ?? "").toUpperCase() !== "NONE";
      if (underlinePresent !== targetUnderline) return false;
      // Check strikethrough
      const strikeEl = findChild(element, HH_NS, "strikeout");
      const strikePresent = strikeEl != null && (strikeEl.getAttribute("type") ?? "").toUpperCase() !== "NONE";
      if (strikePresent !== targetStrikethrough) return false;
      // Check height
      if (targetHeight != null && element.getAttribute("height") !== targetHeight) return false;
      // Check textColor
      if (targetTextColor != null && element.getAttribute("textColor") !== targetTextColor) return false;
      // Check shadeColor
      if (targetShadeColor != null && element.getAttribute("shadeColor") !== targetShadeColor) return false;
      // Check font
      if (fontId != null) {
        const fontRef = findChild(element, HH_NS, "fontRef");
        if (!fontRef) return false;
        if (fontRef.getAttribute("hangul") !== fontId) return false;
      }
      return true;
    };

    const modifier = (element: Element): void => {
      // Bold / italic
      for (const child of findAllChildren(element, HH_NS, "bold")) element.removeChild(child);
      for (const child of findAllChildren(element, HH_NS, "italic")) element.removeChild(child);
      if (targetBold) subElement(element, HH_NS, "bold");
      if (targetItalic) subElement(element, HH_NS, "italic");

      // Underline
      const underlineNodes = findAllChildren(element, HH_NS, "underline");
      const baseAttrs: Record<string, string> = underlineNodes.length > 0 ? getAttributes(underlineNodes[0]!) : {};
      for (const child of underlineNodes) element.removeChild(child);
      if (targetUnderline) {
        const attrs = { ...baseAttrs };
        if (!attrs["type"] || attrs["type"].toUpperCase() === "NONE") attrs["type"] = "SOLID";
        if (!attrs["shape"]) attrs["shape"] = baseAttrs["shape"] ?? "SOLID";
        if (!attrs["color"]) attrs["color"] = baseAttrs["color"] ?? "#000000";
        subElement(element, HH_NS, "underline", attrs);
      } else {
        const attrs: Record<string, string> = { ...baseAttrs, type: "NONE" };
        if (!attrs["shape"]) attrs["shape"] = baseAttrs["shape"] ?? "SOLID";
        subElement(element, HH_NS, "underline", attrs);
      }

      // Strikethrough
      const strikeNodes = findAllChildren(element, HH_NS, "strikeout");
      const strikeBaseAttrs: Record<string, string> = strikeNodes.length > 0 ? getAttributes(strikeNodes[0]!) : {};
      for (const child of strikeNodes) element.removeChild(child);
      if (targetStrikethrough) {
        const attrs = { ...strikeBaseAttrs };
        if (!attrs["type"] || attrs["type"].toUpperCase() === "NONE") attrs["type"] = "SOLID";
        if (!attrs["shape"]) attrs["shape"] = strikeBaseAttrs["shape"] ?? "SOLID";
        if (!attrs["color"]) attrs["color"] = strikeBaseAttrs["color"] ?? "#000000";
        subElement(element, HH_NS, "strikeout", attrs);
      } else {
        const attrs: Record<string, string> = { ...strikeBaseAttrs, type: "NONE" };
        if (!attrs["shape"]) attrs["shape"] = strikeBaseAttrs["shape"] ?? "SOLID";
        subElement(element, HH_NS, "strikeout", attrs);
      }

      // Font size (height)
      if (targetHeight != null) {
        element.setAttribute("height", targetHeight);
      }

      // Text color
      if (targetTextColor != null) {
        element.setAttribute("textColor", targetTextColor);
      }

      // Highlight / shade color
      if (targetShadeColor != null) {
        element.setAttribute("shadeColor", targetShadeColor);
      }

      // Font family — update fontRef child
      if (fontId != null) {
        let fontRef = findChild(element, HH_NS, "fontRef");
        if (fontRef) {
          // Set all lang attributes to the same fontId
          fontRef.setAttribute("hangul", fontId);
          fontRef.setAttribute("latin", fontId);
          fontRef.setAttribute("hanja", fontId);
          fontRef.setAttribute("japanese", fontId);
          fontRef.setAttribute("other", fontId);
          fontRef.setAttribute("symbol", fontId);
          fontRef.setAttribute("user", fontId);
        } else {
          subElement(element, HH_NS, "fontRef", {
            hangul: fontId, latin: fontId, hanja: fontId,
            japanese: fontId, other: fontId, symbol: fontId, user: fontId,
          });
        }
      }
    };

    const element = header!.ensureCharProperty({
      predicate,
      modifier,
      baseCharPrId: opts.baseCharPrId,
    });
    const charId = element.getAttribute("id");
    if (!charId) throw new Error("charPr element is missing an id");
    return charId;
  }

  ensureParaStyle(opts: {
    alignment?: string;
    lineSpacingValue?: number; // e.g. 160 for 1.6x (percent)
    marginLeft?: number; // hwpUnit
    marginRight?: number; // hwpUnit
    indent?: number; // hwpUnit (first-line indent, "intent" in HWPX)
    baseParaPrId?: string | number;
  }): string {
    if (this._headers.length === 0) throw new Error("document does not contain any headers");
    const header = this._headers[0]!;

    const targetAlignment = opts.alignment?.toUpperCase() ?? null;
    const targetLineSpacingValue = opts.lineSpacingValue != null ? String(Math.round(opts.lineSpacingValue)) : null;
    const targetMarginLeft = opts.marginLeft != null ? String(Math.round(opts.marginLeft)) : null;
    const targetMarginRight = opts.marginRight != null ? String(Math.round(opts.marginRight)) : null;
    const targetIndent = opts.indent != null ? String(Math.round(opts.indent)) : null;

    const predicate = (element: Element): boolean => {
      if (targetAlignment != null) {
        const align = findChild(element, HH_NS, "align");
        const h = (align?.getAttribute("horizontal") ?? "JUSTIFY").toUpperCase();
        if (h !== targetAlignment) return false;
      }
      if (targetLineSpacingValue != null) {
        const ls = findChild(element, HH_NS, "lineSpacing");
        const v = ls?.getAttribute("value") ?? "160";
        if (v !== targetLineSpacingValue) return false;
      }
      if (targetMarginLeft != null || targetMarginRight != null || targetIndent != null) {
        const margin = findChild(element, HH_NS, "margin");
        if (!margin) return false;
        if (targetMarginLeft != null && (margin.getAttribute("left") ?? "0") !== targetMarginLeft) return false;
        if (targetMarginRight != null && (margin.getAttribute("right") ?? "0") !== targetMarginRight) return false;
        if (targetIndent != null && (margin.getAttribute("intent") ?? "0") !== targetIndent) return false;
      }
      return true;
    };

    const modifier = (element: Element): void => {
      if (targetAlignment != null) {
        let align = findChild(element, HH_NS, "align");
        if (!align) {
          align = subElement(element, HH_NS, "align", { horizontal: targetAlignment, vertical: "BASELINE" });
        } else {
          align.setAttribute("horizontal", targetAlignment);
        }
      }
      if (targetLineSpacingValue != null) {
        let ls = findChild(element, HH_NS, "lineSpacing");
        if (!ls) {
          ls = subElement(element, HH_NS, "lineSpacing", {
            type: "PERCENT", value: targetLineSpacingValue, unit: "HWPUNIT",
          });
        } else {
          ls.setAttribute("value", targetLineSpacingValue);
          if (!ls.getAttribute("type")) ls.setAttribute("type", "PERCENT");
        }
      }
      if (targetMarginLeft != null || targetMarginRight != null || targetIndent != null) {
        let margin = findChild(element, HH_NS, "margin");
        if (!margin) {
          margin = subElement(element, HH_NS, "margin", { intent: "0", left: "0", right: "0", prev: "0", next: "0" });
        }
        if (targetMarginLeft != null) margin.setAttribute("left", targetMarginLeft);
        if (targetMarginRight != null) margin.setAttribute("right", targetMarginRight);
        if (targetIndent != null) margin.setAttribute("intent", targetIndent);
      }
    };

    const element = header.ensureParaProperty({
      predicate,
      modifier,
      baseParaPrId: opts.baseParaPrId,
    });
    const paraId = element.getAttribute("id");
    if (!paraId) throw new Error("paraPr element is missing an id");
    return paraId;
  }

  ensureBasicBorderFill(): string {
    if (this._headers.length === 0) return "0";
    for (const header of this._headers) {
      const existing = header.findBasicBorderFillId();
      if (existing) return existing;
    }
    return this._headers[0]!.ensureBasicBorderFill();
  }

  // -- Paragraphs --

  get paragraphs(): HwpxOxmlParagraph[] {
    const result: HwpxOxmlParagraph[] = [];
    for (const section of this._sections) result.push(...section.paragraphs);
    return result;
  }

  addParagraph(text: string = "", opts?: {
    section?: HwpxOxmlSection;
    sectionIndex?: number;
    paraPrIdRef?: string | number;
    styleIdRef?: string | number;
    charPrIdRef?: string | number;
    runAttributes?: Record<string, string>;
    includeRun?: boolean;
  }): HwpxOxmlParagraph {
    let section: HwpxOxmlSection | null | undefined = opts?.section ?? null;
    if (!section && opts?.sectionIndex != null) section = this._sections[opts.sectionIndex];
    if (!section) {
      if (this._sections.length === 0) throw new Error("document does not contain any sections");
      section = this._sections[this._sections.length - 1]!;
    }
    return section!.addParagraph(text, {
      paraPrIdRef: opts?.paraPrIdRef,
      styleIdRef: opts?.styleIdRef,
      charPrIdRef: opts?.charPrIdRef,
      runAttributes: opts?.runAttributes,
      includeRun: opts?.includeRun,
    });
  }

  insertParagraphAt(sectionIndex: number, paragraphIndex: number, text: string = "", opts?: {
    paraPrIdRef?: string | number;
    styleIdRef?: string | number;
    charPrIdRef?: string | number;
    runAttributes?: Record<string, string>;
    includeRun?: boolean;
  }): HwpxOxmlParagraph {
    const section = this._sections[sectionIndex];
    if (!section) throw new Error(`section index ${sectionIndex} out of bounds`);
    return section.insertParagraphAt(paragraphIndex, text, opts);
  }

  removeParagraph(sectionIndex: number, paragraphIndex: number): void {
    const section = this._sections[sectionIndex];
    if (!section) throw new Error(`section index ${sectionIndex} out of bounds`);
    section.removeParagraph(paragraphIndex);
  }

  // -- Serialize --

  serialize(): Record<string, string> {
    const updates: Record<string, string> = {};
    for (const section of this._sections) {
      if (section.dirty) updates[section.partName] = section.toBytes();
    }
    let headersDirty = false;
    for (const header of this._headers) {
      if (header.dirty) { updates[header.partName] = header.toBytes(); headersDirty = true; }
    }
    if (headersDirty) this.invalidateCharPropertyCache();
    for (const mp of this._masterPages) {
      if (mp.dirty) updates[mp.partName] = mp.toBytes();
    }
    for (const h of this._histories) {
      if (h.dirty) updates[h.partName] = h.toBytes();
    }
    if (this._version?.dirty) updates[this._version.partName] = this._version.toBytes();
    return updates;
  }

  resetDirty(): void {
    for (const s of this._sections) s.resetDirty();
    for (const h of this._headers) h.resetDirty();
    for (const m of this._masterPages) m.resetDirty();
    for (const h of this._histories) h.resetDirty();
    if (this._version) this._version.resetDirty();
  }
}
