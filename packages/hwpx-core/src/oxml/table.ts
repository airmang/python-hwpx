/**
 * Table-related OXML classes: HwpxOxmlTableCell, HwpxOxmlTableRow, HwpxOxmlTable.
 */

import type { HwpxOxmlParagraph } from "./paragraph.js";
import {
  HP_NS,
  DEFAULT_CELL_WIDTH,
  DEFAULT_CELL_HEIGHT,
  objectId,
  paragraphId,
  findChild,
  findAllChildren,
  findDescendant,
  createNsElement,
  subElement,
  clearParagraphLayoutCache,
  distributeSize,
  defaultCellAttributes,
  defaultSublistAttributes,
  defaultCellParagraphAttributes,
  defaultCellMarginAttributes,
} from "./xml-utils.js";

// -- HwpxOxmlTableCell --

/** Margin values (top, bottom, left, right) in hwpUnits. */
export interface HwpxMargin {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

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

  /** Get cell margin (cellMargin element). */
  getMargin(): HwpxMargin {
    const el = findChild(this.element, HP_NS, "cellMargin");
    if (!el) return { top: 0, bottom: 0, left: 0, right: 0 };
    return {
      top: parseInt(el.getAttribute("top") ?? "0", 10),
      bottom: parseInt(el.getAttribute("bottom") ?? "0", 10),
      left: parseInt(el.getAttribute("left") ?? "0", 10),
      right: parseInt(el.getAttribute("right") ?? "0", 10),
    };
  }

  /** Set cell margin (cellMargin element). */
  setMargin(margin: Partial<HwpxMargin>): void {
    let el = findChild(this.element, HP_NS, "cellMargin");
    if (!el) el = subElement(this.element, HP_NS, "cellMargin", defaultCellMarginAttributes());
    if (margin.top != null) el.setAttribute("top", String(Math.max(margin.top, 0)));
    if (margin.bottom != null) el.setAttribute("bottom", String(Math.max(margin.bottom, 0)));
    if (margin.left != null) el.setAttribute("left", String(Math.max(margin.left, 0)));
    if (margin.right != null) el.setAttribute("right", String(Math.max(margin.right, 0)));
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

  /** Table width in hwpUnits. */
  get width(): number {
    const sz = findChild(this.element, HP_NS, "sz");
    return parseInt(sz?.getAttribute("width") ?? "0", 10);
  }

  /** Table height in hwpUnits. */
  get height(): number {
    const sz = findChild(this.element, HP_NS, "sz");
    return parseInt(sz?.getAttribute("height") ?? "0", 10);
  }

  /** Set table size (width and/or height in hwpUnits). */
  setSize(width?: number, height?: number): void {
    let sz = findChild(this.element, HP_NS, "sz");
    if (!sz) sz = subElement(this.element, HP_NS, "sz", { width: "0", height: "0", widthRelTo: "ABSOLUTE", heightRelTo: "ABSOLUTE", protect: "0" });
    if (width != null) sz.setAttribute("width", String(Math.max(width, 0)));
    if (height != null) sz.setAttribute("height", String(Math.max(height, 0)));
    this.markDirty();
  }

  /** Get table outer margin (outMargin element). */
  getOutMargin(): HwpxMargin {
    const el = findChild(this.element, HP_NS, "outMargin");
    if (!el) return { top: 0, bottom: 0, left: 0, right: 0 };
    return {
      top: parseInt(el.getAttribute("top") ?? "0", 10),
      bottom: parseInt(el.getAttribute("bottom") ?? "0", 10),
      left: parseInt(el.getAttribute("left") ?? "0", 10),
      right: parseInt(el.getAttribute("right") ?? "0", 10),
    };
  }

  /** Set table outer margin (outMargin element). */
  setOutMargin(margin: Partial<HwpxMargin>): void {
    let el = findChild(this.element, HP_NS, "outMargin");
    if (!el) el = subElement(this.element, HP_NS, "outMargin", defaultCellMarginAttributes());
    if (margin.top != null) el.setAttribute("top", String(Math.max(margin.top, 0)));
    if (margin.bottom != null) el.setAttribute("bottom", String(Math.max(margin.bottom, 0)));
    if (margin.left != null) el.setAttribute("left", String(Math.max(margin.left, 0)));
    if (margin.right != null) el.setAttribute("right", String(Math.max(margin.right, 0)));
    this.markDirty();
  }

  /** Get table inner cell margin (inMargin element). */
  getInMargin(): HwpxMargin {
    const el = findChild(this.element, HP_NS, "inMargin");
    if (!el) return { top: 0, bottom: 0, left: 0, right: 0 };
    return {
      top: parseInt(el.getAttribute("top") ?? "0", 10),
      bottom: parseInt(el.getAttribute("bottom") ?? "0", 10),
      left: parseInt(el.getAttribute("left") ?? "0", 10),
      right: parseInt(el.getAttribute("right") ?? "0", 10),
    };
  }

  /** Set table inner cell margin (inMargin element). */
  setInMargin(margin: Partial<HwpxMargin>): void {
    let el = findChild(this.element, HP_NS, "inMargin");
    if (!el) el = subElement(this.element, HP_NS, "inMargin", defaultCellMarginAttributes());
    if (margin.top != null) el.setAttribute("top", String(Math.max(margin.top, 0)));
    if (margin.bottom != null) el.setAttribute("bottom", String(Math.max(margin.bottom, 0)));
    if (margin.left != null) el.setAttribute("left", String(Math.max(margin.left, 0)));
    if (margin.right != null) el.setAttribute("right", String(Math.max(margin.right, 0)));
    this.markDirty();
  }

  /** Set the width of a column (updates all cells in that column). */
  setColumnWidth(colIdx: number, width: number): void {
    if (colIdx < 0 || colIdx >= this.columnCount) {
      throw new Error(`column index ${colIdx} out of range (0..${this.columnCount - 1})`);
    }
    const grid = this._buildCellGrid();
    const processed = new Set<Element>();
    for (let r = 0; r < this.rowCount; r++) {
      const entry = grid.get(`${r},${colIdx}`);
      if (!entry) continue;
      // Only update anchor cells at this column
      if (entry.anchor[1] !== colIdx) continue;
      if (processed.has(entry.cell.element)) continue;
      processed.add(entry.cell.element);
      entry.cell.setSize(Math.max(width, 0));
    }
    this.markDirty();
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
