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
}

export interface TableVM {
  rowCount: number;
  colCount: number;
  cells: TableCellVM[][]; // 2D grid [row][col], non-anchor cells have isAnchor=false
  tableIndex: number; // index within the paragraph
  pageBreak: string; // "CELL", "NONE", etc.
  repeatHeader: boolean;
}

export interface ImageVM {
  dataUrl: string;
  widthPx: number;
  heightPx: number;
  binaryItemIdRef: string;
}

export interface ParagraphVM {
  runs: RunVM[];
  tables: TableVM[];
  images: ImageVM[];
  alignment: string;
  lineSpacing: number;
  spacingBefore: number;
  spacingAfter: number;
  firstLineIndent: number;
  marginLeftPx: number;
  marginRightPx: number;
  paragraphIndex: number; // global index across all sections
}

export interface SectionVM {
  pageWidthPx: number;
  pageHeightPx: number;
  marginTopPx: number;
  marginBottomPx: number;
  marginLeftPx: number;
  marginRightPx: number;
  paragraphs: ParagraphVM[];
  sectionIndex: number;
}

export interface EditorViewModel {
  sections: SectionVM[];
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

  const bold = style.attributes["bold"] === "1";
  const italic = style.attributes["italic"] === "1";

  // Check underline child element
  const underlineChild = style.childAttributes["underline"];
  const underline =
    underlineChild != null &&
    underlineChild["type"] != null &&
    underlineChild["type"] !== "NONE";

  // Strikethrough
  const strikeChild = style.childAttributes["strikeout"];
  const strikethrough =
    strikeChild != null &&
    strikeChild["type"] != null &&
    strikeChild["type"] !== "NONE";

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

/** Find binaryItemIDRef from a picture element inside a run. */
function findPictureRefs(
  runElement: Element,
): { binaryItemIdRef: string; width: number; height: number }[] {
  const results: { binaryItemIdRef: string; width: number; height: number }[] = [];

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

      // Find img element inside pic (possibly nested in renderingInfo or directly)
      if (pName === "img") {
        const ref = pel.getAttribute("binaryItemIDRef");
        if (ref) results.push({ binaryItemIdRef: ref, width, height });
      }
    }

    // Also search deeper for img (might be in a sub-element)
    const allDescendants = el.getElementsByTagName("*");
    for (let k = 0; k < allDescendants.length; k++) {
      const desc = allDescendants.item(k);
      if (!desc) continue;
      const dName = desc.localName || desc.nodeName.split(":").pop() || "";
      if (dName === "img") {
        const ref = desc.getAttribute("binaryItemIDRef");
        if (ref && !results.some((r) => r.binaryItemIdRef === ref)) {
          results.push({ binaryItemIdRef: ref, width, height });
        }
      }
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

    const sectionVM: SectionVM = {
      pageWidthPx: hwpToPx(pageSize.width),
      pageHeightPx: hwpToPx(pageSize.height),
      marginTopPx: hwpToPx(pageMargins.top),
      marginBottomPx: hwpToPx(pageMargins.bottom),
      marginLeftPx: hwpToPx(pageMargins.left),
      marginRightPx: hwpToPx(pageMargins.right),
      paragraphs: [],
      sectionIndex: sIdx,
    };

    const paragraphs = section.paragraphs;
    for (const para of paragraphs) {
      const runs: RunVM[] = [];
      const images: ImageVM[] = [];

      for (const run of para.runs) {
        const style = run.style;
        const {
          bold, italic, underline, strikethrough, color,
          fontFamily, fontSize, highlightColor, letterSpacing,
        } = extractRunStyle(style, doc);
        const text = run.text;

        if (text) {
          runs.push({
            text,
            bold,
            italic,
            underline,
            strikethrough,
            color,
            fontFamily,
            fontSize,
            highlightColor,
            letterSpacing,
            charPrIdRef: run.charPrIdRef,
          });
        }

        // Check for images inside this run
        const picRefs = findPictureRefs(run.element);
        for (const ref of picRefs) {
          const dataUrl = imageMap.get(ref.binaryItemIdRef);
          if (dataUrl) {
            images.push({
              dataUrl,
              widthPx: hwpToPx(ref.width),
              heightPx: hwpToPx(ref.height),
              binaryItemIdRef: ref.binaryItemIdRef,
            });
          }
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
              });
              continue;
            }

            const isAnchor = pos.anchor[0] === r && pos.anchor[1] === c;
            row.push({
              row: r,
              col: c,
              rowSpan: pos.span[0],
              colSpan: pos.span[1],
              widthPx: hwpToPx(pos.cell.width),
              heightPx: hwpToPx(pos.cell.height),
              text: isAnchor ? pos.cell.text : "",
              isAnchor,
            });
          }
          cellsVM.push(row);
        }

        tables.push({
          rowCount,
          colCount,
          cells: cellsVM,
          tableIndex: tIdx,
          pageBreak: table.pageBreak,
          repeatHeader: table.repeatHeader,
        });
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
        alignment,
        lineSpacing,
        spacingBefore,
        spacingAfter,
        firstLineIndent,
        marginLeftPx,
        marginRightPx,
        paragraphIndex: globalParaIndex,
      });

      globalParaIndex++;
    }

    sections.push(sectionVM);
  }

  return { sections };
}
