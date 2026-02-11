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
  binaryItemIdRef: string;
  outMargin: MarginVM;
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
  defaultFontSize: number | null;
  defaultFontFamily: string | null;
}

export interface FootnoteVM {
  marker: string; // e.g. "1", "2", ...
  text: string;
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
  headerText: string;
  footerText: string;
  footnotes: FootnoteVM[];
  endnotes: FootnoteVM[];
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

    // Extract header/footer text
    let headerText = "";
    let footerText = "";
    try {
      const hdr = props.getHeader("BOTH");
      if (hdr) headerText = hdr.text;
    } catch { /* no header */ }
    try {
      const ftr = props.getFooter("BOTH");
      if (ftr) footerText = ftr.text;
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
      headerText,
      footerText,
      footnotes,
      endnotes,
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
              binaryItemIdRef: ref.binaryItemIdRef,
              outMargin,
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
                borderFillIDRef: null,
                vertAlign: "CENTER",
                style: null,
              });
              continue;
            }

            const isAnchor = pos.anchor[0] === r && pos.anchor[1] === c;
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
                const sl = pos.cell.element.querySelector("subList") ??
                  Array.from(pos.cell.element.childNodes).find(
                    (n) => n.nodeType === 1 && ((n as Element).localName === "subList" || (n as Element).nodeName.split(":").pop() === "subList"),
                  ) as Element | undefined;
                return (sl?.getAttribute?.("vertAlign") ?? "CENTER").toUpperCase();
              })(),
              style: cellStyle,
            });
          }
          cellsVM.push(row);
        }

        // Compute per-column widths from the first row's anchor cells
        const columnWidths: number[] = [];
        for (let c = 0; c < colCount; c++) {
          const pos = cellGrid[0]?.[c];
          if (pos && pos.anchor[1] === c) {
            columnWidths.push(pos.cell.width);
          } else {
            columnWidths.push(0);
          }
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
