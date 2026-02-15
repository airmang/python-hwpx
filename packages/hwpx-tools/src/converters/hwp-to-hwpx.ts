import {
  CharCode,
  CharControl,
  CommonCtrlID,
  ExtendedControl,
  InlineControl,
  PictureControl,
  TableControl,
  parse,
} from "@hwp.js/parser";
import type { HWPDocument, Paragraph as HwpParagraph } from "@hwp.js/parser";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve as pathResolve } from "node:path";
import { HwpxDocument } from "@ubermensch1218/hwpxcore";

export interface HwpToHwpxOptions {
  /** Insert placeholders for unknown inline objects (default: false). */
  inlineObjectPlaceholders?: boolean;
  /** Placeholder text for inline objects (default: "[OBJ]"). */
  inlineObjectPlaceholderText?: string;
  /** Default image size in mm if source size is missing (default: 50x30). */
  defaultImageSizeMm?: { widthMm: number; heightMm: number };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function hwpUnitToMm(value: number): number {
  // HWP internal units are commonly 1/7200 inch (best-effort assumption).
  return (value * 25.4) / 7200;
}

function extensionToMediaType(ext: string): string {
  const e = ext.toLowerCase().replace(/^\./, "");
  if (e === "png") return "image/png";
  if (e === "jpg" || e === "jpeg") return "image/jpeg";
  if (e === "gif") return "image/gif";
  if (e === "bmp") return "image/bmp";
  if (e === "tif" || e === "tiff") return "image/tiff";
  if (e === "webp") return "image/webp";
  if (e === "svg") return "image/svg+xml";
  return "application/octet-stream";
}

function hwpParagraphText(paragraph: HwpParagraph, options: Required<HwpToHwpxOptions>): string {
  const parts: string[] = [];

  for (const ch of paragraph.chars) {
    if (ch instanceof CharCode) {
      const str = ch.toString();
      if (str) parts.push(str);
      continue;
    }

    if (ch instanceof CharControl || ch instanceof InlineControl || ch instanceof ExtendedControl) {
      if (options.inlineObjectPlaceholders) parts.push(options.inlineObjectPlaceholderText);
    }
  }

  const text = parts.join("");
  return text
    .replace(/\r\n?/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trimEnd();
}

function tableCellTextFromHwpParagraphs(
  paragraphs: HwpParagraph[],
  options: Required<HwpToHwpxOptions>
): string {
  const lines: string[] = [];
  for (const p of paragraphs) {
    const t = hwpParagraphText(p, options);
    if (t) lines.push(t);
  }
  return lines.join("\n").trim();
}

let _cachedSkeletonBytes: Uint8Array | null = null;

async function loadSkeletonHwpxBytes(): Promise<Uint8Array> {
  if (_cachedSkeletonBytes != null) return _cachedSkeletonBytes;

  // Prefer resolving the installed package asset.
  try {
    const req = createRequire(import.meta.url);
    const skeletonPath = req.resolve("@ubermensch1218/hwpxcore/assets/Skeleton.hwpx");
    const buf = await readFile(skeletonPath);
    _cachedSkeletonBytes = new Uint8Array(buf);
    return _cachedSkeletonBytes;
  } catch {
    // Fall back to monorepo path.
    const skeletonPath = pathResolve(process.cwd(), "packages", "hwpx-core", "assets", "Skeleton.hwpx");
    const buf = await readFile(skeletonPath);
    _cachedSkeletonBytes = new Uint8Array(buf);
    return _cachedSkeletonBytes;
  }
}

async function createEmptyHwpxDocument(): Promise<HwpxDocument> {
  const skeleton = await loadSkeletonHwpxBytes();
  const doc = await HwpxDocument.open(skeleton);

  // Clear all paragraphs from all sections.
  for (let s = doc.sections.length - 1; s >= 0; s--) {
    const section = doc.sections[s]!;
    for (let p = section.paragraphs.length - 1; p >= 0; p--) {
      doc.removeParagraph(s, p);
    }
  }

  return doc;
}

function findEmbeddedBinFileNameById(hwpDoc: HWPDocument, binItemId: number): string | null {
  const mappings = hwpDoc.info?.idMappings?.binaryData ?? [];
  for (const item of mappings) {
    if (item.id === binItemId) return item.getCFBFileName();
  }

  // Fallback guess: id is stored as hex in file name. Extension is unknown here.
  try {
    const hex = binItemId.toString(16).padStart(4, "0");
    return `BIN${hex}.bin`;
  } catch {
    return null;
  }
}

function findBinDataBytesByName(hwpDoc: HWPDocument, name: string): Uint8Array | null {
  const target = name.toLowerCase();
  for (const item of hwpDoc.binDataList ?? []) {
    if (item?.name?.toLowerCase?.() === target) {
      return item.data ?? null;
    }
  }
  return null;
}

export async function convertHwpBytesToHwpxBytes(
  hwpBytes: Uint8Array,
  options?: HwpToHwpxOptions
): Promise<Uint8Array> {
  const resolved: Required<HwpToHwpxOptions> = {
    inlineObjectPlaceholders: options?.inlineObjectPlaceholders ?? false,
    inlineObjectPlaceholderText: options?.inlineObjectPlaceholderText ?? "[OBJ]",
    defaultImageSizeMm: options?.defaultImageSizeMm ?? { widthMm: 50, heightMm: 30 },
  };

  const hwpDoc: HWPDocument = parse(hwpBytes);
  const out = await createEmptyHwpxDocument();

  // Flatten all source sections into section 0.
  const sectionIndex = 0;

  for (const section of hwpDoc.sections) {
    for (const para of section.paragraphs) {
      const text = hwpParagraphText(para, resolved);
      if (text) {
        out.addParagraph(text, { sectionIndex });
      }

      for (const ctrl of para.controls ?? []) {
        if (ctrl.id === CommonCtrlID.Table && ctrl.content instanceof TableControl) {
          const tableControl = ctrl.content;
          const rows = tableControl.record?.rows ?? 0;
          const cols = tableControl.record?.cols ?? 0;
          if (rows <= 0 || cols <= 0) continue;

          const tablePara = out.addParagraph("", { sectionIndex });
          const table = tablePara.addTable(rows, cols);

          // Fill cell texts.
          for (const cell of tableControl.cells ?? []) {
            const r = cell.row;
            const c = cell.column;
            const paras: HwpParagraph[] = [];
            for (const p of cell.paragraphs ?? []) paras.push(p);
            const cellText = tableCellTextFromHwpParagraphs(paras, resolved);
            if (cellText) table.setCellText(r, c, cellText);
          }

          // Apply merges (best-effort).
          for (const cell of tableControl.cells ?? []) {
            const rs = cell.rowSpan ?? 1;
            const cs = cell.colSpan ?? 1;
            if (rs > 1 || cs > 1) {
              table.mergeCells(cell.row, cell.column, cell.row + rs - 1, cell.column + cs - 1);
            }
          }

          continue;
        }

        if (ctrl.id === CommonCtrlID.Picture && ctrl.content instanceof PictureControl) {
          const pic = ctrl.content;
          const binItemId = pic.content?.image?.binItemId ?? null;
          if (binItemId == null) continue;

          const fileName = findEmbeddedBinFileNameById(hwpDoc, binItemId);
          if (!fileName) continue;

          const bytes = findBinDataBytesByName(hwpDoc, fileName);
          if (!bytes) continue;

          const ext = fileName.split(".").pop() ?? "bin";
          const mediaType = extensionToMediaType(ext);

          const w = pic.commonProperties?.width ?? 0;
          const h = pic.commonProperties?.height ?? 0;

          const widthMm = w > 0
            ? clamp(hwpUnitToMm(w), 10, 200)
            : resolved.defaultImageSizeMm.widthMm;
          const heightMm = h > 0
            ? clamp(hwpUnitToMm(h), 10, 200)
            : resolved.defaultImageSizeMm.heightMm;

          out.addImage(bytes, {
            mediaType,
            widthMm,
            heightMm,
            sectionIndex,
            treatAsChar: true,
          });
        }
      }
    }
  }

  return out.save();
}
