"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";
import { COLOR_PRESETS } from "@/lib/constants";

interface ColorPickerProps {
  color: string;
  onChange: (color: string) => void;
  icon?: ReactNode;
  title?: string;
  disabled?: boolean;
  allowNone?: boolean;
  noneLabel?: string;
  buttonClassName?: string;
  variant?: "toolbar" | "swatch";
}

export function ColorPicker({
  color,
  onChange,
  icon,
  title,
  disabled,
  allowNone = false,
  noneLabel = "없음",
  buttonClassName = "",
  variant = "toolbar",
}: ColorPickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const normalizedColor =
    color && color !== "none" ? color : "#000000";
  const isNone = color === "none";

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
        className={
          variant === "swatch"
            ? `w-full h-6 p-1 rounded border border-gray-300 bg-white transition-colors hover:border-gray-400 disabled:opacity-40 disabled:cursor-not-allowed ${buttonClassName}`.trim()
            : `p-2 rounded transition-colors text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed flex flex-col items-center [&_svg]:w-5 [&_svg]:h-5 ${buttonClassName}`.trim()
        }
      >
        {variant === "swatch" ? (
          <span
            className="block w-full h-full rounded-sm border border-gray-200"
            style={{
              background: isNone
                ? "repeating-linear-gradient(135deg, #e5e7eb 0 2px, #ffffff 2px 4px)"
                : normalizedColor,
            }}
          />
        ) : (
          <>
            {icon ?? <span className="w-5 h-5 rounded border border-gray-300 bg-white" />}
            <div
              className="w-5 h-1 mt-0.5 rounded-sm"
              style={{
                background: isNone
                  ? "repeating-linear-gradient(135deg, #e5e7eb 0 2px, #ffffff 2px 4px)"
                  : normalizedColor,
              }}
            />
          </>
        )}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-white border border-gray-200 rounded-lg shadow-lg p-2">
          {allowNone ? (
            <button
              onClick={() => {
                onChange("none");
                setOpen(false);
              }}
              className={`w-full mb-2 px-2 py-1 text-xs rounded border text-left transition-colors ${
                isNone
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {noneLabel}
            </button>
          ) : null}
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
            <label className="text-sm text-gray-500">커스텀:</label>
            <input
              type="color"
              value={normalizedColor}
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
