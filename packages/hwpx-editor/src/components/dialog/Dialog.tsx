"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

interface DialogProps {
  title: string;
  description?: string;
  open: boolean;
  onClose: () => void;
  onApply?: () => void;
  children: ReactNode;
  width?: number;
  footer?: ReactNode;
  hideDefaultFooter?: boolean;
  closeLabel?: string;
  applyLabel?: string;
  contentClassName?: string;
}

export function Dialog({
  title,
  description,
  open,
  onClose,
  onApply,
  children,
  width = 560,
  footer,
  hideDefaultFooter = false,
  closeLabel = "취소",
  applyLabel = "설정",
  contentClassName,
}: DialogProps) {
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
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="flex max-h-[90vh] w-full flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl"
        style={{ maxWidth: width }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-gray-200 px-6 py-5">
          <div className="min-w-0">
            <div className="text-lg font-semibold tracking-tight text-gray-900">{title}</div>
            {description ? (
              <p className="mt-1 text-sm text-gray-500">{description}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-700"
            aria-label="닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className={`flex-1 overflow-auto px-6 py-5 ${contentClassName ?? ""}`}>
          {children}
        </div>

        {footer ? (
          <div className="border-t border-gray-200 px-6 py-4">{footer}</div>
        ) : hideDefaultFooter ? null : (
          <div className="flex justify-end gap-2 border-t border-gray-200 px-6 py-4">
            <button
              type="button"
              onClick={onClose}
              className="h-10 rounded-lg border border-gray-300 bg-white px-4 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              {closeLabel}
            </button>
            {onApply ? (
              <button
                type="button"
                onClick={onApply}
                className="h-10 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700"
              >
                {applyLabel}
              </button>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
