/**
 * EditorViewModel — pure data structures derived from HwpxDocument for rendering.
 */

import type {
  HwpxDocument,
  RunStyle,
  HwpxTableGridPosition,
} from "@ubermensch1218/hwpxcore";
import { parseHeaderXml, serializeXml } from "@ubermensch1218/hwpxcore";
import type { Header, ParagraphProperty } from "@ubermensch1218/hwpxcore";
import { hwpToPx } from "./hwp-units";
import { extractImages } from "./image-extractor";

// ── ViewModel types ────────────────────────────────────────────────────────

export interface RunVM {
  text: string;
  bold: boolean;
  italic: boolean;
  underline: boolean;
  strikethrough: boolean;
  color: string | null;
  fontFamily: string | null;
  fontSize: number | null;
  highlightColor: string | null;
  letterSpacing: number | null;
  charPrIdRef: string | null;
  hasTab?: boolean; // true if this run contains a tab character
  hasFwSpace?: boolean; // true if this run is a full-width space
  hasLineBreak?: boolean; // true if this run is a line break
  hyperlink?: string; // URL if this run is inside a hyperlink
}

export interface MarginVM {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export interface CellBorderStyleVM {
  type: string;
  width: string;
  color: string;
}

export interface CellStyleVM {
  borderLeft: CellBorderStyleVM | null;
  borderRight: CellBorderStyleVM | null;
  borderTop: CellBorderStyleVM | null;
  borderBottom: CellBorderStyleVM | null;
  backgroundColor: string | null;
}

export interface TableCellVM {
  row: number;
  col: number;
  rowSpan: number;
  colSpan: number;
  widthPx: number;
  heightPx: number;
  text: string;
  isAnchor: boolean; // true if this is the top-left of a merged region
  borderFillIDRef: string | null;
  vertAlign: string;  // "TOP" | "CENTER" | "BOTTOM"
  style: CellStyleVM | null;
  fontFamily: string | null;
  fontSize: number | null;
  textColor: string | null;
  bold: boolean;
  italic: boolean;
  underline: boolean;
  strikethrough: boolean;
}

export interface TableVM {
  rowCount: number;
  colCount: number;
  cells: TableCellVM[][]; // 2D grid [row][col], non-anchor cells have isAnchor=false
  tableIndex: number; // index within the paragraph
  pageBreak: string; // "CELL", "NONE", etc.
  repeatHeader: boolean;
  widthHwp: number;
  heightHwp: number;
  outMargin: MarginVM; // table outer margin in hwpUnits
  inMargin: MarginVM; // table inner cell margin in hwpUnits
  columnWidths: number[]; // per-column width in hwpUnits
  borderFillIDRef: string | null;
}

export interface ImageVM {
  dataUrl: string;
  widthPx: number;
  heightPx: number;
  widthHwp: number;
  heightHwp: number;
  originalWidthHwp: number;
  originalHeightHwp: number;
  scaleXPercent: number;
  scaleYPercent: number;
  binaryItemIdRef: string;
  outMargin: MarginVM;
  textWrap: string;
  treatAsChar: boolean;
  horzRelTo: string;
  vertRelTo: string;
  horzOffset: number;
  vertOffset: number;
  cropLeftHwp: number;
  cropRightHwp: number;
  cropTopHwp: number;
  cropBottomHwp: number;
  sizeProtected: boolean;
  locked: boolean;
  rotationAngle: number;
  brightness: number;
  contrast: number;
  effect: string;
  alpha: number;
}

export interface EquationVM {
  script: string; // HWP equation script
  widthPx: number;
  heightPx: number;
  textColor: string;
  font: string;
  baseLine: number;
}

export interface TextBoxVM {
  text: string;
  widthPx: number;
  heightPx: number;
  widthHwp: number;
  heightHwp: number;
  x: number;
  y: number;
  borderColor: string;
  fillColor: string;
  textBoxIndex: number;
}

export interface ParagraphVM {
  runs: RunVM[];
  tables: TableVM[];
  images: ImageVM[];
  textBoxes: TextBoxVM[];
  equations: EquationVM[];
  alignment: string;
  lineSpacing: number;
  spacingBefore: number;
  spacingAfter: number;
  firstLineIndent: number;
  marginLeftPx: number;
  marginRightPx: number;
  paragraphIndex: number; // global index across all sections
  defaultFontSize: number | null;
  defaultFontFamily: string | null;
}

export interface FootnoteVM {
  marker: string; // e.g. "1", "2", ...
  text: string;
}

export interface ColumnLayoutVM {
  colCount: number;
  sameGap: number; // gap in px
  type: string; // "NEWSPAPER", "BALANCED", etc.
}

export interface PageNumVM {
  pos: string; // "BOTTOM_CENTER", "TOP_CENTER", etc.
  formatType: string; // "DIGIT", "ROMAN", etc.
  sideChar: string; // e.g. "-" for "- 1 -"
}

export interface PageBorderFillVM {
  type: string; // "BOTH", "EVEN", "ODD"
  borderFillIdRef: string;
  textBorder: string; // "PAPER", "CONTENT"
  fillArea: string; // "PAPER", "CONTENT"
}

export interface SectionVM {
  pageWidthPx: number;
  pageHeightPx: number;
  marginTopPx: number;
  marginBottomPx: number;
  marginLeftPx: number;
  marginRightPx: number;
  headerHeightPx: number;
  footerHeightPx: number;
  paragraphs: ParagraphVM[];
  sectionIndex: number;
  startPageNumber: number;
  headerText: string;
  footerText: string;
  headerAlign: string;
  footerAlign: string;
  footnotes: FootnoteVM[];
  endnotes: FootnoteVM[];
  columnLayout: ColumnLayoutVM;
  pageNum: PageNumVM | null;
  pageBorderFill: PageBorderFillVM | null;
}

export interface EditorViewModel {
  sections: SectionVM[];
  watermarkText: string;
}

// ── Builder ────────────────────────────────────────────────────────────────

function extractRunStyle(
  style: RunStyle | null,
  doc?: HwpxDocument | null,
): {
  bold: boolean;
  italic: boolean;
  underline: boolean;
  strikethrough: boolean;
  color: string | null;
  fontFamily: string | null;
  fontSize: number | null;
  highlightColor: string | null;
  letterSpacing: number | null;
} {
  if (!style) {
    return {
      bold: false,
      italic: false,
      underline: false,
      strikethrough: false,
      color: null,
      fontFamily: null,
      fontSize: null,
      highlightColor: null,
      letterSpacing: null,
    };
  }

  const normalizeFlag = (value?: string | null): boolean =>
    value === "1" || value?.toLowerCase() === "true";

  // HWPX charPr often stores bold/italic as child tags (<hh:bold />, <hh:italic />).
  const bold =
    normalizeFlag(style.attributes["bold"]) ||
    style.childAttributes["bold"] != null;
  const italic =
    normalizeFlag(style.attributes["italic"]) ||
    style.childAttributes["italic"] != null;

  // Check underline child element
  const underlineChild = style.childAttributes["underline"];
  const underline =
    underlineChild != null &&
    ((underlineChild["type"] == null) ||
      underlineChild["type"].toUpperCase() !== "NONE");

  // Strikethrough
  const strikeChild = style.childAttributes["strikeout"];
  const strikeType = strikeChild?.["type"] ?? strikeChild?.["shape"] ?? null;
  const strikethrough =
    strikeType != null &&
    strikeType.toUpperCase() !== "NONE";

  const color = style.attributes["textColor"] ?? null;

  // Highlight
  const highlightColor = style.attributes["shadeColor"] ?? null;

  // Font family — resolve numeric ID to face name
  let fontFamily: string | null = null;
  const fontRef = style.childAttributes["fontRef"];
  if (fontRef) {
    const hangulId = fontRef["hangul"] ?? fontRef["latin"] ?? null;
    if (hangulId != null && doc) {
      fontFamily = doc.fontFaceName(hangulId) ?? hangulId;
    } else {
      fontFamily = hangulId;
    }
  }

  // Font size (height in hwpUnits / 100 = pt)
  let fontSize: number | null = null;
  const sizeStr = style.attributes["height"];
  if (sizeStr) {
    const hwpVal = parseInt(sizeStr, 10);
    if (!isNaN(hwpVal)) fontSize = hwpVal / 100;
  }

  // Letter spacing
  let letterSpacing: number | null = null;
  const spacingStr = style.attributes["spacing"];
  if (spacingStr) {
    const val = parseInt(spacingStr, 10);
    if (!isNaN(val) && val !== 0) letterSpacing = val;
  }

  return { bold, italic, underline, strikethrough, color, fontFamily, fontSize, highlightColor, letterSpacing };
}

function extractCellTextStyle(cellElement: Element, doc: HwpxDocument) {
  const stack: Element[] = [cellElement];
  let paragraphCharPrIdRef: string | null = null;
  const readCharPrRef = (el: Element): string | null =>
    el.getAttribute("charPrIDRef")
    ?? el.getAttribute("charPrIdRef")
    ?? el.getAttribute("charPrRef");
  while (stack.length > 0) {
    const current = stack.shift()!;
    const local = current.localName ?? current.nodeName.split(":").pop() ?? "";
    if (local === "p" && paragraphCharPrIdRef == null) {
      paragraphCharPrIdRef = readCharPrRef(current);
    }
    if (local === "run") {
      const charPrIdRef = readCharPrRef(current);
      const style = doc.charProperty(charPrIdRef ?? paragraphCharPrIdRef);
      return extractRunStyle(style, doc);
    }
    for (const child of Array.from(current.childNodes)) {
      if (child.nodeType === 1) stack.push(child as Element);
    }
  }
  if (paragraphCharPrIdRef) {
    return extractRunStyle(doc.charProperty(paragraphCharPrIdRef), doc);
  }
  return extractRunStyle(null, doc);
}

/** Find equation elements inside a run. */
function findEquationRefs(
  runElement: Element,
): { script: string; width: number; height: number; textColor: string; font: string; baseLine: number }[] {
  const results: { script: string; width: number; height: number; textColor: string; font: string; baseLine: number }[] = [];

  const children = runElement.childNodes;
  for (let i = 0; i < children.length; i++) {
    const child = children.item(i);
    if (!child || child.nodeType !== 1) continue;
    const el = child as Element;
    const localName = el.localName || el.nodeName.split(":").pop() || "";
    if (localName !== "equation") continue;

    let width = 0;
    let height = 0;
    let script = "";
    const textColor = el.getAttribute("textColor") ?? "#000000";
    const font = el.getAttribute("font") ?? "HancomEQN";
    const baseLine = parseInt(el.getAttribute("baseLine") ?? "85", 10);

    const eqChildren = el.childNodes;
    for (let j = 0; j < eqChildren.length; j++) {
      const ec = eqChildren.item(j);
      if (!ec || ec.nodeType !== 1) continue;
      const eel = ec as Element;
      const eName = eel.localName || eel.nodeName.split(":").pop() || "";

      if (eName === "sz") {
        width = parseInt(eel.getAttribute("width") ?? "0", 10);
        height = parseInt(eel.getAttribute("height") ?? "0", 10);
      } else if (eName === "script") {
        script = eel.textContent ?? "";
      }
    }

    results.push({ script, width, height, textColor, font, baseLine });
  }

  return results;
}

/** Find drawText (text box) elements inside a run. */
function findTextBoxRefs(
  runElement: Element,
): { text: string; width: number; height: number; x: number; y: number; borderColor: string; fillColor: string }[] {
  const results: { text: string; width: number; height: number; x: number; y: number; borderColor: string; fillColor: string }[] = [];

  const children = runElement.childNodes;
  for (let i = 0; i < children.length; i++) {
    const child = children.item(i);
    if (!child || child.nodeType !== 1) continue;
    const el = child as Element;
    const localName = el.localName || el.nodeName.split(":").pop() || "";
    if (localName !== "drawText") continue;

    let width = 0;
    let height = 0;
    let x = 0;
    let y = 0;
    let borderColor = "#000000";
    let fillColor = "#FFFFFF";
    let text = "";

    const boxChildren = el.childNodes;
    for (let j = 0; j < boxChildren.length; j++) {
      const bc = boxChildren.item(j);
      if (!bc || bc.nodeType !== 1) continue;
      const bel = bc as Element;
      const bName = bel.localName || bel.nodeName.split(":").pop() || "";

      if (bName === "sz") {
        width = parseInt(bel.getAttribute("width") ?? "0", 10);
        height = parseInt(bel.getAttribute("height") ?? "0", 10);
      } else if (bName === "pos") {
        x = parseInt(bel.getAttribute("horzOffset") ?? "0", 10);
        y = parseInt(bel.getAttribute("vertOffset") ?? "0", 10);
      } else if (bName === "lineShape") {
        borderColor = bel.getAttribute("color") ?? "#000000";
      }
    }

    // Get fill color from fillBrush/winBrush
    const fillBrushes = el.getElementsByTagName("*");
    for (let k = 0; k < fillBrushes.length; k++) {
      const fb = fillBrushes.item(k);
      if (!fb) continue;
      const fbName = fb.localName || fb.nodeName.split(":").pop() || "";
      if (fbName === "winBrush") {
        fillColor = fb.getAttribute("faceColor") ?? "#FFFFFF";
      }
    }

    // Get text from sub-paragraphs
    const textEls = el.getElementsByTagName("*");
    for (let k = 0; k < textEls.length; k++) {
      const te = textEls.item(k);
      if (!te) continue;
      const teName = te.localName || te.nodeName.split(":").pop() || "";
      if (teName === "t") {
        text += te.textContent ?? "";
      }
    }

    results.push({ text, width, height, x, y, borderColor, fillColor });
  }

  return results;
}

/** Find binaryItemIDRef from a picture element inside a run. */
function findPictureRefs(
  runElement: Element,
): {
  binaryItemIdRef: string;
  width: number;
  height: number;
  originalWidth: number;
  originalHeight: number;
  textWrap: string;
  treatAsChar: boolean;
  horzRelTo: string;
  vertRelTo: string;
  horzOffset: number;
  vertOffset: number;
  clipLeft: number;
  clipRight: number;
  clipTop: number;
  clipBottom: number;
  sizeProtected: boolean;
  locked: boolean;
  rotationAngle: number;
  brightness: number;
  contrast: number;
  effect: string;
  alpha: number;
}[] {
  const results: {
    binaryItemIdRef: string;
    width: number;
    height: number;
    originalWidth: number;
    originalHeight: number;
    textWrap: string;
    treatAsChar: boolean;
    horzRelTo: string;
    vertRelTo: string;
    horzOffset: number;
    vertOffset: number;
    clipLeft: number;
    clipRight: number;
    clipTop: number;
    clipBottom: number;
    sizeProtected: boolean;
    locked: boolean;
    rotationAngle: number;
    brightness: number;
    contrast: number;
    effect: string;
    alpha: number;
  }[] = [];

  // Look for <pic> elements inside the run
  const children = runElement.childNodes;
  for (let i = 0; i < children.length; i++) {
    const child = children.item(i);
    if (!child || child.nodeType !== 1) continue;
    const el = child as Element;
    const localName = el.localName || el.nodeName.split(":").pop() || "";
    if (localName !== "pic") continue;

    // Get size from curSz
    let width = 0;
    let height = 0;
    let originalWidth = 0;
    let originalHeight = 0;
    const textWrap = el.getAttribute("textWrap") ?? "TOP_AND_BOTTOM";
    const locked = (el.getAttribute("lock") ?? "0") === "1";
    let treatAsChar = true;
    let horzRelTo = "COLUMN";
    let vertRelTo = "PARA";
    let horzOffset = 0;
    let vertOffset = 0;
    let clipLeft = 0;
    let clipRight = 0;
    let clipTop = 0;
    let clipBottom = 0;
    let sizeProtected = false;
    let rotationAngle = 0;
    let brightness = 0;
    let contrast = 0;
    let effect = "REAL_PIC";
    let alpha = 0;
    let binaryItemIdRef: string | null = null;
    const picChildren = el.childNodes;
    for (let j = 0; j < picChildren.length; j++) {
      const pc = picChildren.item(j);
      if (!pc || pc.nodeType !== 1) continue;
      const pel = pc as Element;
      const pName = pel.localName || pel.nodeName.split(":").pop() || "";

      if (pName === "curSz") {
        width = parseInt(pel.getAttribute("width") ?? "0", 10);
        height = parseInt(pel.getAttribute("height") ?? "0", 10);
      }

      if (pName === "orgSz") {
        originalWidth = parseInt(pel.getAttribute("width") ?? "0", 10);
        originalHeight = parseInt(pel.getAttribute("height") ?? "0", 10);
      }

      if (pName === "pos") {
        treatAsChar = (pel.getAttribute("treatAsChar") ?? "1") === "1";
        horzRelTo = pel.getAttribute("horzRelTo") ?? "COLUMN";
        vertRelTo = pel.getAttribute("vertRelTo") ?? "PARA";
        horzOffset = parseInt(pel.getAttribute("horzOffset") ?? "0", 10);
        vertOffset = parseInt(pel.getAttribute("vertOffset") ?? "0", 10);
      }

      if (pName === "imgClip") {
        clipLeft = parseInt(pel.getAttribute("left") ?? "0", 10);
        clipRight = parseInt(pel.getAttribute("right") ?? "0", 10);
        clipTop = parseInt(pel.getAttribute("top") ?? "0", 10);
        clipBottom = parseInt(pel.getAttribute("bottom") ?? "0", 10);
      }

      if (pName === "sz") {
        sizeProtected = (pel.getAttribute("protect") ?? "0") === "1";
      }

      if (pName === "rotationInfo") {
        rotationAngle = parseInt(pel.getAttribute("angle") ?? "0", 10);
      }

      // Find img element inside pic (possibly nested in renderingInfo or directly)
      if (pName === "img") {
        brightness = parseInt(pel.getAttribute("bright") ?? "0", 10);
        contrast = parseInt(pel.getAttribute("contrast") ?? "0", 10);
        effect = pel.getAttribute("effect") ?? "REAL_PIC";
        alpha = parseInt(pel.getAttribute("alpha") ?? "0", 10);
        const ref = pel.getAttribute("binaryItemIDRef");
        if (ref) binaryItemIdRef = ref;
      }
    }

    if (!binaryItemIdRef) {
      // Also search deeper for img (might be in a sub-element)
      const allDescendants = el.getElementsByTagName("*");
      for (let k = 0; k < allDescendants.length; k++) {
        const desc = allDescendants.item(k);
        if (!desc) continue;
        const dName = desc.localName || desc.nodeName.split(":").pop() || "";
        if (dName !== "img") continue;

        brightness = parseInt(desc.getAttribute("bright") ?? "0", 10);
        contrast = parseInt(desc.getAttribute("contrast") ?? "0", 10);
        effect = desc.getAttribute("effect") ?? "REAL_PIC";
        alpha = parseInt(desc.getAttribute("alpha") ?? "0", 10);
        const ref = desc.getAttribute("binaryItemIDRef");
        if (ref) {
          binaryItemIdRef = ref;
          break;
        }
      }
    }

    if (binaryItemIdRef) {
      const resolvedOrgWidth = originalWidth > 0 ? originalWidth : width;
      const resolvedOrgHeight = originalHeight > 0 ? originalHeight : height;
      const resolvedClipRight = clipRight > 0 ? clipRight : width;
      const resolvedClipBottom = clipBottom > 0 ? clipBottom : height;
      results.push({
        binaryItemIdRef,
        width,
        height,
        originalWidth: resolvedOrgWidth,
        originalHeight: resolvedOrgHeight,
        textWrap,
        treatAsChar,
        horzRelTo,
        vertRelTo,
        horzOffset,
        vertOffset,
        clipLeft,
        clipRight: resolvedClipRight,
        clipTop,
        clipBottom: resolvedClipBottom,
        sizeProtected,
        locked,
        rotationAngle,
        brightness,
        contrast,
        effect,
        alpha,
      });
    }
  }

  return results;
}

/** Parse the header element to get ParagraphProperty lookup. */
function buildParaPrLookup(doc: HwpxDocument): Map<string, ParagraphProperty> {
  const lookup = new Map<string, ParagraphProperty>();
  try {
    const headers = doc.headers;
    if (headers.length === 0) return lookup;
    const headerEl = headers[0]!.element;
    const xml = serializeXml(headerEl);
    const parsed: Header = parseHeaderXml(xml);
    if (!parsed.refList?.paraProperties) return lookup;
    for (const prop of parsed.refList.paraProperties.properties) {
      if (prop.rawId) lookup.set(prop.rawId, prop);
      if (prop.id != null) lookup.set(String(prop.id), prop);
    }
  } catch {
    // ignore parse errors
  }
  return lookup;
}

function findFirstParagraphElement(root: Element): Element | null {
  const all = root.getElementsByTagName("*");
  for (let i = 0; i < all.length; i++) {
    const el = all.item(i);
    if (!el) continue;
    const localName = el.localName || el.nodeName.split(":").pop() || "";
    if (localName === "p") return el;
  }
  return null;
}

function extractHeaderFooterAlignment(
  headerFooterElement: Element | null,
  paraPrLookup: Map<string, ParagraphProperty>,
): string {
  if (!headerFooterElement) return "CENTER";
  const para = findFirstParagraphElement(headerFooterElement);
  if (!para) return "CENTER";
  const paraPrIdRef =
    para.getAttribute("paraPrIDRef") ??
    para.getAttribute("paraPrIdRef") ??
    para.getAttribute("paraPrRef");
  if (!paraPrIdRef) return "CENTER";
  const paraPr = paraPrLookup.get(paraPrIdRef);
  const horizontal = paraPr?.align?.horizontal;
  if (!horizontal) return "CENTER";
  const normalized = horizontal.toUpperCase();
  if (normalized === "LEFT" || normalized === "CENTER" || normalized === "RIGHT") {
    return normalized;
  }
  if (normalized === "JUSTIFY" || normalized === "DISTRIBUTE") {
    return "CENTER";
  }
  return "CENTER";
}

export function buildViewModel(doc: HwpxDocument): EditorViewModel {
  const imageMap = extractImages(doc.package);
  const paraPrLookup = buildParaPrLookup(doc);
  const sections: SectionVM[] = [];

  let globalParaIndex = 0;

  for (let sIdx = 0; sIdx < doc.sections.length; sIdx++) {
    const section = doc.sections[sIdx]!;
    const props = section.properties;
    const pageSize = props.pageSize;
    const pageMargins = props.pageMargins;

    // Extract header/footer text
    let headerText = "";
    let footerText = "";
    let headerAlign = "CENTER";
    let footerAlign = "CENTER";
    try {
      const hdr = props.getHeader("BOTH");
      if (hdr) {
        headerText = hdr.text;
        headerAlign = extractHeaderFooterAlignment(hdr.element, paraPrLookup);
      }
    } catch { /* no header */ }
    try {
      const ftr = props.getFooter("BOTH");
      if (ftr) {
        footerText = ftr.text;
        footerAlign = extractHeaderFooterAlignment(ftr.element, paraPrLookup);
      }
    } catch { /* no footer */ }

    // Extract footnotes from paragraph annotation elements
    const footnotes: FootnoteVM[] = [];
    const endnotes: FootnoteVM[] = [];
    try {
      const sectionEl = section.element;
      const allEls = sectionEl.getElementsByTagName("*");
      let fnIdx = 1;
      let enIdx = 1;
      for (let k = 0; k < allEls.length; k++) {
        const el = allEls.item(k);
        if (!el) continue;
        const ln = el.localName || el.nodeName.split(":").pop() || "";
        if (ln === "footNote" || ln === "endNote") {
          // Extract text from sub paragraphs
          const subParas = el.getElementsByTagName("*");
          let noteText = "";
          for (let m = 0; m < subParas.length; m++) {
            const sp = subParas.item(m);
            if (!sp) continue;
            const spName = sp.localName || sp.nodeName.split(":").pop() || "";
            if (spName === "t") noteText += sp.textContent ?? "";
          }
          if (ln === "footNote") {
            footnotes.push({ marker: String(fnIdx++), text: noteText });
          } else {
            endnotes.push({ marker: String(enIdx++), text: noteText });
          }
        }
      }
    } catch { /* ignore */ }

    // Extract column layout
    let columnLayoutVM: ColumnLayoutVM = { colCount: 1, sameGap: 0, type: "NEWSPAPER" };
    try {
      const colLayout = props.columnLayout;
      columnLayoutVM = {
        colCount: colLayout.colCount,
        sameGap: hwpToPx(colLayout.sameGap),
        type: colLayout.type,
      };
    } catch { /* ignore */ }

    // Extract page numbering
    let pageNumVM: PageNumVM | null = null;
    try {
      const sectionEl = section.element;
      const pageNumEls = sectionEl.getElementsByTagName("*");
      for (let k = 0; k < pageNumEls.length; k++) {
        const el = pageNumEls.item(k);
        if (!el) continue;
        const ln = el.localName || el.nodeName.split(":").pop() || "";
        if (ln === "pageNum") {
          pageNumVM = {
            pos: el.getAttribute("pos") ?? "BOTTOM_CENTER",
            formatType: el.getAttribute("formatType") ?? "DIGIT",
            sideChar: el.getAttribute("sideChar") ?? "",
          };
          break;
        }
      }
    } catch { /* ignore */ }

    let startPageNumber = 1;
    try {
      const start = props.startNumbering.page;
      startPageNumber = start > 0 ? start : 1;
    } catch {
      startPageNumber = 1;
    }

    // Extract page border fill
    let pageBorderFillVM: PageBorderFillVM | null = null;
    try {
      const sectionEl = section.element;
      const borderFillEls = sectionEl.getElementsByTagName("*");
      for (let k = 0; k < borderFillEls.length; k++) {
        const el = borderFillEls.item(k);
        if (!el) continue;
        const ln = el.localName || el.nodeName.split(":").pop() || "";
        if (ln === "pageBorderFill") {
          const type = el.getAttribute("type") ?? "BOTH";
          // Use the BOTH type or first found
          if (type === "BOTH" || !pageBorderFillVM) {
            pageBorderFillVM = {
              type,
              borderFillIdRef: el.getAttribute("borderFillIDRef") ?? "0",
              textBorder: el.getAttribute("textBorder") ?? "PAPER",
              fillArea: el.getAttribute("fillArea") ?? "PAPER",
            };
            if (type === "BOTH") break;
          }
        }
      }
    } catch { /* ignore */ }

    const sectionVM: SectionVM = {
      pageWidthPx: hwpToPx(pageSize.width),
      pageHeightPx: hwpToPx(pageSize.height),
      marginTopPx: hwpToPx(pageMargins.top),
      marginBottomPx: hwpToPx(pageMargins.bottom),
      marginLeftPx: hwpToPx(pageMargins.left),
      marginRightPx: hwpToPx(pageMargins.right),
      headerHeightPx: hwpToPx(pageMargins.header ?? 0),
      footerHeightPx: hwpToPx(pageMargins.footer ?? 0),
      paragraphs: [],
      sectionIndex: sIdx,
      startPageNumber,
      headerText,
      footerText,
      headerAlign,
      footerAlign,
      footnotes,
      endnotes,
      columnLayout: columnLayoutVM,
      pageNum: pageNumVM,
      pageBorderFill: pageBorderFillVM,
    };

    const paragraphs = section.paragraphs;
    for (const para of paragraphs) {
      const runs: RunVM[] = [];
      const images: ImageVM[] = [];
      const textBoxes: TextBoxVM[] = [];
      const equations: EquationVM[] = [];
      let currentHyperlink: string | null = null; // Track hyperlink across runs

      for (const run of para.runs) {
        const style = run.style;
        const {
          bold, italic, underline, strikethrough, color,
          fontFamily, fontSize, highlightColor, letterSpacing,
        } = extractRunStyle(style, doc);

        // Process run children to handle tabs and text in order
        const runChildren = run.element.childNodes;
        let currentText = "";
        let hasTab = false;

        for (let i = 0; i < runChildren.length; i++) {
          const child = runChildren.item(i);
          if (!child) continue;

          if (child.nodeType === 1) {
            const el = child as Element;
            const localName = el.localName || el.nodeName.split(":").pop() || "";

            if (localName === "t") {
              currentText += el.textContent ?? "";
            } else if (localName === "tab") {
              // Flush current text if any, then add tab
              if (currentText) {
                runs.push({
                  text: currentText,
                  bold, italic, underline, strikethrough, color,
                  fontFamily, fontSize, highlightColor, letterSpacing,
                  charPrIdRef: run.charPrIdRef,
                  hyperlink: currentHyperlink ?? undefined,
                });
                currentText = "";
              }
              // Add a tab run
              runs.push({
                text: "\t",
                bold, italic, underline, strikethrough, color,
                fontFamily, fontSize, highlightColor, letterSpacing,
                charPrIdRef: run.charPrIdRef,
                hasTab: true,
              });
              hasTab = true;
            } else if (localName === "fwSpace") {
              // Full-width space (전각 공백)
              if (currentText) {
                runs.push({
                  text: currentText,
                  bold, italic, underline, strikethrough, color,
                  fontFamily, fontSize, highlightColor, letterSpacing,
                  charPrIdRef: run.charPrIdRef,
                  hyperlink: currentHyperlink ?? undefined,
                });
                currentText = "";
              }
              runs.push({
                text: "\u3000", // Full-width space character
                bold, italic, underline, strikethrough, color,
                fontFamily, fontSize, highlightColor, letterSpacing,
                charPrIdRef: run.charPrIdRef,
                hasFwSpace: true,
                hyperlink: currentHyperlink ?? undefined,
              });
            } else if (localName === "lineBreak") {
              // Line break within paragraph
              if (currentText) {
                runs.push({
                  text: currentText,
                  bold, italic, underline, strikethrough, color,
                  fontFamily, fontSize, highlightColor, letterSpacing,
                  charPrIdRef: run.charPrIdRef,
                  hyperlink: currentHyperlink ?? undefined,
                });
                currentText = "";
              }
              runs.push({
                text: "\n",
                bold, italic, underline, strikethrough, color,
                fontFamily, fontSize, highlightColor, letterSpacing,
                charPrIdRef: run.charPrIdRef,
                hasLineBreak: true,
              });
            } else if (localName === "fieldBegin") {
              // Start of a field (e.g., hyperlink)
              const fieldType = el.getAttribute("type");
              if (fieldType === "HYPERLINK") {
                // Flush current text before hyperlink
                if (currentText) {
                  runs.push({
                    text: currentText,
                    bold, italic, underline, strikethrough, color,
                    fontFamily, fontSize, highlightColor, letterSpacing,
                    charPrIdRef: run.charPrIdRef,
                  });
                  currentText = "";
                }
                // Extract URL from stringParam elements
                const params = el.getElementsByTagName("*");
                for (let pi = 0; pi < params.length; pi++) {
                  const param = params.item(pi);
                  if (!param) continue;
                  const pName = param.localName || param.nodeName.split(":").pop() || "";
                  if (pName === "stringParam") {
                    const paramName = param.getAttribute("name");
                    if (paramName === "Command" || paramName === "Path") {
                      const url = param.textContent?.trim();
                      if (url) {
                        currentHyperlink = url;
                        break;
                      }
                    }
                  }
                }
              }
            } else if (localName === "fieldEnd") {
              // End of a field
              if (currentHyperlink && currentText) {
                runs.push({
                  text: currentText,
                  bold, italic, underline, strikethrough, color,
                  fontFamily, fontSize, highlightColor, letterSpacing,
                  charPrIdRef: run.charPrIdRef,
                  hyperlink: currentHyperlink,
                });
                currentText = "";
              }
              currentHyperlink = null;
            }
          }
        }

        // Flush remaining text
        if (currentText) {
          runs.push({
            text: currentText,
            bold, italic, underline, strikethrough, color,
            fontFamily, fontSize, highlightColor, letterSpacing,
            charPrIdRef: run.charPrIdRef,
            hyperlink: currentHyperlink ?? undefined,
          });
        }

        // If no content was found but run has text, use fallback
        if (runs.length === 0 || (!currentText && !hasTab)) {
          const text = run.text;
          if (text) {
            runs.push({
              text,
              bold, italic, underline, strikethrough, color,
              fontFamily, fontSize, highlightColor, letterSpacing,
              charPrIdRef: run.charPrIdRef,
            });
          }
        }

        // Check for images inside this run
        const picRefs = findPictureRefs(run.element);
        for (let picIdx = 0; picIdx < picRefs.length; picIdx++) {
          const ref = picRefs[picIdx]!;
          const dataUrl = imageMap.get(ref.binaryItemIdRef);
          if (dataUrl) {
            const outMargin = para.getPictureOutMargin(images.length);
            images.push({
              dataUrl,
              widthPx: hwpToPx(ref.width),
              heightPx: hwpToPx(ref.height),
              widthHwp: ref.width,
              heightHwp: ref.height,
              originalWidthHwp: ref.originalWidth,
              originalHeightHwp: ref.originalHeight,
              scaleXPercent: ref.originalWidth > 0 ? (ref.width * 100) / ref.originalWidth : 100,
              scaleYPercent: ref.originalHeight > 0 ? (ref.height * 100) / ref.originalHeight : 100,
              binaryItemIdRef: ref.binaryItemIdRef,
              outMargin,
              textWrap: ref.textWrap,
              treatAsChar: ref.treatAsChar,
              horzRelTo: ref.horzRelTo,
              vertRelTo: ref.vertRelTo,
              horzOffset: ref.horzOffset,
              vertOffset: ref.vertOffset,
              cropLeftHwp: Math.max(ref.clipLeft, 0),
              cropRightHwp: Math.max(ref.width - ref.clipRight, 0),
              cropTopHwp: Math.max(ref.clipTop, 0),
              cropBottomHwp: Math.max(ref.height - ref.clipBottom, 0),
              sizeProtected: ref.sizeProtected,
              locked: ref.locked,
              rotationAngle: ref.rotationAngle,
              brightness: ref.brightness,
              contrast: ref.contrast,
              effect: ref.effect,
              alpha: ref.alpha,
            });
          }
        }

        // Check for text boxes inside this run
        const textBoxRefs = findTextBoxRefs(run.element);
        for (let tbIdx = 0; tbIdx < textBoxRefs.length; tbIdx++) {
          const ref = textBoxRefs[tbIdx]!;
          textBoxes.push({
            text: ref.text,
            widthPx: hwpToPx(ref.width),
            heightPx: hwpToPx(ref.height),
            widthHwp: ref.width,
            heightHwp: ref.height,
            x: ref.x,
            y: ref.y,
            borderColor: ref.borderColor,
            fillColor: ref.fillColor,
            textBoxIndex: textBoxes.length,
          });
        }

        // Check for equations inside this run
        const equationRefs = findEquationRefs(run.element);
        for (const ref of equationRefs) {
          equations.push({
            script: ref.script,
            widthPx: hwpToPx(ref.width),
            heightPx: hwpToPx(ref.height),
            textColor: ref.textColor,
            font: ref.font,
            baseLine: ref.baseLine,
          });
        }
      }

      // Tables
      const tables: TableVM[] = [];
      const paraTables = para.tables;
      for (let tIdx = 0; tIdx < paraTables.length; tIdx++) {
        const table = paraTables[tIdx]!;
        const rowCount = table.rowCount;
        const colCount = table.columnCount;

        let cellGrid: HwpxTableGridPosition[][] = [];
        try {
          cellGrid = table.getCellMap();
        } catch {
          // If grid building fails, skip
          continue;
        }

        const cellsVM: TableCellVM[][] = [];
        for (let r = 0; r < rowCount; r++) {
          const row: TableCellVM[] = [];
          for (let c = 0; c < colCount; c++) {
            const pos = cellGrid[r]?.[c];
            if (!pos) {
              row.push({
                row: r,
                col: c,
                rowSpan: 1,
                colSpan: 1,
                widthPx: 0,
                heightPx: 0,
                text: "",
                isAnchor: false,
                borderFillIDRef: null,
                vertAlign: "CENTER",
                style: null,
                fontFamily: null,
                fontSize: null,
                textColor: null,
                bold: false,
                italic: false,
                underline: false,
                strikethrough: false,
              });
              continue;
            }

            const isAnchor = pos.anchor[0] === r && pos.anchor[1] === c;
            const textStyle = extractCellTextStyle(pos.cell.element, doc);
            const cellBfId = pos.cell.element.getAttribute("borderFillIDRef");
            let cellStyle: CellStyleVM | null = null;
            if (cellBfId) {
              try {
                const bfInfo = doc.oxml.getBorderFillInfo(cellBfId);
                if (bfInfo) {
                  cellStyle = {
                    borderLeft: bfInfo.left.type !== "NONE" ? bfInfo.left : null,
                    borderRight: bfInfo.right.type !== "NONE" ? bfInfo.right : null,
                    borderTop: bfInfo.top.type !== "NONE" ? bfInfo.top : null,
                    borderBottom: bfInfo.bottom.type !== "NONE" ? bfInfo.bottom : null,
                    backgroundColor: bfInfo.backgroundColor,
                  };
                }
              } catch { /* ignore */ }
            }
            row.push({
              row: r,
              col: c,
              rowSpan: pos.span[0],
              colSpan: pos.span[1],
              widthPx: hwpToPx(pos.cell.width),
              heightPx: hwpToPx(pos.cell.height),
              text: isAnchor ? pos.cell.text : "",
              isAnchor,
              borderFillIDRef: cellBfId,
              vertAlign: (() => {
                const el = pos.cell.element as Element & { querySelector?: (selector: string) => Element | null };
                const sl = (typeof el.querySelector === "function" ? el.querySelector("subList") : null) ??
                  Array.from(pos.cell.element.childNodes).find(
                    (n) => n.nodeType === 1 && ((n as Element).localName === "subList" || (n as Element).nodeName.split(":").pop() === "subList"),
                  ) as Element | undefined;
                return (sl?.getAttribute?.("vertAlign") ?? "CENTER").toUpperCase();
              })(),
              style: cellStyle,
              fontFamily: textStyle.fontFamily,
              fontSize: textStyle.fontSize,
              textColor: textStyle.color,
              bold: textStyle.bold,
              italic: textStyle.italic,
              underline: textStyle.underline,
              strikethrough: textStyle.strikethrough,
            });
          }
          cellsVM.push(row);
        }

        // Compute per-column widths - find a cell with colSpan=1 for each column
        const columnWidths: number[] = [];
        for (let c = 0; c < colCount; c++) {
          let width = 0;
          // First, try to find a cell with colSpan=1 in this column
          for (let r = 0; r < rowCount && width === 0; r++) {
            const pos = cellGrid[r]?.[c];
            if (pos && pos.anchor[1] === c && pos.span[1] === 1) {
              width = pos.cell.width;
            }
          }
          // If not found, distribute merged cell width
          if (width === 0) {
            const pos = cellGrid[0]?.[c];
            if (pos) {
              width = Math.round(pos.cell.width / pos.span[1]);
            }
          }
          columnWidths.push(width);
        }

        const outMargin = table.getOutMargin();
        const inMargin = table.getInMargin();

        tables.push({
          rowCount,
          colCount,
          cells: cellsVM,
          tableIndex: tIdx,
          pageBreak: table.pageBreak,
          repeatHeader: table.repeatHeader,
          widthHwp: table.width,
          heightHwp: table.height,
          outMargin,
          inMargin,
          columnWidths,
          borderFillIDRef: table.element.getAttribute("borderFillIDRef"),
        });
      }

      // Extract default character formatting from paragraph's charPrIdRef
      let defaultFontSize: number | null = null;
      let defaultFontFamily: string | null = null;
      const paraCharPrIdRef = para.charPrIdRef;
      if (paraCharPrIdRef) {
        const charStyle = doc.charProperty(paraCharPrIdRef);
        if (charStyle) {
          const extracted = extractRunStyle(charStyle, doc);
          defaultFontSize = extracted.fontSize;
          defaultFontFamily = extracted.fontFamily;
        }
      }
      // Fallback: use first run's style if paragraph-level is missing
      if (defaultFontSize == null && runs.length > 0) {
        defaultFontSize = runs[0]!.fontSize;
      }
      if (defaultFontFamily == null && runs.length > 0) {
        defaultFontFamily = runs[0]!.fontFamily;
      }

      // Extract paragraph formatting from paraPrIdRef
      let alignment = "LEFT";
      let lineSpacing = 1.6;
      let spacingBefore = 0;
      let spacingAfter = 0;
      let firstLineIndent = 0;
      let marginLeftPx = 0;
      let marginRightPx = 0;

      const paraPrIdRef = para.paraPrIdRef;
      if (paraPrIdRef) {
        const paraPr = paraPrLookup.get(paraPrIdRef);
        if (paraPr) {
          // Alignment
          if (paraPr.align?.horizontal) {
            alignment = paraPr.align.horizontal.toUpperCase();
          }
          // Line spacing
          if (paraPr.lineSpacing?.value != null) {
            lineSpacing = paraPr.lineSpacing.value / 100;
          }
          // Margins and spacing
          if (paraPr.margin) {
            if (paraPr.margin.left) {
              marginLeftPx = hwpToPx(parseInt(paraPr.margin.left, 10) || 0);
            }
            if (paraPr.margin.right) {
              marginRightPx = hwpToPx(parseInt(paraPr.margin.right, 10) || 0);
            }
            if (paraPr.margin.intent) {
              firstLineIndent = hwpToPx(parseInt(paraPr.margin.intent, 10) || 0);
            }
            if (paraPr.margin.prev) {
              spacingBefore = hwpToPx(parseInt(paraPr.margin.prev, 10) || 0);
            }
            if (paraPr.margin.next) {
              spacingAfter = hwpToPx(parseInt(paraPr.margin.next, 10) || 0);
            }
          }
        }
      }

      sectionVM.paragraphs.push({
        runs,
        tables,
        images,
        textBoxes,
        equations,
        alignment,
        lineSpacing,
        spacingBefore,
        spacingAfter,
        firstLineIndent,
        marginLeftPx,
        marginRightPx,
        paragraphIndex: globalParaIndex,
        defaultFontSize,
        defaultFontFamily,
      });

      globalParaIndex++;
    }

    sections.push(sectionVM);
  }

  return { sections, watermarkText: "" };
}
