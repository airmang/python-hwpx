"use client";

import type { ReactNode } from "react";

interface RibbonGroupProps {
  label: string;
  children: ReactNode;
}

export function RibbonGroup({ label, children }: RibbonGroupProps) {
  return (
    <div className="flex flex-col items-center border-r border-gray-200 px-2 last:border-r-0">
      <div className="flex items-center gap-0.5 py-1">{children}</div>
      <span className="text-[10px] text-gray-400 pb-0.5">{label}</span>
    </div>
  );
}
