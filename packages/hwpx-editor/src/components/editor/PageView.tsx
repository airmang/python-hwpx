"use client";

import type { ReactNode } from "react";
import { useEditorStore } from "@/lib/store";
import { Page } from "./Page";

interface PageViewProps {
  leftCanvasSlot?: ReactNode;
}

export function PageView({ leftCanvasSlot }: PageViewProps = {}) {
  const viewModel = useEditorStore((s) => s.viewModel);
  // Subscribe to revision to trigger re-render
  useEditorStore((s) => s.revision);
  const hasLeftCanvasSlot = Boolean(leftCanvasSlot);
  const sideRailWidth = hasLeftCanvasSlot ? 132 : 0;

  if (!viewModel) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        문서를 열거나 새 문서를 만드세요.
      </div>
    );
  }

  return (
    <div
      data-hwpx-scroll-container="true"
      className="flex-1 min-h-0 bg-gray-200 py-8"
      style={{ overflowY: "auto", overflowX: "auto" }}
    >
      <div
        className="mx-auto grid w-full max-w-[1720px] gap-4 px-3"
        style={{
          gridTemplateColumns: `${sideRailWidth}px minmax(760px, 1fr) ${sideRailWidth}px`,
          minWidth: hasLeftCanvasSlot ? "1060px" : "760px",
        }}
      >
        <aside>
          {leftCanvasSlot ? <div className="sticky top-3">{leftCanvasSlot}</div> : null}
        </aside>
        <div>
          {viewModel.sections.map((section) => (
            <Page key={section.sectionIndex} section={section} />
          ))}
        </div>
        <div aria-hidden="true" />
      </div>
    </div>
  );
}
