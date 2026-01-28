/**
 * Simple OXML part classes: SimplePart, MasterPage, History, Version.
 */

import { serializeXmlBytes } from "./xml-utils.js";
import type { HwpxOxmlDocument } from "./document.js";

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
