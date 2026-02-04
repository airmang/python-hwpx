/**
 * Internal XML utility functions and constants for HWPX OXML document model.
 * Not part of the public API — used only within the oxml package.
 */

import {
  serializeXml,
  localName as domLocalName,
  childElements,
} from "../xml/dom.js";

export const HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph";
export const HH_NS = "http://www.hancom.co.kr/hwpml/2011/head";
export const HC_NS = "http://www.hancom.co.kr/hwpml/2011/core";

export const DEFAULT_PARAGRAPH_ATTRS: Record<string, string> = {
  paraPrIDRef: "0",
  styleIDRef: "0",
  pageBreak: "0",
  columnBreak: "0",
  merged: "0",
};

export const DEFAULT_CELL_WIDTH = 7200;
export const DEFAULT_CELL_HEIGHT = 3600;

export const BASIC_BORDER_FILL_ATTRIBUTES: Record<string, string> = {
  threeD: "0",
  shadow: "0",
  centerLine: "NONE",
  breakCellSeparateLine: "0",
};

export const BASIC_BORDER_CHILDREN: [string, Record<string, string>][] = [
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

export function generateId(): string {
  const bytes = new Uint8Array(16);
  if (typeof globalThis.crypto !== "undefined" && globalThis.crypto.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  const view = new DataView(bytes.buffer);
  return String(view.getUint32(0) >>> 0);
}

export function paragraphId(): string {
  return generateId();
}

export function objectId(): string {
  return generateId();
}

export function memoId(): string {
  return generateId();
}

// -- XML helpers --

export function serializeXmlBytes(element: Element): string {
  return '<?xml version="1.0" encoding="UTF-8"?>' + serializeXml(element);
}

export function elementLocalName(node: Element): string {
  return domLocalName(node);
}

export function normalizeLength(value: string | null): string {
  if (value == null) return "";
  return value.replace(/ /g, "").toLowerCase();
}

export function getIntAttr(element: Element, name: string, defaultValue: number = 0): number {
  const value = element.getAttribute(name);
  if (value == null) return defaultValue;
  const n = parseInt(value, 10);
  return isNaN(n) ? defaultValue : n;
}

export function clearParagraphLayoutCache(paragraph: Element): void {
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

export function distributeSize(total: number, parts: number): number[] {
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

export function defaultCellAttributes(borderFillIdRef: string): Record<string, string> {
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

export function defaultSublistAttributes(): Record<string, string> {
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

export function defaultCellParagraphAttributes(): Record<string, string> {
  return { ...DEFAULT_PARAGRAPH_ATTRS, id: paragraphId() };
}

export function defaultCellMarginAttributes(): Record<string, string> {
  return { left: "0", right: "0", top: "0", bottom: "0" };
}

export function findChild(parent: Element, ns: string, localNameStr: string): Element | null {
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

export function findAllChildren(parent: Element, ns: string, localNameStr: string): Element[] {
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

export function findDescendant(parent: Element, localNameStr: string): Element | null {
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

export function findAllDescendants(parent: Element, localNameStr: string): Element[] {
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

export function createNsElement(
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

export function subElement(
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

export function createParagraphElement(
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

export function borderFillIsBasicSolidLine(element: Element): boolean {
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

export function createBasicBorderFillElement(doc: Document, borderId: string): Element {
  const attrs = { id: borderId, ...BASIC_BORDER_FILL_ATTRIBUTES };
  const element = createNsElement(doc, HH_NS, "borderFill", attrs);
  for (const [childName, childAttrs] of BASIC_BORDER_CHILDREN) {
    subElement(element, HH_NS, childName, { ...childAttrs });
  }
  return element;
}

// -- Background color fill helpers --

/**
 * Create a borderFill with solid color background (winBrush)
 * @param doc - XML Document
 * @param id - borderFill ID
 * @param faceColor - Background color (e.g., "#EFEFEF", "none")
 * @param options - Optional parameters
 */
export function createSolidBorderFill(
  doc: Document,
  id: string,
  faceColor: string,
  options?: {
    hatchColor?: string;
    alpha?: number;
    borderAttrs?: Partial<typeof BASIC_BORDER_FILL_ATTRIBUTES>;
    borderChildren?: boolean;
  }
): Element {
  const opts = options ?? {};
  const borderAttrs = { ...BASIC_BORDER_FILL_ATTRIBUTES, ...opts.borderAttrs };
  const element = createNsElement(doc, HH_NS, "borderFill", { id, ...borderAttrs });

  // Add winBrush with faceColor
  subElement(element, HC_NS, "winBrush", {
    faceColor,
    hatchColor: opts.hatchColor ?? "#000000",
    alpha: String(opts.alpha ?? 0),
  });

  // Add border children if requested
  if (opts.borderChildren !== false) {
    for (const [childName, childAttrs] of BASIC_BORDER_CHILDREN) {
      subElement(element, HH_NS, childName, { ...childAttrs });
    }
  }

  return element;
}

/**
 * Create a borderFill with image background (imgBrush)
 * @param doc - XML Document
 * @param id - borderFill ID
 * @param binaryItemIdRef - Binary item ID reference for the image
 * @param options - Optional parameters
 */
export function createImageBorderFill(
  doc: Document,
  id: string,
  binaryItemIdRef: string,
  options?: {
    borderAttrs?: Partial<typeof BASIC_BORDER_FILL_ATTRIBUTES>;
    borderChildren?: boolean;
  }
): Element {
  const opts = options ?? {};
  const borderAttrs = { ...BASIC_BORDER_FILL_ATTRIBUTES, ...opts.borderAttrs };
  const element = createNsElement(doc, HH_NS, "borderFill", { id, ...borderAttrs });

  // Add imgBrush with img reference
  const imgBrush = subElement(element, HC_NS, "imgBrush");
  subElement(imgBrush, HC_NS, "img", {
    binaryItemIDRef: binaryItemIdRef,
  });

  // Add border children if requested
  if (opts.borderChildren !== false) {
    for (const [childName, childAttrs] of BASIC_BORDER_CHILDREN) {
      subElement(element, HH_NS, childName, { ...childAttrs });
    }
  }

  return element;
}

/**
 * Check if a borderFill element has a specific faceColor
 */
export function borderFillHasFaceColor(element: Element, faceColor: string): boolean {
  if (elementLocalName(element) !== "borderFill") return false;

  const winBrush = findChild(element, HC_NS, "winBrush");
  if (!winBrush) return false;

  const actualFaceColor = winBrush.getAttribute("faceColor");
  return actualFaceColor === faceColor;
}

/**
 * Check if a borderFill element has an image brush
 */
export function borderFillHasImageBrush(element: Element): boolean {
  if (elementLocalName(element) !== "borderFill") return false;
  return findChild(element, HC_NS, "imgBrush") !== null;
}
