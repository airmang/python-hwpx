"use client";

import { useState, useCallback } from "react";
import { FONT_SIZES } from "@/lib/constants";

interface FontSizeInputProps {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}

export function FontSizeInput({ value, onChange, disabled }: FontSizeInputProps) {
  const [editing, setEditing] = useState(false);
  const [inputValue, setInputValue] = useState(String(value));

  const handleBlur = useCallback(() => {
    setEditing(false);
    const num = parseFloat(inputValue);
    if (!isNaN(num) && num > 0 && num <= 200) {
      onChange(num);
    } else {
      setInputValue(String(value));
    }
  }, [inputValue, value, onChange]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        (e.target as HTMLInputElement).blur();
      } else if (e.key === "Escape") {
        setInputValue(String(value));
        setEditing(false);
      }
    },
    [value],
  );

  if (editing) {
    return (
      <input
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        autoFocus
        className="w-14 h-7 px-2 text-xs border border-blue-400 rounded text-center focus:outline-none"
      />
    );
  }

  return (
    <div className="relative">
      <select
        value={String(value)}
        onChange={(e) => {
          const num = parseFloat(e.target.value);
          if (!isNaN(num)) onChange(num);
        }}
        disabled={disabled}
        className="w-14 h-7 px-1 text-xs border border-gray-300 rounded bg-white text-center appearance-none cursor-pointer disabled:opacity-40"
        title="글자 크기"
        onDoubleClick={() => {
          setInputValue(String(value));
          setEditing(true);
        }}
      >
        {FONT_SIZES.map((s) => (
          <option key={s} value={String(s)}>
            {s}
          </option>
        ))}
        {!FONT_SIZES.includes(value as any) && (
          <option value={String(value)}>{value}</option>
        )}
      </select>
    </div>
  );
}
