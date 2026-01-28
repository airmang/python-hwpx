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
  /** Total number of paragraphs in this section (for merge/delete bounds) */
  paragraphCount: number;
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
  paragraphCount,
}: ParagraphBlockProps) {
  const updateParagraphText = useEditorStore((s) => s.updateParagraphText);
  const setSelection = useEditorStore((s) => s.setSelection);
  const selection = useEditorStore((s) => s.selection);
  const splitParagraph = useEditorStore((s) => s.splitParagraph);
  const mergeParagraphWithPrevious = useEditorStore((s) => s.mergeParagraphWithPrevious);
  const deleteBlock = useEditorStore((s) => s.deleteBlock);
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

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (hasTables || hasImages) return;

      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        // Flush current text before split
        const currentText = ref.current?.textContent ?? "";
        const oldText = paragraph.runs.map((r) => r.text).join("");
        if (currentText !== oldText) {
          updateParagraphText(sectionIndex, localIndex, currentText);
        }

        // Get cursor offset within the text
        const sel = window.getSelection();
        let offset = currentText.length;
        if (sel && sel.rangeCount > 0 && ref.current) {
          const range = sel.getRangeAt(0);
          const preRange = document.createRange();
          preRange.selectNodeContents(ref.current);
          preRange.setEnd(range.startContainer, range.startOffset);
          offset = preRange.toString().length;
        }

        splitParagraph(sectionIndex, localIndex, offset);
        return;
      }

      if (e.key === "Backspace") {
        const sel = window.getSelection();
        if (sel && sel.isCollapsed && sel.rangeCount > 0 && ref.current) {
          const range = sel.getRangeAt(0);
          const preRange = document.createRange();
          preRange.selectNodeContents(ref.current);
          preRange.setEnd(range.startContainer, range.startOffset);
          const offset = preRange.toString().length;

          if (offset === 0 && localIndex > 0) {
            e.preventDefault();
            // Flush current text
            const currentText = ref.current.textContent ?? "";
            const oldText = paragraph.runs.map((r) => r.text).join("");
            if (currentText !== oldText) {
              updateParagraphText(sectionIndex, localIndex, currentText);
            }
            mergeParagraphWithPrevious(sectionIndex, localIndex);
            return;
          }
        }
      }

      if (e.key === "Delete") {
        const sel = window.getSelection();
        if (sel && sel.isCollapsed && sel.rangeCount > 0 && ref.current) {
          const fullText = ref.current.textContent ?? "";
          const range = sel.getRangeAt(0);
          const preRange = document.createRange();
          preRange.selectNodeContents(ref.current);
          preRange.setEnd(range.startContainer, range.startOffset);
          const offset = preRange.toString().length;

          // At end of paragraph: merge with next
          if (offset >= fullText.length && localIndex < paragraphCount - 1) {
            e.preventDefault();
            // Flush current text
            const oldText = paragraph.runs.map((r) => r.text).join("");
            if (fullText !== oldText) {
              updateParagraphText(sectionIndex, localIndex, fullText);
            }
            // Merge next paragraph into this one (implemented as merging next with "previous" = current)
            const store = useEditorStore.getState();
            const doc = store.doc;
            if (!doc) return;
            store.pushUndo();
            const section = doc.sections[sectionIndex];
            if (!section) return;
            const nextPara = section.paragraphs[localIndex + 1];
            const currPara = section.paragraphs[localIndex];
            if (!nextPara || !currPara) return;
            const currText = currPara.text;
            const nextText = nextPara.text;
            currPara.text = currText + nextText;
            doc.removeParagraph(sectionIndex, localIndex + 1);
            store.rebuild();
            return;
          }
        }
      }
    },
    [sectionIndex, localIndex, paragraph, hasTables, hasImages, paragraphCount, splitParagraph, mergeParagraphWithPrevious, deleteBlock, updateParagraphText],
  );

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

  // If paragraph has images, render them (possibly alongside text)
  if (hasImages) {
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
        {paragraph.images.map((img, i) => (
          <ImageBlock
            key={i}
            image={img}
            selected={
              selection?.sectionIndex === sectionIndex &&
              selection?.paragraphIndex === localIndex &&
              selection?.objectType === "image" &&
              selection?.imageIndex === i
            }
            onClick={() =>
              setSelection({
                sectionIndex,
                paragraphIndex: localIndex,
                type: "paragraph",
                objectType: "image",
                imageIndex: i,
              })
            }
          />
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
      onKeyDown={handleKeyDown}
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
