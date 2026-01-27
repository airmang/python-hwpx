"use client";

import { useEditorStore } from "@/lib/store";
import { Page } from "./Page";

export function PageView() {
  const viewModel = useEditorStore((s) => s.viewModel);
  // Subscribe to revision to trigger re-render
  useEditorStore((s) => s.revision);

  if (!viewModel) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        문서를 열거나 새 문서를 만드세요.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto bg-gray-200 py-8">
      {viewModel.sections.map((section) => (
        <Page key={section.sectionIndex} section={section} />
      ))}
    </div>
  );
}
