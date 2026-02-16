"use client";

import { FONT_FAMILIES } from "@/lib/constants";
import { useEffect, useMemo, useRef, useState } from "react";

interface FontSelectorProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

const RECENT_FONT_KEY = "hwpx-recent-fonts";
const MAX_RECENT_FONTS = 5;

export function FontSelector({ value, onChange, disabled }: FontSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [recentFonts, setRecentFonts] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const raw = window.localStorage.getItem(RECENT_FONT_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter((font): font is string => typeof font === "string")
        .slice(0, MAX_RECENT_FONTS);
    } catch {
      return [];
    }
  });
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const allFonts = useMemo(() => {
    const fonts = [...FONT_FAMILIES];
    if (value && !fonts.some((font) => font === value)) {
      return [value, ...fonts];
    }
    return fonts;
  }, [value]);

  const filteredFonts = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return allFonts;
    return allFonts.filter((font) => font.toLowerCase().includes(trimmed));
  }, [allFonts, query]);

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const raf = window.requestAnimationFrame(() => searchRef.current?.focus());
    return () => window.cancelAnimationFrame(raf);
  }, [open]);

  const saveRecentFonts = (next: string[]) => {
    setRecentFonts(next);
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(RECENT_FONT_KEY, JSON.stringify(next));
    } catch {
      // ignore storage write failures
    }
  };

  const selectFont = (font: string) => {
    onChange(font);
    const nextRecents = [font, ...recentFonts.filter((item) => item !== font)].slice(0, MAX_RECENT_FONTS);
    saveRecentFonts(nextRecents);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={rootRef} className="relative" title="글꼴" data-hwpx-testid="toolbar-font-family">
      <button
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center gap-1.5 w-32 h-9 px-2.5 text-sm border border-gray-300 rounded bg-white hover:bg-gray-50 text-left disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span className="flex-1 truncate">{value}</span>
        <svg className="w-5 h-5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open ? (
        <div className="absolute top-full left-0 mt-1 z-50 bg-white border border-gray-200 rounded shadow-lg min-w-[220px]">
          <div className="p-2 border-b border-gray-100">
            <input
              ref={searchRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="글꼴 검색"
              className="w-full h-8 px-2.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-300"
            />
          </div>

          {recentFonts.length > 0 ? (
            <div className="border-b border-gray-100">
              <div className="px-3 pt-2 pb-1 text-[11px] text-gray-500">최근 사용</div>
              <div className="max-h-28 overflow-auto pb-1">
                {recentFonts.map((font) => (
                  <button
                    key={`recent-${font}`}
                    onClick={() => selectFont(font)}
                    className={`block w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 ${
                      font === value ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-700"
                    }`}
                  >
                    {font}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="px-3 pt-2 pb-1 text-[11px] text-gray-500">전체 글꼴</div>
          <div className="max-h-56 overflow-auto pb-1">
            {filteredFonts.length > 0 ? (
              filteredFonts.map((font) => (
                <button
                  key={font}
                  onClick={() => selectFont(font)}
                  className={`block w-full text-left px-3 py-2 text-sm hover:bg-blue-50 ${
                    font === value ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-700"
                  }`}
                >
                  {font}
                </button>
              ))
            ) : (
              <div className="px-3 py-3 text-sm text-gray-500">검색 결과가 없습니다.</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
