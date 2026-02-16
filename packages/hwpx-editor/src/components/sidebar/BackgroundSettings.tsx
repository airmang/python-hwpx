"use client";

import { useState } from "react";
import { SidebarField } from "./SidebarField";
import { ColorPicker } from "../toolbar/ColorPicker";

interface BackgroundSettingsProps {
  disabled?: boolean;
}

export function BackgroundSettings({ disabled }: BackgroundSettingsProps) {
  const [color, setColor] = useState("#FFFFFF");

  return (
    <div className="space-y-1">
      <SidebarField label="채우기">
        <select
          disabled={disabled}
          className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
        >
          <option value="none">없음</option>
          <option value="color">색 채우기</option>
          <option value="gradient">그라데이션</option>
          <option value="pattern">무늬</option>
        </select>
      </SidebarField>
      <SidebarField label="배경색">
        <ColorPicker
          color={color}
          onChange={setColor}
          disabled={disabled}
          variant="swatch"
          title="배경 색상"
        />
      </SidebarField>
    </div>
  );
}
