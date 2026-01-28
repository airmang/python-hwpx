/**
 * Object model mapping for XML parts of an HWPX document.
 * Ported from Python hwpx/oxml/document.py (3,406 LOC)
 */

import {
  parseXml,
  serializeXml,
  localName as domLocalName,
  childElements,
  getAttributes,
  createElement,
} from "../xml/dom.js";
import { HC_NS } from "./schema.js";
import * as body from "./body.js";
import { GenericElement, parseGenericElement } from "./common.js";
import {
  Bullet,
  MemoProperties,
  MemoShape,
  ParagraphProperty,
  Style,
  TrackChange,
  TrackChangeAuthor,
  memoShapeFromAttributes,
  parseBullets,
  parseBorderFills,
  parseParagraphProperties,
  parseStyles,
  parseTrackChanges,
  parseTrackChangeAuthors,
  memoPropertiesAsDict,
  bulletListAsDict,
  paragraphPropertyListAsDict,
  styleListAsDict,
  trackChangeListAsDict,
  trackChangeAuthorListAsDict,
} from "./header.js";
import { parseInt_ as parseIntUtil } from "./utils.js";
import { HwpxPackage } from "../package.js";

const HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph";
const HH_NS = "http://www.hancom.co.kr/hwpml/2011/head";

const DEFAULT_PARAGRAPH_ATTRS: Record<string, string> = {
  paraPrIDRef: "0",
  styleIDRef: "0",
  pageBreak: "0",
  columnBreak: "0",
  merged: "0",
};

const DEFAULT_CELL_WIDTH = 7200;
const DEFAULT_CELL_HEIGHT = 3600;

const BASIC_BORDER_FILL_ATTRIBUTES: Record<string, string> = {
  threeD: "0",
  shadow: "0",
  centerLine: "NONE",
  breakCellSeparateLine: "0",
};

const BASIC_BORDER_CHILDREN: [string, Record<string, string>][] = [
  ["slash", { type: "NONE", Crooked: "0", isCounter: "0" }],
  ["backSlash", { type: "NONE", Crooked: "0", isCounter: "0" }],
  ["leftBorder", { type: "SOLID", width: "0.12 mm", color: "#000000" }],
  ["rightBorder", { type: "SOLID", width: "0.12 mm", color: "#000000" }],
  ["topBorder", { type: "SOLID", width: "0.12 mm", color: "#000000" }],
  ["bottomBorder", { type: "SOLID", width: "0.12 mm", color: "#000000" }],
  ["diagonal", { type: "SOLID", width: "0.1 mm", color: "#000000" }],
];

const LAYOUT_CACHE_ELEMENT_NAMES = new Set(["linesegarray"]);

// -- ID generators --

function generateId(): string {
  // Use crypto if available, otherwise fall back to uuid
  const bytes = new Uint8Array(16);
  if (typeof globalThis.crypto !== "undefined" && globalThis.crypto.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  // Convert to 32-bit unsigned integer
  const view = new DataView(bytes.buffer);
  return String(view.getUint32(0) >>> 0);
}

function paragraphId(): string {
  return generateId();
}

function objectId(): string {
  return generateId();
}

function memoId(): string {
  return generateId();
}

// -- XML helpers --

function serializeXmlBytes(element: Element): string {
  return '<?xml version="1.0" encoding="UTF-8"?>' + serializeXml(element);
}

function elementLocalName(node: Element): string {
  return domLocalName(node);
}

function normalizeLength(value: string | null): string {
  if (value == null) return "";
  return value.replace(/ /g, "").toLowerCase();
}

function getIntAttr(element: Element, name: string, defaultValue: number = 0): number {
  const value = element.getAttribute(name);
  if (value == null) return defaultValue;
  const n = parseInt(value, 10);
  return isNaN(n) ? defaultValue : n;
}

function clearParagraphLayoutCache(paragraph: Element): void {
  const children = paragraph.childNodes;
  for (let i = children.length - 1; i >= 0; i--) {
    const child = children.item(i);
    if (child && child.nodeType === 1) {
      const el = child as Element;
      if (LAYOUT_CACHE_ELEMENT_NAMES.has(elementLocalName(el).toLowerCase())) {
        paragraph.removeChild(el);
      }
    }
  }
}

function distributeSize(total: number, parts: number): number[] {
  if (parts <= 0) return [];
  const base = Math.floor(total / parts);
  let remainder = total - base * parts;
  const sizes: number[] = [];
  for (let i = 0; i < parts; i++) {
    let value = base;
    if (remainder > 0) {
      value += 1;
      remainder -= 1;
    }
    sizes.push(Math.max(value, 0));
  }
  return sizes;
}

function defaultCellAttributes(borderFillIdRef: string): Record<string, string> {
  return {
    name: "",
    header: "0",
    hasMargin: "0",
    protect: "0",
    editable: "0",
    dirty: "0",
    borderFillIDRef: borderFillIdRef,
  };
}

function defaultSublistAttributes(): Record<string, string> {
  return {
    id: "",
    textDirection: "HORIZONTAL",
    lineWrap: "BREAK",
    vertAlign: "CENTER",
    linkListIDRef: "0",
    linkListNextIDRef: "0",
    textWidth: "0",
    textHeight: "0",
    hasTextRef: "0",
    hasNumRef: "0",
  };
}

function defaultCellParagraphAttributes(): Record<string, string> {
  return { ...DEFAULT_PARAGRAPH_ATTRS, id: paragraphId() };
}

function defaultCellMarginAttributes(): Record<string, string> {
  return { left: "0", right: "0", top: "0", bottom: "0" };
}

function findChild(parent: Element, ns: string, localNameStr: string): Element | null {
  const children = parent.childNodes;
  for (let i = 0; i < children.length; i++) {
    const child = children.item(i);
    if (child && child.nodeType === 1) {
      const el = child as Element;
      if (elementLocalName(el) === localNameStr) return el;
    }
  }
  return null;
}

function findAllChildren(parent: Element, ns: string, localNameStr: string): Element[] {
  const result: Element[] = [];
  const children = parent.childNodes;
  for (let i = 0; i < children.length; i++) {
    const child = children.item(i);
    if (child && child.nodeType === 1) {
      const el = child as Element;
      if (elementLocalName(el) === localNameStr) result.push(el);
    }
  }
  return result;
}

function findDescendant(parent: Element, localNameStr: string): Element | null {
  const children = parent.childNodes;
  for (let i = 0; i < children.length; i++) {
    const child = children.item(i);
    if (child && child.nodeType === 1) {
      const el = child as Element;
      if (elementLocalName(el) === localNameStr) return el;
      const result = findDescendant(el, localNameStr);
      if (result) return result;
    }
  }
  return null;
}

function findAllDescendants(parent: Element, localNameStr: string): Element[] {
  const result: Element[] = [];
  const walk = (node: Element): void => {
    const children = node.childNodes;
    for (let i = 0; i < children.length; i++) {
      const child = children.item(i);
      if (child && child.nodeType === 1) {
        const el = child as Element;
        if (elementLocalName(el) === localNameStr) result.push(el);
        walk(el);
      }
    }
  };
  walk(parent);
  return result;
}

function createNsElement(
  doc: Document,
  ns: string,
  localNameStr: string,
  attributes?: Record<string, string>,
): Element {
  const el = doc.createElementNS(ns, localNameStr);
  if (attributes) {
    for (const [key, value] of Object.entries(attributes)) {
      el.setAttribute(key, value);
    }
  }
  return el;
}

function subElement(
  parent: Element,
  ns: string,
  localNameStr: string,
  attributes?: Record<string, string>,
): Element {
  const doc = parent.ownerDocument!;
  const el = createNsElement(doc, ns, localNameStr, attributes);
  parent.appendChild(el);
  return el;
}

function createParagraphElement(
  doc: Document,
  text: string,
  options?: {
    charPrIdRef?: string | number | null;
    paraPrIdRef?: string | number | null;
    styleIdRef?: string | number | null;
    paragraphAttributes?: Record<string, string>;
    runAttributes?: Record<string, string>;
  },
): Element {
  const opts = options ?? {};
  const attrs: Record<string, string> = { id: paragraphId(), ...DEFAULT_PARAGRAPH_ATTRS };
  if (opts.paragraphAttributes) Object.assign(attrs, opts.paragraphAttributes);
  if (opts.paraPrIdRef != null) attrs["paraPrIDRef"] = String(opts.paraPrIdRef);
  if (opts.styleIdRef != null) attrs["styleIDRef"] = String(opts.styleIdRef);

  const paragraph = createNsElement(doc, HP_NS, "p", attrs);

  const runAttrs: Record<string, string> = { ...(opts.runAttributes ?? {}) };
  if (opts.charPrIdRef != null) {
    if (!("charPrIDRef" in runAttrs)) runAttrs["charPrIDRef"] = String(opts.charPrIdRef);
  } else {
    if (!("charPrIDRef" in runAttrs)) runAttrs["charPrIDRef"] = "0";
  }

  const run = subElement(paragraph, HP_NS, "run", runAttrs);
  const t = subElement(run, HP_NS, "t");
  t.textContent = text;
  return paragraph;
}

// -- Border fill helpers --

function borderFillIsBasicSolidLine(element: Element): boolean {
  if (elementLocalName(element) !== "borderFill") return false;

  for (const [attr, expected] of Object.entries(BASIC_BORDER_FILL_ATTRIBUTES)) {
    const actual = element.getAttribute(attr);
    if (attr === "centerLine") {
      if ((actual ?? "").toUpperCase() !== expected) return false;
    } else {
      if (actual !== expected) return false;
    }
  }

  for (const [childName, childAttrs] of BASIC_BORDER_CHILDREN) {
    const child = findChild(element, HH_NS, childName);
    if (child == null) return false;
    for (const [attr, expected] of Object.entries(childAttrs)) {
      const actual = child.getAttribute(attr);
      if (attr === "type") {
        if ((actual ?? "").toUpperCase() !== expected) return false;
      } else if (attr === "width") {
        if (normalizeLength(actual) !== normalizeLength(expected)) return false;
      } else if (attr === "color") {
        if ((actual ?? "").toUpperCase() !== expected.toUpperCase()) return false;
      } else {
        if (actual !== expected) return false;
      }
    }
  }

  // Check no fillBrush child
  for (const child of childElements(element)) {
    if (elementLocalName(child) === "fillBrush") return false;
  }

  return true;
}

function createBasicBorderFillElement(doc: Document, borderId: string): Element {
  const attrs = { id: borderId, ...BASIC_BORDER_FILL_ATTRIBUTES };
  const element = createNsElement(doc, HH_NS, "borderFill", attrs);
  for (const [childName, childAttrs] of BASIC_BORDER_CHILDREN) {
    subElement(element, HH_NS, childName, { ...childAttrs });
  }
  return element;
}

// -- Dataclass equivalents --

export interface PageSize {
  width: number;
  height: number;
  orientation: string;
  gutterType: string;
}

export interface PageMargins {
  left: number;
  right: number;
  top: number;
  bottom: number;
  header: number;
  footer: number;
  gutter: number;
}

export interface SectionStartNumbering {
  pageStartsOn: string;
  page: number;
  picture: number;
  table: number;
  equation: number;
}

export interface DocumentNumbering {
  page: number;
  footnote: number;
  endnote: number;
  picture: number;
  table: number;
  equation: number;
}

export interface RunStyle {
  id: string;
  attributes: Record<string, string>;
  childAttributes: Record<string, Record<string, string>>;
}

export function runStyleTextColor(style: RunStyle): string | null {
  return style.attributes["textColor"] ?? null;
}

export function runStyleUnderlineType(style: RunStyle): string | null {
  const underline = style.childAttributes["underline"];
  if (!underline) return null;
  return underline["type"] ?? null;
}

export function runStyleUnderlineColor(style: RunStyle): string | null {
  const underline = style.childAttributes["underline"];
  if (!underline) return null;
  return underline["color"] ?? null;
}

export function runStyleMatches(
  style: RunStyle,
  opts: { textColor?: string | null; underlineType?: string | null; underlineColor?: string | null },
): boolean {
  if (opts.textColor != null && runStyleTextColor(style) !== opts.textColor) return false;
  if (opts.underlineType != null && runStyleUnderlineType(style) !== opts.underlineType) return false;
  if (opts.underlineColor != null && runStyleUnderlineColor(style) !== opts.underlineColor) return false;
  return true;
}

function charPropertiesFromHeader(element: Element): Record<string, RunStyle> {
  const mapping: Record<string, RunStyle> = {};
  const refList = findChild(element, HH_NS, "refList");
  if (!refList) return mapping;
  const charPropsElement = findChild(refList, HH_NS, "charProperties");
  if (!charPropsElement) return mapping;

  for (const child of findAllChildren(charPropsElement, HH_NS, "charPr")) {
    const charId = child.getAttribute("id");
    if (!charId) continue;
    const attributes: Record<string, string> = {};
    const namedMap = child.attributes;
    for (let i = 0; i < namedMap.length; i++) {
      const attr = namedMap.item(i);
      if (attr && attr.name !== "id") {
        attributes[attr.name] = attr.value;
      }
    }
    const childAttributes: Record<string, Record<string, string>> = {};
    for (const grandchild of childElements(child)) {
      if (childElements(grandchild).length === 0 && !(grandchild.textContent?.trim())) {
        const gcAttrs: Record<string, string> = {};
        const gcNamedMap = grandchild.attributes;
        for (let i = 0; i < gcNamedMap.length; i++) {
          const attr = gcNamedMap.item(i);
          if (attr) gcAttrs[attr.name] = attr.value;
        }
        childAttributes[elementLocalName(grandchild)] = gcAttrs;
      }
    }
    const style: RunStyle = { id: charId, attributes, childAttributes };
    if (!(charId in mapping)) mapping[charId] = style;
    try {
      const normalized = String(parseInt(charId, 10));
      if (normalized && !(normalized in mapping)) mapping[normalized] = style;
    } catch { /* ignore */ }
  }
  return mapping;
}

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

// -- HwpxOxmlRun --

export class HwpxOxmlRun {
  element: Element;
  paragraph: HwpxOxmlParagraph;

  constructor(element: Element, paragraph: HwpxOxmlParagraph) {
    this.element = element;
    this.paragraph = paragraph;
  }

  get charPrIdRef(): string | null {
    return this.element.getAttribute("charPrIDRef");
  }

  set charPrIdRef(value: string | number | null) {
    if (value == null) {
      if (this.element.hasAttribute("charPrIDRef")) {
        this.element.removeAttribute("charPrIDRef");
        this.paragraph.section.markDirty();
      }
      return;
    }
    const newValue = String(value);
    if (this.element.getAttribute("charPrIDRef") !== newValue) {
      this.element.setAttribute("charPrIDRef", newValue);
      this.paragraph.section.markDirty();
    }
  }

  get text(): string {
    const parts: string[] = [];
    for (const node of findAllChildren(this.element, HP_NS, "t")) {
      if (node.textContent) parts.push(node.textContent);
    }
    return parts.join("");
  }

  set text(value: string) {
    const primary = this._ensurePlainTextNode();
    const changed = (primary.textContent ?? "") !== value;
    primary.textContent = value;
    const plainNodes = this._plainTextNodes();
    for (let i = 1; i < plainNodes.length; i++) {
      if (plainNodes[i]!.textContent) {
        plainNodes[i]!.textContent = "";
      }
    }
    if (changed) this.paragraph.section.markDirty();
  }

  get style(): RunStyle | null {
    const document = this.paragraph.section.document;
    if (!document) return null;
    const charPrId = this.charPrIdRef;
    if (!charPrId) return null;
    return document.charProperty(charPrId);
  }

  replaceText(search: string, replacement: string, count?: number): number {
    if (!search) throw new Error("search text must be a non-empty string");
    if (count != null && count <= 0) return 0;

    // Simplified: replace in each <t> element text content
    let totalReplacements = 0;
    let remaining = count ?? Infinity;

    for (const textNode of findAllChildren(this.element, HP_NS, "t")) {
      if (remaining <= 0) break;
      let content = textNode.textContent ?? "";
      let replacedCount = 0;
      let result = "";
      let searchStart = 0;

      while (remaining > 0) {
        const pos = content.indexOf(search, searchStart);
        if (pos === -1) {
          result += content.substring(searchStart);
          break;
        }
        result += content.substring(searchStart, pos) + replacement;
        searchStart = pos + search.length;
        replacedCount++;
        remaining--;
      }
      if (searchStart < content.length && remaining <= 0) {
        result += content.substring(searchStart);
      }

      if (replacedCount > 0) {
        textNode.textContent = result;
        totalReplacements += replacedCount;
      }
    }

    if (totalReplacements > 0) this.paragraph.section.markDirty();
    return totalReplacements;
  }

  remove(): void {
    try {
      this.paragraph.element.removeChild(this.element);
    } catch { return; }
    this.paragraph.section.markDirty();
  }

  private _plainTextNodes(): Element[] {
    return findAllChildren(this.element, HP_NS, "t").filter(
      (n) => childElements(n).length === 0,
    );
  }

  private _ensurePlainTextNode(): Element {
    const nodes = this._plainTextNodes();
    if (nodes.length > 0) return nodes[0]!;
    return subElement(this.element, HP_NS, "t");
  }
}

// -- HwpxOxmlTableCell --

export class HwpxOxmlTableCell {
  element: Element;
  table: HwpxOxmlTable;
  private _rowElement: Element;

  constructor(element: Element, table: HwpxOxmlTable, rowElement: Element) {
    this.element = element;
    this.table = table;
    this._rowElement = rowElement;
  }

  private _addrElement(): Element | null {
    return findChild(this.element, HP_NS, "cellAddr");
  }

  private _spanElement(): Element {
    let span = findChild(this.element, HP_NS, "cellSpan");
    if (!span) span = subElement(this.element, HP_NS, "cellSpan", { colSpan: "1", rowSpan: "1" });
    return span;
  }

  private _sizeElement(): Element {
    let size = findChild(this.element, HP_NS, "cellSz");
    if (!size) size = subElement(this.element, HP_NS, "cellSz", { width: "0", height: "0" });
    return size;
  }

  get address(): [number, number] {
    const addr = this._addrElement();
    if (!addr) return [0, 0];
    return [
      parseInt(addr.getAttribute("rowAddr") ?? "0", 10),
      parseInt(addr.getAttribute("colAddr") ?? "0", 10),
    ];
  }

  get span(): [number, number] {
    const span = this._spanElement();
    return [
      parseInt(span.getAttribute("rowSpan") ?? "1", 10),
      parseInt(span.getAttribute("colSpan") ?? "1", 10),
    ];
  }

  setSpan(rowSpan: number, colSpan: number): void {
    const span = this._spanElement();
    span.setAttribute("rowSpan", String(Math.max(rowSpan, 1)));
    span.setAttribute("colSpan", String(Math.max(colSpan, 1)));
    this.table.markDirty();
  }

  get width(): number {
    return parseInt(this._sizeElement().getAttribute("width") ?? "0", 10);
  }

  get height(): number {
    return parseInt(this._sizeElement().getAttribute("height") ?? "0", 10);
  }

  setSize(width?: number, height?: number): void {
    const size = this._sizeElement();
    if (width != null) size.setAttribute("width", String(Math.max(width, 0)));
    if (height != null) size.setAttribute("height", String(Math.max(height, 0)));
    this.table.markDirty();
  }

  get text(): string {
    const textEl = findDescendant(this.element, "t");
    if (!textEl || !textEl.textContent) return "";
    return textEl.textContent;
  }

  set text(value: string) {
    const textEl = this._ensureTextElement();
    textEl.textContent = value;
    this.element.setAttribute("dirty", "1");
    this.table.markDirty();
  }

  remove(): void {
    this._rowElement.removeChild(this.element);
    this.table.markDirty();
  }

  private _ensureTextElement(): Element {
    let sublist = findChild(this.element, HP_NS, "subList");
    if (!sublist) sublist = subElement(this.element, HP_NS, "subList", defaultSublistAttributes());
    let paragraph = findChild(sublist, HP_NS, "p");
    if (!paragraph) paragraph = subElement(sublist, HP_NS, "p", defaultCellParagraphAttributes());
    clearParagraphLayoutCache(paragraph);
    let run = findChild(paragraph, HP_NS, "run");
    if (!run) run = subElement(paragraph, HP_NS, "run", { charPrIDRef: "0" });
    let t = findChild(run, HP_NS, "t");
    if (!t) t = subElement(run, HP_NS, "t");
    return t;
  }
}

// -- HwpxTableGridPosition --

export interface HwpxTableGridPosition {
  row: number;
  column: number;
  cell: HwpxOxmlTableCell;
  anchor: [number, number];
  span: [number, number];
}

export function gridPositionIsAnchor(pos: HwpxTableGridPosition): boolean {
  return pos.row === pos.anchor[0] && pos.column === pos.anchor[1];
}

// -- HwpxOxmlTableRow --

export class HwpxOxmlTableRow {
  element: Element;
  table: HwpxOxmlTable;

  constructor(element: Element, table: HwpxOxmlTable) {
    this.element = element;
    this.table = table;
  }

  get cells(): HwpxOxmlTableCell[] {
    return findAllChildren(this.element, HP_NS, "tc").map(
      (el) => new HwpxOxmlTableCell(el, this.table, this.element),
    );
  }
}

// -- HwpxOxmlTable --

export class HwpxOxmlTable {
  element: Element;
  paragraph: HwpxOxmlParagraph;

  constructor(element: Element, paragraph: HwpxOxmlParagraph) {
    this.element = element;
    this.paragraph = paragraph;
  }

  markDirty(): void {
    this.paragraph.section.markDirty();
  }

  /** Page break mode: "CELL" (split at cell), "NONE" (no split), or other HWPX values. */
  get pageBreak(): string {
    return this.element.getAttribute("pageBreak") ?? "CELL";
  }

  set pageBreak(value: string) {
    if (this.element.getAttribute("pageBreak") !== value) {
      this.element.setAttribute("pageBreak", value);
      this.markDirty();
    }
  }

  /** Whether the header row repeats on each page ("0" = no, "1" = yes). */
  get repeatHeader(): boolean {
    return this.element.getAttribute("repeatHeader") === "1";
  }

  set repeatHeader(value: boolean) {
    const v = value ? "1" : "0";
    if (this.element.getAttribute("repeatHeader") !== v) {
      this.element.setAttribute("repeatHeader", v);
      this.markDirty();
    }
  }

  get rowCount(): number {
    const value = this.element.getAttribute("rowCnt");
    if (value && /^\d+$/.test(value)) return parseInt(value, 10);
    return findAllChildren(this.element, HP_NS, "tr").length;
  }

  get columnCount(): number {
    const value = this.element.getAttribute("colCnt");
    if (value && /^\d+$/.test(value)) return parseInt(value, 10);
    const firstRow = findChild(this.element, HP_NS, "tr");
    if (!firstRow) return 0;
    return findAllChildren(firstRow, HP_NS, "tc").length;
  }

  get rows(): HwpxOxmlTableRow[] {
    return findAllChildren(this.element, HP_NS, "tr").map((el) => new HwpxOxmlTableRow(el, this));
  }

  cell(rowIndex: number, colIndex: number): HwpxOxmlTableCell {
    const entry = this._gridEntry(rowIndex, colIndex);
    return entry.cell;
  }

  setCellText(rowIndex: number, colIndex: number, text: string): void {
    this.cell(rowIndex, colIndex).text = text;
  }

  private _buildCellGrid(): Map<string, HwpxTableGridPosition> {
    const mapping = new Map<string, HwpxTableGridPosition>();
    for (const row of findAllChildren(this.element, HP_NS, "tr")) {
      for (const cellElement of findAllChildren(row, HP_NS, "tc")) {
        const wrapper = new HwpxOxmlTableCell(cellElement, this, row);
        const [startRow, startCol] = wrapper.address;
        const [spanRow, spanCol] = wrapper.span;
        for (let lr = startRow; lr < startRow + spanRow; lr++) {
          for (let lc = startCol; lc < startCol + spanCol; lc++) {
            const key = `${lr},${lc}`;
            mapping.set(key, {
              row: lr,
              column: lc,
              cell: wrapper,
              anchor: [startRow, startCol],
              span: [spanRow, spanCol],
            });
          }
        }
      }
    }
    return mapping;
  }

  private _gridEntry(rowIndex: number, colIndex: number): HwpxTableGridPosition {
    if (rowIndex < 0 || colIndex < 0) throw new Error("row_index and col_index must be non-negative");
    const rowCount = this.rowCount;
    const colCount = this.columnCount;
    if (rowIndex >= rowCount || colIndex >= colCount) {
      throw new Error(`cell coordinates (${rowIndex}, ${colIndex}) exceed table bounds ${rowCount}x${colCount}`);
    }
    const entry = this._buildCellGrid().get(`${rowIndex},${colIndex}`);
    if (!entry) throw new Error(`cell coordinates (${rowIndex}, ${colIndex}) not found in grid`);
    return entry;
  }

  iterGrid(): HwpxTableGridPosition[] {
    const mapping = this._buildCellGrid();
    const result: HwpxTableGridPosition[] = [];
    for (let r = 0; r < this.rowCount; r++) {
      for (let c = 0; c < this.columnCount; c++) {
        const entry = mapping.get(`${r},${c}`);
        if (!entry) throw new Error(`cell coordinates (${r}, ${c}) do not resolve`);
        result.push(entry);
      }
    }
    return result;
  }

  getCellMap(): HwpxTableGridPosition[][] {
    const rowCount = this.rowCount;
    const colCount = this.columnCount;
    const grid: HwpxTableGridPosition[][] = [];
    const entries = this.iterGrid();
    let idx = 0;
    for (let r = 0; r < rowCount; r++) {
      const row: HwpxTableGridPosition[] = [];
      for (let c = 0; c < colCount; c++) {
        row.push(entries[idx++]!);
      }
      grid.push(row);
    }
    return grid;
  }

  static create(
    doc: Document,
    rows: number,
    cols: number,
    opts: { width?: number; height?: number; borderFillIdRef: string | number },
  ): Element {
    if (rows <= 0 || cols <= 0) throw new Error("rows and cols must be positive");
    const tableWidth = opts.width ?? cols * DEFAULT_CELL_WIDTH;
    const tableHeight = opts.height ?? rows * DEFAULT_CELL_HEIGHT;
    const borderFill = String(opts.borderFillIdRef);

    const tableAttrs: Record<string, string> = {
      id: objectId(), zOrder: "0", numberingType: "TABLE", textWrap: "TOP_AND_BOTTOM",
      textFlow: "BOTH_SIDES", lock: "0", dropcapstyle: "None", pageBreak: "CELL",
      repeatHeader: "0", rowCnt: String(rows), colCnt: String(cols),
      cellSpacing: "0", borderFillIDRef: borderFill, noAdjust: "0",
    };

    const table = createNsElement(doc, HP_NS, "tbl", tableAttrs);
    subElement(table, HP_NS, "sz", {
      width: String(Math.max(tableWidth, 0)), widthRelTo: "ABSOLUTE",
      height: String(Math.max(tableHeight, 0)), heightRelTo: "ABSOLUTE", protect: "0",
    });
    subElement(table, HP_NS, "pos", {
      treatAsChar: "1", affectLSpacing: "0", flowWithText: "1", allowOverlap: "0",
      holdAnchorAndSO: "0", vertRelTo: "PARA", horzRelTo: "COLUMN",
      vertAlign: "TOP", horzAlign: "LEFT", vertOffset: "0", horzOffset: "0",
    });
    subElement(table, HP_NS, "outMargin", defaultCellMarginAttributes());
    subElement(table, HP_NS, "inMargin", defaultCellMarginAttributes());

    const columnWidths = distributeSize(Math.max(tableWidth, 0), cols);
    const rowHeights = distributeSize(Math.max(tableHeight, 0), rows);

    for (let rowIdx = 0; rowIdx < rows; rowIdx++) {
      const row = subElement(table, HP_NS, "tr");
      for (let colIdx = 0; colIdx < cols; colIdx++) {
        const cell = subElement(row, HP_NS, "tc", defaultCellAttributes(borderFill));
        const sl = subElement(cell, HP_NS, "subList", defaultSublistAttributes());
        const p = subElement(sl, HP_NS, "p", defaultCellParagraphAttributes());
        const run = subElement(p, HP_NS, "run", { charPrIDRef: "0" });
        subElement(run, HP_NS, "t");
        subElement(cell, HP_NS, "cellAddr", { colAddr: String(colIdx), rowAddr: String(rowIdx) });
        subElement(cell, HP_NS, "cellSpan", { colSpan: "1", rowSpan: "1" });
        subElement(cell, HP_NS, "cellSz", {
          width: String(columnWidths[colIdx] ?? 0), height: String(rowHeights[rowIdx] ?? 0),
        });
        subElement(cell, HP_NS, "cellMargin", defaultCellMarginAttributes());
      }
    }
    return table;
  }
}

// -- HwpxOxmlParagraph --

export class HwpxOxmlParagraph {
  element: Element;
  section: HwpxOxmlSection;

  constructor(element: Element, section: HwpxOxmlSection) {
    this.element = element;
    this.section = section;
  }

  get runs(): HwpxOxmlRun[] {
    return findAllChildren(this.element, HP_NS, "run").map((el) => new HwpxOxmlRun(el, this));
  }

  get text(): string {
    const parts: string[] = [];
    for (const el of findAllDescendants(this.element, "t")) {
      if (el.textContent) parts.push(el.textContent);
    }
    return parts.join("");
  }

  set text(value: string) {
    for (const run of findAllChildren(this.element, HP_NS, "run")) {
      for (const child of findAllChildren(run, HP_NS, "t")) {
        run.removeChild(child);
      }
    }
    const run = this._ensureRun();
    const t = subElement(run, HP_NS, "t");
    t.textContent = value;
    this.section.markDirty();
  }

  get tables(): HwpxOxmlTable[] {
    const tables: HwpxOxmlTable[] = [];
    for (const run of findAllChildren(this.element, HP_NS, "run")) {
      for (const child of childElements(run)) {
        if (elementLocalName(child) === "tbl") tables.push(new HwpxOxmlTable(child, this));
      }
    }
    return tables;
  }

  get paraPrIdRef(): string | null {
    return this.element.getAttribute("paraPrIDRef");
  }

  set paraPrIdRef(value: string | number | null) {
    if (value == null) {
      if (this.element.hasAttribute("paraPrIDRef")) {
        this.element.removeAttribute("paraPrIDRef");
        this.section.markDirty();
      }
      return;
    }
    const newValue = String(value);
    if (this.element.getAttribute("paraPrIDRef") !== newValue) {
      this.element.setAttribute("paraPrIDRef", newValue);
      this.section.markDirty();
    }
  }

  get styleIdRef(): string | null {
    return this.element.getAttribute("styleIDRef");
  }

  set styleIdRef(value: string | number | null) {
    if (value == null) {
      if (this.element.hasAttribute("styleIDRef")) {
        this.element.removeAttribute("styleIDRef");
        this.section.markDirty();
      }
      return;
    }
    const newValue = String(value);
    if (this.element.getAttribute("styleIDRef") !== newValue) {
      this.element.setAttribute("styleIDRef", newValue);
      this.section.markDirty();
    }
  }

  get charPrIdRef(): string | null {
    const values = new Set<string>();
    for (const run of findAllChildren(this.element, HP_NS, "run")) {
      const v = run.getAttribute("charPrIDRef");
      if (v != null) values.add(v);
    }
    if (values.size === 0) return null;
    if (values.size === 1) return values.values().next().value!;
    return null;
  }

  set charPrIdRef(value: string | number | null) {
    const newValue = value == null ? null : String(value);
    let runs = findAllChildren(this.element, HP_NS, "run");
    if (runs.length === 0) runs = [this._ensureRun()];
    let changed = false;
    for (const run of runs) {
      if (newValue == null) {
        if (run.hasAttribute("charPrIDRef")) { run.removeAttribute("charPrIDRef"); changed = true; }
      } else {
        if (run.getAttribute("charPrIDRef") !== newValue) { run.setAttribute("charPrIDRef", newValue); changed = true; }
      }
    }
    if (changed) this.section.markDirty();
  }

  addRun(text: string = "", opts?: { charPrIdRef?: string | number; attributes?: Record<string, string> }): HwpxOxmlRun {
    const runAttrs: Record<string, string> = { ...(opts?.attributes ?? {}) };
    if (!("charPrIDRef" in runAttrs)) {
      if (opts?.charPrIdRef != null) {
        runAttrs["charPrIDRef"] = String(opts.charPrIdRef);
      } else {
        runAttrs["charPrIDRef"] = this.charPrIdRef ?? "0";
      }
    }
    const runElement = subElement(this.element, HP_NS, "run", runAttrs);
    const t = subElement(runElement, HP_NS, "t");
    t.textContent = text;
    this.section.markDirty();
    return new HwpxOxmlRun(runElement, this);
  }

  addTable(rows: number, cols: number, opts?: { width?: number; height?: number; borderFillIdRef?: string | number }): HwpxOxmlTable {
    let borderFillIdRef = opts?.borderFillIdRef;
    if (borderFillIdRef == null) {
      const document = this.section.document;
      if (document) borderFillIdRef = document.ensureBasicBorderFill();
      else borderFillIdRef = "0";
    }
    const doc = this.element.ownerDocument!;
    const run = subElement(this.element, HP_NS, "run", { charPrIDRef: this.charPrIdRef ?? "0" });
    const tableElement = HwpxOxmlTable.create(doc, rows, cols, {
      width: opts?.width, height: opts?.height, borderFillIdRef,
    });
    run.appendChild(tableElement);
    this.section.markDirty();
    return new HwpxOxmlTable(tableElement, this);
  }

  /**
   * Add a picture (image) element to this paragraph.
   * @param binaryItemIdRef - The binary item ID returned by HwpxPackage.addBinaryItem()
   * @param opts - width/height in hwpUnits (7200 = 1 inch). Use mmToHwp() to convert from mm.
   */
  addPicture(binaryItemIdRef: string, opts: {
    width: number;
    height: number;
    textWrap?: string;
    treatAsChar?: boolean;
  }): Element {
    const doc = this.element.ownerDocument!;
    const width = Math.max(opts.width, 1);
    const height = Math.max(opts.height, 1);
    const textWrap = opts.textWrap ?? "TOP_AND_BOTTOM";
    const treatAsChar = opts.treatAsChar !== false ? "1" : "0";

    const run = subElement(this.element, HP_NS, "run", { charPrIDRef: this.charPrIdRef ?? "0" });

    const pic = createNsElement(doc, HP_NS, "pic", {
      id: objectId(),
      zOrder: "0",
      numberingType: "PICTURE",
      textWrap,
      textFlow: "BOTH_SIDES",
      lock: "0",
      dropcapstyle: "None",
      href: "",
      groupLevel: "0",
      instid: objectId(),
      reverse: "0",
    });
    run.appendChild(pic);

    subElement(pic, HP_NS, "offset", { x: "0", y: "0" });
    subElement(pic, HP_NS, "orgSz", { width: String(width), height: String(height) });
    subElement(pic, HP_NS, "curSz", { width: String(width), height: String(height) });
    subElement(pic, HP_NS, "flip", { horizontal: "0", vertical: "0" });
    subElement(pic, HP_NS, "rotationInfo", {
      angle: "0",
      centerX: String(Math.floor(width / 2)),
      centerY: String(Math.floor(height / 2)),
      rotateimage: "1",
    });

    // renderingInfo with identity matrices
    const renderingInfo = subElement(pic, HP_NS, "renderingInfo");
    createNsElement(doc, HC_NS, "transMatrix", { e1: "1", e2: "0", e3: "0", e4: "0", e5: "1", e6: "0" });
    renderingInfo.appendChild(createNsElement(doc, HC_NS, "transMatrix", { e1: "1", e2: "0", e3: "0", e4: "0", e5: "1", e6: "0" }));
    renderingInfo.appendChild(createNsElement(doc, HC_NS, "scaMatrix", { e1: "1", e2: "0", e3: "0", e4: "0", e5: "1", e6: "0" }));
    renderingInfo.appendChild(createNsElement(doc, HC_NS, "rotMatrix", { e1: "1", e2: "0", e3: "0", e4: "0", e5: "1", e6: "0" }));

    // img reference
    const img = createNsElement(doc, HC_NS, "img", {
      binaryItemIDRef: binaryItemIdRef,
      bright: "0",
      contrast: "0",
      effect: "REAL_PIC",
      alpha: "0",
    });
    pic.appendChild(img);

    // imgRect (4 corner points)
    const imgRect = subElement(pic, HP_NS, "imgRect");
    imgRect.appendChild(createNsElement(doc, HC_NS, "pt0", { x: "0", y: "0" }));
    imgRect.appendChild(createNsElement(doc, HC_NS, "pt1", { x: String(width), y: "0" }));
    imgRect.appendChild(createNsElement(doc, HC_NS, "pt2", { x: String(width), y: String(height) }));
    imgRect.appendChild(createNsElement(doc, HC_NS, "pt3", { x: "0", y: String(height) }));

    subElement(pic, HP_NS, "imgClip", { left: "0", right: String(width), top: "0", bottom: String(height) });
    subElement(pic, HP_NS, "inMargin", { left: "0", right: "0", top: "0", bottom: "0" });
    subElement(pic, HP_NS, "imgDim", { dimwidth: String(width), dimheight: String(height) });
    subElement(pic, HP_NS, "effects");
    subElement(pic, HP_NS, "sz", {
      width: String(width), widthRelTo: "ABSOLUTE",
      height: String(height), heightRelTo: "ABSOLUTE", protect: "0",
    });
    subElement(pic, HP_NS, "pos", {
      treatAsChar, affectLSpacing: "0", flowWithText: "1", allowOverlap: "0",
      holdAnchorAndSO: "0", vertRelTo: "PARA", horzRelTo: "COLUMN",
      vertAlign: "TOP", horzAlign: "LEFT", vertOffset: "0", horzOffset: "0",
    });
    subElement(pic, HP_NS, "outMargin", { left: "0", right: "0", top: "0", bottom: "0" });

    this.section.markDirty();
    return pic;
  }

  /** Return all <pic> elements across all runs. */
  get pictures(): Element[] {
    const pics: Element[] = [];
    for (const run of findAllChildren(this.element, HP_NS, "run")) {
      for (const child of childElements(run)) {
        if (elementLocalName(child) === "pic") pics.push(child);
      }
    }
    return pics;
  }

  /**
   * Set the size of a picture element (by index) in hwpUnits.
   * Updates curSz, sz, imgRect, imgClip, imgDim, and rotationInfo.
   */
  setPictureSize(pictureIndex: number, width: number, height: number): void {
    const pics = this.pictures;
    const pic = pics[pictureIndex];
    if (!pic) return;
    const w = Math.max(width, 1);
    const h = Math.max(height, 1);

    // Update curSz
    const curSz = findChild(pic, HP_NS, "curSz");
    if (curSz) { curSz.setAttribute("width", String(w)); curSz.setAttribute("height", String(h)); }

    // Update sz
    const sz = findChild(pic, HP_NS, "sz");
    if (sz) { sz.setAttribute("width", String(w)); sz.setAttribute("height", String(h)); }

    // Update imgRect corner points
    const imgRect = findChild(pic, HP_NS, "imgRect");
    if (imgRect) {
      const pts = childElements(imgRect);
      if (pts[0]) { pts[0].setAttribute("x", "0"); pts[0].setAttribute("y", "0"); }
      if (pts[1]) { pts[1].setAttribute("x", String(w)); pts[1].setAttribute("y", "0"); }
      if (pts[2]) { pts[2].setAttribute("x", String(w)); pts[2].setAttribute("y", String(h)); }
      if (pts[3]) { pts[3].setAttribute("x", "0"); pts[3].setAttribute("y", String(h)); }
    }

    // Update imgClip
    const imgClip = findChild(pic, HP_NS, "imgClip");
    if (imgClip) { imgClip.setAttribute("right", String(w)); imgClip.setAttribute("bottom", String(h)); }

    // Update imgDim
    const imgDim = findChild(pic, HP_NS, "imgDim");
    if (imgDim) { imgDim.setAttribute("dimwidth", String(w)); imgDim.setAttribute("dimheight", String(h)); }

    // Update rotationInfo center
    const rotInfo = findChild(pic, HP_NS, "rotationInfo");
    if (rotInfo) {
      rotInfo.setAttribute("centerX", String(Math.floor(w / 2)));
      rotInfo.setAttribute("centerY", String(Math.floor(h / 2)));
    }

    this.section.markDirty();
  }

  private _ensureRun(): Element {
    const runs = findAllChildren(this.element, HP_NS, "run");
    if (runs.length > 0) return runs[0]!;
    return subElement(this.element, HP_NS, "run", { charPrIDRef: this.charPrIdRef ?? "0" });
  }
}

// -- HwpxOxmlMemo --

export class HwpxOxmlMemo {
  element: Element;
  group: HwpxOxmlMemoGroup;

  constructor(element: Element, group: HwpxOxmlMemoGroup) {
    this.element = element;
    this.group = group;
  }

  get id(): string | null { return this.element.getAttribute("id"); }
  set id(value: string | null) {
    if (value == null) {
      if (this.element.hasAttribute("id")) { this.element.removeAttribute("id"); this.group.section.markDirty(); }
      return;
    }
    const v = String(value);
    if (this.element.getAttribute("id") !== v) { this.element.setAttribute("id", v); this.group.section.markDirty(); }
  }

  get memoShapeIdRef(): string | null { return this.element.getAttribute("memoShapeIDRef"); }
  set memoShapeIdRef(value: string | number | null) {
    if (value == null) {
      if (this.element.hasAttribute("memoShapeIDRef")) { this.element.removeAttribute("memoShapeIDRef"); this.group.section.markDirty(); }
      return;
    }
    const v = String(value);
    if (this.element.getAttribute("memoShapeIDRef") !== v) { this.element.setAttribute("memoShapeIDRef", v); this.group.section.markDirty(); }
  }

  get text(): string {
    const parts: string[] = [];
    for (const p of this.paragraphs) {
      const v = p.text;
      if (v) parts.push(v);
    }
    return parts.join("\n");
  }

  set text(value: string) {
    this.setText(value);
  }

  setText(value: string, charPrIdRef?: string | number | null): void {
    // Remove existing paraList/p children
    for (const child of childElements(this.element)) {
      const name = elementLocalName(child);
      if (name === "paraList" || name === "p") this.element.removeChild(child);
    }
    const doc = this.element.ownerDocument!;
    const paraList = subElement(this.element, HP_NS, "paraList");
    const p = createParagraphElement(doc, value, {
      charPrIdRef: charPrIdRef ?? "0",
    });
    paraList.appendChild(p);
    this.group.section.markDirty();
  }

  get paragraphs(): HwpxOxmlParagraph[] {
    return findAllDescendants(this.element, "p").map(
      (el) => new HwpxOxmlParagraph(el, this.group.section),
    );
  }

  remove(): void {
    try { this.group.element.removeChild(this.element); } catch { return; }
    this.group.section.markDirty();
    this.group._cleanup();
  }
}

// -- HwpxOxmlMemoGroup --

export class HwpxOxmlMemoGroup {
  element: Element;
  section: HwpxOxmlSection;

  constructor(element: Element, section: HwpxOxmlSection) {
    this.element = element;
    this.section = section;
  }

  get memos(): HwpxOxmlMemo[] {
    return findAllChildren(this.element, HP_NS, "memo").map(
      (el) => new HwpxOxmlMemo(el, this),
    );
  }

  addMemo(text: string = "", opts?: { memoShapeIdRef?: string | number; memoId?: string; charPrIdRef?: string | number; attributes?: Record<string, string> }): HwpxOxmlMemo {
    const attrs: Record<string, string> = { ...(opts?.attributes ?? {}) };
    if (!attrs["id"]) attrs["id"] = opts?.memoId ?? memoId();
    if (opts?.memoShapeIdRef != null) {
      if (!attrs["memoShapeIDRef"]) attrs["memoShapeIDRef"] = String(opts.memoShapeIdRef);
    }
    const memoElement = subElement(this.element, HP_NS, "memo", attrs);
    const memo = new HwpxOxmlMemo(memoElement, this);
    memo.setText(text, opts?.charPrIdRef);
    this.section.markDirty();
    return memo;
  }

  _cleanup(): void {
    if (childElements(this.element).length > 0) return;
    try { this.section._element.removeChild(this.element); } catch { return; }
    this.section.markDirty();
  }
}

// -- Simple parts --

export class HwpxOxmlSimplePart {
  partName: string;
  protected _element: Element;
  protected _document: HwpxOxmlDocument | null;
  protected _dirty: boolean = false;

  constructor(partName: string, element: Element, document: HwpxOxmlDocument | null = null) {
    this.partName = partName;
    this._element = element;
    this._document = document;
  }

  get element(): Element { return this._element; }
  get document(): HwpxOxmlDocument | null { return this._document; }
  attachDocument(document: HwpxOxmlDocument): void { this._document = document; }
  get dirty(): boolean { return this._dirty; }
  markDirty(): void { this._dirty = true; }
  resetDirty(): void { this._dirty = false; }
  replaceElement(element: Element): void { this._element = element; this.markDirty(); }
  toBytes(): string { return serializeXmlBytes(this._element); }
}

export class HwpxOxmlMasterPage extends HwpxOxmlSimplePart {}
export class HwpxOxmlHistory extends HwpxOxmlSimplePart {}
export class HwpxOxmlVersion extends HwpxOxmlSimplePart {}

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

  markDirty(): void { this._dirty = true; }
  get dirty(): boolean { return this._dirty; }
  resetDirty(): void { this._dirty = false; }
  toBytes(): string { return serializeXmlBytes(this._element); }
}

// -- HwpxOxmlHeader --

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

  ensureRunStyle(opts: { bold?: boolean; italic?: boolean; underline?: boolean; baseCharPrId?: string | number }): string {
    if (this._headers.length === 0) throw new Error("document does not contain any headers");
    const target = [!!opts.bold, !!opts.italic, !!opts.underline];
    const header = this._headers[0]!;

    const elementFlags = (element: Element): [boolean, boolean, boolean] => {
      const boldPresent = findChild(element, HH_NS, "bold") != null;
      const italicPresent = findChild(element, HH_NS, "italic") != null;
      const underlineEl = findChild(element, HH_NS, "underline");
      let underlinePresent = false;
      if (underlineEl) underlinePresent = (underlineEl.getAttribute("type") ?? "").toUpperCase() !== "NONE";
      return [boldPresent, italicPresent, underlinePresent];
    };

    const predicate = (element: Element): boolean => {
      const flags = elementFlags(element);
      return flags[0] === target[0] && flags[1] === target[1] && flags[2] === target[2];
    };

    const modifier = (element: Element): void => {
      // Remove existing bold/italic/underline
      for (const child of findAllChildren(element, HH_NS, "bold")) element.removeChild(child);
      for (const child of findAllChildren(element, HH_NS, "italic")) element.removeChild(child);
      const underlineNodes = findAllChildren(element, HH_NS, "underline");
      const baseAttrs: Record<string, string> = underlineNodes.length > 0 ? getAttributes(underlineNodes[0]!) : {};
      for (const child of underlineNodes) element.removeChild(child);

      const doc = element.ownerDocument!;
      if (target[0]) subElement(element, HH_NS, "bold");
      if (target[1]) subElement(element, HH_NS, "italic");

      if (target[2]) {
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
