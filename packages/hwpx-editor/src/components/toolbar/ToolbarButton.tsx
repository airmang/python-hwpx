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
  className = "",
}: ToolbarButtonProps) {
  const sizeClass = size === "md" ? "p-2" : "p-1.5";
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      title={title}
      className={`${sizeClass} rounded transition-colors flex items-center gap-1 ${
        active
          ? "bg-blue-100 text-blue-700"
          : "text-gray-600 hover:bg-gray-100"
      } disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
    >
      {icon}
      {label && <span className="text-xs">{label}</span>}
    </button>
  );
}
