/**
 * XML manipulation helper functions for HWPX documents.
 */

import {
  localName as domLocalName,
  childElements,
  getAttributes,
  getTextContent,
} from "@ubermensch1218/hwpxcore";

/**
 * Strip namespace prefix from a tag name.
 */
export function stripNamespace(tag: string): string {
  const idx = tag.lastIndexOf("}");
  return idx >= 0 ? tag.substring(idx + 1) : tag;
}

/**
 * Check if an element's tag matches the given local name.
 */
export function tagMatches(element: Element, localNameTarget: string): boolean {
  return domLocalName(element) === localNameTarget;
}

/**
 * Build a map from each element to its parent element.
 */
export function buildParentMap(root: Element): Map<Element, Element> {
  const parentMap = new Map<Element, Element>();
  const walk = (node: Element): void => {
    for (const child of childElements(node)) {
      parentMap.set(child, node);
      walk(child);
    }
  };
  walk(root);
  return parentMap;
}

/**
 * Describe the path from root to the given element.
 */
export function describeElementPath(
  element: Element,
  parentMap: Map<Element, Element>
): string {
  const parts: string[] = [];
  let current: Element | undefined = element;
  while (current) {
    parts.unshift(domLocalName(current));
    current = parentMap.get(current);
  }
  return parts.join("/");
}

/**
 * Find all descendant elements matching the given local name.
 */
export function findAllDescendants(parent: Element, localNameStr: string): Element[] {
  const result: Element[] = [];
  const walk = (node: Element): void => {
    for (const child of childElements(node)) {
      if (domLocalName(child) === localNameStr) {
        result.push(child);
      }
      walk(child);
    }
  };
  walk(parent);
  return result;
}

/**
 * Find the first descendant element matching the given local name.
 */
export function findDescendant(parent: Element, localNameStr: string): Element | null {
  for (const child of childElements(parent)) {
    if (domLocalName(child) === localNameStr) {
      return child;
    }
    const result = findDescendant(child, localNameStr);
    if (result) return result;
  }
  return null;
}

/**
 * Collect all text content from descendant text nodes.
 */
export function collectAllText(element: Element): string {
  const parts: string[] = [];
  const walk = (node: Element): void => {
    for (const child of childElements(node)) {
      const name = domLocalName(child);
      if (name === "t") {
        const text = child.textContent ?? "";
        if (text) parts.push(text);
      }
      walk(child);
    }
  };
  walk(element);
  return parts.join("");
}

/**
 * Get element attributes as a plain object.
 */
export function getElementAttributes(element: Element): Record<string, string> {
  return getAttributes(element);
}

/**
 * Get text content from an element.
 */
export function getElementText(element: Element): string {
  return getTextContent(element) ?? "";
}

export { domLocalName as localName, childElements };
