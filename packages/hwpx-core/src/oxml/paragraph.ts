/**
 * Paragraph and Run OXML classes: HwpxOxmlRun, HwpxOxmlParagraph.
 */

import { childElements } from "../xml/dom.js";
import { HC_NS } from "./schema.js";
import type { RunStyle } from "./types.js";
import type { HwpxOxmlSection } from "./section.js";
import { HwpxOxmlTable, type HwpxMargin } from "./table.js";
import {
  HP_NS,
  objectId,
  paragraphId,
  DEFAULT_PARAGRAPH_ATTRS,
  elementLocalName,
  findChild,
  findAllChildren,
  findAllDescendants,
  createNsElement,
  subElement,
} from "./xml-utils.js";

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

  /** Whether this paragraph forces a column break before it. */
  get columnBreak(): boolean {
    return this.element.getAttribute("columnBreak") === "1";
  }

  set columnBreak(value: boolean) {
    const newValue = value ? "1" : "0";
    if (this.element.getAttribute("columnBreak") !== newValue) {
      this.element.setAttribute("columnBreak", newValue);
      this.section.markDirty();
    }
  }

  /** Whether this paragraph forces a page break before it. */
  get pageBreak(): boolean {
    return this.element.getAttribute("pageBreak") === "1";
  }

  set pageBreak(value: boolean) {
    const newValue = value ? "1" : "0";
    if (this.element.getAttribute("pageBreak") !== newValue) {
      this.element.setAttribute("pageBreak", newValue);
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

  /** Get picture outer margin by index. */
  getPictureOutMargin(pictureIndex: number): HwpxMargin {
    const pic = this.pictures[pictureIndex];
    if (!pic) return { top: 0, bottom: 0, left: 0, right: 0 };
    const el = findChild(pic, HP_NS, "outMargin");
    if (!el) return { top: 0, bottom: 0, left: 0, right: 0 };
    return {
      top: parseInt(el.getAttribute("top") ?? "0", 10),
      bottom: parseInt(el.getAttribute("bottom") ?? "0", 10),
      left: parseInt(el.getAttribute("left") ?? "0", 10),
      right: parseInt(el.getAttribute("right") ?? "0", 10),
    };
  }

  /** Set picture outer margin by index. */
  setPictureOutMargin(pictureIndex: number, margin: Partial<HwpxMargin>): void {
    const pic = this.pictures[pictureIndex];
    if (!pic) return;
    let el = findChild(pic, HP_NS, "outMargin");
    if (!el) el = subElement(pic, HP_NS, "outMargin", { left: "0", right: "0", top: "0", bottom: "0" });
    if (margin.top != null) el.setAttribute("top", String(Math.max(margin.top, 0)));
    if (margin.bottom != null) el.setAttribute("bottom", String(Math.max(margin.bottom, 0)));
    if (margin.left != null) el.setAttribute("left", String(Math.max(margin.left, 0)));
    if (margin.right != null) el.setAttribute("right", String(Math.max(margin.right, 0)));
    this.section.markDirty();
  }

  /** Get picture inner margin by index. */
  getPictureInMargin(pictureIndex: number): HwpxMargin {
    const pic = this.pictures[pictureIndex];
    if (!pic) return { top: 0, bottom: 0, left: 0, right: 0 };
    const el = findChild(pic, HP_NS, "inMargin");
    if (!el) return { top: 0, bottom: 0, left: 0, right: 0 };
    return {
      top: parseInt(el.getAttribute("top") ?? "0", 10),
      bottom: parseInt(el.getAttribute("bottom") ?? "0", 10),
      left: parseInt(el.getAttribute("left") ?? "0", 10),
      right: parseInt(el.getAttribute("right") ?? "0", 10),
    };
  }

  /** Set picture inner margin by index. */
  setPictureInMargin(pictureIndex: number, margin: Partial<HwpxMargin>): void {
    const pic = this.pictures[pictureIndex];
    if (!pic) return;
    let el = findChild(pic, HP_NS, "inMargin");
    if (!el) el = subElement(pic, HP_NS, "inMargin", { left: "0", right: "0", top: "0", bottom: "0" });
    if (margin.top != null) el.setAttribute("top", String(Math.max(margin.top, 0)));
    if (margin.bottom != null) el.setAttribute("bottom", String(Math.max(margin.bottom, 0)));
    if (margin.left != null) el.setAttribute("left", String(Math.max(margin.left, 0)));
    if (margin.right != null) el.setAttribute("right", String(Math.max(margin.right, 0)));
    this.section.markDirty();
  }

  /**
   * Add an equation element to this paragraph.
   * The script uses HWP equation scripting language (e.g. "rmCH _{3} COOH").
   *
   * @param script - HWP equation script text
   * @param opts - Optional configuration:
   *   - width/height in hwpUnits (estimated size; Hangul recalculates on open)
   *   - textColor: equation text color (default "#000000")
   *   - font: equation font (default "HancomEQN")
   *   - baseUnit: base unit size (default 1000)
   *   - baseLine: baseline percentage (default 85)
   *   - charPrIdRef: character property ID for the enclosing run
   */
  addEquation(script: string, opts?: {
    width?: number;
    height?: number;
    textColor?: string;
    font?: string;
    baseUnit?: number;
    baseLine?: number;
    charPrIdRef?: string | number;
  }): Element {
    const doc = this.element.ownerDocument!;
    const width = opts?.width ?? 3000;
    const height = opts?.height ?? 1100;
    const textColor = opts?.textColor ?? "#000000";
    const font = opts?.font ?? "HancomEQN";
    const baseUnit = opts?.baseUnit ?? 1000;
    const baseLine = opts?.baseLine ?? 85;

    const runCharPrId = opts?.charPrIdRef != null ? String(opts.charPrIdRef) : (this.charPrIdRef ?? "0");
    const run = subElement(this.element, HP_NS, "run", { charPrIDRef: runCharPrId });

    const eq = createNsElement(doc, HP_NS, "equation", {
      id: objectId(),
      zOrder: "0",
      numberingType: "EQUATION",
      textWrap: "TOP_AND_BOTTOM",
      textFlow: "BOTH_SIDES",
      lock: "0",
      dropcapstyle: "None",
      version: "Equation Version 60",
      baseLine: String(baseLine),
      textColor,
      baseUnit: String(baseUnit),
      lineMode: "CHAR",
      font,
    });
    run.appendChild(eq);

    subElement(eq, HP_NS, "sz", {
      width: String(width), widthRelTo: "ABSOLUTE",
      height: String(height), heightRelTo: "ABSOLUTE",
      protect: "0",
    });
    subElement(eq, HP_NS, "pos", {
      treatAsChar: "1", affectLSpacing: "0", flowWithText: "1",
      allowOverlap: "0", holdAnchorAndSO: "0",
      vertRelTo: "PARA", horzRelTo: "PARA",
      vertAlign: "TOP", horzAlign: "LEFT",
      vertOffset: "0", horzOffset: "0",
    });
    subElement(eq, HP_NS, "outMargin", { left: "56", right: "56", top: "0", bottom: "0" });

    const commentEl = subElement(eq, HP_NS, "shapeComment");
    commentEl.textContent = "수식입니다.";

    const scriptEl = subElement(eq, HP_NS, "script");
    // Preserve whitespace for multiline scripts (those using # for line breaks)
    if (script.includes("#") || script.includes("\n")) {
      scriptEl.setAttribute("xml:space", "preserve");
    }
    scriptEl.textContent = script;

    this.section.markDirty();
    return eq;
  }

  /** Return all <equation> elements across all runs. */
  get equations(): Element[] {
    const eqs: Element[] = [];
    for (const run of findAllChildren(this.element, HP_NS, "run")) {
      for (const child of childElements(run)) {
        if (elementLocalName(child) === "equation") eqs.push(child);
      }
    }
    return eqs;
  }

  remove(): void {
    const parent = this.element.parentNode;
    if (!parent) return;
    parent.removeChild(this.element);
    this.section.markDirty();
  }

  private _ensureRun(): Element {
    const runs = findAllChildren(this.element, HP_NS, "run");
    if (runs.length > 0) return runs[0]!;
    return subElement(this.element, HP_NS, "run", { charPrIDRef: this.charPrIdRef ?? "0" });
  }
}
