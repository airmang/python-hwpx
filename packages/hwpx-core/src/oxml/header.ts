/**
 * Header reference list models and parsing.
 * Ported from Python hwpx/oxml/header.py
 */

import { localName as domLocalName, childElements, getAttributes, getTextContent } from "../xml/dom.js";
import { GenericElement, parseGenericElement } from "./common.js";
import { localName, parseInt_, parseBool, textOrNone } from "./utils.js";

// ── Interfaces ──────────────────────────────────────────────────────

export interface BeginNum {
  page: number;
  footnote: number;
  endnote: number;
  pic: number;
  tbl: number;
  equation: number;
}

export interface LinkInfo {
  path: string;
  pageInherit: boolean;
  footnoteInherit: boolean;
}

export interface LicenseMark {
  type: number;
  flag: number;
  lang: number | null;
}

export interface DocOption {
  linkInfo: LinkInfo;
  licenseMark: LicenseMark | null;
}

export interface KeyDerivation {
  algorithm: string | null;
  size: number | null;
  count: number | null;
  salt: string | null; // base64 encoded
}

export interface KeyEncryption {
  derivationKey: KeyDerivation;
  hashValue: string; // base64 encoded
}

export interface TrackChangeConfig {
  flags: number | null;
  encryption: KeyEncryption | null;
}

export interface FontSubstitution {
  face: string;
  type: string;
  isEmbedded: boolean;
  binaryItemIdRef: string | null;
}

export interface FontTypeInfo {
  attributes: Record<string, string>;
}

export interface Font {
  id: number | null;
  face: string;
  type: string | null;
  isEmbedded: boolean;
  binaryItemIdRef: string | null;
  substitution: FontSubstitution | null;
  typeInfo: FontTypeInfo | null;
  otherChildren: Record<string, GenericElement[]>;
}

export interface FontFace {
  lang: string | null;
  fontCnt: number | null;
  fonts: Font[];
  attributes: Record<string, string>;
}

export interface FontFaceList {
  itemCnt: number | null;
  fontfaces: FontFace[];
}

export interface BorderFillList {
  itemCnt: number | null;
  fills: GenericElement[];
}

export interface TabProperties {
  itemCnt: number | null;
  tabs: GenericElement[];
}

export interface NumberingList {
  itemCnt: number | null;
  numberings: GenericElement[];
}

export interface CharProperty {
  id: number | null;
  attributes: Record<string, string>;
  childAttributes: Record<string, Record<string, string>>;
  childElements: Record<string, GenericElement[]>;
}

export interface CharPropertyList {
  itemCnt: number | null;
  properties: CharProperty[];
}

export interface ForbiddenWordList {
  itemCnt: number | null;
  words: string[];
}

export interface MemoShape {
  id: number | null;
  width: number | null;
  lineWidth: string | null;
  lineType: string | null;
  lineColor: string | null;
  fillColor: string | null;
  activeColor: string | null;
  memoType: string | null;
  attributes: Record<string, string>;
}

export function memoShapeMatchesId(shape: MemoShape, memoShapeIdRef: number | string | null): boolean {
  if (memoShapeIdRef == null) return false;
  const candidate = typeof memoShapeIdRef === "string" ? memoShapeIdRef.trim() : String(memoShapeIdRef);
  if (!candidate) return false;
  const rawId = shape.attributes["id"];
  if (rawId != null && candidate === rawId) return true;
  if (shape.id == null) return false;
  try { return Number(candidate) === shape.id; } catch { return false; }
}

export interface MemoProperties {
  itemCnt: number | null;
  memoShapes: MemoShape[];
  attributes: Record<string, string>;
}

export function memoPropertiesShapeById(props: MemoProperties, memoShapeIdRef: number | string | null): MemoShape | null {
  for (const shape of props.memoShapes) {
    if (memoShapeMatchesId(shape, memoShapeIdRef)) return shape;
  }
  return null;
}

export function memoPropertiesAsDict(props: MemoProperties): Record<string, MemoShape> {
  const mapping: Record<string, MemoShape> = {};
  for (const shape of props.memoShapes) {
    const rawId = shape.attributes["id"];
    const keys: string[] = [];
    if (rawId) {
      keys.push(rawId);
      try {
        const normalized = String(Number(rawId));
        if (normalized !== rawId && !keys.includes(normalized)) keys.push(normalized);
      } catch { /* ignore */ }
    } else if (shape.id != null) {
      keys.push(String(shape.id));
    }
    for (const key of keys) {
      if (!(key in mapping)) mapping[key] = shape;
    }
  }
  return mapping;
}

export interface BulletParaHead {
  text: string;
  level: number | null;
  start: number | null;
  align: string | null;
  useInstWidth: boolean | null;
  autoIndent: boolean | null;
  widthAdjust: number | null;
  textOffsetType: string | null;
  textOffset: number | null;
  attributes: Record<string, string>;
}

export interface Bullet {
  id: number | null;
  rawId: string | null;
  char: string;
  checkedChar: string | null;
  useImage: boolean;
  paraHead: BulletParaHead;
  image: GenericElement | null;
  attributes: Record<string, string>;
  otherChildren: Record<string, GenericElement[]>;
}

export function bulletMatchesId(bullet: Bullet, bulletIdRef: number | string | null): boolean {
  if (bulletIdRef == null) return false;
  const candidate = typeof bulletIdRef === "string" ? bulletIdRef.trim() : String(bulletIdRef);
  if (!candidate) return false;
  if (bullet.rawId && candidate === bullet.rawId) return true;
  if (bullet.id == null) return false;
  try { return Number(candidate) === bullet.id; } catch { return false; }
}

export interface BulletList {
  itemCnt: number | null;
  bullets: Bullet[];
}

export function bulletListAsDict(list: BulletList): Record<string, Bullet> {
  const mapping: Record<string, Bullet> = {};
  for (const bullet of list.bullets) {
    const keys: string[] = [];
    if (bullet.rawId) {
      keys.push(bullet.rawId);
      try {
        const normalized = String(Number(bullet.rawId));
        if (normalized !== bullet.rawId && !keys.includes(normalized)) keys.push(normalized);
      } catch { /* ignore */ }
    } else if (bullet.id != null) {
      keys.push(String(bullet.id));
    }
    for (const key of keys) {
      if (!(key in mapping)) mapping[key] = bullet;
    }
  }
  return mapping;
}

export function bulletListBulletById(list: BulletList, bulletIdRef: number | string | null): Bullet | null {
  for (const bullet of list.bullets) {
    if (bulletMatchesId(bullet, bulletIdRef)) return bullet;
  }
  return null;
}

export interface ParagraphAlignment {
  horizontal: string | null;
  vertical: string | null;
  attributes: Record<string, string>;
}

export interface ParagraphHeading {
  type: string | null;
  idRef: number | null;
  level: number | null;
  attributes: Record<string, string>;
}

export interface ParagraphBreakSetting {
  breakLatinWord: string | null;
  breakNonLatinWord: string | null;
  widowOrphan: boolean | null;
  keepWithNext: boolean | null;
  keepLines: boolean | null;
  pageBreakBefore: boolean | null;
  lineWrap: string | null;
  attributes: Record<string, string>;
}

export interface ParagraphMargin {
  intent: string | null;
  left: string | null;
  right: string | null;
  prev: string | null;
  next: string | null;
  otherChildren: Record<string, GenericElement[]>;
}

export interface ParagraphLineSpacing {
  spacingType: string | null;
  value: number | null;
  unit: string | null;
  attributes: Record<string, string>;
}

export interface ParagraphBorder {
  borderFillIdRef: number | null;
  offsetLeft: number | null;
  offsetRight: number | null;
  offsetTop: number | null;
  offsetBottom: number | null;
  connect: boolean | null;
  ignoreMargin: boolean | null;
  attributes: Record<string, string>;
}

export interface ParagraphAutoSpacing {
  eAsianEng: boolean | null;
  eAsianNum: boolean | null;
  attributes: Record<string, string>;
}

export interface ParagraphProperty {
  id: number | null;
  rawId: string | null;
  tabPrIdRef: number | null;
  condense: number | null;
  fontLineHeight: boolean | null;
  snapToGrid: boolean | null;
  suppressLineNumbers: boolean | null;
  checked: boolean | null;
  align: ParagraphAlignment | null;
  heading: ParagraphHeading | null;
  breakSetting: ParagraphBreakSetting | null;
  margin: ParagraphMargin | null;
  lineSpacing: ParagraphLineSpacing | null;
  border: ParagraphBorder | null;
  autoSpacing: ParagraphAutoSpacing | null;
  attributes: Record<string, string>;
  otherChildren: Record<string, GenericElement[]>;
}

export function paragraphPropertyMatchesId(prop: ParagraphProperty, paraPrIdRef: number | string | null): boolean {
  if (paraPrIdRef == null) return false;
  const candidate = typeof paraPrIdRef === "string" ? paraPrIdRef.trim() : String(paraPrIdRef);
  if (!candidate) return false;
  if (prop.rawId && candidate === prop.rawId) return true;
  if (prop.id == null) return false;
  try { return Number(candidate) === prop.id; } catch { return false; }
}

export interface ParagraphPropertyList {
  itemCnt: number | null;
  properties: ParagraphProperty[];
}

export function paragraphPropertyListAsDict(list: ParagraphPropertyList): Record<string, ParagraphProperty> {
  const mapping: Record<string, ParagraphProperty> = {};
  for (const prop of list.properties) {
    const keys: string[] = [];
    if (prop.rawId) {
      keys.push(prop.rawId);
      try {
        const normalized = String(Number(prop.rawId));
        if (normalized !== prop.rawId && !keys.includes(normalized)) keys.push(normalized);
      } catch { /* ignore */ }
    } else if (prop.id != null) {
      keys.push(String(prop.id));
    }
    for (const key of keys) {
      if (!(key in mapping)) mapping[key] = prop;
    }
  }
  return mapping;
}

export function paragraphPropertyListPropertyById(list: ParagraphPropertyList, paraPrIdRef: number | string | null): ParagraphProperty | null {
  for (const prop of list.properties) {
    if (paragraphPropertyMatchesId(prop, paraPrIdRef)) return prop;
  }
  return null;
}

export interface Style {
  id: number | null;
  rawId: string | null;
  type: string | null;
  name: string | null;
  engName: string | null;
  paraPrIdRef: number | null;
  charPrIdRef: number | null;
  nextStyleIdRef: number | null;
  langId: number | null;
  lockForm: boolean | null;
  attributes: Record<string, string>;
}

export function styleMatchesId(style: Style, styleIdRef: number | string | null): boolean {
  if (styleIdRef == null) return false;
  const candidate = typeof styleIdRef === "string" ? styleIdRef.trim() : String(styleIdRef);
  if (!candidate) return false;
  if (style.rawId && candidate === style.rawId) return true;
  if (style.id == null) return false;
  try { return Number(candidate) === style.id; } catch { return false; }
}

export interface StyleList {
  itemCnt: number | null;
  styles: Style[];
}

export function styleListAsDict(list: StyleList): Record<string, Style> {
  const mapping: Record<string, Style> = {};
  for (const style of list.styles) {
    const keys: string[] = [];
    if (style.rawId) {
      keys.push(style.rawId);
      try {
        const normalized = String(Number(style.rawId));
        if (normalized !== style.rawId && !keys.includes(normalized)) keys.push(normalized);
      } catch { /* ignore */ }
    } else if (style.id != null) {
      keys.push(String(style.id));
    }
    for (const key of keys) {
      if (!(key in mapping)) mapping[key] = style;
    }
  }
  return mapping;
}

export function styleListStyleById(list: StyleList, styleIdRef: number | string | null): Style | null {
  for (const style of list.styles) {
    if (styleMatchesId(style, styleIdRef)) return style;
  }
  return null;
}

export interface TrackChange {
  id: number | null;
  rawId: string | null;
  changeType: string | null;
  date: string | null;
  authorId: number | null;
  charShapeId: number | null;
  paraShapeId: number | null;
  hide: boolean | null;
  attributes: Record<string, string>;
}

export function trackChangeMatchesId(change: TrackChange, changeIdRef: number | string | null): boolean {
  if (changeIdRef == null) return false;
  const candidate = typeof changeIdRef === "string" ? changeIdRef.trim() : String(changeIdRef);
  if (!candidate) return false;
  if (change.rawId && candidate === change.rawId) return true;
  if (change.id == null) return false;
  try { return Number(candidate) === change.id; } catch { return false; }
}

export interface TrackChangeList {
  itemCnt: number | null;
  changes: TrackChange[];
}

export function trackChangeListAsDict(list: TrackChangeList): Record<string, TrackChange> {
  const mapping: Record<string, TrackChange> = {};
  for (const change of list.changes) {
    const keys: string[] = [];
    if (change.rawId) {
      keys.push(change.rawId);
      try {
        const normalized = String(Number(change.rawId));
        if (normalized !== change.rawId && !keys.includes(normalized)) keys.push(normalized);
      } catch { /* ignore */ }
    } else if (change.id != null) {
      keys.push(String(change.id));
    }
    for (const key of keys) {
      if (!(key in mapping)) mapping[key] = change;
    }
  }
  return mapping;
}

export function trackChangeListChangeById(list: TrackChangeList, changeIdRef: number | string | null): TrackChange | null {
  for (const change of list.changes) {
    if (trackChangeMatchesId(change, changeIdRef)) return change;
  }
  return null;
}

export interface TrackChangeAuthor {
  id: number | null;
  rawId: string | null;
  name: string | null;
  mark: boolean | null;
  color: string | null;
  attributes: Record<string, string>;
}

export function trackChangeAuthorMatchesId(author: TrackChangeAuthor, authorIdRef: number | string | null): boolean {
  if (authorIdRef == null) return false;
  const candidate = typeof authorIdRef === "string" ? authorIdRef.trim() : String(authorIdRef);
  if (!candidate) return false;
  if (author.rawId && candidate === author.rawId) return true;
  if (author.id == null) return false;
  try { return Number(candidate) === author.id; } catch { return false; }
}

export interface TrackChangeAuthorList {
  itemCnt: number | null;
  authors: TrackChangeAuthor[];
}

export function trackChangeAuthorListAsDict(list: TrackChangeAuthorList): Record<string, TrackChangeAuthor> {
  const mapping: Record<string, TrackChangeAuthor> = {};
  for (const author of list.authors) {
    const keys: string[] = [];
    if (author.rawId) {
      keys.push(author.rawId);
      try {
        const normalized = String(Number(author.rawId));
        if (normalized !== author.rawId && !keys.includes(normalized)) keys.push(normalized);
      } catch { /* ignore */ }
    } else if (author.id != null) {
      keys.push(String(author.id));
    }
    for (const key of keys) {
      if (!(key in mapping)) mapping[key] = author;
    }
  }
  return mapping;
}

export function trackChangeAuthorListAuthorById(list: TrackChangeAuthorList, authorIdRef: number | string | null): TrackChangeAuthor | null {
  for (const author of list.authors) {
    if (trackChangeAuthorMatchesId(author, authorIdRef)) return author;
  }
  return null;
}

export interface RefList {
  fontfaces: FontFaceList | null;
  borderFills: BorderFillList | null;
  charProperties: CharPropertyList | null;
  tabProperties: TabProperties | null;
  numberings: NumberingList | null;
  bullets: BulletList | null;
  paraProperties: ParagraphPropertyList | null;
  styles: StyleList | null;
  memoProperties: MemoProperties | null;
  trackChanges: TrackChangeList | null;
  trackChangeAuthors: TrackChangeAuthorList | null;
  otherCollections: Record<string, GenericElement[]>;
}

export interface Header {
  version: string;
  secCnt: number;
  beginNum: BeginNum | null;
  refList: RefList | null;
  forbiddenWordList: ForbiddenWordList | null;
  compatibleDocument: GenericElement | null;
  docOption: DocOption | null;
  metaTag: string | null;
  trackChangeConfig: TrackChangeConfig | null;
  otherElements: Record<string, GenericElement[]>;
}

// Header lookup helpers
export function headerMemoShape(header: Header, memoShapeIdRef: number | string | null): MemoShape | null {
  if (!header.refList?.memoProperties) return null;
  return memoPropertiesShapeById(header.refList.memoProperties, memoShapeIdRef);
}

export function headerBullet(header: Header, bulletIdRef: number | string | null): Bullet | null {
  if (!header.refList?.bullets) return null;
  return bulletListBulletById(header.refList.bullets, bulletIdRef);
}

export function headerParagraphProperty(header: Header, paraPrIdRef: number | string | null): ParagraphProperty | null {
  if (!header.refList?.paraProperties) return null;
  return paragraphPropertyListPropertyById(header.refList.paraProperties, paraPrIdRef);
}

export function headerStyle(header: Header, styleIdRef: number | string | null): Style | null {
  if (!header.refList?.styles) return null;
  return styleListStyleById(header.refList.styles, styleIdRef);
}

export function headerTrackChange(header: Header, changeIdRef: number | string | null): TrackChange | null {
  if (!header.refList?.trackChanges) return null;
  return trackChangeListChangeById(header.refList.trackChanges, changeIdRef);
}

export function headerTrackChangeAuthor(header: Header, authorIdRef: number | string | null): TrackChangeAuthor | null {
  if (!header.refList?.trackChangeAuthors) return null;
  return trackChangeAuthorListAuthorById(header.refList.trackChangeAuthors, authorIdRef);
}

// ── Parse functions ─────────────────────────────────────────────────

export function parseBeginNum(node: Element): BeginNum {
  return {
    page: parseInt_(node.getAttribute("page"), { allowNone: false })!,
    footnote: parseInt_(node.getAttribute("footnote"), { allowNone: false })!,
    endnote: parseInt_(node.getAttribute("endnote"), { allowNone: false })!,
    pic: parseInt_(node.getAttribute("pic"), { allowNone: false })!,
    tbl: parseInt_(node.getAttribute("tbl"), { allowNone: false })!,
    equation: parseInt_(node.getAttribute("equation"), { allowNone: false })!,
  };
}

function parseLinkInfo(node: Element): LinkInfo {
  return {
    path: node.getAttribute("path") ?? "",
    pageInherit: parseBool(node.getAttribute("pageInherit"), { default: false }) ?? false,
    footnoteInherit: parseBool(node.getAttribute("footnoteInherit"), { default: false }) ?? false,
  };
}

function parseLicenseMark(node: Element): LicenseMark {
  return {
    type: parseInt_(node.getAttribute("type"), { allowNone: false })!,
    flag: parseInt_(node.getAttribute("flag"), { allowNone: false })!,
    lang: parseInt_(node.getAttribute("lang")),
  };
}

export function parseDocOption(node: Element): DocOption {
  let linkInfo: LinkInfo | null = null;
  let licenseMark: LicenseMark | null = null;

  for (const child of childElements(node)) {
    const name = localName(child);
    if (name === "linkinfo") linkInfo = parseLinkInfo(child);
    else if (name === "licensemark") licenseMark = parseLicenseMark(child);
  }

  if (linkInfo == null) throw new Error("docOption element is missing required linkinfo child");
  return { linkInfo, licenseMark };
}

function parseKeyEncryption(node: Element): KeyEncryption | null {
  let derivationNode: Element | null = null;
  let hashNode: Element | null = null;
  for (const child of childElements(node)) {
    const name = localName(child);
    if (name === "derivationKey") derivationNode = child;
    else if (name === "hash") hashNode = child;
  }
  if (!derivationNode || !hashNode) return null;

  const derivation: KeyDerivation = {
    algorithm: derivationNode.getAttribute("algorithm"),
    size: parseInt_(derivationNode.getAttribute("size")),
    count: parseInt_(derivationNode.getAttribute("count")),
    salt: derivationNode.getAttribute("salt"),
  };
  const hashText = textOrNone(hashNode) ?? "";
  return { derivationKey: derivation, hashValue: hashText };
}

function parseTrackChangeConfig(node: Element): TrackChangeConfig {
  let encryption: KeyEncryption | null = null;
  for (const child of childElements(node)) {
    if (localName(child) === "trackChangeEncrpytion") {
      encryption = parseKeyEncryption(child);
      break;
    }
  }
  return { flags: parseInt_(node.getAttribute("flags")), encryption };
}

function parseFontSubstitution(node: Element): FontSubstitution {
  return {
    face: node.getAttribute("face") ?? "",
    type: node.getAttribute("type") ?? "",
    isEmbedded: parseBool(node.getAttribute("isEmbedded"), { default: false }) ?? false,
    binaryItemIdRef: node.getAttribute("binaryItemIDRef"),
  };
}

function parseFontTypeInfo(node: Element): FontTypeInfo {
  return { attributes: getAttributes(node) };
}

function parseFont(node: Element): Font {
  let substitution: FontSubstitution | null = null;
  let typeInfo: FontTypeInfo | null = null;
  const otherChildren: Record<string, GenericElement[]> = {};

  for (const child of childElements(node)) {
    const name = localName(child);
    if (name === "substFont") substitution = parseFontSubstitution(child);
    else if (name === "typeInfo") typeInfo = parseFontTypeInfo(child);
    else {
      if (!otherChildren[name]) otherChildren[name] = [];
      otherChildren[name].push(parseGenericElement(child));
    }
  }

  return {
    id: parseInt_(node.getAttribute("id")),
    face: node.getAttribute("face") ?? "",
    type: node.getAttribute("type"),
    isEmbedded: parseBool(node.getAttribute("isEmbedded"), { default: false }) ?? false,
    binaryItemIdRef: node.getAttribute("binaryItemIDRef"),
    substitution,
    typeInfo,
    otherChildren,
  };
}

function parseFontFace(node: Element): FontFace {
  const fonts = childElements(node).filter((c) => localName(c) === "font").map(parseFont);
  return {
    lang: node.getAttribute("lang"),
    fontCnt: parseInt_(node.getAttribute("fontCnt")),
    fonts,
    attributes: getAttributes(node),
  };
}

function parseFontFaces(node: Element): FontFaceList {
  const fontfaces = childElements(node).filter((c) => localName(c) === "fontface").map(parseFontFace);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), fontfaces };
}

export function parseBorderFills(node: Element): BorderFillList {
  const fills = childElements(node).filter((c) => localName(c) === "borderFill").map(parseGenericElement);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), fills };
}

function parseCharProperty(node: Element): CharProperty {
  const childAttrs: Record<string, Record<string, string>> = {};
  const childElems: Record<string, GenericElement[]> = {};
  for (const child of childElements(node)) {
    const children = childElements(child);
    const text = getTextContent(child);
    if (children.length === 0 && (text == null || !text.trim())) {
      childAttrs[localName(child)] = getAttributes(child);
    } else {
      const name = localName(child);
      if (!childElems[name]) childElems[name] = [];
      childElems[name].push(parseGenericElement(child));
    }
  }
  const allAttrs = getAttributes(node);
  const id = parseInt_(allAttrs["id"]);
  const { id: _id, ...attributes } = allAttrs;
  return { id, attributes, childAttributes: childAttrs, childElements: childElems };
}

function parseCharProperties(node: Element): CharPropertyList {
  const properties = childElements(node).filter((c) => localName(c) === "charPr").map(parseCharProperty);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), properties };
}

function parseTabProperties(node: Element): TabProperties {
  const tabs = childElements(node).filter((c) => localName(c) === "tabPr").map(parseGenericElement);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), tabs };
}

function parseNumberings(node: Element): NumberingList {
  const numberings = childElements(node).filter((c) => localName(c) === "numbering").map(parseGenericElement);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), numberings };
}

function parseForbiddenWordList(node: Element): ForbiddenWordList {
  const words = childElements(node)
    .filter((c) => localName(c) === "forbiddenWord")
    .map((c) => textOrNone(c) ?? "");
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), words };
}

export function memoShapeFromAttributes(attrs: Record<string, string>): MemoShape {
  return {
    id: parseInt_(attrs["id"] ?? null),
    width: parseInt_(attrs["width"] ?? null),
    lineWidth: attrs["lineWidth"] ?? null,
    lineType: attrs["lineType"] ?? null,
    lineColor: attrs["lineColor"] ?? null,
    fillColor: attrs["fillColor"] ?? null,
    activeColor: attrs["activeColor"] ?? null,
    memoType: attrs["memoType"] ?? null,
    attributes: { ...attrs },
  };
}

export function parseMemoShape(node: Element): MemoShape {
  return memoShapeFromAttributes(getAttributes(node));
}

export function parseMemoProperties(node: Element): MemoProperties {
  const memoShapes = childElements(node).filter((c) => localName(c) === "memoPr").map(parseMemoShape);
  const allAttrs = getAttributes(node);
  const { itemCnt: _itemCnt, ...attributes } = allAttrs;
  return {
    itemCnt: parseInt_(node.getAttribute("itemCnt")),
    memoShapes,
    attributes,
  };
}

export function parseBulletParaHead(node: Element): BulletParaHead {
  return {
    text: textOrNone(node) ?? "",
    level: parseInt_(node.getAttribute("level")),
    start: parseInt_(node.getAttribute("start")),
    align: node.getAttribute("align"),
    useInstWidth: parseBool(node.getAttribute("useInstWidth")),
    autoIndent: parseBool(node.getAttribute("autoIndent")),
    widthAdjust: parseInt_(node.getAttribute("widthAdjust")),
    textOffsetType: node.getAttribute("textOffsetType"),
    textOffset: parseInt_(node.getAttribute("textOffset")),
    attributes: getAttributes(node),
  };
}

export function parseBullet(node: Element): Bullet {
  let image: GenericElement | null = null;
  let paraHead: BulletParaHead | null = null;
  const otherChildren: Record<string, GenericElement[]> = {};

  for (const child of childElements(node)) {
    const name = localName(child);
    if (name === "img") image = parseGenericElement(child);
    else if (name === "paraHead") paraHead = parseBulletParaHead(child);
    else {
      if (!otherChildren[name]) otherChildren[name] = [];
      otherChildren[name].push(parseGenericElement(child));
    }
  }

  if (paraHead == null) throw new Error("bullet element missing required paraHead child");

  return {
    id: parseInt_(node.getAttribute("id")),
    rawId: node.getAttribute("id"),
    char: node.getAttribute("char") ?? "",
    checkedChar: node.getAttribute("checkedChar"),
    useImage: parseBool(node.getAttribute("useImage"), { default: false }) ?? false,
    paraHead,
    image,
    attributes: getAttributes(node),
    otherChildren,
  };
}

export function parseBullets(node: Element): BulletList {
  const bullets = childElements(node).filter((c) => localName(c) === "bullet").map(parseBullet);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), bullets };
}

export function parseParagraphAlignment(node: Element): ParagraphAlignment {
  return {
    horizontal: node.getAttribute("horizontal"),
    vertical: node.getAttribute("vertical"),
    attributes: getAttributes(node),
  };
}

function parseParagraphHeading(node: Element): ParagraphHeading {
  return {
    type: node.getAttribute("type"),
    idRef: parseInt_(node.getAttribute("idRef")),
    level: parseInt_(node.getAttribute("level")),
    attributes: getAttributes(node),
  };
}

export function parseParagraphBreakSetting(node: Element): ParagraphBreakSetting {
  return {
    breakLatinWord: node.getAttribute("breakLatinWord"),
    breakNonLatinWord: node.getAttribute("breakNonLatinWord"),
    widowOrphan: parseBool(node.getAttribute("widowOrphan")),
    keepWithNext: parseBool(node.getAttribute("keepWithNext")),
    keepLines: parseBool(node.getAttribute("keepLines")),
    pageBreakBefore: parseBool(node.getAttribute("pageBreakBefore")),
    lineWrap: node.getAttribute("lineWrap"),
    attributes: getAttributes(node),
  };
}

export function parseParagraphMargin(node: Element): ParagraphMargin {
  const values: Record<string, string | null> = {
    intent: null, left: null, right: null, prev: null, next: null,
  };
  const otherChildren: Record<string, GenericElement[]> = {};

  for (const child of childElements(node)) {
    const name = localName(child);
    if (name in values) {
      values[name] = textOrNone(child);
    } else {
      if (!otherChildren[name]) otherChildren[name] = [];
      otherChildren[name].push(parseGenericElement(child));
    }
  }

  return {
    intent: values["intent"] ?? null,
    left: values["left"] ?? null,
    right: values["right"] ?? null,
    prev: values["prev"] ?? null,
    next: values["next"] ?? null,
    otherChildren,
  };
}

export function parseParagraphLineSpacing(node: Element): ParagraphLineSpacing {
  return {
    spacingType: node.getAttribute("type"),
    value: parseInt_(node.getAttribute("value")),
    unit: node.getAttribute("unit"),
    attributes: getAttributes(node),
  };
}

export function parseParagraphBorder(node: Element): ParagraphBorder {
  return {
    borderFillIdRef: parseInt_(node.getAttribute("borderFillIDRef")),
    offsetLeft: parseInt_(node.getAttribute("offsetLeft")),
    offsetRight: parseInt_(node.getAttribute("offsetRight")),
    offsetTop: parseInt_(node.getAttribute("offsetTop")),
    offsetBottom: parseInt_(node.getAttribute("offsetBottom")),
    connect: parseBool(node.getAttribute("connect")),
    ignoreMargin: parseBool(node.getAttribute("ignoreMargin")),
    attributes: getAttributes(node),
  };
}

export function parseParagraphAutoSpacing(node: Element): ParagraphAutoSpacing {
  return {
    eAsianEng: parseBool(node.getAttribute("eAsianEng")),
    eAsianNum: parseBool(node.getAttribute("eAsianNum")),
    attributes: getAttributes(node),
  };
}

export function parseParagraphProperty(node: Element): ParagraphProperty {
  let align: ParagraphAlignment | null = null;
  let heading: ParagraphHeading | null = null;
  let breakSetting: ParagraphBreakSetting | null = null;
  let margin: ParagraphMargin | null = null;
  let lineSpacing: ParagraphLineSpacing | null = null;
  let border: ParagraphBorder | null = null;
  let autoSpacing: ParagraphAutoSpacing | null = null;
  const otherChildren: Record<string, GenericElement[]> = {};

  for (const child of childElements(node)) {
    const name = localName(child);
    if (name === "align") align = parseParagraphAlignment(child);
    else if (name === "heading") heading = parseParagraphHeading(child);
    else if (name === "breakSetting") breakSetting = parseParagraphBreakSetting(child);
    else if (name === "margin") margin = parseParagraphMargin(child);
    else if (name === "lineSpacing") lineSpacing = parseParagraphLineSpacing(child);
    else if (name === "border") border = parseParagraphBorder(child);
    else if (name === "autoSpacing") autoSpacing = parseParagraphAutoSpacing(child);
    else {
      if (!otherChildren[name]) otherChildren[name] = [];
      otherChildren[name].push(parseGenericElement(child));
    }
  }

  const knownAttrs = new Set(["id", "tabPrIDRef", "condense", "fontLineHeight", "snapToGrid", "suppressLineNumbers", "checked"]);
  const allAttrs = getAttributes(node);
  const attributes: Record<string, string> = {};
  for (const [key, value] of Object.entries(allAttrs)) {
    if (!knownAttrs.has(key)) attributes[key] = value;
  }

  return {
    id: parseInt_(node.getAttribute("id")),
    rawId: node.getAttribute("id"),
    tabPrIdRef: parseInt_(node.getAttribute("tabPrIDRef")),
    condense: parseInt_(node.getAttribute("condense")),
    fontLineHeight: parseBool(node.getAttribute("fontLineHeight")),
    snapToGrid: parseBool(node.getAttribute("snapToGrid")),
    suppressLineNumbers: parseBool(node.getAttribute("suppressLineNumbers")),
    checked: parseBool(node.getAttribute("checked")),
    align, heading, breakSetting, margin, lineSpacing, border, autoSpacing,
    attributes, otherChildren,
  };
}

export function parseParagraphProperties(node: Element): ParagraphPropertyList {
  const properties = childElements(node).filter((c) => localName(c) === "paraPr").map(parseParagraphProperty);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), properties };
}

export function parseStyle(node: Element): Style {
  const knownAttrs = new Set(["id", "type", "name", "engName", "paraPrIDRef", "charPrIDRef", "nextStyleIDRef", "langID", "lockForm"]);
  const allAttrs = getAttributes(node);
  const attributes: Record<string, string> = {};
  for (const [key, value] of Object.entries(allAttrs)) {
    if (!knownAttrs.has(key)) attributes[key] = value;
  }

  return {
    id: parseInt_(node.getAttribute("id")),
    rawId: node.getAttribute("id"),
    type: node.getAttribute("type"),
    name: node.getAttribute("name"),
    engName: node.getAttribute("engName"),
    paraPrIdRef: parseInt_(node.getAttribute("paraPrIDRef")),
    charPrIdRef: parseInt_(node.getAttribute("charPrIDRef")),
    nextStyleIdRef: parseInt_(node.getAttribute("nextStyleIDRef")),
    langId: parseInt_(node.getAttribute("langID")),
    lockForm: parseBool(node.getAttribute("lockForm")),
    attributes,
  };
}

export function parseStyles(node: Element): StyleList {
  const styles = childElements(node).filter((c) => localName(c) === "style").map(parseStyle);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), styles };
}

export function parseTrackChange(node: Element): TrackChange {
  const knownAttrs = new Set(["id", "type", "date", "authorID", "charShapeID", "paraShapeID", "hide"]);
  const allAttrs = getAttributes(node);
  const attributes: Record<string, string> = {};
  for (const [key, value] of Object.entries(allAttrs)) {
    if (!knownAttrs.has(key)) attributes[key] = value;
  }

  return {
    id: parseInt_(node.getAttribute("id")),
    rawId: node.getAttribute("id"),
    changeType: node.getAttribute("type"),
    date: node.getAttribute("date"),
    authorId: parseInt_(node.getAttribute("authorID")),
    charShapeId: parseInt_(node.getAttribute("charShapeID")),
    paraShapeId: parseInt_(node.getAttribute("paraShapeID")),
    hide: parseBool(node.getAttribute("hide")),
    attributes,
  };
}

export function parseTrackChanges(node: Element): TrackChangeList {
  const changes = childElements(node).filter((c) => localName(c) === "trackChange").map(parseTrackChange);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), changes };
}

export function parseTrackChangeAuthor(node: Element): TrackChangeAuthor {
  const knownAttrs = new Set(["id", "name", "mark", "color"]);
  const allAttrs = getAttributes(node);
  const attributes: Record<string, string> = {};
  for (const [key, value] of Object.entries(allAttrs)) {
    if (!knownAttrs.has(key)) attributes[key] = value;
  }

  return {
    id: parseInt_(node.getAttribute("id")),
    rawId: node.getAttribute("id"),
    name: node.getAttribute("name"),
    mark: parseBool(node.getAttribute("mark")),
    color: node.getAttribute("color"),
    attributes,
  };
}

export function parseTrackChangeAuthors(node: Element): TrackChangeAuthorList {
  const authors = childElements(node).filter((c) => localName(c) === "trackChangeAuthor").map(parseTrackChangeAuthor);
  return { itemCnt: parseInt_(node.getAttribute("itemCnt")), authors };
}

export function parseRefList(node: Element): RefList {
  const refList: RefList = {
    fontfaces: null, borderFills: null, charProperties: null,
    tabProperties: null, numberings: null, bullets: null,
    paraProperties: null, styles: null, memoProperties: null,
    trackChanges: null, trackChangeAuthors: null,
    otherCollections: {},
  };

  for (const child of childElements(node)) {
    const name = localName(child);
    if (name === "fontfaces") refList.fontfaces = parseFontFaces(child);
    else if (name === "borderFills") refList.borderFills = parseBorderFills(child);
    else if (name === "charProperties") refList.charProperties = parseCharProperties(child);
    else if (name === "tabProperties") refList.tabProperties = parseTabProperties(child);
    else if (name === "numberings") refList.numberings = parseNumberings(child);
    else if (name === "bullets") refList.bullets = parseBullets(child);
    else if (name === "paraProperties") refList.paraProperties = parseParagraphProperties(child);
    else if (name === "styles") refList.styles = parseStyles(child);
    else if (name === "memoProperties") refList.memoProperties = parseMemoProperties(child);
    else if (name === "trackChanges") refList.trackChanges = parseTrackChanges(child);
    else if (name === "trackChangeAuthors") refList.trackChangeAuthors = parseTrackChangeAuthors(child);
    else {
      if (!refList.otherCollections[name]) refList.otherCollections[name] = [];
      refList.otherCollections[name].push(parseGenericElement(child));
    }
  }

  return refList;
}

export function parseHeaderElement(node: Element): Header {
  const version = node.getAttribute("version");
  if (version == null) throw new Error("Header element is missing required version attribute");
  const secCnt = parseInt_(node.getAttribute("secCnt"), { allowNone: false })!;

  const header: Header = {
    version,
    secCnt,
    beginNum: null,
    refList: null,
    forbiddenWordList: null,
    compatibleDocument: null,
    docOption: null,
    metaTag: null,
    trackChangeConfig: null,
    otherElements: {},
  };

  for (const child of childElements(node)) {
    const name = localName(child);
    if (name === "beginNum") header.beginNum = parseBeginNum(child);
    else if (name === "refList") header.refList = parseRefList(child);
    else if (name === "forbiddenWordList") header.forbiddenWordList = parseForbiddenWordList(child);
    else if (name === "compatibleDocument") header.compatibleDocument = parseGenericElement(child);
    else if (name === "docOption") header.docOption = parseDocOption(child);
    else if (name === "metaTag") header.metaTag = textOrNone(child);
    else if (name === "trackchangeConfig") header.trackChangeConfig = parseTrackChangeConfig(child);
    else {
      if (!header.otherElements[name]) header.otherElements[name] = [];
      header.otherElements[name].push(parseGenericElement(child));
    }
  }

  return header;
}
