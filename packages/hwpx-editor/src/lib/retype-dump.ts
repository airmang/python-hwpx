import { useEditorStore } from "./store";
import { HwpxOxmlTable } from "@ubermensch1218/hwpxcore";

type Store = ReturnType<typeof useEditorStore.getState>;

export interface RetypeDump {
  sections: Array<{
    paragraphs: Array<{
      inlineText: string;
      tables: RetypeTableDump[];
    }>;
  }>;
}

export interface RetypeTableDump {
  rowCount: number;
  colCount: number;
  cells: Array<{
    row: number;
    col: number;
    rowSpan: number;
    colSpan: number;
    text: string;
    nestedTables: RetypeTableDump[];
  }>;
}

function localName(el: Element): string {
  return el.localName ?? el.nodeName.split(":").pop() ?? "";
}

function childElements(el: Element): Element[] {
  return Array.from(el.childNodes).filter((n): n is Element => n.nodeType === 1);
}

function ensureChild(parent: Element, name: string): Element {
  const found = childElements(parent).find((c) => localName(c) === name);
  if (found) return found;
  const ns = parent.namespaceURI;
  const prefix = parent.prefix;
  const qualified = prefix ? `${prefix}:${name}` : name;
  const created = ns
    ? parent.ownerDocument.createElementNS(ns, qualified)
    : parent.ownerDocument.createElement(name);
  parent.appendChild(created);
  return created;
}

function ensureCellFirstRun(cellEl: Element): Element {
  const subList = ensureChild(cellEl, "subList");
  const p = ensureChild(subList, "p");
  const run = ensureChild(p, "run");
  return run;
}

function applyTableDump(
  table: {
    mergeCells: (r1: number, c1: number, r2: number, c2: number) => void;
    cell: (r: number, c: number) => { text: string; element: Element };
    borderFillIDRef?: string | null;
  },
  paragraph: { element: Element; section: { markDirty: () => void } },
  dump: RetypeTableDump,
): void {
  // Apply merges first.
  for (const cell of dump.cells) {
    if (cell.rowSpan > 1 || cell.colSpan > 1) {
      table.mergeCells(cell.row, cell.col, cell.row + cell.rowSpan - 1, cell.col + cell.colSpan - 1);
    }
  }

  // Then populate anchor cell text and nested tables.
  for (const cell of dump.cells) {
    const target = table.cell(cell.row, cell.col);
    if (cell.text) target.text = cell.text;

    if (cell.nestedTables.length > 0) {
      const run = ensureCellFirstRun(target.element);
      for (const nested of cell.nestedTables) {
        const borderFillIdRef = table.borderFillIDRef ?? "1";
        const nestedEl = HwpxOxmlTable.create(
          paragraph.element.ownerDocument,
          nested.rowCount,
          nested.colCount,
          { borderFillIdRef },
        );
        run.appendChild(nestedEl);
        const nestedTable = new HwpxOxmlTable(nestedEl, paragraph as any);
        applyTableDump(nestedTable as any, paragraph, nested);
      }
    }
  }

  paragraph.section.markDirty();
}

export async function applyRetypeDump(store: Store, dump: RetypeDump): Promise<void> {
  const doc = store.doc;
  if (!doc) throw new Error("doc is missing");

  const sections = dump.sections ?? [];
  if (sections.length === 0) return;

  // For now, target the existing section count (typical skeleton: 1 section).
  const section = doc.sections[0];
  if (!section) throw new Error("section 0 is missing");

  // Remove all existing paragraphs (reverse order).
  for (let i = section.paragraphs.length - 1; i >= 0; i -= 1) {
    try {
      doc.removeParagraph(0, i);
    } catch {
      // ignore and continue
    }
  }

  const sourceSection = sections[0]!;
  for (let pIdx = 0; pIdx < sourceSection.paragraphs.length; pIdx += 1) {
    const pDump = sourceSection.paragraphs[pIdx]!;
    const para = doc.addParagraph(pDump.inlineText ?? "", { sectionIndex: 0 });

    for (const tDump of pDump.tables ?? []) {
      para.addTable(tDump.rowCount, tDump.colCount);
      const tableIndex = para.tables.length - 1;
      const table = para.tables[tableIndex];
      if (!table) throw new Error("failed to create table");
      applyTableDump(table as any, para as any, tDump);
    }
  }

  store.rebuild();
}
