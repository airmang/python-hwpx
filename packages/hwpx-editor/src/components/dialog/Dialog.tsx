"use client";

import { useEffect, useRef, type ReactNode } from "react";

interface DialogProps {
  title: string;
  open: boolean;
  onClose: () => void;
  onApply?: () => void;
  children: ReactNode;
  width?: number;
}

export function Dialog({ title, open, onClose, onApply, children, width = 560 }: DialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30">
      <div
        ref={dialogRef}
        className="bg-[#f0f0f0] rounded-lg shadow-2xl flex flex-col max-h-[90vh]"
        style={{ width }}
      >
        {/* Title bar */}
        <div className="text-center py-2.5 text-sm font-medium text-gray-800 border-b border-gray-300/50">
          {title}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto px-5 py-3">
          {children}
        </div>

        {/* Footer with buttons */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-gray-300/50">
          <button
            onClick={onClose}
            className="px-6 py-1.5 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50 text-gray-700"
          >
            취소
          </button>
          {onApply && (
            <button
              onClick={onApply}
              className="px-6 py-1.5 text-sm bg-blue-500 border border-blue-600 rounded hover:bg-blue-600 text-white font-medium"
            >
              설정
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
