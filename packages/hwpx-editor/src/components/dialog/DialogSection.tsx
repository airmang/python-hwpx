"use client";

import type { ReactNode } from "react";

interface DialogSectionProps {
  title: string;
  children: ReactNode;
}

export function DialogSection({ title, children }: DialogSectionProps) {
  return (
    <div className="mb-4">
      <div className="text-xs font-bold text-gray-800 mb-1.5">{title}</div>
      <div className="bg-gray-100 border border-gray-200 rounded-md p-3">
        {children}
      </div>
    </div>
  );
}
