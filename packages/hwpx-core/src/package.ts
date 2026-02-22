/**
 * HWPX OPC-style package handling.
 * Ported from Python hwpx/package.py - uses JSZip for async ZIP I/O.
 */

import JSZip from "jszip";
import { parseXml, serializeXml } from "./xml/dom.js";

const _OPF_NS = "http://www.idpf.org/2007/opf/";

const MEDIA_TYPE_EXTENSIONS: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/jpg": "jpg",
  "image/png": "png",
  "image/bmp": "bmp",
  "image/gif": "gif",
  "image/tiff": "tif",
  "image/svg+xml": "svg",
  "image/webp": "webp",
};

function mediaTypeToExtension(mediaType: string): string {
  return MEDIA_TYPE_EXTENSIONS[mediaType.toLowerCase()] ?? "bin";
}

function normalizedManifestValue(element: Element): string {
  const parts = ["id", "href", "media-type", "properties"]
    .map((attr) => (element.getAttribute(attr) ?? "").toLowerCase())
    .filter((v) => v);
  return parts.join(" ");
}

function manifestMatches(element: Element, ...candidates: string[]): boolean {
  const normalized = normalizedManifestValue(element);
  return candidates.some((c) => c && normalized.includes(c));
}

function ensureBytes(value: Uint8Array | string): Uint8Array {
  if (value instanceof Uint8Array) return value;
  return new TextEncoder().encode(value);
}

export interface RootFile {
  fullPath: string;
  mediaType: string | null;
}

/** Get the filename portion of a path (like PurePosixPath.name). */
function pathName(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx >= 0 ? path.substring(idx + 1) : path;
}

export class HwpxPackage {
  static readonly MIMETYPE_PATH = "mimetype";
  static readonly CONTAINER_PATH = "META-INF/container.xml";
  static readonly MANIFEST_PATH = "Contents/content.hpf";
  static readonly HEADER_PATH = "Contents/header.xml";
  static readonly VERSION_PATH = "version.xml";

  private static _warningHandler: ((message: string) => void) | null = null;

  private _parts: Map<string, Uint8Array>;
  private _manifestTree: Document | null = null;
  private _spineCache: string[] | null = null;
  private _sectionPathsCache: string[] | null = null;
  private _headerPathsCache: string[] | null = null;
  private _masterPagePathsCache: string[] | null = null;
  private _historyPathsCache: string[] | null = null;
  private _versionPathCache: string | null = null;
  private _versionPathCacheResolved = false;
  private _rootfilesCache: RootFile[] | null = null;
  private _closed = false;

  constructor(parts: Map<string, Uint8Array>) {
    this._parts = new Map(parts);
  }

  static setWarningHandler(handler: ((message: string) => void) | null): void {
    HwpxPackage._warningHandler = handler;
  }

  private _warn(message: string): void {
    HwpxPackage._warningHandler?.(message);
  }

  private _validateOpenStructure(): void {
    if (!this._parts.has(HwpxPackage.MIMETYPE_PATH)) {
      throw new Error("HWPX package is missing mandatory mimetype part");
    }
    const mimetype = this.getText(HwpxPackage.MIMETYPE_PATH).trim();
    if (mimetype !== "application/hwp+zip") {
      throw new Error(`Invalid HWPX mimetype: ${mimetype}`);
    }
    if (!this._parts.has(HwpxPackage.CONTAINER_PATH)) {
      throw new Error("HWPX package is missing META-INF/container.xml");
    }
    if (this.rootfiles().length === 0) {
      throw new Error("container.xml does not declare any rootfiles");
    }
  }

  private _assertOpen(): void {
    if (this._closed) {
      throw new Error("HwpxPackage is closed");
    }
  }

  get closed(): boolean {
    return this._closed;
  }

  close(): void {
    if (this._closed) return;
    this._parts.clear();
    this._manifestTree = null;
    this._spineCache = null;
    this._sectionPathsCache = null;
    this._headerPathsCache = null;
    this._masterPagePathsCache = null;
    this._historyPathsCache = null;
    this._versionPathCache = null;
    this._versionPathCacheResolved = false;
    this._rootfilesCache = null;
    this._closed = true;
  }

  /** Open an HWPX package from a Uint8Array or ArrayBuffer. */
  static async open(source: Uint8Array | ArrayBuffer): Promise<HwpxPackage> {
    const zip = await JSZip.loadAsync(source);
    const parts = new Map<string, Uint8Array>();
    const promises: Promise<void>[] = [];

    zip.forEach((relativePath, file) => {
      if (!file.dir) {
        promises.push(
          file.async("uint8array").then((data) => {
            parts.set(relativePath, data);
          }),
        );
      }
    });

    await Promise.all(promises);
    const pkg = new HwpxPackage(parts);
    pkg._validateOpenStructure();
    return pkg;
  }

  // -- Accessors --

  partNames(): string[] {
    this._assertOpen();
    return Array.from(this._parts.keys());
  }

  toJSON(): {
    partCount: number;
    sectionCount: number;
    headerCount: number;
    hasManifest: boolean;
    hasMimetype: boolean;
  } {
    return {
      partCount: this._parts.size,
      sectionCount: this.sectionPaths().length,
      headerCount: this.headerPaths().length,
      hasManifest: this.hasPart(HwpxPackage.MANIFEST_PATH),
      hasMimetype: this.hasPart(HwpxPackage.MIMETYPE_PATH),
    };
  }

  toString(): string {
    const summary = this.toJSON();
    return `HwpxPackage(parts=${summary.partCount}, sections=${summary.sectionCount}, headers=${summary.headerCount})`;
  }

  hasPart(partName: string): boolean {
    this._assertOpen();
    return this._parts.has(partName);
  }

  getPart(partName: string): Uint8Array {
    this._assertOpen();
    const data = this._parts.get(partName);
    if (data == null) {
      this._warn(`missing part: ${partName}`);
      throw new Error(`Package does not contain part '${partName}'`);
    }
    return data;
  }

  setPart(partName: string, payload: Uint8Array | string): void {
    this._assertOpen();
    this._parts.set(partName, ensureBytes(payload));
    if (partName === HwpxPackage.MANIFEST_PATH) {
      this._manifestTree = null;
      this._spineCache = null;
      this._sectionPathsCache = null;
      this._headerPathsCache = null;
      this._masterPagePathsCache = null;
      this._historyPathsCache = null;
      this._versionPathCache = null;
      this._versionPathCacheResolved = false;
    }
    if (partName === HwpxPackage.CONTAINER_PATH) {
      this._rootfilesCache = null;
    }
  }

  getXml(partName: string): Element {
    this._assertOpen();
    const data = this.getPart(partName);
    const text = new TextDecoder().decode(data);
    const doc = parseXml(text);
    return doc.documentElement;
  }

  setXml(partName: string, element: Element): void {
    this._assertOpen();
    const xml = '<?xml version="1.0" encoding="UTF-8"?>' + serializeXml(element);
    this.setPart(partName, xml);
  }

  getText(partName: string): string {
    this._assertOpen();
    return new TextDecoder().decode(this.getPart(partName));
  }

  rootfiles(): RootFile[] {
    this._assertOpen();
    if (this._rootfilesCache == null) {
      const containerText = this.getText(HwpxPackage.CONTAINER_PATH);
      const containerDoc = parseXml(containerText);
      const rootfiles: RootFile[] = [];

      const walk = (node: Element): void => {
        const children = node.childNodes;
        for (let i = 0; i < children.length; i++) {
          const child = children.item(i);
          if (child && child.nodeType === 1) {
            const el = child as Element;
            const tag = el.localName ?? el.tagName;
            if (tag === "rootfile") {
              const fullPathAttr = el.getAttribute("full-path");
              const fullPath = fullPathAttr ?? el.getAttribute("fullPath") ?? el.getAttribute("full_path");
              if (!fullPath) {
                throw new Error("container.xml rootfile is missing full-path");
              }
              if (!fullPathAttr) {
                this._warn("container rootfile uses non-standard full-path attribute");
              }

              const mediaTypeAttr = el.getAttribute("media-type");
              const mediaType = mediaTypeAttr ?? el.getAttribute("mediaType") ?? el.getAttribute("media_type");
              if (mediaType && !mediaTypeAttr) {
                this._warn("container rootfile uses non-standard media-type attribute");
              }

              rootfiles.push({ fullPath, mediaType: mediaType ?? null });
            }
            walk(el);
          }
        }
      };

      walk(containerDoc.documentElement);
      this._rootfilesCache = rootfiles;
    }

    return this._rootfilesCache.map((r) => ({ ...r }));
  }

  mainRootFile(): RootFile {
    this._assertOpen();
    const rootfiles = this.rootfiles();
    const standard = rootfiles.find((rootfile) => rootfile.mediaType === "application/hwpml-package+xml");
    if (standard) return standard;

    const fallback = rootfiles[0];
    if (!fallback) {
      throw new Error("container.xml does not declare any rootfiles");
    }
    this._warn(`main rootfile fallback: ${fallback.fullPath}`);
    return fallback;
  }

  // -- Manifest helpers --

  private manifestTree(): Document {
    this._assertOpen();
    if (this._manifestTree == null) {
      const data = this.getPart(HwpxPackage.MANIFEST_PATH);
      const text = new TextDecoder().decode(data);
      this._manifestTree = parseXml(text);
    }
    return this._manifestTree;
  }

  private manifestItems(): Element[] {
    const doc = this.manifestTree();
    const root = doc.documentElement;
    const items: Element[] = [];
    // Walk the DOM tree to find item elements under manifest
    const walk = (node: Element): void => {
      const children = node.childNodes;
      for (let i = 0; i < children.length; i++) {
        const child = children.item(i);
        if (child && child.nodeType === 1) {
          const el = child as Element;
          const tag = el.localName ?? el.tagName;
          if (tag === "item") {
            items.push(el);
          }
          walk(el);
        }
      }
    };
    walk(root);
    return items;
  }

  private resolveSpinePaths(): string[] {
    if (this._spineCache == null) {
      const doc = this.manifestTree();
      const root = doc.documentElement;
      const manifestItems: Record<string, string> = {};

      const findElements = (node: Element, localNameTarget: string): Element[] => {
        const result: Element[] = [];
        const walk = (n: Element): void => {
          const children = n.childNodes;
          for (let i = 0; i < children.length; i++) {
            const child = children.item(i);
            if (child && child.nodeType === 1) {
              const el = child as Element;
              const tag = el.localName ?? el.tagName;
              if (tag === localNameTarget) {
                result.push(el);
              }
              walk(el);
            }
          }
        };
        walk(node);
        return result;
      };

      for (const item of findElements(root, "item")) {
        const id = item.getAttribute("id");
        const href = item.getAttribute("href") ?? "";
        if (id && href) {
          manifestItems[id] = href;
        }
      }

      const spinePaths: string[] = [];
      for (const itemref of findElements(root, "itemref")) {
        const idref = itemref.getAttribute("idref");
        if (!idref) continue;
        const href = manifestItems[idref];
        if (href) {
          spinePaths.push(href);
        }
      }
      this._spineCache = spinePaths;
    }
    return this._spineCache;
  }

  sectionPaths(): string[] {
    this._assertOpen();
    if (this._sectionPathsCache == null) {
      let paths = this.resolveSpinePaths().filter(
        (p) => p && pathName(p).startsWith("section"),
      );
      if (paths.length === 0) {
        this._warn("sectionPaths fallback: using filename scan instead of manifest spine");
        paths = Array.from(this._parts.keys()).filter((name) =>
          pathName(name).startsWith("section"),
        );
      }
      this._sectionPathsCache = paths;
    }
    return [...this._sectionPathsCache];
  }

  headerPaths(): string[] {
    this._assertOpen();
    if (this._headerPathsCache == null) {
      let paths = this.resolveSpinePaths().filter(
        (p) => p && pathName(p).startsWith("header"),
      );
      if (paths.length === 0 && this.hasPart(HwpxPackage.HEADER_PATH)) {
        this._warn(`headerPaths fallback: using default header path ${HwpxPackage.HEADER_PATH}`);
        paths = [HwpxPackage.HEADER_PATH];
      }
      this._headerPathsCache = paths;
    }
    return [...this._headerPathsCache];
  }

  masterPagePaths(): string[] {
    this._assertOpen();
    if (this._masterPagePathsCache == null) {
      let paths = this.manifestItems()
        .filter((item) => manifestMatches(item, "masterpage", "master-page"))
        .map((item) => item.getAttribute("href") ?? "")
        .filter((href) => href);

      if (paths.length === 0) {
        this._warn("masterPagePaths fallback: using filename scan instead of manifest metadata");
        paths = Array.from(this._parts.keys()).filter((name) => {
          const n = pathName(name).toLowerCase();
          return n.includes("master") && n.includes("page");
        });
      }
      this._masterPagePathsCache = paths;
    }
    return [...this._masterPagePathsCache];
  }

  historyPaths(): string[] {
    this._assertOpen();
    if (this._historyPathsCache == null) {
      let paths = this.manifestItems()
        .filter((item) => manifestMatches(item, "history"))
        .map((item) => item.getAttribute("href") ?? "")
        .filter((href) => href);

      if (paths.length === 0) {
        this._warn("historyPaths fallback: using filename scan instead of manifest metadata");
        paths = Array.from(this._parts.keys()).filter((name) =>
          pathName(name).toLowerCase().includes("history"),
        );
      }
      this._historyPathsCache = paths;
    }
    return [...this._historyPathsCache];
  }

  versionPath(): string | null {
    this._assertOpen();
    if (!this._versionPathCacheResolved) {
      let path: string | null = null;
      for (const item of this.manifestItems()) {
        if (manifestMatches(item, "version")) {
          const href = (item.getAttribute("href") ?? "").trim();
          if (href) {
            path = href;
            break;
          }
        }
      }
      if (path == null && this.hasPart(HwpxPackage.VERSION_PATH)) {
        this._warn(`versionPath fallback: using default path ${HwpxPackage.VERSION_PATH}`);
        path = HwpxPackage.VERSION_PATH;
      }
      this._versionPathCache = path;
      this._versionPathCacheResolved = true;
    }
    return this._versionPathCache;
  }

  // -- Binary item management --

  /**
   * Add a binary item (image, etc.) to the package.
   * Stores the data in BinData/ and registers it in the manifest.
   * Returns the binaryItemIDRef to use in <hc:img>.
   */
  addBinaryItem(data: Uint8Array, opts: {
    mediaType: string;
    extension?: string;
  }): string {
    this._assertOpen();
    // Determine extension from mediaType if not provided
    const ext = opts.extension ?? mediaTypeToExtension(opts.mediaType);

    // Find next available image number
    const existingParts = this.partNames().filter(p => p.startsWith("BinData/"));
    let maxNum = 0;
    for (const p of existingParts) {
      const match = /^BinData\/image(\d+)\./.exec(p);
      if (match?.[1]) {
        const n = parseInt(match[1], 10);
        if (n > maxNum) maxNum = n;
      }
    }
    const nextNum = maxNum + 1;
    const itemId = `image${nextNum}`;
    const href = `BinData/${itemId}.${ext}`;

    // Store binary data
    this._parts.set(href, data);

    // Update manifest: add <opf:item> element
    const manifestDoc = this.manifestTree();
    const root = manifestDoc.documentElement;

    // Find <manifest> element
    let manifestEl: Element | null = null;
    const walk = (node: Element): void => {
      const children = node.childNodes;
      for (let i = 0; i < children.length; i++) {
        const child = children.item(i);
        if (child && child.nodeType === 1) {
          const el = child as Element;
          const tag = el.localName ?? el.tagName;
          if (tag === "manifest") { manifestEl = el; return; }
          walk(el);
        }
      }
    };
    walk(root);

    if (manifestEl) {
      const item = manifestDoc.createElementNS(_OPF_NS, "opf:item");
      item.setAttribute("id", itemId);
      item.setAttribute("href", href);
      item.setAttribute("media-type", opts.mediaType);
      item.setAttribute("isEmbeded", "1");
      (manifestEl as Element).appendChild(item);

      // Persist updated manifest (serializeXml on Document includes <?xml?> declaration)
      const xml = serializeXml(manifestDoc as unknown as Node);
      this._parts.set(HwpxPackage.MANIFEST_PATH, new TextEncoder().encode(xml));
      // Keep cached tree (we just modified it)
    }

    // Invalidate caches that depend on manifest
    this._spineCache = null;
    this._sectionPathsCache = null;
    this._headerPathsCache = null;
    this._masterPagePathsCache = null;
    this._historyPathsCache = null;
    this._versionPathCache = null;
    this._versionPathCacheResolved = false;

    return itemId;
  }

  // -- Saving --

  async save(updates?: Record<string, Uint8Array | string>): Promise<Uint8Array> {
    this._assertOpen();
    if (updates) {
      for (const [partName, payload] of Object.entries(updates)) {
        this.setPart(partName, payload);
      }
    }

    const zip = new JSZip();
    const mimetype = this._parts.get(HwpxPackage.MIMETYPE_PATH);
    if (mimetype) {
      zip.file(HwpxPackage.MIMETYPE_PATH, mimetype, { compression: "STORE" });
    }

    for (const [name, data] of this._parts.entries()) {
      if (name === HwpxPackage.MIMETYPE_PATH) continue;
      zip.file(name, data, { compression: "DEFLATE" });
    }
    return zip.generateAsync({ type: "uint8array", compression: "DEFLATE" });
  }
}
