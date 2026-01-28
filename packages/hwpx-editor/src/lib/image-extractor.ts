/**
 * Extract binary image data from an HwpxDocument package as data URLs.
 */

import type { HwpxPackage } from "@ubermensch1218/hwpxcore";

/** Map of binaryItemIdRef → data:... URL for all images in the package. */
export function extractImages(pkg: HwpxPackage): Map<string, string> {
  const images = new Map<string, string>();
  const partNames = pkg.partNames();

  for (const name of partNames) {
    if (!name.startsWith("BinData/")) continue;

    const ext = name.split(".").pop()?.toLowerCase() ?? "";
    let mediaType = "application/octet-stream";
    if (ext === "png") mediaType = "image/png";
    else if (ext === "jpg" || ext === "jpeg") mediaType = "image/jpeg";
    else if (ext === "gif") mediaType = "image/gif";
    else if (ext === "bmp") mediaType = "image/bmp";
    else if (ext === "svg") mediaType = "image/svg+xml";
    else if (ext === "webp") mediaType = "image/webp";
    else if (ext === "tif" || ext === "tiff") mediaType = "image/tiff";
    else if (ext === "emf") mediaType = "image/x-emf";
    else if (ext === "wmf") mediaType = "image/x-wmf";

    try {
      const data = pkg.getPart(name);
      const base64 = uint8ToBase64(data);
      const dataUrl = `data:${mediaType};base64,${base64}`;

      // Store with the filename (e.g. "image1.png")
      const fileName = name.replace("BinData/", "");
      images.set(fileName, dataUrl);
    } catch {
      // Skip parts that can't be read
    }
  }

  return images;
}

function uint8ToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]!);
  }
  return btoa(binary);
}
