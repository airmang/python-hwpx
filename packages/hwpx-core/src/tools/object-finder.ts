/**
 * Object finder for locating elements inside HWPX documents.
 * Ported from Python hwpx/tools/object_finder.py
 */

import { parseXml, localName as domLocalName, childElements, getAttributes } from "../xml/dom.js";
import type { HwpxPackage } from "../package.js";
import {
  DEFAULT_NAMESPACES,
  SectionInfo,
  TextExtractor,
  stripNamespace,
  tagMatches,
  buildParentMap,
  describeElementPath,
} from "./text-extractor.js";

export type AttrMatcher = string | string[] | RegExp | ((value: string) => boolean);

export interface FoundElement {
  section: SectionInfo;
  path: string;
  element: Element;
}

export function foundElementTag(found: FoundElement): string {
  return stripNamespace(found.element.tagName ?? found.element.localName ?? "");
}

export function foundElementHierarchy(found: FoundElement): string[] {
  return found.path.split("/");
}

export function foundElementGet(found: FoundElement, name: string): string | null {
  return found.element.getAttribute(name);
}

export interface AnnotationMatch {
  kind: string;
  element: FoundElement;
  value: string | null;
}

function matchesAttr(value: string | null, matcher: AttrMatcher): boolean {
  if (value == null) return false;
  if (typeof matcher === "string") return value === matcher;
  if (Array.isArray(matcher)) return matcher.includes(value);
  if (matcher instanceof RegExp) return matcher.test(value);
  if (typeof matcher === "function") return matcher(value);
  return false;
}

export class ObjectFinder {
  private _pkg: HwpxPackage;
  private _namespaces: Record<string, string>;

  constructor(pkg: HwpxPackage, namespaces?: Record<string, string>) {
    this._pkg = pkg;
    this._namespaces = { ...DEFAULT_NAMESPACES, ...namespaces };
  }

  /** Return sections found in the package. */
  sections(): SectionInfo[] {
    const extractor = new TextExtractor(this._pkg);
    return extractor.sections();
  }

  /** Find elements by local tag name. */
  findByTag(tagName: string, opts?: { sectionIndex?: number }): FoundElement[] {
    const sections = this.sections();
    const targetSections = opts?.sectionIndex != null
      ? sections.filter((s) => s.index === opts.sectionIndex)
      : sections;

    const results: FoundElement[] = [];

    for (const sectionInfo of targetSections) {
      const xmlText = this._pkg.getText(sectionInfo.path);
      const doc = parseXml(xmlText);
      const root = doc.documentElement;
      const parentMap = buildParentMap(root);

      const walk = (node: Element): void => {
        if (domLocalName(node) === tagName) {
          results.push({
            section: sectionInfo,
            path: describeElementPath(node, parentMap),
            element: node,
          });
        }
        for (const child of childElements(node)) {
          walk(child);
        }
      };
      walk(root);
    }

    return results;
  }

  /** Find elements by attribute match. */
  findByAttribute(
    attributeName: string,
    matcher: AttrMatcher,
    opts?: { tagName?: string; sectionIndex?: number },
  ): FoundElement[] {
    const sections = this.sections();
    const targetSections = opts?.sectionIndex != null
      ? sections.filter((s) => s.index === opts.sectionIndex)
      : sections;

    const results: FoundElement[] = [];

    for (const sectionInfo of targetSections) {
      const xmlText = this._pkg.getText(sectionInfo.path);
      const doc = parseXml(xmlText);
      const root = doc.documentElement;
      const parentMap = buildParentMap(root);

      const walk = (node: Element): void => {
        const name = domLocalName(node);
        if (opts?.tagName && name !== opts.tagName) {
          // Continue searching children
        } else {
          const value = node.getAttribute(attributeName);
          if (matchesAttr(value, matcher)) {
            results.push({
              section: sectionInfo,
              path: describeElementPath(node, parentMap),
              element: node,
            });
          }
        }
        for (const child of childElements(node)) {
          walk(child);
        }
      };
      walk(root);
    }

    return results;
  }

  /** Find all tables in the document. */
  findTables(opts?: { sectionIndex?: number }): FoundElement[] {
    return this.findByTag("tbl", opts);
  }

  /** Find all pictures/images in the document. */
  findPictures(opts?: { sectionIndex?: number }): FoundElement[] {
    return this.findByTag("pic", opts);
  }

  /** Find all controls in the document. */
  findControls(opts?: { controlType?: string; sectionIndex?: number }): FoundElement[] {
    const elements = this.findByTag("ctrl", opts);
    if (opts?.controlType) {
      return elements.filter((el) => el.element.getAttribute("type") === opts.controlType);
    }
    return elements;
  }

  /** Find annotations (highlights, footnotes, etc.) */
  findAnnotations(opts?: { kind?: string; sectionIndex?: number }): AnnotationMatch[] {
    const results: AnnotationMatch[] = [];
    const sections = this.sections();
    const targetSections = opts?.sectionIndex != null
      ? sections.filter((s) => s.index === opts.sectionIndex)
      : sections;

    for (const sectionInfo of targetSections) {
      const xmlText = this._pkg.getText(sectionInfo.path);
      const doc = parseXml(xmlText);
      const root = doc.documentElement;
      const parentMap = buildParentMap(root);

      const walk = (node: Element): void => {
        const name = domLocalName(node);
        let kind: string | null = null;
        let value: string | null = null;

        if (name === "markpenBegin" || name === "markpenEnd") {
          kind = "highlight";
          value = node.getAttribute("color") ?? null;
        } else if (name === "footNote" || name === "endNote") {
          kind = name === "footNote" ? "footnote" : "endnote";
          value = node.getAttribute("instId") ?? null;
        } else if (name === "hyperlink") {
          kind = "hyperlink";
          value = node.getAttribute("url") ?? node.getAttribute("target") ?? null;
        }

        if (kind && (!opts?.kind || opts.kind === kind)) {
          results.push({
            kind,
            element: {
              section: sectionInfo,
              path: describeElementPath(node, parentMap),
              element: node,
            },
            value,
          });
        }

        for (const child of childElements(node)) {
          walk(child);
        }
      };
      walk(root);
    }

    return results;
  }
}
