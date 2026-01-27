"use client";

import type { ImageVM } from "@/lib/view-model";

interface ImageBlockProps {
  image: ImageVM;
}

export function ImageBlock({ image }: ImageBlockProps) {
  return (
    <div className="my-2 flex justify-center">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={image.dataUrl}
        alt=""
        style={{
          width: image.widthPx > 0 ? image.widthPx : undefined,
          height: image.heightPx > 0 ? image.heightPx : undefined,
          maxWidth: "100%",
        }}
      />
    </div>
  );
}
