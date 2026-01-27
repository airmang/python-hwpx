"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";

interface ToolbarDropdownProps {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
  title?: string;
  className?: string;
  width?: string;
  icon?: ReactNode;
}

export function ToolbarDropdown({
  value,
  options,
  onChange,
  disabled,
  title,
  className = "",
  width = "w-28",
  icon,
}: ToolbarDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const selectedLabel = options.find((o) => o.value === value)?.label ?? value;

  return (
    <div ref={ref} className={`relative ${className}`} title={title}>
      <button
        disabled={disabled}
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1 ${width} h-7 px-2 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 text-left disabled:opacity-40 disabled:cursor-not-allowed`}
      >
        {icon}
        <span className="flex-1 truncate">{selectedLabel}</span>
        <svg className="w-3 h-3 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-white border border-gray-200 rounded shadow-lg max-h-64 overflow-auto min-w-full">
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
              className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-blue-50 ${
                opt.value === value ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
