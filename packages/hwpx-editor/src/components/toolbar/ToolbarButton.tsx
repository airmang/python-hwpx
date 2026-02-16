"use client";

import type { ReactNode } from "react";

interface ToolbarButtonProps {
  icon: ReactNode;
  label?: string;
  active?: boolean;
  disabled?: boolean;
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
  onClick,
  title,
  size = "sm",
  layout = "horizontal",
  className = "",
}: ToolbarButtonProps) {
  const sizeClass = size === "md" ? "p-2.5" : "p-2";
  const isVertical = layout === "vertical";
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      title={title}
      className={`${sizeClass} rounded transition-colors flex ${
        isVertical ? "flex-col items-center gap-1 px-2.5" : "items-center gap-1.5"
      } ${
        active
          ? "bg-blue-100 text-blue-700"
          : "text-gray-600 hover:bg-gray-100"
      } [&_svg]:w-5 [&_svg]:h-5 disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
    >
      {icon}
      {label && (
        <span className={isVertical ? "text-[11px] leading-tight" : "text-sm"}>
          {label}
        </span>
      )}
    </button>
  );
}
