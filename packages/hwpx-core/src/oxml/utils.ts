/**
 * Utility functions for OXML parsing.
 * Ported from Python hwpx/oxml/utils.py
 */

import { localName as domLocalName } from "../xml/dom.js";

const _TRUE_VALUES = new Set(["1", "true", "True", "TRUE"]);
const _FALSE_VALUES = new Set(["0", "false", "False", "FALSE"]);

/** Return the local (namespace-stripped) tag name for a node. */
export function localName(node: Element): string {
  return domLocalName(node);
}

/** Parse a string as an integer. Returns null if value is null/undefined and allowNone is true. */
export function parseInt_(
  value: string | null | undefined,
  options?: { allowNone?: boolean },
): number | null {
  const allowNone = options?.allowNone ?? true;
  if (value == null) {
    if (allowNone) return null;
    throw new Error("Missing integer value");
  }
  const n = Number(value);
  if (!Number.isFinite(n) || Math.floor(n) !== n) {
    throw new Error(`Invalid integer value: ${JSON.stringify(value)}`);
  }
  return n;
}

/** Convert a string attribute into a boolean. */
export function parseBool(
  value: string | null | undefined,
  options?: { default?: boolean | null },
): boolean | null {
  const defaultValue = options?.default ?? null;
  if (value == null) return defaultValue;
  if (_TRUE_VALUES.has(value)) return true;
  if (_FALSE_VALUES.has(value)) return false;
  throw new Error(`Invalid boolean value: ${JSON.stringify(value)}`);
}

/** Return the text content of a node stripped of leading/trailing whitespace, or null. */
export function textOrNone(node: Element): string | null {
  const text = node.textContent;
  if (text == null) return null;
  const trimmed = text.trim();
  return trimmed || null;
}
