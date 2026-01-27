/**
 * Text extraction from HWPX documents.
 * Ported from Python hwpx/tools/text_extractor.py
 */

import { parseXml, localName as domLocalName, childElements, getAttributes } from "../xml/dom.js";
import type { HwpxPackage } from "../package.js";

export const DEFAULT_NAMESPACES: Record<string, string> = {
  hp: "http://www.hancom.co.kr/hwpml/2011/paragraph",
  hp10: "http://www.hancom.co.kr/hwpml/2016/paragraph",
  hs: "http://www.hancom.co.kr/hwpml/2011/section",
  hc: "http://www.hancom.co.kr/hwpml/2011/core",
  ha: "http://www.hancom.co.kr/hwpml/2011/app",
  hh: "http://www.hancom.co.kr/hwpml/2011/head",
  hhs: "http://www.hancom.co.kr/hwpml/2011/history",
  hm: "http://www.hancom.co.kr/hwpml/2011/master-page",
  hpf: "http://www.hancom.co.kr/schema/2011/hpf",
  dc: "http://purl.org/dc/elements/1.1/",
  opf: "http://www.idpf.org/2007/opf/",
};

const SECTION_PATTERN = /^Contents\/section(\d+)\.xml$/;

const OBJECT_CONTAINERS = new Set([
  "tbl", "container", "line", "rect", "ellipse", "arc", "polygon",
  "curve", "connectLine", "textart", "pic", "compose", "switch",
  "equation", "ole", "edit", "btn", "checkBtn", "radioBtn",
]);

export function stripNamespace(tag: string): string {
  const idx = tag.lastIndexOf("}");
  return idx >= 0 ? tag.substring(idx + 1) : tag;
}

export function tagMatches(tag: string, localNameTarget: string): boolean {
  return stripNamespace(tag) === localNameTarget;
}

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

export function describeElementPath(
  element: Element,
  parentMap: Map<Element, Element>,
): string {
  const parts: string[] = [];
  let current: Element | undefined = element;
  while (current) {
    parts.unshift(domLocalName(current));
    current = parentMap.get(current);
  }
  return parts.join("/");
}

export interface SectionInfo {
  index: number;
  name: string;
  path: string;
}

export interface ParagraphInfo {
  sectionIndex: number;
  paragraphIndex: number;
  text: string;
  attributes: Record<string, string>;
}

export type HighlightBehavior = "ignore" | "markers";
export type NoteBehavior = "ignore" | "placeholder" | "inline";
export type HyperlinkBehavior = "ignore" | "placeholder" | "target";
export type ControlBehavior = "ignore" | "placeholder" | "nested";

export interface AnnotationOptions {
  highlight?: HighlightBehavior;
  highlightStart?: string;
  highlightEnd?: string;
  footnote?: NoteBehavior;
  endnote?: NoteBehavior;
  noteInlineFormat?: string;
  notePlaceholder?: string;
  hyperlink?: HyperlinkBehavior;
  hyperlinkTargetFormat?: string;
  hyperlinkPlaceholder?: string;
  control?: ControlBehavior;
  controlPlaceholder?: string;
}

function collectTextFromElement(element: Element): string {
  const parts: string[] = [];

  const walk = (node: Element): void => {
    const name = domLocalName(node);

    if (name === "t") {
      // Text span
      const text = node.textContent ?? "";
      if (text) parts.push(text);
      return;
    }

    if (OBJECT_CONTAINERS.has(name)) {
      // Walk into subList inside containers for nested text
      for (const child of childElements(node)) {
        if (domLocalName(child) === "subList") {
          for (const subChild of childElements(child)) {
            walk(subChild);
          }
        }
      }
      return;
    }

    for (const child of childElements(node)) {
      walk(child);
    }
  };

  walk(element);
  return parts.join("");
}

function collectParagraphText(paragraphElement: Element): string {
  const parts: string[] = [];
  for (const run of childElements(paragraphElement)) {
    if (domLocalName(run) !== "run") continue;
    for (const child of childElements(run)) {
      const name = domLocalName(child);
      if (name === "t") {
        const text = child.textContent ?? "";
        if (text) parts.push(text);
      }
    }
  }
  return parts.join("");
}

export class TextExtractor {
  private _pkg: HwpxPackage;
  private _annotationOptions: AnnotationOptions;

  constructor(pkg: HwpxPackage, annotationOptions?: AnnotationOptions) {
    this._pkg = pkg;
    this._annotationOptions = annotationOptions ?? {};
  }

  /** Return sections found in the package. */
  sections(): SectionInfo[] {
    const result: SectionInfo[] = [];
    const partNames = this._pkg.partNames();
    for (const name of partNames) {
      const match = SECTION_PATTERN.exec(name);
      if (match && match[1]) {
        const index = parseInt(match[1], 10);
        result.push({
          index,
          name: `section${match[1]}`,
          path: name,
        });
      }
    }
    result.sort((a, b) => a.index - b.index);
    return result;
  }

  /** Extract paragraphs from a section XML string or all sections. */
  extractParagraphs(sectionIndex?: number): ParagraphInfo[] {
    const sections = this.sections();
    const targetSections = sectionIndex != null
      ? sections.filter((s) => s.index === sectionIndex)
      : sections;

    const paragraphs: ParagraphInfo[] = [];

    for (const sectionInfo of targetSections) {
      const xmlText = this._pkg.getText(sectionInfo.path);
      const doc = parseXml(xmlText);
      const root = doc.documentElement;

      let paragraphIndex = 0;
      const findParagraphs = (node: Element): void => {
        for (const child of childElements(node)) {
          if (domLocalName(child) === "p") {
            const text = collectParagraphText(child);
            paragraphs.push({
              sectionIndex: sectionInfo.index,
              paragraphIndex: paragraphIndex++,
              text,
              attributes: getAttributes(child),
            });
          }
          // Also look inside subList for nested paragraphs
          if (domLocalName(child) === "subList" || domLocalName(child) === "sec") {
            findParagraphs(child);
          }
        }
      };

      findParagraphs(root);
    }

    return paragraphs;
  }

  /** Extract all text from the document as a single string. */
  extractText(separator: string = "\n"): string {
    const paragraphs = this.extractParagraphs();
    return paragraphs.map((p) => p.text).join(separator);
  }

  /** Extract text section by section. */
  extractSectionTexts(separator: string = "\n"): Map<number, string> {
    const sections = this.sections();
    const result = new Map<number, string>();

    for (const sectionInfo of sections) {
      const paragraphs = this.extractParagraphs(sectionInfo.index);
      result.set(sectionInfo.index, paragraphs.map((p) => p.text).join(separator));
    }

    return result;
  }
}
