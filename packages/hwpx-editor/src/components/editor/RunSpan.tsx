"use client";

import type { RunVM } from "@/lib/view-model";
import { fontFamilyCssStack } from "@/lib/constants";

interface RunSpanProps {
  run: RunVM;
  tabWidth?: number; // Tab width in pixels, default 40
}

export function RunSpan({ run, tabWidth = 40 }: RunSpanProps) {
  const style: React.CSSProperties = {};

  if (run.bold) style.fontWeight = 700;
  if (run.italic) style.fontStyle = "oblique 10deg";

  // Text decoration (underline + strikethrough)
  const decorations: string[] = [];
  if (run.underline) decorations.push("underline");
  if (run.strikethrough) decorations.push("line-through");
  if (decorations.length > 0) style.textDecoration = decorations.join(" ");

  if (run.color && run.color !== "#000000") style.color = run.color;
  if (run.fontFamily) {
    style.fontFamily = fontFamilyCssStack(run.fontFamily);
  }
  if (run.fontSize) style.fontSize = `${run.fontSize}pt`;
  if (run.highlightColor) style.backgroundColor = run.highlightColor;
  if (run.letterSpacing) {
    // hwp letter spacing units -> px approximation
    style.letterSpacing = `${run.letterSpacing / 100}px`;
  }

  // Render tab as fixed-width space
  if (run.hasTab) {
    return (
      <span
        style={{ display: "inline-block", width: tabWidth, ...style }}
        data-tab="true"
      />
    );
  }

  // Render full-width space
  if (run.hasFwSpace) {
    return (
      <span style={style} data-fwspace="true">
        {"\u3000"}
      </span>
    );
  }

  // Render line break
  if (run.hasLineBreak) {
    return <br data-linebreak="true" />;
  }

  // Render hyperlink
  if (run.hyperlink) {
    return (
      <a
        href={run.hyperlink}
        target="_blank"
        rel="noopener noreferrer"
        style={{ ...style, color: style.color || "#0066cc", textDecoration: "underline" }}
        onClick={(e) => e.stopPropagation()}
      >
        {run.text}
      </a>
    );
  }

  return <span style={style}>{run.text}</span>;
}
