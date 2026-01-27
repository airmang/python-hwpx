"use client";

import { STYLE_PRESETS } from "@/lib/constants";
import { ToolbarDropdown } from "./ToolbarDropdown";

interface StyleSelectorProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function StyleSelector({ value, onChange, disabled }: StyleSelectorProps) {
  const options = STYLE_PRESETS.map((s) => ({
    value: s.id,
    label: s.name,
  }));

  return (
    <ToolbarDropdown
      value={value}
      options={options}
      onChange={onChange}
      disabled={disabled}
      title="스타일"
      width="w-24"
    />
  );
}
