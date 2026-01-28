"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";
import { COLOR_PRESETS } from "@/lib/constants";

interface ColorPickerProps {
  color: string;
  onChange: (color: string) => void;
  icon: ReactNode;
  title?: string;
  disabled?: boolean;
}

export function ColorPicker({
  color,
  onChange,
  icon,
  title,
  disabled,
}: ColorPickerProps) {
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

  return (
    <div ref={ref} className="relative">
      <button
        disabled={disabled}
        onClick={() => setOpen(!open)}
        title={title}
        className="p-1.5 rounded transition-colors text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed flex flex-col items-center"
      >
        {icon}
        <div
          className="w-4 h-0.5 mt-0.5 rounded-sm"
          style={{ backgroundColor: color || "#000000" }}
        />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-white border border-gray-200 rounded-lg shadow-lg p-2">
          <div className="grid grid-cols-8 gap-1">
            {COLOR_PRESETS.map((c) => (
              <button
                key={c}
                onClick={() => {
                  onChange(c);
                  setOpen(false);
                }}
                className={`w-5 h-5 rounded border ${
                  c === color ? "border-blue-500 ring-1 ring-blue-300" : "border-gray-300"
                } hover:scale-110 transition-transform`}
                style={{ backgroundColor: c }}
                title={c}
              />
            ))}
          </div>
          <div className="mt-2 pt-2 border-t border-gray-100 flex items-center gap-2">
            <label className="text-xs text-gray-500">커스텀:</label>
            <input
              type="color"
              value={color && color !== "none" ? color : "#000000"}
              onChange={(e) => {
                onChange(e.target.value);
                setOpen(false);
              }}
              className="w-6 h-6 cursor-pointer border-0"
            />
          </div>
        </div>
      )}
    </div>
  );
}
