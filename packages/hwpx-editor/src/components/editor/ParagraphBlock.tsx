"use client";

import { useRef, useCallback, useEffect } from "react";
import type { ParagraphVM } from "@/lib/view-model";
import { useEditorStore } from "@/lib/store";
import { fontFamilyCssStack } from "@/lib/constants";
import { RunSpan } from "./RunSpan";
import { TableBlock } from "./TableBlock";
import { ImageBlock } from "./ImageBlock";
import { TextBoxBlock } from "./TextBoxBlock";
import { EquationBlock } from "./EquationBlock";

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

  const revision = useEditorStore((s) => s.revision);
  const hasTables = paragraph.tables.length > 0;
  const hasImages = paragraph.images.length > 0;
  const hasTextBoxes = paragraph.textBoxes.length > 0;
  const hasEquations = paragraph.equations.length > 0;
  const hasText = paragraph.runs.length > 0;

  // Auto-focus when this paragraph is selected (e.g. after splitParagraph)
  useEffect(() => {
    if (
      selection &&
      selection.sectionIndex === sectionIndex &&
      selection.paragraphIndex === localIndex &&
      selection.type === "paragraph" &&
      !selection.objectType &&
      ref.current &&
      document.activeElement !== ref.current
    ) {
      ref.current.focus();
      // Place cursor at start
      const sel = window.getSelection();
      if (sel) {
        sel.selectAllChildren(ref.current);
        sel.collapseToStart();
      }
    }
  }, [revision, sectionIndex, localIndex, selection]);

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

  // Track text selection changes within this paragraph
  const updateTextSelection = useCallback(() => {
    if (!ref.current) return;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;

    // Check if selection is within this paragraph
    const range = sel.getRangeAt(0);
    if (!ref.current.contains(range.commonAncestorContainer)) return;

    // Calculate start and end offsets relative to the entire paragraph text
    const preRangeStart = document.createRange();
    preRangeStart.selectNodeContents(ref.current);
    preRangeStart.setEnd(range.startContainer, range.startOffset);
    const startOffset = preRangeStart.toString().length;

    const preRangeEnd = document.createRange();
    preRangeEnd.selectNodeContents(ref.current);
    preRangeEnd.setEnd(range.endContainer, range.endOffset);
    const endOffset = preRangeEnd.toString().length;

    // Only update if there's an actual selection (not just cursor)
    if (startOffset !== endOffset) {
      setSelection({
        sectionIndex,
        paragraphIndex: localIndex,
        type: "paragraph",
        textStartOffset: startOffset,
        textEndOffset: endOffset,
      });
    } else {
      // Clear text range when selection is collapsed (cursor only)
      setSelection({
        sectionIndex,
        paragraphIndex: localIndex,
        type: "paragraph",
      });
    }
  }, [sectionIndex, localIndex, setSelection]);

  // Listen for selection changes
  useEffect(() => {
    const handleSelectionChange = () => {
      if (document.activeElement === ref.current) {
        updateTextSelection();
      }
    };

    document.addEventListener("selectionchange", handleSelectionChange);
    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
    };
  }, [updateTextSelection]);

  const insertTab = useEditorStore((s) => s.insertTab);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (hasTables || hasImages || hasTextBoxes || hasEquations) return;

      // Tab key: insert tab character
      if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        insertTab();
        return;
      }

      // Block Shift+Enter (no soft line break)
      if (e.key === "Enter" && e.shiftKey) {
        e.preventDefault();
        return;
      }

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
      // Arrow key navigation between paragraphs
      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        const sel = window.getSelection();
        if (!sel || !sel.isCollapsed || !sel.rangeCount || !ref.current) return;

        const range = sel.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        const containerRect = ref.current.getBoundingClientRect();

        const atTop = rect.top <= containerRect.top + 2;
        const atBottom = rect.bottom >= containerRect.bottom - 2;

        if (e.key === "ArrowUp" && atTop && localIndex > 0) {
          e.preventDefault();
          const prev = ref.current.parentElement
            ? ref.current.previousElementSibling as HTMLElement | null
            : null;
          // Find previous contenteditable sibling within the page
          const page = ref.current.closest("[data-page]") ?? ref.current.parentElement;
          if (page) {
            const editables = page.querySelectorAll<HTMLElement>("[contenteditable]");
            const arr = Array.from(editables);
            const idx = arr.indexOf(ref.current);
            if (idx > 0) {
              const target = arr[idx - 1]!;
              target.focus();
              // Place cursor at end
              const s = window.getSelection();
              if (s) { s.selectAllChildren(target); s.collapseToEnd(); }
            }
          }
          return;
        }

        if (e.key === "ArrowDown" && atBottom && localIndex < paragraphCount - 1) {
          e.preventDefault();
          const page = ref.current.closest("[data-page]") ?? ref.current.parentElement;
          if (page) {
            const editables = page.querySelectorAll<HTMLElement>("[contenteditable]");
            const arr = Array.from(editables);
            const idx = arr.indexOf(ref.current);
            if (idx >= 0 && idx < arr.length - 1) {
              const target = arr[idx + 1]!;
              target.focus();
              // Place cursor at start
              const s = window.getSelection();
              if (s) { s.selectAllChildren(target); s.collapseToStart(); }
            }
          }
          return;
        }
      }
    },
    [sectionIndex, localIndex, paragraph, hasTables, hasImages, hasTextBoxes, hasEquations, paragraphCount, splitParagraph, mergeParagraphWithPrevious, deleteBlock, updateParagraphText, insertTab],
  );

  // Common paragraph styles (includes base font for contentEditable typing)
  const paraStyle: React.CSSProperties = {
    textAlign: alignmentToCSS(paragraph.alignment),
    lineHeight: paragraph.lineSpacing,
    marginLeft: paragraph.marginLeftPx || undefined,
    marginRight: paragraph.marginRightPx || undefined,
    textIndent: paragraph.firstLineIndent || undefined,
    paddingTop: paragraph.spacingBefore || undefined,
    paddingBottom: paragraph.spacingAfter || undefined,
    fontSize: paragraph.defaultFontSize ? `${paragraph.defaultFontSize}pt` : undefined,
    fontFamily: paragraph.defaultFontFamily ? fontFamilyCssStack(paragraph.defaultFontFamily) : undefined,
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
            onKeyDown={handleKeyDown}
            className="outline-none leading-relaxed caret-gray-900"
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
            onKeyDown={handleKeyDown}
            className="outline-none leading-relaxed caret-gray-900"
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

  // If paragraph has text boxes, render them
  if (hasTextBoxes) {
    return (
      <div className="my-1" style={paraStyle}>
        {hasText && (
          <div
            ref={ref}
            contentEditable
            suppressContentEditableWarning
            onBlur={handleBlur}
            onFocus={handleFocus}
            onKeyDown={handleKeyDown}
            className="outline-none leading-relaxed caret-gray-900"
          >
            {paragraph.runs.map((run, i) => (
              <RunSpan key={i} run={run} />
            ))}
          </div>
        )}
        {paragraph.textBoxes.map((tb, i) => (
          <TextBoxBlock
            key={i}
            textBox={tb}
            selected={
              selection?.sectionIndex === sectionIndex &&
              selection?.paragraphIndex === localIndex &&
              selection?.objectType === "textBox" &&
              selection?.textBoxIndex === i
            }
            onClick={() =>
              setSelection({
                sectionIndex,
                paragraphIndex: localIndex,
                type: "paragraph",
                objectType: "textBox",
                textBoxIndex: i,
              })
            }
          />
        ))}
      </div>
    );
  }

  // If paragraph has equations, render them
  if (hasEquations) {
    return (
      <div className="my-1" style={paraStyle}>
        {hasText && (
          <span>
            {paragraph.runs.map((run, i) => (
              <RunSpan key={i} run={run} />
            ))}
          </span>
        )}
        {paragraph.equations.map((eq, i) => (
          <EquationBlock key={i} equation={eq} />
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
      className="outline-none min-h-[1.5em] caret-gray-900"
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
