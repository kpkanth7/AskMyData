"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import type { QueryResponse, ResultBlock } from "@/types/api";

const chartPalette = ["#1fbf9b", "#ff6f61", "#5b8def", "#f5b841", "#e05d8f", "#2f9e44", "#20a4f3", "#7c6df0", "#00a6a6", "#d95f02", "#6a994e", "#c77dff"];
const SVG_WIDTH = 880;
const SVG_HEIGHT = 360;

type ChartPoint = {
  label: string;
  value: number;
  xNumber: number | null;
  color: string;
};

type VisualInteraction = {
  activePoint: ChartPoint | null;
  onActivate: (point: ChartPoint) => void;
};

export function ResultsView({ response }: { response: QueryResponse | null }) {
  if (!response) {
    return (
      <div className="rounded-lg border border-ink/10 bg-white p-6 text-center text-ink/60">
        Ask a question after adding a source. Results, charts, SQL preview, and the single grounded summary will appear here.
      </div>
    );
  }

  if (!response.result_blocks.length) {
    return (
      <div className="rounded-lg border border-ink/10 bg-white p-6 text-center text-ink/60">
        No matching records were returned.
      </div>
    );
  }

  return <InteractiveResults response={response} />;
}

function InteractiveResults({ response }: { response: QueryResponse }) {
  const [activeId, setActiveId] = useState(response.result_blocks[0]?.id ?? "");
  const activeBlock = response.result_blocks.find((block) => block.id === activeId) ?? response.result_blocks[0];
  if (!activeBlock) return null;

  return (
    <div className="space-y-4">
      {response.result_blocks.length > 1 && (
        <div className="rounded-lg border border-ink/10 bg-white p-2 shadow-soft">
          <div className="grid gap-2 md:grid-cols-2">
            {response.result_blocks.map((block) => (
              <button
                key={block.id}
                type="button"
                onClick={() => setActiveId(block.id)}
                className={`rounded-md px-4 py-3 text-left transition ${
                  activeBlock.id === block.id ? "bg-ink text-white" : "bg-cloud text-ink hover:bg-mint/15"
                }`}
              >
                <span className="block truncate text-sm font-semibold">{block.label || block.question}</span>
                <span className="mt-1 block text-xs font-semibold uppercase tracking-normal opacity-70">{block.rows.length} rows</span>
              </button>
            ))}
          </div>
        </div>
      )}
      <ResultSection key={activeBlock.id} block={activeBlock} />
      {response.final_summary && (
        <div className="rounded-lg bg-ink p-5 text-white">
          <p className="text-sm uppercase tracking-normal text-white/55">Final summary</p>
          <p className="mt-2 leading-7">{response.final_summary}</p>
        </div>
      )}
    </div>
  );
}

function ResultSection({ block }: { block: ResultBlock }) {
  const [view, setView] = useState<"records" | "visual" | "sql">("records");
  const canShowSql = Boolean(block.sql);
  const options: Array<{ id: "records" | "visual" | "sql"; label: string; enabled: boolean }> = [
    { id: "records", label: "Records", enabled: true },
    { id: "visual", label: "Visual", enabled: block.chart.enabled },
    { id: "sql", label: "SQL", enabled: canShowSql },
  ];

  return (
    <article className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft transition">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-normal text-coral">{block.source_name}</p>
          <h3 className="mt-1 text-lg font-semibold text-ink">{block.question}</h3>
        </div>
        <span className="rounded-md bg-cloud px-3 py-1 text-sm text-ink/70">{block.rows.length} rows</span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            disabled={!option.enabled}
            onClick={() => setView(option.id)}
            className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
              view === option.id ? "bg-mint text-ink" : "bg-cloud text-ink/70 hover:bg-mint/15 disabled:cursor-not-allowed disabled:opacity-40"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      {view === "records" && <DataTable block={block} />}
      {view === "visual" && block.chart.enabled && <Chart block={block} />}
      {view === "sql" && block.sql && (
        <pre className="mt-5 max-h-64 max-w-full overflow-auto whitespace-pre-wrap break-words rounded-md bg-cloud p-4 text-xs leading-5 text-ink">{block.sql}</pre>
      )}
    </article>
  );
}

function Chart({ block }: { block: ResultBlock }) {
  const chart = block.chart;
  if (!chart.x_key || !chart.y_key) return <ChartEmptyState />;
  const rows = normalizedChartRows(block);
  const chartType = chart.chart_type ?? "bar";
  const xLabel = formatColumnName(chart.x_key);
  const yLabel = formatColumnName(chart.y_key);

  return (
    <div className="mt-5 rounded-lg border border-ink/10 bg-[#fbfefc] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-ink">{chart.title || "Visual"}</p>
          <p className="mt-1 text-xs uppercase tracking-normal text-ink/55">
            {xLabel} by {yLabel}
          </p>
        </div>
        <span className="rounded-md bg-white px-3 py-1 text-xs font-semibold uppercase tracking-normal text-ink/60">{formatChartType(chartType)}</span>
      </div>
      {rows.length ? <CustomChart chartType={chartType} rows={rows} xLabel={xLabel} yLabel={yLabel} /> : <ChartEmptyState />}
    </div>
  );
}

function CustomChart({ chartType, rows, xLabel, yLabel }: { chartType: string; rows: ChartPoint[]; xLabel: string; yLabel: string }) {
  const displayRows = chartType === "histogram" ? histogramRows(rows) : rows;
  const [activePoint, setActivePoint] = useState<ChartPoint | null>(displayRows[0] ?? null);
  const interaction = { activePoint, onActivate: setActivePoint };
  const total = displayRows.reduce((sum, row) => sum + Math.max(row.value, 0), 0);
  let visual: ReactNode;

  if (chartType === "pie") visual = <PieVisual rows={displayRows} yLabel={yLabel} interaction={interaction} />;
  else if (chartType === "line") visual = <LineVisual rows={displayRows} xLabel={xLabel} yLabel={yLabel} interaction={interaction} />;
  else if (chartType === "area") visual = <LineVisual rows={displayRows} xLabel={xLabel} yLabel={yLabel} area interaction={interaction} />;
  else if (chartType === "scatter") visual = <ScatterVisual rows={displayRows} xLabel={xLabel} yLabel={yLabel} interaction={interaction} />;
  else if (chartType === "histogram") visual = <BarVisual rows={displayRows} xLabel={xLabel} yLabel="Count" interaction={interaction} />;
  else if (chartType === "treemap") visual = <TreemapVisual rows={displayRows} interaction={interaction} />;
  else if (chartType === "radial_bar") visual = <RadialVisual rows={displayRows} yLabel={yLabel} interaction={interaction} />;
  else if (chartType === "radar") visual = <RadarVisual rows={displayRows} yLabel={yLabel} interaction={interaction} />;
  else if (chartType === "horizontal_bar") visual = <BarVisual rows={displayRows} xLabel={xLabel} yLabel={yLabel} horizontal interaction={interaction} />;
  else visual = <BarVisual rows={displayRows} xLabel={xLabel} yLabel={yLabel} interaction={interaction} />;

  return (
    <>
      <ActiveDatumPanel point={activePoint ?? displayRows[0] ?? null} xLabel={xLabel} yLabel={chartType === "histogram" ? "Count" : yLabel} total={total} />
      {visual}
      <p className="mt-2 text-xs text-ink/55">Hover or tab through marks to inspect full IDs and values. Dense charts can be scrolled inside the visual area.</p>
    </>
  );
}

function BarVisual({
  rows,
  xLabel,
  yLabel,
  interaction,
  horizontal = false,
}: {
  rows: ChartPoint[];
  xLabel: string;
  yLabel: string;
  interaction: VisualInteraction;
  horizontal?: boolean;
}) {
  const data = rows.slice(0, 60);
  const max = Math.max(...data.map((row) => Math.abs(row.value)), 1);
  const svgWidth = horizontal ? SVG_WIDTH : Math.max(SVG_WIDTH, data.length * 64 + 120);
  const svgHeight = horizontal ? Math.max(SVG_HEIGHT, data.length * 34 + 96) : SVG_HEIGHT;
  const plot = { left: horizontal ? 174 : 56, top: 28, width: svgWidth - (horizontal ? 236 : 116), height: svgHeight - 112 };

  if (horizontal) {
    const barGap = 8;
    const barHeight = Math.max(12, (plot.height - barGap * (data.length - 1)) / Math.max(data.length, 1));
    return (
      <ChartFrame minHeight={svgHeight} minWidth={svgWidth}>
        <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="h-full w-full" role="img" aria-label={`${xLabel} by ${yLabel}`}>
          <Grid plot={plot} />
          {data.map((row, index) => {
            const width = (Math.abs(row.value) / max) * plot.width;
            const y = plot.top + index * (barHeight + barGap);
            const active = isActivePoint(row, interaction.activePoint);
            return (
              <g key={`${row.label}-${index}`} {...interactiveMarkProps(row, interaction.onActivate)} opacity={active ? 1 : 0.42}>
                <title>{chartPointTitle(row, yLabel)}</title>
                <text x={plot.left - 10} y={y + barHeight * 0.68} textAnchor="end" className="fill-ink/70 text-[11px]">
                  {truncate(row.label, 22)}
                </text>
                <rect x={plot.left} y={y} width={width} height={barHeight} rx={6} fill={row.color} stroke={active ? "#111827" : "transparent"} strokeWidth="2" />
                <text x={plot.left + width + 8} y={y + barHeight * 0.68} className="fill-ink text-[11px] font-semibold">
                  {formatNumber(row.value)}
                </text>
              </g>
            );
          })}
          <AxisLabel x={plot.left + plot.width / 2} y={svgHeight - 18} label={yLabel} />
        </svg>
      </ChartFrame>
    );
  }

  const barGap = 10;
  const barWidth = Math.max(10, (plot.width - barGap * (data.length - 1)) / Math.max(data.length, 1));
  return (
    <ChartFrame minWidth={svgWidth}>
      <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="h-full w-full" role="img" aria-label={`${xLabel} by ${yLabel}`}>
        <Grid plot={plot} />
        {data.map((row, index) => {
          const height = (Math.abs(row.value) / max) * plot.height;
          const x = plot.left + index * (barWidth + barGap);
          const y = plot.top + plot.height - height;
          const active = isActivePoint(row, interaction.activePoint);
          return (
            <g key={`${row.label}-${index}`} {...interactiveMarkProps(row, interaction.onActivate)} opacity={active ? 1 : 0.42}>
              <title>{chartPointTitle(row, yLabel)}</title>
              <rect x={x} y={y} width={barWidth} height={height} rx={6} fill={row.color} stroke={active ? "#111827" : "transparent"} strokeWidth="2" />
              <text x={x + barWidth / 2} y={y - 7} textAnchor="middle" className="fill-ink text-[11px] font-semibold">
                {formatNumber(row.value)}
              </text>
              <text x={x + barWidth / 2} y={plot.top + plot.height + 18} textAnchor="middle" className="fill-ink/65 text-[10px]">
                {truncate(row.label, 9)}
              </text>
            </g>
          );
        })}
        <AxisLabel x={plot.left + plot.width / 2} y={svgHeight - 18} label={xLabel} />
        <AxisLabel x={17} y={plot.top + plot.height / 2} label={yLabel} rotate />
      </svg>
    </ChartFrame>
  );
}

function LineVisual({
  rows,
  xLabel,
  yLabel,
  interaction,
  area = false,
}: {
  rows: ChartPoint[];
  xLabel: string;
  yLabel: string;
  interaction: VisualInteraction;
  area?: boolean;
}) {
  const data = rows.slice(0, 120);
  const svgWidth = Math.max(SVG_WIDTH, data.length * 32 + 120);
  const plot = { left: 58, top: 28, width: svgWidth - 118, height: 248 };
  const values = data.map((row) => row.value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const span = max - min || 1;
  const points = data.map((row, index) => ({
    x: plot.left + (index / Math.max(data.length - 1, 1)) * plot.width,
    y: plot.top + plot.height - ((row.value - min) / span) * plot.height,
    row,
  }));
  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const areaPath = `${linePath} L ${plot.left + plot.width} ${plot.top + plot.height} L ${plot.left} ${plot.top + plot.height} Z`;

  return (
    <ChartFrame minWidth={svgWidth}>
      <svg viewBox={`0 0 ${svgWidth} ${SVG_HEIGHT}`} className="h-full w-full" role="img" aria-label={`${xLabel} by ${yLabel}`}>
        <Grid plot={plot} />
        {area && <path d={areaPath} fill="#1fbf9b" opacity="0.22" />}
        <path d={linePath} fill="none" stroke="#1fbf9b" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((point, index) => {
          const active = isActivePoint(point.row, interaction.activePoint);
          return (
            <circle
              key={`${point.row.label}-${index}`}
              cx={point.x}
              cy={point.y}
              r={active ? 8 : 5}
              fill={point.row.color}
              stroke={active ? "#111827" : "#ffffff"}
              strokeWidth="2"
              opacity={active ? 1 : 0.58}
              {...interactiveMarkProps(point.row, interaction.onActivate)}
            >
              <title>{chartPointTitle(point.row, yLabel)}</title>
            </circle>
          );
        })}
        <AxisLabel x={plot.left + plot.width / 2} y={SVG_HEIGHT - 18} label={xLabel} />
        <AxisLabel x={17} y={plot.top + plot.height / 2} label={yLabel} rotate />
      </svg>
    </ChartFrame>
  );
}

function ScatterVisual({ rows, xLabel, yLabel, interaction }: { rows: ChartPoint[]; xLabel: string; yLabel: string; interaction: VisualInteraction }) {
  const data = rows.filter((row) => row.xNumber !== null).slice(0, 80);
  if (!data.length) return <BarVisual rows={rows} xLabel={xLabel} yLabel={yLabel} interaction={interaction} />;
  const svgWidth = Math.max(SVG_WIDTH, data.length * 22 + 120);
  const plot = { left: 58, top: 28, width: svgWidth - 118, height: 248 };
  const xs = data.map((row) => row.xNumber ?? 0);
  const ys = data.map((row) => row.value);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys, 0);
  const maxY = Math.max(...ys, 1);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  return (
    <ChartFrame minWidth={svgWidth}>
      <svg viewBox={`0 0 ${svgWidth} ${SVG_HEIGHT}`} className="h-full w-full" role="img" aria-label={`${xLabel} by ${yLabel}`}>
        <Grid plot={plot} />
        {data.map((row, index) => {
          const x = plot.left + (((row.xNumber ?? 0) - minX) / spanX) * plot.width;
          const y = plot.top + plot.height - ((row.value - minY) / spanY) * plot.height;
          const active = isActivePoint(row, interaction.activePoint);
          return (
            <circle
              key={`${row.label}-${index}`}
              cx={x}
              cy={y}
              r={active ? 10 : 7}
              fill={row.color}
              opacity={active ? 1 : 0.6}
              stroke={active ? "#111827" : "#ffffff"}
              strokeWidth="2"
              {...interactiveMarkProps(row, interaction.onActivate)}
            >
              <title>{chartPointTitle(row, yLabel)}</title>
            </circle>
          );
        })}
        <AxisLabel x={plot.left + plot.width / 2} y={SVG_HEIGHT - 18} label={xLabel} />
        <AxisLabel x={17} y={plot.top + plot.height / 2} label={yLabel} rotate />
      </svg>
    </ChartFrame>
  );
}

function PieVisual({ rows, yLabel, interaction }: { rows: ChartPoint[]; yLabel: string; interaction: VisualInteraction }) {
  const data = rows.filter((row) => row.value > 0).slice(0, 12);
  const total = data.reduce((sum, row) => sum + row.value, 0);
  if (!total) return <ChartEmptyState />;
  const slices = data.reduce<Array<{ row: ChartPoint; path: string }>>((items, row) => {
    const startAngle = items.reduce((angle, item) => angle + (item.row.value / total) * 360, -90);
    const sweep = (row.value / total) * 360;
    return [...items, { row, path: donutArcPath(210, 160, 120, 58, startAngle, startAngle + sweep) }];
  }, []);
  return (
    <div className="mt-4 grid min-h-80 gap-4 lg:grid-cols-[1.2fr_0.8fr]">
      <svg viewBox="0 0 420 320" className="h-80 w-full" role="img" aria-label={`Pie chart by ${yLabel}`}>
        <circle cx="210" cy="160" r="118" fill="#ffffff" />
        {slices.map(({ row, path }, index) => {
          const active = isActivePoint(row, interaction.activePoint);
          return (
            <path
              key={`${row.label}-${index}`}
              d={path}
              fill={row.color}
              stroke={active ? "#111827" : "#ffffff"}
              strokeWidth={active ? 5 : 3}
              opacity={active ? 1 : 0.55}
              {...interactiveMarkProps(row, interaction.onActivate)}
            >
              <title>{chartPointTitle(row, yLabel, total)}</title>
            </path>
          );
        })}
        <text x="210" y="153" textAnchor="middle" className="fill-ink text-[22px] font-bold">
          {formatNumber(total)}
        </text>
        <text x="210" y="176" textAnchor="middle" className="fill-ink/55 text-[12px] uppercase tracking-normal">
          total {yLabel}
        </text>
      </svg>
      <LegendList rows={data} total={total} interaction={interaction} />
    </div>
  );
}

function TreemapVisual({ rows, interaction }: { rows: ChartPoint[]; interaction: VisualInteraction }) {
  const data = rows.filter((row) => row.value > 0).slice(0, 16);
  const total = data.reduce((sum, row) => sum + row.value, 0) || 1;
  const rectangles = data.reduce<Array<{ row: ChartPoint; x: number; width: number }>>((items, row) => {
    const x = items.reduce((offset, item) => offset + item.width, 0);
    const width = (row.value / total) * SVG_WIDTH;
    return [...items, { row, x, width }];
  }, []);
  return (
    <ChartFrame>
      <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} className="h-full w-full" role="img" aria-label="Treemap chart">
        {rectangles.map(({ row, x, width }, index) => {
          const active = isActivePoint(row, interaction.activePoint);
          return (
            <g key={`${row.label}-${index}`} {...interactiveMarkProps(row, interaction.onActivate)} opacity={active ? 1 : 0.48}>
              <title>{chartPointTitle(row, "Value", total)}</title>
              <rect x={x + 2} y="28" width={Math.max(width - 4, 0)} height="270" rx="8" fill={row.color} stroke={active ? "#111827" : "transparent"} strokeWidth="3" />
              {width > 70 && (
                <>
                  <text x={x + 16} y="64" className="fill-white text-[13px] font-semibold">
                    {truncate(row.label, 14)}
                  </text>
                  <text x={x + 16} y="88" className="fill-white/85 text-[12px]">
                    {formatNumber(row.value)}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}

function RadialVisual({ rows, yLabel, interaction }: { rows: ChartPoint[]; yLabel: string; interaction: VisualInteraction }) {
  const data = rows.filter((row) => row.value > 0).slice(0, 8);
  const max = Math.max(...data.map((row) => row.value), 1);
  return (
    <ChartFrame>
      <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} className="h-full w-full" role="img" aria-label={`Radial chart by ${yLabel}`}>
        {data.map((row, index) => {
          const radius = 42 + index * 16;
          const end = -90 + (row.value / max) * 360;
          const active = isActivePoint(row, interaction.activePoint);
          return (
            <g key={`${row.label}-${index}`} {...interactiveMarkProps(row, interaction.onActivate)} opacity={active ? 1 : 0.48}>
              <title>{chartPointTitle(row, yLabel)}</title>
              <path d={arcPath(280, 178, radius, -90, 270)} fill="none" stroke="#e3eee8" strokeWidth="10" strokeLinecap="round" />
              <path d={arcPath(280, 178, radius, -90, end)} fill="none" stroke={row.color} strokeWidth={active ? 14 : 10} strokeLinecap="round" />
              <text x="475" y={70 + index * 25} className="fill-ink text-[12px]">
                {truncate(row.label, 24)}: {formatNumber(row.value)}
              </text>
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}

function RadarVisual({ rows, yLabel, interaction }: { rows: ChartPoint[]; yLabel: string; interaction: VisualInteraction }) {
  const data = rows.filter((row) => row.value >= 0).slice(0, 10);
  const max = Math.max(...data.map((row) => row.value), 1);
  const cx = 440;
  const cy = 176;
  const radius = 120;
  const points = data.map((row, index) => {
    const angle = -Math.PI / 2 + (index / data.length) * Math.PI * 2;
    const valueRadius = (row.value / max) * radius;
    return {
      x: cx + Math.cos(angle) * valueRadius,
      y: cy + Math.sin(angle) * valueRadius,
      lx: cx + Math.cos(angle) * (radius + 28),
      ly: cy + Math.sin(angle) * (radius + 28),
      row,
    };
  });
  return (
    <ChartFrame>
      <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} className="h-full w-full" role="img" aria-label={`Radar chart by ${yLabel}`}>
        {[0.25, 0.5, 0.75, 1].map((scale) => (
          <circle key={scale} cx={cx} cy={cy} r={radius * scale} fill="none" stroke="#dbe8df" />
        ))}
        {points.map((point, index) => (
          <g key={`${point.row.label}-${index}`} {...interactiveMarkProps(point.row, interaction.onActivate)}>
            <line x1={cx} y1={cy} x2={point.lx} y2={point.ly} stroke="#dbe8df" />
            <text x={point.lx} y={point.ly} textAnchor={point.lx < cx ? "end" : "start"} className="fill-ink/65 text-[10px]">
              {truncate(point.row.label, 12)}
            </text>
          </g>
        ))}
        <polygon points={points.map((point) => `${point.x},${point.y}`).join(" ")} fill="#5b8def" opacity="0.28" stroke="#5b8def" strokeWidth="3" />
        {points.map((point, index) => {
          const active = isActivePoint(point.row, interaction.activePoint);
          return (
            <circle
              key={`${point.row.label}-point-${index}`}
              cx={point.x}
              cy={point.y}
              r={active ? 8 : 5}
              fill={point.row.color}
              stroke={active ? "#111827" : "#ffffff"}
              strokeWidth="2"
              opacity={active ? 1 : 0.7}
              {...interactiveMarkProps(point.row, interaction.onActivate)}
            >
              <title>{chartPointTitle(point.row, yLabel)}</title>
            </circle>
          );
        })}
      </svg>
    </ChartFrame>
  );
}

function LegendList({ rows, total, interaction }: { rows: ChartPoint[]; total: number; interaction: VisualInteraction }) {
  return (
    <div className="grid max-h-80 content-center gap-2 overflow-y-auto pr-1">
      {rows.map((row, index) => (
        <button
          key={`${row.label}-${index}`}
          type="button"
          title={chartPointTitle(row, "Value", total)}
          onMouseEnter={() => interaction.onActivate(row)}
          onFocus={() => interaction.onActivate(row)}
          onClick={() => interaction.onActivate(row)}
          className={`flex items-center justify-between gap-3 rounded-md px-3 py-2 text-left transition ${
            isActivePoint(row, interaction.activePoint) ? "bg-ink text-white" : "bg-white text-ink hover:bg-mint/15"
          }`}
        >
          <span className="flex min-w-0 items-center gap-2">
            <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: row.color }} />
            <span className="truncate text-sm font-medium">{row.label}</span>
          </span>
          <span className="text-sm font-semibold opacity-75">{Math.round((row.value / total) * 100)}%</span>
        </button>
      ))}
    </div>
  );
}

function ActiveDatumPanel({ point, xLabel, yLabel, total }: { point: ChartPoint | null; xLabel: string; yLabel: string; total: number }) {
  if (!point) {
    return null;
  }
  const percent = total > 0 && point.value > 0 ? `${((point.value / total) * 100).toFixed(1)}%` : null;
  return (
    <div className="mt-4 grid gap-2 rounded-md border border-ink/10 bg-white p-3 sm:grid-cols-[1fr_auto_auto] sm:items-center">
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-normal text-ink/45">{xLabel}</p>
        <p className="mt-1 break-words text-sm font-semibold text-ink">{point.label}</p>
      </div>
      <div className="rounded-md bg-cloud px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-normal text-ink/45">{yLabel}</p>
        <p className="mt-1 text-sm font-bold text-ink">{formatNumber(point.value)}</p>
      </div>
      {percent && (
        <div className="rounded-md bg-mint/20 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-normal text-ink/45">Share</p>
          <p className="mt-1 text-sm font-bold text-ink">{percent}</p>
        </div>
      )}
    </div>
  );
}

function ChartFrame({ children, minHeight = 320, minWidth = SVG_WIDTH }: { children: ReactNode; minHeight?: number; minWidth?: number }) {
  return (
    <div className="mt-4 h-80 w-full overflow-auto rounded-md bg-white p-2">
      <div style={{ minHeight, minWidth }} className="h-full">
        {children}
      </div>
    </div>
  );
}

function interactiveMarkProps(point: ChartPoint, onActivate: (point: ChartPoint) => void) {
  return {
    role: "button" as const,
    tabIndex: 0,
    onMouseEnter: () => onActivate(point),
    onFocus: () => onActivate(point),
    onClick: () => onActivate(point),
    className: "cursor-pointer outline-none transition duration-150",
  };
}

function isActivePoint(point: ChartPoint, activePoint: ChartPoint | null) {
  if (!activePoint) return true;
  return point.label === activePoint.label && point.value === activePoint.value;
}

function chartPointTitle(point: ChartPoint, yLabel: string, total?: number) {
  const percent = total && total > 0 && point.value > 0 ? ` (${((point.value / total) * 100).toFixed(1)}%)` : "";
  return `${point.label}: ${formatNumber(point.value)} ${yLabel}${percent}`;
}

function Grid({ plot }: { plot: { left: number; top: number; width: number; height: number } }) {
  return (
    <g>
      {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
        const y = plot.top + tick * plot.height;
        return <line key={tick} x1={plot.left} y1={y} x2={plot.left + plot.width} y2={y} stroke="#dbe8df" strokeWidth="1" />;
      })}
      <line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.top + plot.height} stroke="#b8c9c0" />
      <line x1={plot.left} y1={plot.top + plot.height} x2={plot.left + plot.width} y2={plot.top + plot.height} stroke="#b8c9c0" />
    </g>
  );
}

function AxisLabel({ x, y, label, rotate = false }: { x: number; y: number; label: string; rotate?: boolean }) {
  return (
    <text x={x} y={y} textAnchor="middle" transform={rotate ? `rotate(-90 ${x} ${y})` : undefined} className="fill-ink/55 text-[11px] font-semibold uppercase tracking-normal">
      {label}
    </text>
  );
}

function ChartEmptyState() {
  return (
    <div className="mt-4 flex h-80 items-center justify-center rounded-md bg-white text-sm text-ink/60">
      This result needs a label column and numeric values before it can be visualized.
    </div>
  );
}

function normalizedChartRows(block: ResultBlock): ChartPoint[] {
  const chart = block.chart;
  if (!chart.x_key || !chart.y_key) return [];
  const numericX = chart.chart_type === "scatter" || chart.chart_type === "histogram";
  return block.rows
    .map((row, index) => {
      const value = finiteNumericValue(row[chart.y_key as string]);
      const rawX = row[chart.x_key as string];
      const xNumber = numericX ? finiteNumericValue(rawX) : null;
      if (value === null || rawX === null || rawX === undefined || rawX === "") {
        return null;
      }
      if (numericX && xNumber === null) {
        return null;
      }
      return {
        label: String(rawX),
        value,
        xNumber,
        color: chartPalette[index % chartPalette.length],
      };
    })
    .filter((row): row is ChartPoint => row !== null);
}

function histogramRows(rows: ChartPoint[]): ChartPoint[] {
  const values = rows.map((row) => row.value).filter((value) => Number.isFinite(value));
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return [{ label: String(min), value: values.length, xNumber: null, color: chartPalette[0] }];
  }
  const binCount = Math.min(10, Math.max(4, Math.ceil(Math.sqrt(values.length))));
  const binSize = (max - min) / binCount;
  const bins = Array.from({ length: binCount }, (_, index) => {
    const start = min + index * binSize;
    const end = index === binCount - 1 ? max : start + binSize;
    return {
      label: `${formatNumber(start)}-${formatNumber(end)}`,
      value: 0,
      xNumber: null,
      color: chartPalette[index % chartPalette.length],
    };
  });
  values.forEach((value) => {
    const index = Math.min(Math.floor((value - min) / binSize), binCount - 1);
    bins[index].value += 1;
  });
  return bins;
}

function donutArcPath(cx: number, cy: number, outerRadius: number, innerRadius: number, startAngle: number, endAngle: number) {
  const outerStart = polarPoint(cx, cy, outerRadius, startAngle);
  const outerEnd = polarPoint(cx, cy, outerRadius, endAngle);
  const innerStart = polarPoint(cx, cy, innerRadius, endAngle);
  const innerEnd = polarPoint(cx, cy, innerRadius, startAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outerRadius} ${outerRadius} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerStart.x} ${innerStart.y}`,
    `A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${innerEnd.x} ${innerEnd.y}`,
    "Z",
  ].join(" ");
}

function arcPath(cx: number, cy: number, radius: number, startAngle: number, endAngle: number) {
  const start = polarPoint(cx, cy, radius, startAngle);
  const end = polarPoint(cx, cy, radius, endAngle);
  const largeArc = Math.abs(endAngle - startAngle) > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x} ${end.y}`;
}

function polarPoint(cx: number, cy: number, radius: number, angle: number) {
  const radians = (angle * Math.PI) / 180;
  return {
    x: cx + radius * Math.cos(radians),
    y: cy + radius * Math.sin(radians),
  };
}

function formatColumnName(column: string) {
  return column.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatChartType(chartType: string) {
  return chartType.replace(/_/g, " ");
}

function finiteNumericValue(value: unknown) {
  const cleanedValue = typeof value === "string" ? value.trim().replace(/,/g, "").replace(/%$/, "") : value;
  const numberValue = typeof cleanedValue === "number" ? cleanedValue : Number(cleanedValue);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function truncate(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value;
}

function DataTable({ block }: { block: ResultBlock }) {
  return (
    <div className="mt-5 overflow-x-auto rounded-lg border border-ink/10">
      <table className="min-w-full divide-y divide-ink/10 text-sm">
        <thead className="bg-cloud">
          <tr>
            {block.columns.map((column) => (
              <th key={column} className="px-3 py-3 text-left font-semibold text-ink">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink/10 bg-white">
          {block.rows.slice(0, 100).map((row, index) => (
            <tr key={index}>
              {block.columns.map((column) => (
                <td key={column} className="max-w-72 truncate px-3 py-3 text-ink/75">
                  {String(row[column] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
