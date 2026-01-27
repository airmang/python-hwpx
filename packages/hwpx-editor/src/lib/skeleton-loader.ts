/**
 * Browser-side Skeleton.hwpx loader.
 * Fetches from /Skeleton.hwpx and calls setSkeletonHwpx() to register it.
 */

import { setSkeletonHwpx, HwpxDocument } from "@hwpx/core";

let loaded = false;

/** Fetch Skeleton.hwpx from the public folder and register it with @hwpx/core. */
export async function ensureSkeletonLoaded(): Promise<void> {
  if (loaded) return;
  const res = await fetch("/Skeleton.hwpx");
  if (!res.ok) throw new Error(`Failed to fetch Skeleton.hwpx: ${res.status}`);
  const buf = await res.arrayBuffer();
  setSkeletonHwpx(new Uint8Array(buf));
  loaded = true;
}

/** Create a new empty HwpxDocument from the skeleton template. */
export async function createNewDocument(): Promise<HwpxDocument> {
  await ensureSkeletonLoaded();
  const res = await fetch("/Skeleton.hwpx");
  const buf = await res.arrayBuffer();
  return HwpxDocument.open(buf);
}
