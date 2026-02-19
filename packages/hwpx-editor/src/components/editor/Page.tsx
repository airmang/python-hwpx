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
  const totalPages = useEditorStore((s) => s.viewModel?.sections.length ?? 1);

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
  const contentPaddingTop = hasHeader ? 4 : section.marginTopPx;
  const contentPaddingBottom = hasFooter || hasFootnotes || hasEndnotes ? 4 : section.marginBottomPx;

  const currentPageNumber = Math.max(1, section.startPageNumber || 1);

  const toRoman = (value: number, lower = false): string => {
    if (value <= 0 || value >= 4000) return String(value);
    const map: Array<[number, string]> = [
      [1000, "M"], [900, "CM"], [500, "D"], [400, "CD"],
      [100, "C"], [90, "XC"], [50, "L"], [40, "XL"],
      [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"],
    ];
    let n = value;
    let out = "";
    for (const [num, symbol] of map) {
      while (n >= num) {
        out += symbol;
        n -= num;
      }
    }
    return lower ? out.toLowerCase() : out;
  };

  const toAlpha = (value: number, lower = false): string => {
    if (value <= 0) return String(value);
    let n = value;
    let out = "";
    while (n > 0) {
      n -= 1;
      out = String.fromCharCode(65 + (n % 26)) + out;
      n = Math.floor(n / 26);
    }
    return lower ? out.toLowerCase() : out;
  };

  // Format page number based on pageNum settings
  const formatPageNum = (num: number): string => {
    if (!pageNum) return String(num);
    let formatted = String(num);
    const formatType = pageNum.formatType?.toUpperCase() ?? "DIGIT";
    if (formatType === "ROMAN") {
      formatted = toRoman(num, false);
    } else if (formatType === "ROMAN_LOWER") {
      formatted = toRoman(num, true);
    } else if (formatType === "ALPHA_UPPER") {
      formatted = toAlpha(num, false);
    } else if (formatType === "ALPHA_LOWER") {
      formatted = toAlpha(num, true);
    } else if (formatType === "KOREAN") {
      const arr = ["", "가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타", "파", "하"];
      formatted = arr[num] ?? String(num);
    } else if (formatType === "HANJA") {
      const arr = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
      formatted = arr[num] ?? String(num);
    }
    if (pageNum.sideChar) {
      formatted = `${pageNum.sideChar} ${formatted} ${pageNum.sideChar}`;
    }
    return formatted;
  };

  const renderHeaderFooterText = (text: string): string => {
    const today = new Date().toLocaleDateString("ko-KR");
    return text
      .replace(/\{\{page\}\}/g, formatPageNum(currentPageNumber))
      .replace(/\{\{total\}\}/g, String(totalPages))
      .replace(/\{\{date\}\}/g, today);
  };

  // Determine page number position
  const pageNumAtTop = pageNum?.pos?.startsWith("TOP");
  const pageNumAtBottom = pageNum?.pos?.startsWith("BOTTOM") || (pageNum && !pageNumAtTop);
  const pageBoundaryLineY = Math.max(section.pageHeightPx - 1, 0);

  const normalizeTextAlign = (value?: string | null): React.CSSProperties["textAlign"] => {
    const normalized = value?.toUpperCase();
    if (normalized === "LEFT") return "left";
    if (normalized === "RIGHT") return "right";
    return "center";
  };

  const pageNumTextAlign = (pos?: string | null): React.CSSProperties["textAlign"] => {
    const normalized = pos?.toUpperCase() ?? "";
    if (normalized.includes("LEFT")) return "left";
    if (normalized.includes("RIGHT")) return "right";
    return "center";
  };

  const headerTextAlign = hasHeader
    ? normalizeTextAlign(section.headerAlign)
    : pageNumTextAlign(pageNum?.pos);
  const footerTextAlign = hasFooter
    ? normalizeTextAlign(section.footerAlign)
    : pageNumTextAlign(pageNum?.pos);

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
        backgroundImage: `repeating-linear-gradient(to bottom, transparent 0px, transparent ${pageBoundaryLineY}px, #e5e7eb ${pageBoundaryLineY}px, #e5e7eb ${section.pageHeightPx}px)`,
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
          className="text-[10px] text-gray-400 border-b border-gray-100 relative z-10"
          style={{
            paddingLeft: section.marginLeftPx,
            paddingRight: section.marginRightPx,
            paddingTop: Math.max(section.headerHeightPx, 8),
            paddingBottom: 4,
            textAlign: headerTextAlign,
          }}
        >
          {hasHeader ? renderHeaderFooterText(section.headerText) : null}
          {pageNumAtTop && !hasHeader && formatPageNum(currentPageNumber)}
        </div>
      )}

      {/* Main content area */}
      <div
        className="relative z-10"
        style={{
          paddingTop: contentPaddingTop,
          paddingBottom: contentPaddingBottom,
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
        <div
          data-editor-area-guide="frame"
          className="pointer-events-none absolute inset-0 rounded-[2px] border border-dashed border-zinc-500/80"
        />
        <div className="pointer-events-none absolute left-0 top-0 h-6 w-6 border-l-[2.5px] border-t-[2.5px] border-zinc-900/85" />
        <div className="pointer-events-none absolute right-0 top-0 h-6 w-6 border-r-[2.5px] border-t-[2.5px] border-zinc-900/85" />
        <div className="pointer-events-none absolute left-0 bottom-0 h-6 w-6 border-l-[2.5px] border-b-[2.5px] border-zinc-900/85" />
        <div className="pointer-events-none absolute right-0 bottom-0 h-6 w-6 border-r-[2.5px] border-b-[2.5px] border-zinc-900/85" />

        <div className="relative z-10">
          {section.paragraphs.map((para, idx) => (
            <div key={`${section.sectionIndex}-${idx}-r${revision}`}>
              {para.pageBreakBefore && idx > 0 ? (
                <div
                  data-page-break-marker="true"
                  className="my-6 flex items-center gap-3 text-[10px] text-gray-400"
                >
                  <div className="h-px flex-1 border-t border-dashed border-gray-300" />
                  <span className="tracking-[0.08em]">쪽 나눔</span>
                  <div className="h-px flex-1 border-t border-dashed border-gray-300" />
                </div>
              ) : null}
              <ParagraphBlock
                paragraph={para}
                sectionIndex={section.sectionIndex}
                localIndex={idx}
                paragraphCount={section.paragraphs.length}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Footnotes area */}
      {hasFootnotes && (
        <div
          data-note-zone="footnotes"
          className="relative z-10"
          style={{
            paddingLeft: section.marginLeftPx,
            paddingRight: section.marginRightPx,
            paddingBottom: 4,
          }}
        >
          <div
            data-note-content="footnotes"
            className="border-t border-gray-300 pt-2 mt-2"
            style={{ width: "40%", maxWidth: "100%" }}
          >
            {section.footnotes.map((fn) => (
              <div key={fn.marker} className="text-[9px] text-gray-500 leading-relaxed mb-0.5 break-words">
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
          data-note-zone="endnotes"
          className="relative z-10"
          style={{
            paddingLeft: section.marginLeftPx,
            paddingRight: section.marginRightPx,
            paddingBottom: 4,
          }}
        >
          <div data-note-content="endnotes" className="border-t-2 border-gray-300 pt-2 mt-4">
            <div className="text-[9px] text-gray-400 font-medium mb-1">미주</div>
            {section.endnotes.map((en) => (
              <div key={en.marker} className="text-[9px] text-gray-500 leading-relaxed mb-0.5 break-words">
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
          className="text-[10px] text-gray-400 border-t border-gray-100 relative z-10"
          style={{
            paddingLeft: section.marginLeftPx,
            paddingRight: section.marginRightPx,
            paddingTop: 4,
            paddingBottom: Math.max(section.footerHeightPx, 8),
            textAlign: footerTextAlign,
          }}
        >
          {hasFooter ? renderHeaderFooterText(section.footerText) : null}
          {pageNumAtBottom && !hasFooter && formatPageNum(currentPageNumber)}
        </div>
      )}
    </div>
  );
}
