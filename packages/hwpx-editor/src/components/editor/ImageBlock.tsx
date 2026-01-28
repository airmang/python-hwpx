"use client";

import { useRef, useCallback, useState } from "react";
import type { ImageVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { pxToHwp } from "@/lib/hwp-units";

interface ImageBlockProps {
  image: ImageVM;
  selected?: boolean;
  onClick?: () => void;
}

type HandlePosition = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

const HANDLE_CURSORS: Record<HandlePosition, string> = {
  nw: "nwse-resize",
  n: "ns-resize",
  ne: "nesw-resize",
  e: "ew-resize",
  se: "nwse-resize",
  s: "ns-resize",
  sw: "nesw-resize",
  w: "ew-resize",
};

function ResizeHandle({
  position,
  onResize,
}: {
  position: HandlePosition;
  onResize: (deltaW: number, deltaH: number) => void;
}) {
  const startRef = useRef({ x: 0, y: 0 });

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      startRef.current = { x: e.clientX, y: e.clientY };

      const onMouseUp = (me: MouseEvent) => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";

        let dx = me.clientX - startRef.current.x;
        let dy = me.clientY - startRef.current.y;

        // Map handle position to delta
        let dw = 0;
        let dh = 0;
        if (position.includes("e")) dw = dx;
        if (position.includes("w")) dw = -dx;
        if (position.includes("s")) dh = dy;
        if (position.includes("n")) dh = -dy;

        // Corner handles: maintain aspect ratio
        if (position === "nw" || position === "ne" || position === "sw" || position === "se") {
          // Use the larger delta as driver
          if (Math.abs(dw) > Math.abs(dh)) {
            dh = dw; // rough 1:1 aspect
          } else {
            dw = dh;
          }
        }

        if (Math.abs(dw) >= 2 || Math.abs(dh) >= 2) {
          onResize(pxToHwp(dw), pxToHwp(dh));
        }
      };

      const onMouseMove = (_me: MouseEvent) => {
        // visual feedback via cursor only
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
      document.body.style.cursor = HANDLE_CURSORS[position];
    },
    [position, onResize],
  );

  // Position styles for each handle
  const posStyles: React.CSSProperties = { position: "absolute" };
  const SIZE = 8;
  const HALF = -SIZE / 2;

  switch (position) {
    case "nw": posStyles.top = HALF; posStyles.left = HALF; break;
    case "n": posStyles.top = HALF; posStyles.left = "50%"; posStyles.marginLeft = HALF; break;
    case "ne": posStyles.top = HALF; posStyles.right = HALF; break;
    case "e": posStyles.top = "50%"; posStyles.marginTop = HALF; posStyles.right = HALF; break;
    case "se": posStyles.bottom = HALF; posStyles.right = HALF; break;
    case "s": posStyles.bottom = HALF; posStyles.left = "50%"; posStyles.marginLeft = HALF; break;
    case "sw": posStyles.bottom = HALF; posStyles.left = HALF; break;
    case "w": posStyles.top = "50%"; posStyles.marginTop = HALF; posStyles.left = HALF; break;
  }

  return (
    <div
      onMouseDown={onMouseDown}
      className="bg-white border border-blue-500 z-20"
      style={{
        ...posStyles,
        width: SIZE,
        height: SIZE,
        cursor: HANDLE_CURSORS[position],
      }}
    />
  );
}

const HANDLES: HandlePosition[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

export function ImageBlock({ image, selected, onClick }: ImageBlockProps) {
  const resizeImage = useEditorStore((s) => s.resizeImage);

  const handleResize = useCallback(
    (dw: number, dh: number) => {
      resizeImage(dw, dh);
    },
    [resizeImage],
  );

  return (
    <div
      className="my-2 flex justify-center cursor-pointer"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
    >
      <div className="relative inline-block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={image.dataUrl}
          alt=""
          draggable={false}
          className={selected ? "ring-2 ring-blue-500" : ""}
          style={{
            width: image.widthPx > 0 ? image.widthPx : undefined,
            height: image.heightPx > 0 ? image.heightPx : undefined,
            maxWidth: "100%",
            display: "block",
          }}
        />
        {selected && HANDLES.map((pos) => (
          <ResizeHandle key={pos} position={pos} onResize={handleResize} />
        ))}
      </div>
    </div>
  );
}
