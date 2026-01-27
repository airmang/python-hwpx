/**
 * Element factory registry and top-level XML parse helpers.
 * Ported from Python hwpx/oxml/parser.py
 */

import * as body from "./body.js";
import * as header from "./header.js";
import { parseGenericElement } from "./common.js";
import { localName } from "./utils.js";
import { parseXml } from "../xml/dom.js";

type ParserFn = (node: Element) => unknown;

const _ELEMENT_FACTORY: Record<string, ParserFn> = {
  head: header.parseHeaderElement,
  beginNum: header.parseBeginNum,
  refList: header.parseRefList,
  docOption: header.parseDocOption,
  sec: body.parseSectionElement,
  p: body.parseParagraphElement,
  run: body.parseRunElement,
  t: body.parseTextSpan,
  ctrl: body.parseControlElement,
  tbl: body.parseTableElement,
};

// Register inline object names
for (const name of body.INLINE_OBJECT_NAMES) {
  if (!(name in _ELEMENT_FACTORY)) {
    _ELEMENT_FACTORY[name] = body.parseInlineObjectElement;
  }
}

// Register track change mark names
for (const markName of ["insertBegin", "insertEnd", "deleteBegin", "deleteEnd"]) {
  if (!(markName in _ELEMENT_FACTORY)) {
    _ELEMENT_FACTORY[markName] = body.parseTrackChangeMark;
  }
}

/** Convert a DOM Element into the corresponding TypeScript model object. */
export function elementToModel(node: Element): unknown {
  const parser = _ELEMENT_FACTORY[localName(node)];
  if (parser == null) {
    return parseGenericElement(node);
  }
  return parser(node);
}

/** Parse an XML string containing a `<head>` root element into a Header model. */
export function parseHeaderXml(source: string): header.Header {
  const doc = parseXml(source);
  const root = doc.documentElement;
  if (localName(root) !== "head") {
    throw new Error("Expected <head> root element");
  }
  return header.parseHeaderElement(root);
}

/** Parse an XML string containing a `<sec>` root element into a Section model. */
export function parseSectionXml(source: string): body.Section {
  const doc = parseXml(source);
  const root = doc.documentElement;
  if (localName(root) !== "sec") {
    throw new Error("Expected <sec> root element");
  }
  return body.parseSectionElement(root);
}
