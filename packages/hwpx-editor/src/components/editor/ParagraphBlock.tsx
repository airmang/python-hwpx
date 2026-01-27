"use client";

import { useRef, useCallback } from "react";
import type { ParagraphVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { RunSpan } from "./RunSpan";
import { TableBlock } from "./TableBlock";
import { ImageBlock } from "./ImageBlock";

interface ParagraphBlockProps {
  paragraph: ParagraphVM;
  sectionIndex: number;
  /** Index of this paragraph within the section's paragraphs array */
  localIndex: number;
}

function alignmentToCSS(alignment: string): React.CSSProperties["textAlign"] {
  switch (alignment.toUpperCase()) {
    case "CENTER":
      return "center";
    case "RIGHT":
      return "right";
    case "JUSTIFY":
    case "DISTRIBUTE":
      return "justify";
    default:
      return "left";
  }
}

export function ParagraphBlock({
  paragraph,
  sectionIndex,
  localIndex,
}: ParagraphBlockProps) {
  const updateParagraphText = useEditorStore((s) => s.updateParagraphText);
  const setSelection = useEditorStore((s) => s.setSelection);
  const ref = useRef<HTMLDivElement>(null);

  const hasTables = paragraph.tables.length > 0;
  const hasImages = paragraph.images.length > 0;
  const hasText = paragraph.runs.length > 0;

  const handleBlur = useCallback(() => {
    if (!ref.current) return;
    const newText = ref.current.textContent ?? "";
    // Only sync text paragraphs (no tables/images)
    if (!hasTables && !hasImages) {
      const oldText = paragraph.runs.map((r) => r.text).join("");
      if (newText !== oldText) {
        updateParagraphText(sectionIndex, localIndex, newText);
      }
    }
  }, [paragraph, sectionIndex, localIndex, hasTables, hasImages, updateParagraphText]);

  const handleFocus = useCallback(() => {
    setSelection({
      sectionIndex,
      paragraphIndex: localIndex,
      type: "paragraph",
    });
  }, [sectionIndex, localIndex, setSelection]);

  // Common paragraph styles
  const paraStyle: React.CSSProperties = {
    textAlign: alignmentToCSS(paragraph.alignment),
    lineHeight: paragraph.lineSpacing,
    marginLeft: paragraph.marginLeftPx || undefined,
    marginRight: paragraph.marginRightPx || undefined,
    textIndent: paragraph.firstLineIndent || undefined,
    paddingTop: paragraph.spacingBefore || undefined,
    paddingBottom: paragraph.spacingAfter || undefined,
  };

  // If paragraph has tables, render them
  if (hasTables) {
    return (
      <div className="my-1" style={paraStyle}>
        {hasText && (
          <div
            ref={ref}
            contentEditable
            suppressContentEditableWarning
            onBlur={handleBlur}
            onFocus={handleFocus}
            className="outline-none leading-relaxed"
          >
            {paragraph.runs.map((run, i) => (
              <RunSpan key={i} run={run} />
            ))}
          </div>
        )}
        {paragraph.tables.map((table) => (
          <TableBlock
            key={table.tableIndex}
            table={table}
            sectionIndex={sectionIndex}
            paragraphIndex={localIndex}
          />
        ))}
      </div>
    );
  }

  // If paragraph has images, render them
  if (hasImages) {
    return (
      <div className="my-1" style={paraStyle}>
        {paragraph.images.map((img, i) => (
          <ImageBlock key={i} image={img} />
        ))}
      </div>
    );
  }

  // Normal text paragraph
  return (
    <div
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      onBlur={handleBlur}
      onFocus={handleFocus}
      className="outline-none min-h-[1.5em]"
      style={paraStyle}
    >
      {paragraph.runs.length > 0 ? (
        paragraph.runs.map((run, i) => <RunSpan key={i} run={run} />)
      ) : (
        <br />
      )}
    </div>
  );
}
