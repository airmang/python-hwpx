"use client";

import { useEditorStore } from "@/lib/store";

export function HorizontalRuler() {
  const viewModel = useEditorStore((s) => s.viewModel);

  if (!viewModel || viewModel.sections.length === 0) return null;

  const section = viewModel.sections[0]!;
  const pageWidthPx = section.pageWidthPx;
  const marginLeftPx = section.marginLeftPx;
  const marginRightPx = section.marginRightPx;
  const contentWidthPx = pageWidthPx - marginLeftPx - marginRightPx;

  // Generate tick marks in cm
  const cmPerPx = 25.4 / 96 / 10; // px to cm
  const totalCm = contentWidthPx * cmPerPx;
  const ticks: { position: number; label: string; major: boolean }[] = [];

  for (let cm = 0; cm <= totalCm + 0.5; cm += 0.5) {
    const px = cm / cmPerPx;
    const major = cm % 1 === 0;
    ticks.push({
      position: px,
      label: major ? String(Math.round(cm)) : "",
      major,
    });
  }

  return (
    <div className="bg-white border-b border-gray-200 overflow-hidden flex-shrink-0">
      <div className="flex justify-center">
        <div
          className="relative h-6"
          style={{ width: pageWidthPx }}
        >
          {/* Left margin area */}
          <div
            className="absolute top-0 left-0 h-full bg-gray-100"
            style={{ width: marginLeftPx }}
          />
          {/* Right margin area */}
          <div
            className="absolute top-0 right-0 h-full bg-gray-100"
            style={{ width: marginRightPx }}
          />
          {/* Ruler content area */}
          <div
            className="absolute top-0 h-full"
            style={{ left: marginLeftPx, width: contentWidthPx }}
          >
            {ticks.map((tick, i) => (
              <div
                key={i}
                className="absolute bottom-0"
                style={{ left: tick.position }}
              >
                <div
                  className={`w-px ${
                    tick.major ? "h-3 bg-gray-500" : "h-1.5 bg-gray-300"
                  }`}
                />
                {tick.label && (
                  <span className="absolute -top-0.5 left-1/2 -translate-x-1/2 text-[8px] text-gray-400 leading-none">
                    {tick.label}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
