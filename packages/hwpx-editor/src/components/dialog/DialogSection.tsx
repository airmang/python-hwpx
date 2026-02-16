"use client";

import type { ReactNode } from "react";

interface DialogSectionProps {
  title: string;
  children: ReactNode;
}

export function DialogSection({ title, children }: DialogSectionProps) {
  return (
    <div className="mb-4 last:mb-0">
      <div className="mb-2 text-[13px] font-semibold text-gray-800">{title}</div>
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3.5">
        {children}
      </div>
    </div>
  );
}
