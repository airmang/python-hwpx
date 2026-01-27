"use client";

import type { ReactNode } from "react";

interface SidebarFieldProps {
  label: string;
  children: ReactNode;
}

export function SidebarField({ label, children }: SidebarFieldProps) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-[11px] text-gray-500 w-14 flex-shrink-0">{label}</span>
      <div className="flex-1">{children}</div>
    </div>
  );
}
