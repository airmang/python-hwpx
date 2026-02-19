"use client";

import { FONT_FAMILIES } from "@/lib/constants";
import { ToolbarDropdown } from "./ToolbarDropdown";

interface FontSelectorProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function FontSelector({ value, onChange, disabled }: FontSelectorProps) {
  const options = FONT_FAMILIES.map((f) => ({
    value: f,
    label: f,
  }));

  return (
    <ToolbarDropdown
      value={value}
      options={options}
      onChange={onChange}
      disabled={disabled}
      title="글꼴"
      width="w-32"
    />
  );
}
