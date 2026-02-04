/**
 * Skeleton.hwpx template loading.
 * Ported from Python hwpx/templates.py
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from "fs";
import { resolve, dirname, join } from "path";
import { fileURLToPath } from "url";
import { homedir } from "os";

let _cachedSkeleton: Uint8Array | null = null;

/**
 * Load the Skeleton.hwpx template as a Uint8Array.
 * In Node.js, reads from the assets directory.
 * Caches the result for subsequent calls.
 */
export function loadSkeletonHwpx(): Uint8Array {
  if (_cachedSkeleton != null) return _cachedSkeleton;

  // Resolve path relative to this module
  // In Node.js ESM, __dirname is not available
  try {
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = dirname(__filename);
    const skeletonPath = resolve(__dirname, "..", "assets", "Skeleton.hwpx");
    _cachedSkeleton = new Uint8Array(readFileSync(skeletonPath));
  } catch {
    // Fallback: try relative to process.cwd
    try {
      const skeletonPath = resolve(process.cwd(), "packages", "hwpx-core", "assets", "Skeleton.hwpx");
      _cachedSkeleton = new Uint8Array(readFileSync(skeletonPath));
    } catch {
      throw new Error(
        "Could not load Skeleton.hwpx template. Ensure the assets directory is available.",
      );
    }
  }

  return _cachedSkeleton;
}

/**
 * Load the Skeleton.hwpx template from a provided Uint8Array.
 * Useful in browser environments where fs is not available.
 */
export function setSkeletonHwpx(data: Uint8Array): void {
  _cachedSkeleton = data;
}

/**
 * Get the user templates directory path.
 * Creates the directory if it doesn't exist.
 */
export function getTemplatesDir(): string {
  const templatesDir = resolve(homedir(), ".hwpx-templates");
  if (!existsSync(templatesDir)) {
    mkdirSync(templatesDir, { recursive: true });
  }
  return templatesDir;
}

/**
 * Template metadata
 */
export interface TemplateInfo {
  id: string;
  name: string;
  description?: string;
  path: string;
  createdAt: number;
  thumbnail?: string;
}

/**
 * List all available templates in the user templates directory.
 */
export function listTemplates(): TemplateInfo[] {
  const templatesDir = getTemplatesDir();
  const templates: TemplateInfo[] = [];

  if (!existsSync(templatesDir)) {
    return templates;
  }

  const files = readdirSync(templatesDir);
  for (const file of files) {
    if (!file.endsWith(".hwpx")) continue;

    const filePath = join(templatesDir, file);
    const stat = readFileSync(filePath); // Just to check it exists
    const name = file.replace(".hwpx", "");

    templates.push({
      id: name,
      name,
      path: filePath,
      createdAt: 0, // TODO: Get actual file creation time
    });
  }

  return templates.sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Save the current document as a template.
 * @param data - HWPX file data as Uint8Array
 * @param name - Template name
 * @param description - Optional description
 * @returns The path to the saved template
 */
export function saveAsTemplate(data: Uint8Array, name: string, description?: string): string {
  const templatesDir = getTemplatesDir();
  const safeName = name.replace(/[^a-zA-Z0-9가-힣_\s-]/g, "_");
  const fileName = `${safeName}.hwpx`;
  const filePath = join(templatesDir, fileName);

  writeFileSync(filePath, Buffer.from(data));

  // Save metadata separately
  if (description) {
    const metaPath = join(templatesDir, `${safeName}.meta.json`);
    writeFileSync(metaPath, JSON.stringify({ name, description, createdAt: Date.now() }, null, 2));
  }

  return filePath;
}

/**
 * Load a template by name.
 * @param name - Template name (without .hwpx extension)
 * @returns The template file data as Uint8Array
 */
export function loadTemplate(name: string): Uint8Array {
  const templatesDir = getTemplatesDir();
  const safeName = name.replace(/[^a-zA-Z0-9가-힣_\s-]/g, "_");
  const filePath = join(templatesDir, `${safeName}.hwpx`);

  if (!existsSync(filePath)) {
    throw new Error(`Template not found: ${name}`);
  }

  return new Uint8Array(readFileSync(filePath));
}

/**
 * Delete a template by name.
 */
export function deleteTemplate(name: string): void {
  const templatesDir = getTemplatesDir();
  const safeName = name.replace(/[^a-zA-Z0-9가-힣_\s-]/g, "_");
  const filePath = join(templatesDir, `${safeName}.hwpx`);

  if (existsSync(filePath)) {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs");
    fs.unlinkSync(filePath);
  }

  // Also delete metadata if exists
  const metaPath = join(templatesDir, `${safeName}.meta.json`);
  if (existsSync(metaPath)) {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs");
    fs.unlinkSync(metaPath);
  }
}

/**
 * Book template options
 */
export interface BookTemplateOptions {
  title: string;
  subtitle?: string;
  author?: string;
  publisher?: string;
  publishDate?: string;
  copyright?: string;
  includeToc?: boolean;
  tocTitle?: string;
  tocTabLeader?: "DOT" | "HYPHEN" | "UNDERLINE" | "NONE";
}
