"use client";

import type { EquationVM } from "@/lib/view-model";

interface EquationBlockProps {
  equation: EquationVM;
}

/**
 * Parse HWP equation script and convert to displayable text.
 * HWP equation language uses special syntax:
 * - _{x} for subscript
 * - ^{x} for superscript
 * - {A} over {B} for fraction
 * - root {n} of {x} for nth root
 * - int _{a} ^{b} for integral
 * - sum _{a} ^{b} for summation
 * - Special symbols: ALPHA, alpha, ohm, INF, etc.
 */
function parseEquationScript(script: string): string {
  if (!script) return "";

  // Symbol replacements
  const symbols: Record<string, string> = {
    "ALPHA": "\u0391", // Greek Alpha
    "alpha": "\u03B1", // Greek alpha
    "BETA": "\u0392",
    "beta": "\u03B2",
    "GAMMA": "\u0393",
    "gamma": "\u03B3",
    "DELTA": "\u0394",
    "delta": "\u03B4",
    "ohm": "\u03A9",
    "INF": "\u221E",
    "+-": "\u00B1",
    "rarrow": "\u2192",
    "larrow": "\u2190",
    "LRARROW": "\u2194",
    "CDOTS": "\u22EF",
    "BOT": "\u22A5",
    "RTANGLE": "\u221F",
    "MSANGLE": "\u2220",
    "SMALLSUM": "\u2211",
    "vec": "\u20D7", // combining vector
    "bar": "\u0305", // combining overline
  };

  let result = script;

  // Replace special symbols
  for (const [key, value] of Object.entries(symbols)) {
    result = result.replace(new RegExp(`\\b${key}\\b`, "g"), value);
  }

  // Handle subscripts: _{x} -> _x (simplified display)
  result = result.replace(/\s*_\s*\{([^}]*)\}/g, "\u2080$1"); // Approximation

  // Handle superscripts: ^{x} -> ^x
  result = result.replace(/\s*\^\s*\{([^}]*)\}/g, "\u00B2"); // Approximation

  // Handle fractions: {A} over {B} -> A/B
  result = result.replace(/\{([^}]*)\}\s*over\s*\{([^}]*)\}/g, "($1)/($2)");

  // Handle roots: root {n} of {x} -> n√x
  result = result.replace(/root\s*\{([^}]*)\}\s*of\s*\{([^}]*)\}/g, "$1\u221A$2");

  // Handle integrals: int _{a} ^{b} -> ∫
  result = result.replace(/\bint\b/g, "\u222B");
  result = result.replace(/\bdint\b/g, "\u222C"); // double integral
  result = result.replace(/\boint\b/g, "\u222E"); // contour integral

  // Handle sum
  result = result.replace(/\bsum\b/g, "\u2211");

  // Handle lim
  result = result.replace(/\blim\b/g, "lim");

  // Remove remaining braces
  result = result.replace(/\{([^}]*)\}/g, "$1");

  // Handle line breaks in equation (# is line break in HWP equations)
  result = result.replace(/#/g, "\n");

  // Clean up whitespace
  result = result.replace(/\s+/g, " ").trim();

  return result;
}

export function EquationBlock({ equation }: EquationBlockProps) {
  const displayText = parseEquationScript(equation.script);

  return (
    <span
      className="inline-block font-serif italic"
      style={{
        color: equation.textColor,
        minWidth: equation.widthPx,
        minHeight: equation.heightPx,
        verticalAlign: "middle",
        whiteSpace: "pre-wrap",
      }}
      title={equation.script}
    >
      {displayText || equation.script}
    </span>
  );
}
