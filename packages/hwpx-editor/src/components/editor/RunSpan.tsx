"use client";

import type { RunVM } from "@/lib/view-model";

interface RunSpanProps {
  run: RunVM;
}

export function RunSpan({ run }: RunSpanProps) {
  const style: React.CSSProperties = {};

  if (run.bold) style.fontWeight = "bold";
  if (run.italic) style.fontStyle = "italic";

  // Text decoration (underline + strikethrough)
  const decorations: string[] = [];
  if (run.underline) decorations.push("underline");
  if (run.strikethrough) decorations.push("line-through");
  if (decorations.length > 0) style.textDecoration = decorations.join(" ");

  if (run.color && run.color !== "#000000") style.color = run.color;
  if (run.fontFamily) {
    if (run.fontFamily === "Noto Sans KR") {
      style.fontFamily = "var(--font-noto-sans-kr), sans-serif";
    } else if (run.fontFamily === "Noto Serif KR") {
      style.fontFamily = "var(--font-noto-serif-kr), serif";
    } else {
      style.fontFamily = run.fontFamily;
    }
  }
  if (run.fontSize) style.fontSize = `${run.fontSize}pt`;
  if (run.highlightColor) style.backgroundColor = run.highlightColor;
  if (run.letterSpacing) {
    // hwp letter spacing units -> px approximation
    style.letterSpacing = `${run.letterSpacing / 100}px`;
  }

  return <span style={style}>{run.text}</span>;
}
