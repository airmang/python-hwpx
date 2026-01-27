/**
 * Skeleton.hwpx template loading.
 * Ported from Python hwpx/templates.py
 */

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

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
