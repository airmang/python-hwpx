/**
 * Common element types for OXML models.
 * Ported from Python hwpx/oxml/common.py
 */

import { localName, childElements, getAttributes, getTextContent } from "../xml/dom.js";

/** Fallback representation for XML elements without a specialised model. */
export interface GenericElement {
  name: string;
  tag: string | null;
  attributes: Record<string, string>;
  children: GenericElement[];
  text: string | null;
}

/** Convert an Element into a GenericElement. */
export function parseGenericElement(node: Element): GenericElement {
  const children = childElements(node).map((child) => parseGenericElement(child));
  const text = getTextContent(node);
  return {
    name: localName(node),
    tag: node.tagName ?? null,
    attributes: getAttributes(node),
    children,
    text: text ?? null,
  };
}
