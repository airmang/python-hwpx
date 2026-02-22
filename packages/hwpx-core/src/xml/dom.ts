/**
 * Cross-platform XML DOM abstraction layer.
 * Uses @xmldom/xmldom in Node.js and native DOMParser/XMLSerializer in browsers.
 *
 * The global DOM lib types (Element, Document, Node) are used as the public API.
 * Internally, xmldom returns compatible objects — we cast at the boundary.
 */

import { DOMParser as XmlDOMParser, XMLSerializer as XmlSerializer } from "@xmldom/xmldom";

const _parser = new XmlDOMParser();
const _serializer = new XmlSerializer();

const PREFERRED_NAMESPACE_PREFIX: Record<string, string> = {
  "http://www.hancom.co.kr/hwpml/2011/paragraph": "hp",
  "http://www.hancom.co.kr/hwpml/2016/paragraph": "hp10",
  "http://www.hancom.co.kr/hwpml/2011/section": "hs",
  "http://www.hancom.co.kr/hwpml/2011/core": "hc",
  "http://www.hancom.co.kr/hwpml/2011/head": "hh",
  "http://www.idpf.org/2007/opf/": "opf",
};

/** Parse an XML string into a Document. */
export function parseXml(xml: string): Document {
  return _parser.parseFromString(xml, "text/xml") as unknown as Document;
}

/** Serialize an Element (or Document) back to an XML string. */
export function serializeXml(node: Node): string {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return _serializer.serializeToString(node as any);
}

/** Return the local (namespace-stripped) tag name for a node. */
export function localName(node: Element): string {
  if (node.localName) return node.localName;
  const tag = node.tagName;
  const idx = tag.indexOf(":");
  return idx >= 0 ? tag.substring(idx + 1) : tag;
}

/** Create a namespaced element. If ns is null, creates without namespace. */
export function createElement(
  doc: Document,
  ns: string | null,
  name: string,
  attributes?: Record<string, string>,
): Element {
  let qualifiedName = name;
  if (ns && !name.includes(":")) {
    const preferred = PREFERRED_NAMESPACE_PREFIX[ns];
    if (preferred) {
      qualifiedName = `${preferred}:${name}`;
    }
  }

  const el = ns ? doc.createElementNS(ns, qualifiedName) : doc.createElement(qualifiedName);
  if (attributes) {
    for (const [key, value] of Object.entries(attributes)) {
      el.setAttribute(key, value);
    }
  }
  return el;
}

/** Return attributes as a plain Record<string, string>. */
export function getAttributes(node: Element): Record<string, string> {
  const attrs: Record<string, string> = {};
  const namedMap = node.attributes;
  if (namedMap) {
    for (let i = 0; i < namedMap.length; i++) {
      const attr = namedMap.item(i);
      if (attr) {
        attrs[attr.name] = attr.value;
      }
    }
  }
  return attrs;
}

/** Return an array of child Element nodes (skipping text, comments, etc.). */
export function childElements(node: Element): Element[] {
  const result: Element[] = [];
  const children = node.childNodes;
  for (let i = 0; i < children.length; i++) {
    const child = children.item(i);
    if (child && child.nodeType === 1) {
      result.push(child as Element);
    }
  }
  return result;
}

/** Get the text content of a node (equivalent to lxml .text). */
export function getTextContent(node: Element): string | null {
  // Get only direct text children (not nested element text)
  let text = "";
  const children = node.childNodes;
  for (let i = 0; i < children.length; i++) {
    const child = children.item(i);
    if (child && child.nodeType === 3) { // TEXT_NODE
      text += child.nodeValue ?? "";
    }
  }
  return text || null;
}

/** Get the "tail" text (text after the closing tag, before the next sibling).
 *  In W3C DOM this is the nextSibling text node. */
export function getTailText(node: Element): string {
  const sibling = node.nextSibling;
  if (sibling && sibling.nodeType === 3) {
    return sibling.nodeValue ?? "";
  }
  return "";
}

/** Set direct text content of an element (replaces only text node children). */
export function setTextContent(node: Element, text: string | null): void {
  // Remove existing text nodes
  const children = node.childNodes;
  for (let i = children.length - 1; i >= 0; i--) {
    const child = children.item(i);
    if (child && child.nodeType === 3) {
      node.removeChild(child);
    }
  }
  // Add new text node if non-empty
  if (text) {
    const doc = node.ownerDocument;
    if (doc) {
      const textNode = doc.createTextNode(text);
      // Insert before first child element
      const firstChild = node.firstChild;
      if (firstChild) {
        node.insertBefore(textNode, firstChild);
      } else {
        node.appendChild(textNode);
      }
    }
  }
}
