"use client";

import type { ImageVM } from "@/lib/view-model";

interface ImageBlockProps {
  image: ImageVM;
  selected?: boolean;
  onClick?: () => void;
}

export function ImageBlock({ image, selected, onClick }: ImageBlockProps) {
  return (
    <div
      className="my-2 flex justify-center cursor-pointer"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={image.dataUrl}
        alt=""
        className={selected ? "ring-2 ring-blue-500" : ""}
        style={{
          width: image.widthPx > 0 ? image.widthPx : undefined,
          height: image.heightPx > 0 ? image.heightPx : undefined,
          maxWidth: "100%",
        }}
      />
    </div>
  );
}
