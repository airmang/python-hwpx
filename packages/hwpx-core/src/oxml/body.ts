/**
 * Body element models: Paragraph, Run, TextSpan, Control, InlineObject, Table.
 * Ported from Python hwpx/oxml/body.py
 */

import {
  localName as domLocalName,
  childElements,
  getAttributes,
  getTextContent,
  getTailText,
  createElement,
  parseXml,
  serializeXml,
} from "../xml/dom.js";
import { GenericElement, parseGenericElement } from "./common.js";
import { localName, parseInt_, parseBool } from "./utils.js";

const _DEFAULT_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph";
const _DEFAULT_HP = `{${_DEFAULT_HP_NS}}`;

export const INLINE_OBJECT_NAMES = new Set([
  "line", "rect", "ellipse", "arc", "polyline", "polygon", "curve",
  "connectLine", "picture", "pic", "shape", "drawingObject", "container",
  "equation", "ole", "chart", "video", "audio", "textart",
]);

const _TRACK_CHANGE_MARK_NAMES = new Set([
  "insertBegin", "insertEnd", "deleteBegin", "deleteEnd",
]);

// -- Type aliases --
export type InlineMark = GenericElement | TrackChangeMark;
export type RunChild = GenericElement | Control | Table | InlineObject | TextSpan;
export type ParagraphChild = Run | GenericElement;

// -- Interfaces / Classes --

export interface TrackChangeMark {
  tag: string;
  name: string;
  changeType: string;
  isBegin: boolean;
  paraEnd: boolean | null;
  tcId: number | null;
  id: number | null;
  attributes: Record<string, string>;
}

export interface TextMarkup {
  element: InlineMark;
  trailingText: string;
}

export function textMarkupName(markup: TextMarkup): string {
  return markup.element.name;
}

export interface TextSpan {
  tag: string;
  leadingText: string;
  marks: TextMarkup[];
  attributes: Record<string, string>;
}

export function textSpanText(span: TextSpan): string {
  return span.leadingText + span.marks.map((m) => m.trailingText).join("");
}

export function setTextSpanText(span: TextSpan, value: string): void {
  span.leadingText = value;
  for (const mark of span.marks) {
    mark.trailingText = "";
  }
}

export interface Control {
  tag: string;
  controlType: string | null;
  attributes: Record<string, string>;
  children: GenericElement[];
}

export interface InlineObject {
  tag: string;
  name: string;
  attributes: Record<string, string>;
  children: GenericElement[];
}

export interface Table {
  tag: string;
  attributes: Record<string, string>;
  children: GenericElement[];
}

export interface Run {
  tag: string;
  charPrIdRef: number | null;
  sectionProperties: GenericElement[];
  controls: Control[];
  tables: Table[];
  inlineObjects: InlineObject[];
  textSpans: TextSpan[];
  otherChildren: GenericElement[];
  attributes: Record<string, string>;
  content: RunChild[];
}

export interface Paragraph {
  tag: string;
  id: number | null;
  paraPrIdRef: number | null;
  styleIdRef: number | null;
  pageBreak: boolean | null;
  columnBreak: boolean | null;
  merged: boolean | null;
  runs: Run[];
  attributes: Record<string, string>;
  otherChildren: GenericElement[];
  content: ParagraphChild[];
}

export interface Section {
  tag: string;
  attributes: Record<string, string>;
  paragraphs: Paragraph[];
  otherChildren: GenericElement[];
}

// -- Helpers --

function qualifiedTag(tag: string | null | undefined, name: string): string {
  if (tag) return tag;
  return `${_DEFAULT_HP}${name}`;
}

function boolToStr(value: boolean): string {
  return value ? "true" : "false";
}

// -- Parse functions --

export function parseTrackChangeMark(node: Element): TrackChangeMark {
  const attrs = { ...getAttributes(node) };
  const paraEnd = parseBool(attrs["paraend"] ?? null);
  delete attrs["paraend"];
  const tcId = parseInt_(attrs["TcId"] ?? null);
  delete attrs["TcId"];
  const markId = parseInt_(attrs["Id"] ?? null);
  delete attrs["Id"];
  const name = localName(node);
  const changeType = name.startsWith("insert") ? "insert" : "delete";
  const isBegin = name.endsWith("Begin");
  return {
    tag: node.tagName,
    name,
    changeType,
    isBegin,
    paraEnd,
    tcId,
    id: markId,
    attributes: attrs,
  };
}

function parseTextMarkup(node: Element): InlineMark {
  const name = localName(node);
  if (_TRACK_CHANGE_MARK_NAMES.has(name)) {
    return parseTrackChangeMark(node);
  }
  return parseGenericElement(node);
}

export function parseTextSpan(node: Element): TextSpan {
  const leading = getTextContent(node) ?? "";
  const marks: TextMarkup[] = [];

  for (const child of childElements(node)) {
    const mark = parseTextMarkup(child);
    const trailing = getTailText(child);
    marks.push({ element: mark, trailingText: trailing });
  }

  return {
    tag: node.tagName,
    leadingText: leading,
    marks,
    attributes: getAttributes(node),
  };
}

export function parseControlElement(node: Element): Control {
  const attrs = { ...getAttributes(node) };
  const controlType = attrs["type"] ?? null;
  delete attrs["type"];
  const children = childElements(node).map((child) => parseGenericElement(child));
  return { tag: node.tagName, controlType, attributes: attrs, children };
}

export function parseInlineObjectElement(node: Element): InlineObject {
  return {
    tag: node.tagName,
    name: localName(node),
    attributes: getAttributes(node),
    children: childElements(node).map((child) => parseGenericElement(child)),
  };
}

export function parseTableElement(node: Element): Table {
  return {
    tag: node.tagName,
    attributes: getAttributes(node),
    children: childElements(node).map((child) => parseGenericElement(child)),
  };
}

export function parseRunElement(node: Element): Run {
  const attributes = { ...getAttributes(node) };
  const charPrIdRef = parseInt_(attributes["charPrIDRef"] ?? null);
  delete attributes["charPrIDRef"];

  const run: Run = {
    tag: node.tagName,
    charPrIdRef,
    sectionProperties: [],
    controls: [],
    tables: [],
    inlineObjects: [],
    textSpans: [],
    otherChildren: [],
    attributes,
    content: [],
  };

  for (const child of childElements(node)) {
    const name = localName(child);
    if (name === "secPr") {
      const element = parseGenericElement(child);
      run.sectionProperties.push(element);
      run.content.push(element);
    } else if (name === "ctrl") {
      const control = parseControlElement(child);
      run.controls.push(control);
      run.content.push(control);
    } else if (name === "t") {
      const span = parseTextSpan(child);
      run.textSpans.push(span);
      run.content.push(span);
    } else if (name === "tbl") {
      const table = parseTableElement(child);
      run.tables.push(table);
      run.content.push(table);
    } else if (INLINE_OBJECT_NAMES.has(name)) {
      const obj = parseInlineObjectElement(child);
      run.inlineObjects.push(obj);
      run.content.push(obj);
    } else {
      const element = parseGenericElement(child);
      run.otherChildren.push(element);
      run.content.push(element);
    }
  }

  return run;
}

export function parseParagraphElement(node: Element): Paragraph {
  const attributes = { ...getAttributes(node) };

  const paragraph: Paragraph = {
    tag: node.tagName,
    id: parseInt_(attributes["id"] ?? null),
    paraPrIdRef: parseInt_(attributes["paraPrIDRef"] ?? null),
    styleIdRef: parseInt_(attributes["styleIDRef"] ?? null),
    pageBreak: parseBool(attributes["pageBreak"] ?? null),
    columnBreak: parseBool(attributes["columnBreak"] ?? null),
    merged: parseBool(attributes["merged"] ?? null),
    runs: [],
    attributes: (() => {
      const a = { ...attributes };
      delete a["id"];
      delete a["paraPrIDRef"];
      delete a["styleIDRef"];
      delete a["pageBreak"];
      delete a["columnBreak"];
      delete a["merged"];
      return a;
    })(),
    otherChildren: [],
    content: [],
  };

  for (const child of childElements(node)) {
    if (localName(child) === "run") {
      const run = parseRunElement(child);
      paragraph.runs.push(run);
      paragraph.content.push(run);
    } else {
      const element = parseGenericElement(child);
      paragraph.otherChildren.push(element);
      paragraph.content.push(element);
    }
  }

  return paragraph;
}

export function parseSectionElement(node: Element): Section {
  const section: Section = {
    tag: node.tagName,
    attributes: getAttributes(node),
    paragraphs: [],
    otherChildren: [],
  };

  for (const child of childElements(node)) {
    if (localName(child) === "p") {
      section.paragraphs.push(parseParagraphElement(child));
    } else {
      section.otherChildren.push(parseGenericElement(child));
    }
  }

  return section;
}

// -- Serialize helpers --

function genericElementToXml(doc: Document, element: GenericElement): Element {
  const tag = element.tag ?? `{${_DEFAULT_HP_NS}}${element.name}`;
  // Parse namespace from tag like {ns}localName
  let ns: string | null = null;
  let localTag = tag;
  if (tag.startsWith("{")) {
    const idx = tag.indexOf("}");
    if (idx >= 0) {
      ns = tag.substring(1, idx);
      localTag = tag.substring(idx + 1);
    }
  }
  const node = ns ? doc.createElementNS(ns, localTag) : doc.createElement(localTag);
  for (const [key, value] of Object.entries(element.attributes)) {
    node.setAttribute(key, value);
  }
  if (element.text) {
    node.appendChild(doc.createTextNode(element.text));
  }
  for (const child of element.children) {
    node.appendChild(genericElementToXml(doc, child));
  }
  return node;
}

function trackChangeMarkToXml(doc: Document, mark: TrackChangeMark): Element {
  const attrs: Record<string, string> = { ...mark.attributes };
  if (mark.paraEnd != null) attrs["paraend"] = boolToStr(mark.paraEnd);
  if (mark.tcId != null) attrs["TcId"] = String(mark.tcId);
  if (mark.id != null) attrs["Id"] = String(mark.id);
  const tag = mark.tag ?? `{${_DEFAULT_HP_NS}}${mark.name}`;
  let ns: string | null = null;
  let localTag = tag;
  if (tag.startsWith("{")) {
    const idx = tag.indexOf("}");
    if (idx >= 0) {
      ns = tag.substring(1, idx);
      localTag = tag.substring(idx + 1);
    }
  }
  const node = ns ? doc.createElementNS(ns, localTag) : doc.createElement(localTag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  return node;
}

function isTrackChangeMark(mark: InlineMark): mark is TrackChangeMark {
  return "changeType" in mark;
}

function inlineMarkToXml(doc: Document, mark: InlineMark): Element {
  if (isTrackChangeMark(mark)) {
    return trackChangeMarkToXml(doc, mark);
  }
  return genericElementToXml(doc, mark);
}

function textSpanToXml(doc: Document, span: TextSpan): Element {
  const tag = span.tag ?? `{${_DEFAULT_HP_NS}}t`;
  let ns: string | null = null;
  let localTag = tag;
  if (tag.startsWith("{")) {
    const idx = tag.indexOf("}");
    if (idx >= 0) {
      ns = tag.substring(1, idx);
      localTag = tag.substring(idx + 1);
    }
  }
  const node = ns ? doc.createElementNS(ns, localTag) : doc.createElement(localTag);
  for (const [key, value] of Object.entries(span.attributes)) {
    node.setAttribute(key, value);
  }
  if (span.leadingText) {
    node.appendChild(doc.createTextNode(span.leadingText));
  }
  for (const mark of span.marks) {
    const child = inlineMarkToXml(doc, mark.element);
    node.appendChild(child);
    if (mark.trailingText) {
      // Tail text: text node after the child element
      node.appendChild(doc.createTextNode(mark.trailingText));
    }
  }
  return node;
}

function controlToXml(doc: Document, control: Control): Element {
  const attrs: Record<string, string> = { ...control.attributes };
  if (control.controlType != null) attrs["type"] = control.controlType;
  const tag = control.tag ?? `{${_DEFAULT_HP_NS}}ctrl`;
  let ns: string | null = null;
  let localTag = tag;
  if (tag.startsWith("{")) {
    const idx = tag.indexOf("}");
    if (idx >= 0) {
      ns = tag.substring(1, idx);
      localTag = tag.substring(idx + 1);
    }
  }
  const node = ns ? doc.createElementNS(ns, localTag) : doc.createElement(localTag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  for (const child of control.children) {
    node.appendChild(genericElementToXml(doc, child));
  }
  return node;
}

function tableToXml(doc: Document, table: Table): Element {
  const tag = table.tag ?? `{${_DEFAULT_HP_NS}}tbl`;
  let ns: string | null = null;
  let localTag = tag;
  if (tag.startsWith("{")) {
    const idx = tag.indexOf("}");
    if (idx >= 0) {
      ns = tag.substring(1, idx);
      localTag = tag.substring(idx + 1);
    }
  }
  const node = ns ? doc.createElementNS(ns, localTag) : doc.createElement(localTag);
  for (const [key, value] of Object.entries(table.attributes)) {
    node.setAttribute(key, value);
  }
  for (const child of table.children) {
    node.appendChild(genericElementToXml(doc, child));
  }
  return node;
}

function inlineObjectToXml(doc: Document, obj: InlineObject): Element {
  const tag = obj.tag ?? `{${_DEFAULT_HP_NS}}${obj.name}`;
  let ns: string | null = null;
  let localTag = tag;
  if (tag.startsWith("{")) {
    const idx = tag.indexOf("}");
    if (idx >= 0) {
      ns = tag.substring(1, idx);
      localTag = tag.substring(idx + 1);
    }
  }
  const node = ns ? doc.createElementNS(ns, localTag) : doc.createElement(localTag);
  for (const [key, value] of Object.entries(obj.attributes)) {
    node.setAttribute(key, value);
  }
  for (const child of obj.children) {
    node.appendChild(genericElementToXml(doc, child));
  }
  return node;
}

function isTextSpan(child: RunChild): child is TextSpan {
  return "leadingText" in child;
}
function isControl(child: RunChild): child is Control {
  return "controlType" in child;
}
function isTable(child: RunChild): child is Table {
  return !("name" in child) && !("leadingText" in child) && !("controlType" in child) && "children" in child && !("charPrIdRef" in child);
}
function isInlineObject(child: RunChild): child is InlineObject {
  return "name" in child && !("children" in child && "text" in child && "tag" in child && !("changeType" in child)) && "children" in child && "name" in child && !("leadingText" in child);
}

export function serializeRun(doc: Document, run: Run): Element {
  const attrs: Record<string, string> = { ...run.attributes };
  if (run.charPrIdRef != null) attrs["charPrIDRef"] = String(run.charPrIdRef);
  const tag = run.tag ?? `{${_DEFAULT_HP_NS}}run`;
  let ns: string | null = null;
  let localTag = tag;
  if (tag.startsWith("{")) {
    const idx = tag.indexOf("}");
    if (idx >= 0) {
      ns = tag.substring(1, idx);
      localTag = tag.substring(idx + 1);
    }
  }
  const node = ns ? doc.createElementNS(ns, localTag) : doc.createElement(localTag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  for (const child of run.content) {
    if (isTextSpan(child)) {
      node.appendChild(textSpanToXml(doc, child));
    } else if (isControl(child)) {
      node.appendChild(controlToXml(doc, child));
    } else if ("children" in child && !("name" in child) && !("leadingText" in child) && !("controlType" in child)) {
      // Table
      node.appendChild(tableToXml(doc, child as Table));
    } else if ("name" in child && "children" in child && !("text" in child)) {
      // InlineObject
      node.appendChild(inlineObjectToXml(doc, child as InlineObject));
    } else {
      node.appendChild(genericElementToXml(doc, child as GenericElement));
    }
  }
  return node;
}

function isRun(child: ParagraphChild): child is Run {
  return "charPrIdRef" in child;
}

export function serializeParagraph(doc: Document, paragraph: Paragraph): Element {
  const attrs: Record<string, string> = { ...paragraph.attributes };
  if (paragraph.id != null) attrs["id"] = String(paragraph.id);
  if (paragraph.paraPrIdRef != null) attrs["paraPrIDRef"] = String(paragraph.paraPrIdRef);
  if (paragraph.styleIdRef != null) attrs["styleIDRef"] = String(paragraph.styleIdRef);
  if (paragraph.pageBreak != null) attrs["pageBreak"] = boolToStr(paragraph.pageBreak);
  if (paragraph.columnBreak != null) attrs["columnBreak"] = boolToStr(paragraph.columnBreak);
  if (paragraph.merged != null) attrs["merged"] = boolToStr(paragraph.merged);

  const tag = paragraph.tag ?? `{${_DEFAULT_HP_NS}}p`;
  let ns: string | null = null;
  let localTag = tag;
  if (tag.startsWith("{")) {
    const idx = tag.indexOf("}");
    if (idx >= 0) {
      ns = tag.substring(1, idx);
      localTag = tag.substring(idx + 1);
    }
  }
  const node = ns ? doc.createElementNS(ns, localTag) : doc.createElement(localTag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  for (const child of paragraph.content) {
    if (isRun(child)) {
      node.appendChild(serializeRun(doc, child));
    } else {
      node.appendChild(genericElementToXml(doc, child as GenericElement));
    }
  }
  return node;
}
