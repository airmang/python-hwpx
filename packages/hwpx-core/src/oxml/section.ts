/**
 * Section-related OXML classes: HwpxOxmlSectionHeaderFooter,
 * HwpxOxmlSectionProperties, HwpxOxmlSection.
 */

import type { PageSize, PageMargins, SectionStartNumbering, ColumnLayout } from "./types.js";
import type { HwpxOxmlDocument } from "./document.js";
import { HwpxOxmlParagraph } from "./paragraph.js";
import { HwpxOxmlMemo, HwpxOxmlMemoGroup } from "./memo.js";
import {
  HP_NS,
  DEFAULT_PARAGRAPH_ATTRS,
  paragraphId,
  objectId,
  serializeXmlBytes,
  getIntAttr,
  findChild,
  findAllChildren,
  findDescendant,
  findAllDescendants,
  createNsElement,
  subElement,
  defaultSublistAttributes,
} from "./xml-utils.js";

// -- HwpxOxmlSectionHeaderFooter --

export class HwpxOxmlSectionHeaderFooter {
  element: Element;
  private _properties: HwpxOxmlSectionProperties;
  private _applyElement: Element | null;

  constructor(element: Element, properties: HwpxOxmlSectionProperties, applyElement: Element | null = null) {
    this.element = element;
    this._properties = properties;
    this._applyElement = applyElement;
  }

  get applyElement(): Element | null {
    return this._applyElement;
  }

  get id(): string | null {
    return this.element.getAttribute("id");
  }

  set id(value: string | null) {
    if (value == null) {
      let changed = false;
      if (this.element.hasAttribute("id")) {
        this.element.removeAttribute("id");
        changed = true;
      }
      if (this._updateApplyReference(null)) changed = true;
      if (changed) this._properties.section.markDirty();
      return;
    }
    const newValue = String(value);
    let changed = false;
    if (this.element.getAttribute("id") !== newValue) {
      this.element.setAttribute("id", newValue);
      changed = true;
    }
    if (this._updateApplyReference(newValue)) changed = true;
    if (changed) this._properties.section.markDirty();
  }

  get applyPageType(): string {
    const value = this.element.getAttribute("applyPageType");
    if (value != null) return value;
    if (this._applyElement != null) return this._applyElement.getAttribute("applyPageType") ?? "BOTH";
    return "BOTH";
  }

  set applyPageType(value: string) {
    let changed = false;
    if (this.element.getAttribute("applyPageType") !== value) {
      this.element.setAttribute("applyPageType", value);
      changed = true;
    }
    if (this._applyElement != null && this._applyElement.getAttribute("applyPageType") !== value) {
      this._applyElement.setAttribute("applyPageType", value);
      changed = true;
    }
    if (changed) this._properties.section.markDirty();
  }

  private _applyIdAttributes(): string[] {
    const tag = this.element.tagName ?? this.element.localName ?? "";
    if (tag.endsWith("header")) return ["idRef", "headerIDRef", "headerIdRef", "headerRef"];
    return ["idRef", "footerIDRef", "footerIdRef", "footerRef"];
  }

  private _updateApplyReference(value: string | null): boolean {
    const apply = this._applyElement;
    if (!apply) return false;

    const candidateKeys = new Set(this._applyIdAttributes().map((n) => n.toLowerCase()));
    const attrCandidates: string[] = [];
    const namedMap = apply.attributes;
    for (let i = 0; i < namedMap.length; i++) {
      const attr = namedMap.item(i);
      if (attr && candidateKeys.has(attr.name.toLowerCase())) {
        attrCandidates.push(attr.name);
      }
    }

    let changed = false;
    if (value == null) {
      for (const attr of attrCandidates) {
        if (apply.hasAttribute(attr)) {
          apply.removeAttribute(attr);
          changed = true;
        }
      }
      return changed;
    }

    let targetAttr: string | null = null;
    const tag = this.element.tagName ?? this.element.localName ?? "";
    for (const attr of attrCandidates) {
      const lower = attr.toLowerCase();
      if (lower === "idref" || (tag.endsWith("header") && lower.includes("header")) || (tag.endsWith("footer") && lower.includes("footer"))) {
        targetAttr = attr;
        break;
      }
    }
    if (targetAttr == null) targetAttr = this._applyIdAttributes()[0]!;

    if (apply.getAttribute(targetAttr!) !== value) {
      apply.setAttribute(targetAttr!, value);
      changed = true;
    }

    const namedMap2 = apply.attributes;
    for (let i = namedMap2.length - 1; i >= 0; i--) {
      const attr = namedMap2.item(i);
      if (attr && attr.name !== targetAttr! && candidateKeys.has(attr.name.toLowerCase())) {
        apply.removeAttribute(attr.name);
        changed = true;
      }
    }

    return changed;
  }

  get text(): string {
    const parts: string[] = [];
    for (const node of findAllDescendants(this.element, "t")) {
      if (node.textContent) parts.push(node.textContent);
    }
    return parts.join("");
  }

  set text(value: string) {
    // Remove existing subList
    for (const child of findAllChildren(this.element, HP_NS, "subList")) {
      this.element.removeChild(child);
    }
    const textNode = this._ensureTextElement();
    textNode.textContent = value;
    this._properties.section.markDirty();
  }

  private _ensureTextElement(): Element {
    let sublist = findChild(this.element, HP_NS, "subList");
    if (!sublist) {
      const attrs = defaultSublistAttributes();
      attrs["vertAlign"] = (this.element.tagName ?? "").endsWith("header") ? "TOP" : "BOTTOM";
      sublist = subElement(this.element, HP_NS, "subList", attrs);
    }
    let paragraph = findChild(sublist, HP_NS, "p");
    if (!paragraph) {
      const pAttrs = { ...DEFAULT_PARAGRAPH_ATTRS, id: paragraphId() };
      paragraph = subElement(sublist, HP_NS, "p", pAttrs);
    }
    let run = findChild(paragraph, HP_NS, "run");
    if (!run) {
      run = subElement(paragraph, HP_NS, "run", { charPrIDRef: "0" });
    }
    let t = findChild(run, HP_NS, "t");
    if (!t) {
      t = subElement(run, HP_NS, "t");
    }
    return t;
  }
}

// -- HwpxOxmlSectionProperties --

export class HwpxOxmlSectionProperties {
  element: Element;
  section: HwpxOxmlSection;

  constructor(element: Element, section: HwpxOxmlSection) {
    this.element = element;
    this.section = section;
  }

  private _pagePrElement(create: boolean = false): Element | null {
    let pagePr = findChild(this.element, HP_NS, "pagePr");
    if (!pagePr && create) {
      pagePr = subElement(this.element, HP_NS, "pagePr", {
        landscape: "PORTRAIT", width: "0", height: "0", gutterType: "LEFT_ONLY",
      });
      this.section.markDirty();
    }
    return pagePr;
  }

  private _marginElement(create: boolean = false): Element | null {
    const pagePr = this._pagePrElement(create);
    if (!pagePr) return null;
    let margin = findChild(pagePr, HP_NS, "margin");
    if (!margin && create) {
      margin = subElement(pagePr, HP_NS, "margin", {
        left: "0", right: "0", top: "0", bottom: "0", header: "0", footer: "0", gutter: "0",
      });
      this.section.markDirty();
    }
    return margin;
  }

  get pageSize(): PageSize {
    const pagePr = this._pagePrElement();
    if (!pagePr) return { width: 0, height: 0, orientation: "PORTRAIT", gutterType: "LEFT_ONLY" };
    return {
      width: getIntAttr(pagePr, "width", 0),
      height: getIntAttr(pagePr, "height", 0),
      orientation: pagePr.getAttribute("landscape") ?? "PORTRAIT",
      gutterType: pagePr.getAttribute("gutterType") ?? "LEFT_ONLY",
    };
  }

  setPageSize(opts: { width?: number; height?: number; orientation?: string; gutterType?: string }): void {
    const pagePr = this._pagePrElement(true);
    if (!pagePr) return;
    let changed = false;
    if (opts.width != null) {
      const v = String(Math.max(opts.width, 0));
      if (pagePr.getAttribute("width") !== v) { pagePr.setAttribute("width", v); changed = true; }
    }
    if (opts.height != null) {
      const v = String(Math.max(opts.height, 0));
      if (pagePr.getAttribute("height") !== v) { pagePr.setAttribute("height", v); changed = true; }
    }
    if (opts.orientation != null && pagePr.getAttribute("landscape") !== opts.orientation) {
      pagePr.setAttribute("landscape", opts.orientation); changed = true;
    }
    if (opts.gutterType != null && pagePr.getAttribute("gutterType") !== opts.gutterType) {
      pagePr.setAttribute("gutterType", opts.gutterType); changed = true;
    }
    if (changed) this.section.markDirty();
  }

  get pageMargins(): PageMargins {
    const margin = this._marginElement();
    if (!margin) return { left: 0, right: 0, top: 0, bottom: 0, header: 0, footer: 0, gutter: 0 };
    return {
      left: getIntAttr(margin, "left", 0),
      right: getIntAttr(margin, "right", 0),
      top: getIntAttr(margin, "top", 0),
      bottom: getIntAttr(margin, "bottom", 0),
      header: getIntAttr(margin, "header", 0),
      footer: getIntAttr(margin, "footer", 0),
      gutter: getIntAttr(margin, "gutter", 0),
    };
  }

  setPageMargins(opts: { left?: number; right?: number; top?: number; bottom?: number; header?: number; footer?: number; gutter?: number }): void {
    const margin = this._marginElement(true);
    if (!margin) return;
    let changed = false;
    for (const [name, value] of Object.entries(opts) as [string, number | undefined][]) {
      if (value == null) continue;
      const safeValue = String(Math.max(value, 0));
      if (margin.getAttribute(name) !== safeValue) {
        margin.setAttribute(name, safeValue);
        changed = true;
      }
    }
    if (changed) this.section.markDirty();
  }

  get startNumbering(): SectionStartNumbering {
    const startNum = findChild(this.element, HP_NS, "startNum");
    if (!startNum) return { pageStartsOn: "BOTH", page: 0, picture: 0, table: 0, equation: 0 };
    return {
      pageStartsOn: startNum.getAttribute("pageStartsOn") ?? "BOTH",
      page: getIntAttr(startNum, "page", 0),
      picture: getIntAttr(startNum, "pic", 0),
      table: getIntAttr(startNum, "tbl", 0),
      equation: getIntAttr(startNum, "equation", 0),
    };
  }

  setStartNumbering(opts: { pageStartsOn?: string; page?: number; picture?: number; table?: number; equation?: number }): void {
    let startNum = findChild(this.element, HP_NS, "startNum");
    if (!startNum) {
      startNum = subElement(this.element, HP_NS, "startNum", {
        pageStartsOn: "BOTH", page: "0", pic: "0", tbl: "0", equation: "0",
      });
      this.section.markDirty();
    }
    let changed = false;
    if (opts.pageStartsOn != null && startNum.getAttribute("pageStartsOn") !== opts.pageStartsOn) {
      startNum.setAttribute("pageStartsOn", opts.pageStartsOn);
      changed = true;
    }
    const nameMap: [string, number | undefined][] = [
      ["page", opts.page], ["pic", opts.picture], ["tbl", opts.table], ["equation", opts.equation],
    ];
    for (const [name, value] of nameMap) {
      if (value == null) continue;
      const safeValue = String(Math.max(value, 0));
      if (startNum.getAttribute(name) !== safeValue) {
        startNum.setAttribute(name, safeValue);
        changed = true;
      }
    }
    if (changed) this.section.markDirty();
  }

  // -- Column layout helpers --

  /**
   * Find the colPr element which lives in a ctrl element that is a sibling
   * of secPr inside the same run element.
   */
  private _findColPrElement(): Element | null {
    const run = this.element.parentNode as Element | null;
    if (!run) return null;
    for (const ctrl of findAllChildren(run, HP_NS, "ctrl")) {
      const colPr = findChild(ctrl, HP_NS, "colPr");
      if (colPr) return colPr;
    }
    return null;
  }

  /**
   * Ensure the colPr element exists, creating the ctrl wrapper if needed.
   */
  private _ensureColPrElement(): Element {
    const existing = this._findColPrElement();
    if (existing) return existing;

    const run = this.element.parentNode as Element;
    const ctrl = subElement(run, HP_NS, "ctrl");
    const colPr = subElement(ctrl, HP_NS, "colPr", {
      id: "", type: "NEWSPAPER", layout: "LEFT", colCount: "1", sameSz: "1", sameGap: "0",
    });
    this.section.markDirty();
    return colPr;
  }

  get columnLayout(): ColumnLayout {
    const colPr = this._findColPrElement();
    if (!colPr) {
      return { type: "NEWSPAPER", layout: "LEFT", colCount: 1, sameSz: true, sameGap: 0 };
    }
    const sameSz = colPr.getAttribute("sameSz") !== "0";
    const result: ColumnLayout = {
      type: colPr.getAttribute("type") ?? "NEWSPAPER",
      layout: colPr.getAttribute("layout") ?? "LEFT",
      colCount: getIntAttr(colPr, "colCount", 1),
      sameSz,
      sameGap: getIntAttr(colPr, "sameGap", 0),
    };
    if (!sameSz) {
      const cols: { width: number; gap: number }[] = [];
      for (const colSz of findAllChildren(colPr, HP_NS, "colSz")) {
        cols.push({
          width: getIntAttr(colSz, "width", 0),
          gap: getIntAttr(colSz, "gap", 0),
        });
      }
      if (cols.length > 0) result.columns = cols;
    }
    return result;
  }

  setColumnLayout(opts: {
    type?: string;
    layout?: string;
    colCount?: number;
    sameGap?: number;
    columns?: { width: number; gap: number }[];
  }): void {
    const colPr = this._ensureColPrElement();
    let changed = false;

    if (opts.type != null && colPr.getAttribute("type") !== opts.type) {
      colPr.setAttribute("type", opts.type); changed = true;
    }
    if (opts.layout != null && colPr.getAttribute("layout") !== opts.layout) {
      colPr.setAttribute("layout", opts.layout); changed = true;
    }
    if (opts.colCount != null) {
      const v = String(Math.max(opts.colCount, 1));
      if (colPr.getAttribute("colCount") !== v) { colPr.setAttribute("colCount", v); changed = true; }
    }

    if (opts.columns && opts.columns.length > 0) {
      // Per-column sizes: sameSz = false
      colPr.setAttribute("sameSz", "0");
      colPr.setAttribute("sameGap", "0");
      // Remove existing colSz children
      for (const old of findAllChildren(colPr, HP_NS, "colSz")) colPr.removeChild(old);
      for (const col of opts.columns) {
        subElement(colPr, HP_NS, "colSz", {
          width: String(Math.max(col.width, 0)),
          gap: String(Math.max(col.gap, 0)),
        });
      }
      changed = true;
    } else if (opts.sameGap != null) {
      // Same-size columns with a uniform gap
      colPr.setAttribute("sameSz", "1");
      const v = String(Math.max(opts.sameGap, 0));
      if (colPr.getAttribute("sameGap") !== v) { colPr.setAttribute("sameGap", v); changed = true; }
    }

    if (changed) this.section.markDirty();
  }

  // -- Header/Footer helpers --

  get headers(): HwpxOxmlSectionHeaderFooter[] {
    const wrappers: HwpxOxmlSectionHeaderFooter[] = [];
    for (const el of findAllChildren(this.element, HP_NS, "header")) {
      const apply = this._matchApplyForElement("header", el);
      wrappers.push(new HwpxOxmlSectionHeaderFooter(el, this, apply));
    }
    return wrappers;
  }

  get footers(): HwpxOxmlSectionHeaderFooter[] {
    const wrappers: HwpxOxmlSectionHeaderFooter[] = [];
    for (const el of findAllChildren(this.element, HP_NS, "footer")) {
      const apply = this._matchApplyForElement("footer", el);
      wrappers.push(new HwpxOxmlSectionHeaderFooter(el, this, apply));
    }
    return wrappers;
  }

  getHeader(pageType: string = "BOTH"): HwpxOxmlSectionHeaderFooter | null {
    const el = this._findHeaderFooter("header", pageType);
    if (!el) return null;
    const apply = this._matchApplyForElement("header", el);
    return new HwpxOxmlSectionHeaderFooter(el, this, apply);
  }

  getFooter(pageType: string = "BOTH"): HwpxOxmlSectionHeaderFooter | null {
    const el = this._findHeaderFooter("footer", pageType);
    if (!el) return null;
    const apply = this._matchApplyForElement("footer", el);
    return new HwpxOxmlSectionHeaderFooter(el, this, apply);
  }

  setHeaderText(text: string, pageType: string = "BOTH"): HwpxOxmlSectionHeaderFooter {
    const el = this._ensureHeaderFooter("header", pageType);
    const apply = this._ensureHeaderFooterApply("header", pageType, el);
    const wrapper = new HwpxOxmlSectionHeaderFooter(el, this, apply);
    wrapper.text = text;
    return wrapper;
  }

  setFooterText(text: string, pageType: string = "BOTH"): HwpxOxmlSectionHeaderFooter {
    const el = this._ensureHeaderFooter("footer", pageType);
    const apply = this._ensureHeaderFooterApply("footer", pageType, el);
    const wrapper = new HwpxOxmlSectionHeaderFooter(el, this, apply);
    wrapper.text = text;
    return wrapper;
  }

  removeHeader(pageType: string = "BOTH"): void {
    const el = this._findHeaderFooter("header", pageType);
    let removed = false;
    if (el) { this.element.removeChild(el); removed = true; }
    if (this._removeHeaderFooterApply("header", pageType, el)) removed = true;
    if (removed) this.section.markDirty();
  }

  removeFooter(pageType: string = "BOTH"): void {
    const el = this._findHeaderFooter("footer", pageType);
    let removed = false;
    if (el) { this.element.removeChild(el); removed = true; }
    if (this._removeHeaderFooterApply("footer", pageType, el)) removed = true;
    if (removed) this.section.markDirty();
  }

  private _findHeaderFooter(tag: string, pageType: string): Element | null {
    for (const el of findAllChildren(this.element, HP_NS, tag)) {
      if ((el.getAttribute("applyPageType") ?? "BOTH") === pageType) return el;
    }
    return null;
  }

  private _ensureHeaderFooter(tag: string, pageType: string): Element {
    let el = this._findHeaderFooter(tag, pageType);
    let changed = false;
    if (!el) {
      el = subElement(this.element, HP_NS, tag, { id: objectId(), applyPageType: pageType });
      changed = true;
    } else {
      if (el.getAttribute("applyPageType") !== pageType) { el.setAttribute("applyPageType", pageType); changed = true; }
    }
    if (!el.getAttribute("id")) { el.setAttribute("id", objectId()); changed = true; }
    if (changed) this.section.markDirty();
    return el;
  }

  private _applyIdAttributes(tag: string): string[] {
    const base = tag === "header" ? "header" : "footer";
    return ["idRef", `${base}IDRef`, `${base}IdRef`, `${base}Ref`];
  }

  private _applyElements(tag: string): Element[] {
    return findAllChildren(this.element, HP_NS, `${tag}Apply`);
  }

  private _applyReference(apply: Element, tag: string): string | null {
    const candidateKeys = new Set(this._applyIdAttributes(tag).map((n) => n.toLowerCase()));
    const namedMap = apply.attributes;
    for (let i = 0; i < namedMap.length; i++) {
      const attr = namedMap.item(i);
      if (attr && candidateKeys.has(attr.name.toLowerCase()) && attr.value) return attr.value;
    }
    return null;
  }

  private _matchApplyForElement(tag: string, element: Element | null): Element | null {
    if (!element) return null;
    const targetId = element.getAttribute("id");
    if (targetId) {
      for (const apply of this._applyElements(tag)) {
        if (this._applyReference(apply, tag) === targetId) return apply;
      }
    }
    const pageType = element.getAttribute("applyPageType") ?? "BOTH";
    for (const apply of this._applyElements(tag)) {
      if ((apply.getAttribute("applyPageType") ?? "BOTH") === pageType) return apply;
    }
    return null;
  }

  private _ensureHeaderFooterApply(tag: string, pageType: string, element: Element): Element {
    let apply = this._matchApplyForElement(tag, element);
    const headerId = element.getAttribute("id");
    let changed = false;
    if (!apply) {
      const attrs: Record<string, string> = { applyPageType: pageType };
      if (headerId) attrs[this._applyIdAttributes(tag)[0]!] = headerId;
      apply = subElement(this.element, HP_NS, `${tag}Apply`, attrs);
      changed = true;
    } else {
      if (apply.getAttribute("applyPageType") !== pageType) { apply.setAttribute("applyPageType", pageType); changed = true; }
    }
    if (changed) this.section.markDirty();
    return apply;
  }

  private _removeHeaderFooterApply(tag: string, pageType: string, element: Element | null): boolean {
    let apply = this._matchApplyForElement(tag, element);
    if (!apply) {
      for (const candidate of this._applyElements(tag)) {
        if ((candidate.getAttribute("applyPageType") ?? "BOTH") === pageType) { apply = candidate; break; }
      }
    }
    if (!apply) return false;
    this.element.removeChild(apply);
    return true;
  }
}

// -- HwpxOxmlSection --

export class HwpxOxmlSection {
  partName: string;
  _element: Element;
  private _dirty: boolean = false;
  private _propertiesCache: HwpxOxmlSectionProperties | null = null;
  private _document: HwpxOxmlDocument | null;

  constructor(partName: string, element: Element, document: HwpxOxmlDocument | null = null) {
    this.partName = partName;
    this._element = element;
    this._document = document;
  }

  get element(): Element { return this._element; }
  get document(): HwpxOxmlDocument | null { return this._document; }
  attachDocument(document: HwpxOxmlDocument): void { this._document = document; }

  get properties(): HwpxOxmlSectionProperties {
    if (!this._propertiesCache) {
      let el = findDescendant(this._element, "secPr");
      if (!el) {
        // Create secPr in first paragraph's run
        let p = findChild(this._element, HP_NS, "p");
        if (!p) {
          p = subElement(this._element, HP_NS, "p", { ...DEFAULT_PARAGRAPH_ATTRS, id: paragraphId() });
        }
        let run = findChild(p, HP_NS, "run");
        if (!run) run = subElement(p, HP_NS, "run", { charPrIDRef: "0" });
        el = subElement(run, HP_NS, "secPr");
        this.markDirty();
      }
      this._propertiesCache = new HwpxOxmlSectionProperties(el, this);
    }
    return this._propertiesCache;
  }

  get paragraphs(): HwpxOxmlParagraph[] {
    return findAllChildren(this._element, HP_NS, "p").map((el) => new HwpxOxmlParagraph(el, this));
  }

  get memoGroup(): HwpxOxmlMemoGroup | null {
    const el = findChild(this._element, HP_NS, "memogroup");
    if (!el) return null;
    return new HwpxOxmlMemoGroup(el, this);
  }

  get memos(): HwpxOxmlMemo[] {
    const group = this.memoGroup;
    if (!group) return [];
    return group.memos;
  }

  addMemo(text: string = "", opts?: { memoShapeIdRef?: string | number; memoId?: string; charPrIdRef?: string | number; attributes?: Record<string, string> }): HwpxOxmlMemo {
    let el = findChild(this._element, HP_NS, "memogroup");
    if (!el) {
      el = subElement(this._element, HP_NS, "memogroup");
      this.markDirty();
    }
    const group = new HwpxOxmlMemoGroup(el, this);
    return group.addMemo(text, opts);
  }

  addParagraph(text: string = "", opts?: {
    paraPrIdRef?: string | number;
    styleIdRef?: string | number;
    charPrIdRef?: string | number;
    runAttributes?: Record<string, string>;
    includeRun?: boolean;
  }): HwpxOxmlParagraph {
    const includeRun = opts?.includeRun ?? true;
    const attrs: Record<string, string> = { id: paragraphId(), ...DEFAULT_PARAGRAPH_ATTRS };
    if (opts?.paraPrIdRef != null) attrs["paraPrIDRef"] = String(opts.paraPrIdRef);
    if (opts?.styleIdRef != null) attrs["styleIDRef"] = String(opts.styleIdRef);

    const doc = this._element.ownerDocument!;
    const paragraph = createNsElement(doc, HP_NS, "p", attrs);

    if (includeRun) {
      const runAttrs: Record<string, string> = { ...(opts?.runAttributes ?? {}) };
      if (opts?.charPrIdRef != null) runAttrs["charPrIDRef"] = String(opts.charPrIdRef);
      else if (!("charPrIDRef" in runAttrs)) runAttrs["charPrIDRef"] = "0";
      const run = subElement(paragraph, HP_NS, "run", runAttrs);
      const t = subElement(run, HP_NS, "t");
      t.textContent = text;
    }

    this._element.appendChild(paragraph);
    this._dirty = true;
    return new HwpxOxmlParagraph(paragraph, this);
  }

  insertParagraphAt(index: number, text: string = "", opts?: {
    paraPrIdRef?: string | number;
    styleIdRef?: string | number;
    charPrIdRef?: string | number;
    runAttributes?: Record<string, string>;
    includeRun?: boolean;
  }): HwpxOxmlParagraph {
    const includeRun = opts?.includeRun ?? true;
    const attrs: Record<string, string> = { id: paragraphId(), ...DEFAULT_PARAGRAPH_ATTRS };
    if (opts?.paraPrIdRef != null) attrs["paraPrIDRef"] = String(opts.paraPrIdRef);
    if (opts?.styleIdRef != null) attrs["styleIDRef"] = String(opts.styleIdRef);

    const doc = this._element.ownerDocument!;
    const paragraph = createNsElement(doc, HP_NS, "p", attrs);

    if (includeRun) {
      const runAttrs: Record<string, string> = { ...(opts?.runAttributes ?? {}) };
      if (opts?.charPrIdRef != null) runAttrs["charPrIDRef"] = String(opts.charPrIdRef);
      else if (!("charPrIDRef" in runAttrs)) runAttrs["charPrIDRef"] = "0";
      const run = subElement(paragraph, HP_NS, "run", runAttrs);
      const t = subElement(run, HP_NS, "t");
      t.textContent = text;
    }

    const existing = findAllChildren(this._element, HP_NS, "p");
    if (index >= existing.length) {
      this._element.appendChild(paragraph);
    } else {
      this._element.insertBefore(paragraph, existing[index]!);
    }
    this._dirty = true;
    return new HwpxOxmlParagraph(paragraph, this);
  }

  /**
   * Insert a pre-created paragraph element at the specified index.
   * Used internally by TOC generation and other features.
   */
  insertParagraph(paragraphElement: Element, index: number): HwpxOxmlParagraph {
    const existing = findAllChildren(this._element, HP_NS, "p");
    if (index >= existing.length) {
      this._element.appendChild(paragraphElement);
    } else {
      this._element.insertBefore(paragraphElement, existing[index]!);
    }
    this._dirty = true;
    return new HwpxOxmlParagraph(paragraphElement, this);
  }

  removeParagraph(index: number): void {
    const existing = findAllChildren(this._element, HP_NS, "p");
    if (index < 0 || index >= existing.length) {
      throw new Error(`paragraph index ${index} out of bounds (${existing.length} paragraphs)`);
    }
    this._element.removeChild(existing[index]!);
    this._propertiesCache = null;
    this._dirty = true;
  }

  replaceElement(newElement: Element): void {
    this._element = newElement;
    this._propertiesCache = null;
    this._dirty = true;
  }

  markDirty(): void { this._dirty = true; }
  get dirty(): boolean { return this._dirty; }
  resetDirty(): void { this._dirty = false; }
  toBytes(): string { return serializeXmlBytes(this._element); }
}
