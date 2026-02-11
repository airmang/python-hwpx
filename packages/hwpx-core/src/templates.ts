/**
 * Skeleton.hwpx template loading.
 * Browser-compatible: use setSkeletonHwpx() or fetchSkeletonHwpx() to provide the template.
 * Node.js: use loadSkeletonHwpx() which auto-detects the environment.
 */

let _cachedSkeleton: Uint8Array | null = null;

/**
 * Load the Skeleton.hwpx template as a Uint8Array.
 * In Node.js, dynamically imports 'fs' to read from the assets directory.
 * In browsers, throws if setSkeletonHwpx() was not called first.
 * Caches the result for subsequent calls.
 */
export function loadSkeletonHwpx(): Uint8Array {
  if (_cachedSkeleton != null) return _cachedSkeleton;

  // Check if we're in a Node.js environment
  if (typeof process !== "undefined" && process.versions?.node) {
    try {
      // Dynamic require to avoid bundler issues
      const fs = require("fs");
      const path = require("path");
      const skeletonPath = path.resolve(__dirname, "..", "assets", "Skeleton.hwpx");
      _cachedSkeleton = new Uint8Array(fs.readFileSync(skeletonPath));
      return _cachedSkeleton;
    } catch {
      // Fallback: try relative to process.cwd
      try {
        const fs = require("fs");
        const path = require("path");
        const skeletonPath = path.resolve(process.cwd(), "packages", "hwpx-core", "assets", "Skeleton.hwpx");
        _cachedSkeleton = new Uint8Array(fs.readFileSync(skeletonPath));
        return _cachedSkeleton;
      } catch {
        // Fall through to error
      }
    }
  }

  throw new Error(
    "Skeleton.hwpx template not loaded. " +
    "In browser environments, call setSkeletonHwpx(data) or fetchSkeletonHwpx(url) before using this function.",
  );
}

/**
 * Set the Skeleton.hwpx template from a provided Uint8Array.
 * Use this in browser environments where fs is not available.
 */
export function setSkeletonHwpx(data: Uint8Array): void {
  _cachedSkeleton = data;
}

/**
 * Fetch and cache the Skeleton.hwpx template from a URL.
 * Convenience method for browser environments.
 */
export async function fetchSkeletonHwpx(url: string): Promise<Uint8Array> {
  if (_cachedSkeleton != null) return _cachedSkeleton;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch Skeleton.hwpx from ${url}: ${res.status}`);
  const buf = await res.arrayBuffer();
  _cachedSkeleton = new Uint8Array(buf);
  return _cachedSkeleton;
}
