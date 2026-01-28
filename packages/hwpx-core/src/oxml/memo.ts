/**
 * Memo-related OXML classes: HwpxOxmlMemo, HwpxOxmlMemoGroup.
 */

import { childElements } from "../xml/dom.js";
import { HwpxOxmlParagraph } from "./paragraph.js";
import type { HwpxOxmlSection } from "./section.js";
import {
  HP_NS,
  memoId,
  elementLocalName,
  findAllChildren,
  findAllDescendants,
  subElement,
  createParagraphElement,
} from "./xml-utils.js";

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
