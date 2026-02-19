"use client";

import { ClipboardGroup } from "./ClipboardGroup";
import { InsertGroup } from "./InsertGroup";

export function RibbonToolbar() {
  return (
    <div className="flex items-stretch bg-white border-b border-gray-200 px-1 min-h-[52px]">
      <ClipboardGroup />
      <InsertGroup />
    </div>
  );
}
