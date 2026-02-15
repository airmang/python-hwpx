/**
 * Skeleton.hwpx template loading.
 *
 * Browser: call setSkeletonHwpx() or fetchSkeletonHwpx() before calling loadSkeletonHwpx().
 * Node (CommonJS): loadSkeletonHwpx() reads from the packaged assets directory.
 *
 * Note: Node ESM does not provide `require()`; consumers should call setSkeletonHwpx()
 * or pass the template bytes directly to HwpxDocument.open().
 */

let _cachedSkeleton: Uint8Array | null = null;

/**
 * Load the Skeleton.hwpx template as a Uint8Array.
 * Caches the result for subsequent calls.
 */
export function loadSkeletonHwpx(): Uint8Array {
  if (_cachedSkeleton != null) return _cachedSkeleton;

  // Node.js (CommonJS only): use require() to avoid bundler resolution of node built-ins.
  if (typeof process !== "undefined" && process.versions?.node && typeof require !== "undefined") {
    try {
      const fs = require("fs");
      const path = require("path");
      const skeletonPath = path.resolve(__dirname, "..", "assets", "Skeleton.hwpx");
      _cachedSkeleton = new Uint8Array(fs.readFileSync(skeletonPath));
      return _cachedSkeleton;
    } catch {
      // Fallback: try relative to process.cwd (useful in monorepos)
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
      "In browser environments (or Node ESM), call setSkeletonHwpx(data) or fetchSkeletonHwpx(url) before using this function.",
  );
}

/**
 * Set the Skeleton.hwpx template from a provided Uint8Array.
 * Use this in browser environments (or Node ESM) where fs/require is not available.
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

