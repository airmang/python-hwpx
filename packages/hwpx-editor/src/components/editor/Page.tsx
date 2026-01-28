"use client";

import type { SectionVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { ParagraphBlock } from "./ParagraphBlock";

interface PageProps {
  section: SectionVM;
}

export function Page({ section }: PageProps) {
  const addParagraph = useEditorStore((s) => s.addParagraph);
  const revision = useEditorStore((s) => s.revision);

  /** Clicking empty area of the page focuses or creates a paragraph */
  const handlePageClick = (e: React.MouseEvent<HTMLDivElement>) => {
    // Only react to clicks directly on the page container (not on child elements)
    if (e.target !== e.currentTarget) return;
    // If no paragraphs exist, create one
    if (section.paragraphs.length === 0) {
      addParagraph("");
      return;
    }
    // Otherwise, focus the last paragraph's contenteditable
    const container = e.currentTarget;
    const editables = container.querySelectorAll<HTMLElement>("[contenteditable]");
    const last = editables[editables.length - 1];
    if (last) {
      last.focus();
      // Place cursor at end
      const sel = window.getSelection();
      if (sel) {
        sel.selectAllChildren(last);
        sel.collapseToEnd();
      }
    }
  };

  return (
    <div
      className="bg-white shadow-lg mx-auto mb-8 cursor-text"
      onClick={handlePageClick}
      style={{
        width: section.pageWidthPx,
        minHeight: section.pageHeightPx,
        paddingTop: section.marginTopPx,
        paddingBottom: section.marginBottomPx,
        paddingLeft: section.marginLeftPx,
        paddingRight: section.marginRightPx,
      }}
    >
      {section.paragraphs.map((para, idx) => (
        <ParagraphBlock
          key={`${section.sectionIndex}-${idx}-r${revision}`}
          paragraph={para}
          sectionIndex={section.sectionIndex}
          localIndex={idx}
          paragraphCount={section.paragraphs.length}
        />
      ))}
    </div>
  );
}
