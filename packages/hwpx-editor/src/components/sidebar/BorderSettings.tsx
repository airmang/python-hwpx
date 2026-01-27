"use client";

import { SidebarField } from "./SidebarField";

interface BorderSettingsProps {
  disabled?: boolean;
}

export function BorderSettings({ disabled }: BorderSettingsProps) {
  return (
    <div className="space-y-1">
      <SidebarField label="종류">
        <select
          disabled={disabled}
          className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
        >
          <option value="none">없음</option>
          <option value="solid">실선</option>
          <option value="dashed">점선</option>
          <option value="double">이중선</option>
        </select>
      </SidebarField>
      <SidebarField label="두께">
        <select
          disabled={disabled}
          className="w-full h-6 px-1 text-[11px] border border-gray-300 rounded bg-white disabled:opacity-40"
        >
          <option value="0.1mm">0.1mm</option>
          <option value="0.12mm">0.12mm</option>
          <option value="0.3mm">0.3mm</option>
          <option value="0.4mm">0.4mm</option>
          <option value="0.5mm">0.5mm</option>
          <option value="1.0mm">1.0mm</option>
        </select>
      </SidebarField>
      <SidebarField label="색">
        <input
          type="color"
          defaultValue="#000000"
          disabled={disabled}
          className="w-6 h-6 border border-gray-300 rounded cursor-pointer disabled:opacity-40"
        />
      </SidebarField>
    </div>
  );
}
