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
  const watermarkText = useEditorStore((s) => s.viewModel?.watermarkText ?? "");

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

  const hasHeader = section.headerText.length > 0;
  const hasFooter = section.footerText.length > 0;
  const hasFootnotes = section.footnotes.length > 0;
  const hasEndnotes = section.endnotes.length > 0;
  const hasMultiColumn = section.columnLayout.colCount > 1;
  const pageNum = section.pageNum;

  // Format page number based on pageNum settings
  const formatPageNum = (num: number): string => {
    if (!pageNum) return String(num);
    let formatted = String(num);
    if (pageNum.formatType === "ROMAN") {
      // Convert to Roman numerals (simplified)
      const romanNumerals = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
      formatted = romanNumerals[num] ?? String(num);
    }
    if (pageNum.sideChar) {
      formatted = `${pageNum.sideChar} ${formatted} ${pageNum.sideChar}`;
    }
    return formatted;
  };

  // Determine page number position
  const pageNumAtTop = pageNum?.pos?.startsWith("TOP");
  const pageNumAtBottom = pageNum?.pos?.startsWith("BOTTOM") || (pageNum && !pageNumAtTop);

  // Page border styling
  const hasPageBorder = section.pageBorderFill !== null;
  const pageBorderStyle: React.CSSProperties = hasPageBorder ? {
    border: "1px solid #cccccc",
  } : {};

  return (
    <div
      className="bg-white shadow-lg mx-auto mb-8 cursor-text relative overflow-hidden"
      data-page
      onClick={handlePageClick}
      style={{
        width: section.pageWidthPx,
        minHeight: section.pageHeightPx,
        ...pageBorderStyle,
      }}
    >
      {/* Watermark overlay */}
      {watermarkText && (
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none select-none z-0"
          aria-hidden="true"
        >
          <span
            className="text-gray-200 font-bold whitespace-nowrap"
            style={{
              fontSize: Math.min(section.pageWidthPx * 0.12, 120),
              transform: "rotate(-35deg)",
              letterSpacing: "0.15em",
              opacity: 0.35,
            }}
          >
            {watermarkText}
          </span>
        </div>
      )}

      {/* Header area */}
      {(hasHeader || pageNumAtTop) && (
        <div
          className="text-center text-[10px] text-gray-400 border-b border-gray-100 relative z-10"
          style={{
            paddingLeft: section.marginLeftPx,
            paddingRight: section.marginRightPx,
            paddingTop: Math.max(section.headerHeightPx, 8),
            paddingBottom: 4,
          }}
        >
          {hasHeader ? section.headerText.replace("{{page}}", "1") : null}
          {pageNumAtTop && !hasHeader && formatPageNum(1)}
        </div>
      )}

      {/* Main content area */}
      <div
        className="relative z-10"
        style={{
          paddingTop: hasHeader ? 4 : section.marginTopPx,
          paddingBottom: hasFooter || hasFootnotes || hasEndnotes ? 4 : section.marginBottomPx,
          paddingLeft: section.marginLeftPx,
          paddingRight: section.marginRightPx,
          minHeight: section.pageHeightPx - section.marginTopPx - section.marginBottomPx,
          // Multi-column CSS
          ...(hasMultiColumn ? {
            columnCount: section.columnLayout.colCount,
            columnGap: section.columnLayout.sameGap || 20,
            columnRule: "1px solid #e5e7eb",
          } : {}),
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

      {/* Footnotes area */}
      {hasFootnotes && (
        <div
          className="relative z-10"
          style={{
            paddingLeft: section.marginLeftPx,
            paddingRight: section.marginRightPx,
            paddingBottom: 4,
          }}
        >
          <div className="border-t border-gray-300 pt-2 mt-2" style={{ width: "40%" }}>
            {section.footnotes.map((fn) => (
              <div key={fn.marker} className="text-[9px] text-gray-500 leading-relaxed mb-0.5">
                <sup className="text-[8px] font-medium mr-0.5">{fn.marker}</sup>
                {fn.text}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Endnotes area (rendered at section end) */}
      {hasEndnotes && (
        <div
          className="relative z-10"
          style={{
            paddingLeft: section.marginLeftPx,
            paddingRight: section.marginRightPx,
            paddingBottom: 4,
          }}
        >
          <div className="border-t-2 border-gray-300 pt-2 mt-4">
            <div className="text-[9px] text-gray-400 font-medium mb-1">미주</div>
            {section.endnotes.map((en) => (
              <div key={en.marker} className="text-[9px] text-gray-500 leading-relaxed mb-0.5">
                <sup className="text-[8px] font-medium mr-0.5">{en.marker}</sup>
                {en.text}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer area */}
      {(hasFooter || pageNumAtBottom) && (
        <div
          className="text-center text-[10px] text-gray-400 border-t border-gray-100 relative z-10"
          style={{
            paddingLeft: section.marginLeftPx,
            paddingRight: section.marginRightPx,
            paddingTop: 4,
            paddingBottom: Math.max(section.footerHeightPx, 8),
          }}
        >
          {hasFooter ? section.footerText.replace("{{page}}", "1") : null}
          {pageNumAtBottom && !hasFooter && formatPageNum(1)}
        </div>
      )}
    </div>
  );
}
