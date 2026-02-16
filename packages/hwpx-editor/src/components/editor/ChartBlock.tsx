"use client";

import type { TableVM } from "@/lib/view-model";

interface ChartBlockProps {
  title: string;
  chartType: "bar" | "line";
  table: TableVM;
}

interface Datum {
  label: string;
  value: number;
}

function parseNumeric(raw: string): number | null {
  const cleaned = raw.replace(/,/g, "").replace(/[^\d.\-]/g, "");
  if (!cleaned) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

function toChartData(table: TableVM): Datum[] {
  const rows: Datum[] = [];
  for (let row = 1; row < table.rowCount; row += 1) {
    const labelCell = table.cells[row]?.[0];
    const valueCell = table.cells[row]?.[1];
    if (!labelCell?.isAnchor || !valueCell?.isAnchor) continue;
    const label = (labelCell.text ?? "").trim() || `항목 ${row}`;
    const parsed = parseNumeric(valueCell.text ?? "");
    if (parsed == null) continue;
    rows.push({ label, value: parsed });
  }
  return rows.slice(0, 20);
}

export function ChartBlock({ title, chartType, table }: ChartBlockProps) {
  const data = toChartData(table);
  if (data.length === 0) return null;

  const viewWidth = 640;
  const viewHeight = 220;
  const margin = { top: 20, right: 18, bottom: 42, left: 44 };
  const plotWidth = viewWidth - margin.left - margin.right;
  const plotHeight = viewHeight - margin.top - margin.bottom;

  const maxValue = Math.max(1, ...data.map((d) => d.value));
  const gap = plotWidth / data.length;
  const barWidth = Math.max(14, gap * 0.58);

  const points = data.map((d, idx) => {
    const centerX = margin.left + gap * idx + gap / 2;
    const valueHeight = (d.value / maxValue) * plotHeight;
    const y = margin.top + plotHeight - valueHeight;
    return { ...d, centerX, y, valueHeight };
  });

  const linePath = points
    .map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.centerX.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(" ");

  return (
    <div className="my-2 rounded-md border border-sky-200 bg-gradient-to-b from-sky-50/70 to-white p-3">
      <div className="mb-1 text-[11px] font-semibold tracking-wide text-sky-700">
        {title}
      </div>
      <svg
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        className="h-[220px] w-full rounded bg-white"
        aria-label={`${title} ${chartType === "line" ? "선" : "막대"} 차트`}
      >
        <line
          x1={margin.left}
          y1={margin.top + plotHeight}
          x2={margin.left + plotWidth}
          y2={margin.top + plotHeight}
          stroke="#94a3b8"
          strokeWidth="1"
        />
        <line
          x1={margin.left}
          y1={margin.top}
          x2={margin.left}
          y2={margin.top + plotHeight}
          stroke="#94a3b8"
          strokeWidth="1"
        />

        {[0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = margin.top + plotHeight - plotHeight * ratio;
          return (
            <line
              key={ratio}
              x1={margin.left}
              y1={y}
              x2={margin.left + plotWidth}
              y2={y}
              stroke="#e2e8f0"
              strokeDasharray="3 4"
            />
          );
        })}

        {chartType === "bar" ? (
          points.map((p) => (
            <g key={p.label}>
              <rect
                x={p.centerX - barWidth / 2}
                y={p.y}
                width={barWidth}
                height={p.valueHeight}
                rx={3}
                fill="#2563eb"
                opacity="0.88"
              />
              <text
                x={p.centerX}
                y={p.y - 6}
                textAnchor="middle"
                fontSize="11"
                fill="#1e3a8a"
              >
                {p.value}
              </text>
            </g>
          ))
        ) : (
          <>
            <path d={linePath} fill="none" stroke="#2563eb" strokeWidth="2.5" />
            {points.map((p) => (
              <g key={p.label}>
                <circle cx={p.centerX} cy={p.y} r={4} fill="#1d4ed8" />
                <text
                  x={p.centerX}
                  y={p.y - 8}
                  textAnchor="middle"
                  fontSize="11"
                  fill="#1e3a8a"
                >
                  {p.value}
                </text>
              </g>
            ))}
          </>
        )}

        {points.map((p) => (
          <text
            key={`${p.label}-x`}
            x={p.centerX}
            y={margin.top + plotHeight + 16}
            textAnchor="middle"
            fontSize="11"
            fill="#334155"
          >
            {p.label.length > 10 ? `${p.label.slice(0, 10)}…` : p.label}
          </text>
        ))}
      </svg>
    </div>
  );
}
