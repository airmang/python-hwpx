/**
 * Header part OXML class: HwpxOxmlHeader.
 */

import type { DocumentNumbering } from "./types.js";
import type { HwpxOxmlDocument } from "./document.js";
import {
  HH_NS,
  serializeXmlBytes,
  getIntAttr,
  findChild,
  findAllChildren,
  createNsElement,
  subElement,
  borderFillIsBasicSolidLine,
  createBasicBorderFillElement,
} from "./xml-utils.js";

export class HwpxOxmlHeader {
  partName: string;
  private _element: Element;
  private _dirty: boolean = false;
  private _document: HwpxOxmlDocument | null;

  constructor(partName: string, element: Element, document: HwpxOxmlDocument | null = null) {
    this.partName = partName;
    this._element = element;
    this._document = document;
  }

  get element(): Element { return this._element; }
  get document(): HwpxOxmlDocument | null { return this._document; }
  attachDocument(document: HwpxOxmlDocument): void { this._document = document; }

  private _refListElement(create: boolean = false): Element | null {
    let el = findChild(this._element, HH_NS, "refList");
    if (!el && create) {
      el = subElement(this._element, HH_NS, "refList");
      this.markDirty();
    }
    return el;
  }

  private _borderFillsElement(create: boolean = false): Element | null {
    const refList = this._refListElement(create);
    if (!refList) return null;
    let el = findChild(refList, HH_NS, "borderFills");
    if (!el && create) {
      el = subElement(refList, HH_NS, "borderFills", { itemCnt: "0" });
      this.markDirty();
    }
    return el;
  }

  private _charPropertiesElement(create: boolean = false): Element | null {
    const refList = this._refListElement(create);
    if (!refList) return null;
    let el = findChild(refList, HH_NS, "charProperties");
    if (!el && create) {
      el = subElement(refList, HH_NS, "charProperties", { itemCnt: "0" });
      this.markDirty();
    }
    return el;
  }

  findBasicBorderFillId(): string | null {
    const el = this._borderFillsElement();
    if (!el) return null;
    for (const child of findAllChildren(el, HH_NS, "borderFill")) {
      if (borderFillIsBasicSolidLine(child)) {
        const id = child.getAttribute("id");
        if (id) return id;
      }
    }
    return null;
  }

  ensureBasicBorderFill(): string {
    const el = this._borderFillsElement(true)!;
    const existing = this.findBasicBorderFillId();
    if (existing) return existing;

    const newId = this._allocateBorderFillId(el);
    const doc = el.ownerDocument!;
    el.appendChild(createBasicBorderFillElement(doc, newId));
    this._updateBorderFillsItemCount(el);
    this.markDirty();
    return newId;
  }

  ensureCharProperty(opts: {
    predicate?: (el: Element) => boolean;
    modifier?: (el: Element) => void;
    baseCharPrId?: string | number;
    preferredId?: string | number;
  }): Element {
    const charProps = this._charPropertiesElement(true)!;

    if (opts.predicate) {
      for (const child of findAllChildren(charProps, HH_NS, "charPr")) {
        if (opts.predicate(child)) return child;
      }
    }

    let baseElement: Element | null = null;
    if (opts.baseCharPrId != null) {
      for (const child of findAllChildren(charProps, HH_NS, "charPr")) {
        if (child.getAttribute("id") === String(opts.baseCharPrId)) { baseElement = child; break; }
      }
    }
    if (!baseElement) {
      const first = findChild(charProps, HH_NS, "charPr");
      if (first) baseElement = first;
    }

    const doc = charProps.ownerDocument!;
    let newCharPr: Element;
    if (!baseElement) {
      newCharPr = createNsElement(doc, HH_NS, "charPr");
    } else {
      newCharPr = baseElement.cloneNode(true) as Element;
      if (newCharPr.hasAttribute("id")) newCharPr.removeAttribute("id");
    }

    if (opts.modifier) opts.modifier(newCharPr);

    const charId = this._allocateCharPropertyId(charProps, opts.preferredId);
    newCharPr.setAttribute("id", charId);
    charProps.appendChild(newCharPr);
    this._updateCharPropertiesItemCount(charProps);
    this.markDirty();
    if (this._document) this._document.invalidateCharPropertyCache();
    return newCharPr;
  }

  // ── Font face management ────────────────────────────────────────────────

  private _fontFacesElement(): Element | null {
    const refList = this._refListElement();
    if (!refList) return null;
    return findChild(refList, HH_NS, "fontfaces");
  }

  /**
   * Ensure a font exists in all fontface lang groups (HANGUL, LATIN, etc.)
   * and return the numeric font ID for the HANGUL group.
   * If the font already exists, returns its existing ID.
   */
  ensureFontFace(fontName: string): string {
    const fontfaces = this._fontFacesElement();
    if (!fontfaces) throw new Error("header does not contain fontfaces element");

    const LANGS = ["HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"];
    let hangulId: string | null = null;

    for (const lang of LANGS) {
      let langGroup: Element | null = null;
      for (const child of findAllChildren(fontfaces, HH_NS, "fontface")) {
        if (child.getAttribute("lang") === lang) { langGroup = child; break; }
      }
      if (!langGroup) {
        langGroup = subElement(fontfaces, HH_NS, "fontface", { lang, fontCnt: "0" });
      }

      // Check if font already exists
      let existingId: string | null = null;
      const fonts = findAllChildren(langGroup, HH_NS, "font");
      for (const font of fonts) {
        if (font.getAttribute("face") === fontName) {
          existingId = font.getAttribute("id");
          break;
        }
      }

      if (existingId != null) {
        if (lang === "HANGUL") hangulId = existingId;
        continue;
      }

      // Allocate new ID = max existing ID + 1
      let maxId = -1;
      for (const font of fonts) {
        const idVal = parseInt(font.getAttribute("id") ?? "-1", 10);
        if (idVal > maxId) maxId = idVal;
      }
      const newId = String(maxId + 1);

      subElement(langGroup, HH_NS, "font", {
        id: newId,
        face: fontName,
        type: "TTF",
        isEmbedded: "0",
      });

      // Update fontCnt
      langGroup.setAttribute("fontCnt", String(fonts.length + 1));

      if (lang === "HANGUL") hangulId = newId;
    }

    this.markDirty();
    return hangulId ?? "0";
  }

  get beginNumbering(): DocumentNumbering {
    const el = findChild(this._element, HH_NS, "beginNum");
    if (!el) return { page: 1, footnote: 1, endnote: 1, picture: 1, table: 1, equation: 1 };
    return {
      page: getIntAttr(el, "page", 1),
      footnote: getIntAttr(el, "footnote", 1),
      endnote: getIntAttr(el, "endnote", 1),
      picture: getIntAttr(el, "pic", 1),
      table: getIntAttr(el, "tbl", 1),
      equation: getIntAttr(el, "equation", 1),
    };
  }

  // ── Paragraph property management ──────────────────────────────────────

  private _paraPropertiesElement(create: boolean = false): Element | null {
    const refList = this._refListElement(create);
    if (!refList) return null;
    let el = findChild(refList, HH_NS, "paraProperties");
    if (!el && create) {
      el = subElement(refList, HH_NS, "paraProperties", { itemCnt: "0" });
      this.markDirty();
    }
    return el;
  }

  ensureParaProperty(opts: {
    predicate?: (el: Element) => boolean;
    modifier?: (el: Element) => void;
    baseParaPrId?: string | number;
  }): Element {
    const paraProps = this._paraPropertiesElement(true)!;

    if (opts.predicate) {
      for (const child of findAllChildren(paraProps, HH_NS, "paraPr")) {
        if (opts.predicate(child)) return child;
      }
    }

    let baseElement: Element | null = null;
    if (opts.baseParaPrId != null) {
      for (const child of findAllChildren(paraProps, HH_NS, "paraPr")) {
        if (child.getAttribute("id") === String(opts.baseParaPrId)) { baseElement = child; break; }
      }
    }
    if (!baseElement) {
      const first = findChild(paraProps, HH_NS, "paraPr");
      if (first) baseElement = first;
    }

    const doc = paraProps.ownerDocument!;
    let newParaPr: Element;
    if (!baseElement) {
      newParaPr = createNsElement(doc, HH_NS, "paraPr");
    } else {
      newParaPr = baseElement.cloneNode(true) as Element;
      if (newParaPr.hasAttribute("id")) newParaPr.removeAttribute("id");
    }

    if (opts.modifier) opts.modifier(newParaPr);

    const paraId = this._allocateParaPropertyId(paraProps);
    newParaPr.setAttribute("id", paraId);
    paraProps.appendChild(newParaPr);
    this._updateParaPropertiesItemCount(paraProps);
    this.markDirty();
    return newParaPr;
  }

  private _allocateParaPropertyId(element: Element): string {
    const existing = new Set<string>();
    for (const child of findAllChildren(element, HH_NS, "paraPr")) {
      const id = child.getAttribute("id");
      if (id) existing.add(id);
    }
    const numericIds: number[] = [];
    for (const id of existing) {
      const n = parseInt(id, 10);
      if (!isNaN(n)) numericIds.push(n);
    }
    let nextId = numericIds.length === 0 ? 0 : Math.max(...numericIds) + 1;
    let candidate = String(nextId);
    while (existing.has(candidate)) { nextId++; candidate = String(nextId); }
    return candidate;
  }

  private _updateParaPropertiesItemCount(element: Element): void {
    const count = findAllChildren(element, HH_NS, "paraPr").length;
    element.setAttribute("itemCnt", String(count));
  }

  // ── Element replacement (for undo/redo) ───────────────────────────────

  replaceElement(newElement: Element): void {
    this._element = newElement;
    this._dirty = true;
  }

  get dirty(): boolean { return this._dirty; }
  markDirty(): void { this._dirty = true; }
  resetDirty(): void { this._dirty = false; }
  toBytes(): string { return serializeXmlBytes(this._element); }

  private _allocateCharPropertyId(element: Element, preferredId?: string | number | null): string {
    const existing = new Set<string>();
    for (const child of findAllChildren(element, HH_NS, "charPr")) {
      const id = child.getAttribute("id");
      if (id) existing.add(id);
    }
    if (preferredId != null) {
      const candidate = String(preferredId);
      if (!existing.has(candidate)) return candidate;
    }
    const numericIds: number[] = [];
    for (const id of existing) {
      const n = parseInt(id, 10);
      if (!isNaN(n)) numericIds.push(n);
    }
    let nextId = numericIds.length === 0 ? 0 : Math.max(...numericIds) + 1;
    let candidate = String(nextId);
    while (existing.has(candidate)) { nextId++; candidate = String(nextId); }
    return candidate;
  }

  private _allocateBorderFillId(element: Element): string {
    const existing = new Set<string>();
    for (const child of findAllChildren(element, HH_NS, "borderFill")) {
      const id = child.getAttribute("id");
      if (id) existing.add(id);
    }
    const numericIds: number[] = [];
    for (const id of existing) {
      const n = parseInt(id, 10);
      if (!isNaN(n)) numericIds.push(n);
    }
    let nextId = numericIds.length === 0 ? 0 : Math.max(...numericIds) + 1;
    let candidate = String(nextId);
    while (existing.has(candidate)) { nextId++; candidate = String(nextId); }
    return candidate;
  }

  private _updateCharPropertiesItemCount(element: Element): void {
    const count = findAllChildren(element, HH_NS, "charPr").length;
    element.setAttribute("itemCnt", String(count));
  }

  private _updateBorderFillsItemCount(element: Element): void {
    const count = findAllChildren(element, HH_NS, "borderFill").length;
    element.setAttribute("itemCnt", String(count));
  }
}
