/**
 * Type definitions and helper functions for the HWPX OXML document model.
 */

import { childElements } from "../xml/dom.js";
import {
  HH_NS,
  elementLocalName,
  findChild,
  findAllChildren,
} from "./xml-utils.js";

// -- Data interfaces --

export interface PageSize {
  width: number;
  height: number;
  orientation: string;
  gutterType: string;
}

export interface PageMargins {
  left: number;
  right: number;
  top: number;
  bottom: number;
  header: number;
  footer: number;
  gutter: number;
}

export interface SectionStartNumbering {
  pageStartsOn: string;
  page: number;
  picture: number;
  table: number;
  equation: number;
}

export interface ColumnLayout {
  /** Column type: "NEWSPAPER", "PARALLEL", "BALANCE_NEWSPAPER", "BALANCE_PARALLEL" */
  type: string;
  /** Column layout direction: "LEFT", "RIGHT", "MIRROR" */
  layout: string;
  /** Number of columns */
  colCount: number;
  /** Whether all columns have the same width */
  sameSz: boolean;
  /** Gap between columns in hwpUnits (used when sameSz is true) */
  sameGap: number;
  /** Per-column width and gap (used when sameSz is false) */
  columns?: { width: number; gap: number }[];
}

export interface DocumentNumbering {
  page: number;
  footnote: number;
  endnote: number;
  picture: number;
  table: number;
  equation: number;
}

export interface RunStyle {
  id: string;
  attributes: Record<string, string>;
  childAttributes: Record<string, Record<string, string>>;
}

// -- RunStyle helpers --

export function runStyleTextColor(style: RunStyle): string | null {
  return style.attributes["textColor"] ?? null;
}

export function runStyleUnderlineType(style: RunStyle): string | null {
  const underline = style.childAttributes["underline"];
  if (!underline) return null;
  return underline["type"] ?? null;
}

export function runStyleUnderlineColor(style: RunStyle): string | null {
  const underline = style.childAttributes["underline"];
  if (!underline) return null;
  return underline["color"] ?? null;
}

export function runStyleMatches(
  style: RunStyle,
  opts: { textColor?: string | null; underlineType?: string | null; underlineColor?: string | null },
): boolean {
  if (opts.textColor != null && runStyleTextColor(style) !== opts.textColor) return false;
  if (opts.underlineType != null && runStyleUnderlineType(style) !== opts.underlineType) return false;
  if (opts.underlineColor != null && runStyleUnderlineColor(style) !== opts.underlineColor) return false;
  return true;
}

// -- Char property parsing --

export function charPropertiesFromHeader(element: Element): Record<string, RunStyle> {
  const mapping: Record<string, RunStyle> = {};
  const refList = findChild(element, HH_NS, "refList");
  if (!refList) return mapping;
  const charPropsElement = findChild(refList, HH_NS, "charProperties");
  if (!charPropsElement) return mapping;

  for (const child of findAllChildren(charPropsElement, HH_NS, "charPr")) {
    const charId = child.getAttribute("id");
    if (!charId) continue;
    const attributes: Record<string, string> = {};
    const namedMap = child.attributes;
    for (let i = 0; i < namedMap.length; i++) {
      const attr = namedMap.item(i);
      if (attr && attr.name !== "id") {
        attributes[attr.name] = attr.value;
      }
    }
    const childAttributes: Record<string, Record<string, string>> = {};
    for (const grandchild of childElements(child)) {
      if (childElements(grandchild).length === 0 && !(grandchild.textContent?.trim())) {
        const gcAttrs: Record<string, string> = {};
        const gcNamedMap = grandchild.attributes;
        for (let i = 0; i < gcNamedMap.length; i++) {
          const attr = gcNamedMap.item(i);
          if (attr) gcAttrs[attr.name] = attr.value;
        }
        childAttributes[elementLocalName(grandchild)] = gcAttrs;
      }
    }
    const style: RunStyle = { id: charId, attributes, childAttributes };
    if (!(charId in mapping)) mapping[charId] = style;
    try {
      const normalized = String(parseInt(charId, 10));
      if (normalized && !(normalized in mapping)) mapping[normalized] = style;
    } catch { /* ignore */ }
  }
  return mapping;
}
