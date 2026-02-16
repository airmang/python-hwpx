"use client";

import type { ReactNode } from "react";

interface ToolbarButtonProps {
  icon: ReactNode;
  label?: string;
  active?: boolean;
  disabled?: boolean;
  todo?: string;
  onClick?: () => void;
  title?: string;
  size?: "sm" | "md";
  layout?: "horizontal" | "vertical";
  className?: string;
}

export function ToolbarButton({
  icon,
  label,
  active,
  disabled,
  todo,
  onClick,
  title,
  size = "sm",
  layout = "horizontal",
  className = "",
}: ToolbarButtonProps) {
  const sizeClass = size === "md" ? "p-2.5" : "p-2";
  const isVertical = layout === "vertical";
  const isTodoDisabled = Boolean(todo) && Boolean(disabled);
  const resolvedTitle = isTodoDisabled
    ? `${title ?? label ?? ""} (준비중: ${todo})`.trim()
    : title;
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      title={resolvedTitle}
      className={`${sizeClass} rounded transition-colors flex ${
        isVertical ? "flex-col items-center gap-1 px-2.5" : "items-center gap-1.5"
      } ${
        active
          ? "bg-blue-100 text-blue-700"
          : "text-gray-600 hover:bg-gray-100"
      } ${
        isTodoDisabled
          ? "border border-dashed border-gray-300 bg-gray-50 text-gray-400"
          : ""
      } [&_svg]:w-5 [&_svg]:h-5 disabled:opacity-40 disabled:cursor-not-allowed disabled:saturate-0 ${className}`}
    >
      {icon}
      {label && (
        <span className={isVertical ? "text-[11px] leading-tight" : "text-sm"}>
          {label}
          {isTodoDisabled && (
            <span
              className={
                isVertical
                  ? "mt-0.5 block text-[9px] leading-none font-semibold tracking-wide text-gray-400"
                  : "ml-1 text-[10px] font-semibold tracking-wide text-gray-400"
              }
            >
              TODO
            </span>
          )}
        </span>
      )}
    </button>
  );
}
