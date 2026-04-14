"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Treemap,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { QueryResponse, ResultBlock } from "@/types/api";

const chartPalette = ["#1fbf9b", "#ff6f61", "#5b8def", "#f5b841", "#8f6ed5", "#2f9e44", "#f06595", "#20a4f3"];

export function ResultsView({ response }: { response: QueryResponse | null }) {
  if (!response) {
    return (
      <div className="rounded-lg border border-ink/10 bg-white p-6 text-center text-ink/60">
        Ask a question after adding a source. Results, charts, SQL preview, and the single grounded summary will appear here.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {response.result_blocks.map((block) => (
        <ResultSection key={block.id} block={block} />
      ))}
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
  return (
    <article className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft transition">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-normal text-coral">{block.source_name}</p>
          <h3 className="mt-1 text-lg font-semibold text-ink">{block.question}</h3>
        </div>
        <span className="rounded-md bg-cloud px-3 py-1 text-sm text-ink/70">{block.rows.length} rows</span>
      </div>
      {block.chart.enabled && <Chart block={block} />}
      <DataTable block={block} />
      {block.sql && (
        <details className="mt-4 max-w-full rounded-md bg-cloud p-3" onClick={(event) => event.stopPropagation()}>
          <summary className="cursor-pointer text-sm font-semibold text-ink">See generated SQL code?</summary>
          <pre className="mt-3 max-h-44 max-w-full whitespace-pre-wrap break-words rounded-md bg-white p-3 text-xs leading-5 text-ink">{block.sql}</pre>
        </details>
      )}
    </article>
  );
}

function Chart({ block }: { block: ResultBlock }) {
  const chart = block.chart;
  if (!chart.x_key || !chart.y_key) return null;
  const xLabel = formatColumnName(chart.x_key);
  const yLabel = formatColumnName(chart.y_key);
  const isPie = chart.chart_type === "pie";
  const isHistogram = chart.chart_type === "histogram";
  const chartRows = normalizedChartRows(block);
  return (
    <div className="mt-5 w-full rounded-lg border border-ink/10 bg-[#fbfefc] p-4">
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-semibold uppercase tracking-normal text-ink/60">
        <span>{isPie ? "Slices" : isHistogram ? "Bins" : "X-axis"}: {xLabel}</span>
        <span>{isPie ? "Values" : isHistogram ? "Frequency" : "Y-axis"}: {isHistogram ? "Count" : yLabel}</span>
      </div>
      <div className="h-80">
        {chartRows.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <ChartGraphic block={block} chartRows={chartRows} xLabel={xLabel} yLabel={yLabel} />
          </ResponsiveContainer>
        ) : (
          <ChartEmptyState />
        )}
      </div>
    </div>
  );
}

function ChartGraphic({
  block,
  chartRows,
  xLabel,
  yLabel,
}: {
  block: ResultBlock;
  chartRows: Record<string, unknown>[];
  xLabel: string;
  yLabel: string;
}) {
  const chart = block.chart;
  if (!chart.x_key || !chart.y_key) return null;
  const commonMargin = { top: 8, right: 24, bottom: 36, left: 28 };

  if (chart.chart_type === "horizontal_bar") {
    return (
      <BarChart data={chartRows} layout="vertical" margin={{ top: 8, right: 24, bottom: 24, left: 72 }}>
        <CartesianGrid stroke="#dbe8df" />
        <XAxis type="number" tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey={chart.x_key} width={86} tick={{ fontSize: 12 }} />
        <Tooltip labelFormatter={(label) => `${xLabel}: ${label}`} formatter={(value) => [value, yLabel]} />
        <Bar dataKey={chart.y_key} radius={[0, 6, 6, 0]}>
          {chartRows.map((_, index) => (
            <Cell key={`horizontal-bar-${index}`} fill={chartPalette[index % chartPalette.length]} />
          ))}
        </Bar>
      </BarChart>
    );
  }

  if (chart.chart_type === "line") {
    return (
      <LineChart data={chartRows} margin={commonMargin}>
        <CartesianGrid stroke="#dbe8df" />
        <XAxis dataKey={chart.x_key} tick={{ fontSize: 12 }} label={{ value: xLabel, position: "insideBottom", offset: -24 }} />
        <YAxis tick={{ fontSize: 12 }} label={{ value: yLabel, angle: -90, position: "insideLeft", offset: -16 }} />
        <Tooltip labelFormatter={(label) => `${xLabel}: ${label}`} formatter={(value) => [value, yLabel]} />
        <Line type="monotone" dataKey={chart.y_key} stroke="#1fbf9b" strokeWidth={3} dot={{ fill: "#ff6f61" }} />
      </LineChart>
    );
  }

  if (chart.chart_type === "area") {
    return (
      <AreaChart data={chartRows} margin={commonMargin}>
        <CartesianGrid stroke="#dbe8df" />
        <XAxis dataKey={chart.x_key} tick={{ fontSize: 12 }} label={{ value: xLabel, position: "insideBottom", offset: -24 }} />
        <YAxis tick={{ fontSize: 12 }} label={{ value: yLabel, angle: -90, position: "insideLeft", offset: -16 }} />
        <Tooltip labelFormatter={(label) => `${xLabel}: ${label}`} formatter={(value) => [value, yLabel]} />
        <Area type="monotone" dataKey={chart.y_key} stroke="#1fbf9b" fill="#1fbf9b" fillOpacity={0.28} strokeWidth={3} />
      </AreaChart>
    );
  }

  if (chart.chart_type === "pie") {
    return (
      <PieChart>
        <Tooltip formatter={(value) => [value, yLabel]} />
        <Legend />
        <Pie data={chartRows} dataKey={chart.y_key} nameKey={chart.x_key} innerRadius={54} outerRadius={104} paddingAngle={2} label>
          {chartRows.map((_, index) => (
            <Cell key={`slice-${index}`} fill={chartPalette[index % chartPalette.length]} />
          ))}
        </Pie>
      </PieChart>
    );
  }

  if (chart.chart_type === "radial_bar") {
    return (
      <RadialBarChart data={chartRows} innerRadius="18%" outerRadius="90%" startAngle={90} endAngle={-270}>
        <Tooltip formatter={(value) => [value, yLabel]} />
        <Legend />
        <RadialBar dataKey={chart.y_key} name={yLabel} background>
          {chartRows.map((_, index) => (
            <Cell key={`radial-${index}`} fill={chartPalette[index % chartPalette.length]} />
          ))}
        </RadialBar>
      </RadialBarChart>
    );
  }

  if (chart.chart_type === "treemap") {
    return (
      <Treemap data={buildNamedValueRows(chartRows, chart.x_key, chart.y_key)} dataKey="value" nameKey="name" stroke="#ffffff" fill="#1fbf9b">
        <Tooltip formatter={(value) => [value, yLabel]} />
      </Treemap>
    );
  }

  if (chart.chart_type === "radar") {
    return (
      <RadarChart data={chartRows} margin={{ top: 16, right: 32, bottom: 16, left: 32 }}>
        <PolarGrid stroke="#dbe8df" />
        <PolarAngleAxis dataKey={chart.x_key} tick={{ fontSize: 12 }} />
        <PolarRadiusAxis tick={{ fontSize: 11 }} />
        <Tooltip formatter={(value) => [value, yLabel]} />
        <Radar dataKey={chart.y_key} stroke="#5b8def" fill="#5b8def" fillOpacity={0.35} />
      </RadarChart>
    );
  }

  if (chart.chart_type === "scatter") {
    return (
      <ScatterChart margin={commonMargin}>
        <CartesianGrid stroke="#dbe8df" />
        <XAxis type="number" dataKey={chart.x_key} name={xLabel} tick={{ fontSize: 12 }} label={{ value: xLabel, position: "insideBottom", offset: -24 }} />
        <YAxis type="number" dataKey={chart.y_key} name={yLabel} tick={{ fontSize: 12 }} label={{ value: yLabel, angle: -90, position: "insideLeft", offset: -16 }} />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} />
        <Scatter data={chartRows} fill="#5b8def" />
      </ScatterChart>
    );
  }

  if (chart.chart_type === "histogram") {
    const histogramRows = buildHistogramRows(chartRows, chart.y_key);
    return (
      <BarChart data={histogramRows} margin={commonMargin}>
        <CartesianGrid stroke="#dbe8df" />
        <XAxis dataKey="bin" tick={{ fontSize: 12 }} label={{ value: xLabel, position: "insideBottom", offset: -24 }} />
        <YAxis tick={{ fontSize: 12 }} label={{ value: "Count", angle: -90, position: "insideLeft", offset: -16 }} />
        <Tooltip formatter={(value) => [value, "Count"]} />
        <Bar dataKey="count" fill="#5b8def" radius={[6, 6, 0, 0]} />
      </BarChart>
    );
  }

  return (
    <BarChart data={chartRows} margin={commonMargin}>
      <CartesianGrid stroke="#dbe8df" />
      <XAxis dataKey={chart.x_key} tick={{ fontSize: 12 }} label={{ value: xLabel, position: "insideBottom", offset: -24 }} />
      <YAxis tick={{ fontSize: 12 }} label={{ value: yLabel, angle: -90, position: "insideLeft", offset: -16 }} />
      <Tooltip labelFormatter={(label) => `${xLabel}: ${label}`} formatter={(value) => [value, yLabel]} />
      <Bar dataKey={chart.y_key} radius={[6, 6, 0, 0]}>
        {chartRows.map((_, index) => (
          <Cell key={`bar-${index}`} fill={chartPalette[index % chartPalette.length]} />
        ))}
      </Bar>
    </BarChart>
  );
}

function formatColumnName(column: string) {
  return column.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function ChartEmptyState() {
  return (
    <div className="flex h-full items-center justify-center rounded-md bg-white text-sm text-ink/60">
      This result needs a label column and numeric values before it can be visualized.
    </div>
  );
}

function normalizedChartRows(block: ResultBlock) {
  const chart = block.chart;
  if (!chart.x_key || !chart.y_key) return [];
  const numericX = chart.chart_type === "scatter" || chart.chart_type === "histogram";
  return block.rows
    .map((row) => {
      const yValue = finiteNumericValue(row[chart.y_key as string]);
      const xValue = numericX ? finiteNumericValue(row[chart.x_key as string]) : row[chart.x_key as string];
      if (yValue === null || xValue === null || xValue === undefined || xValue === "") {
        return null;
      }
      return {
        ...row,
        [chart.x_key as string]: xValue,
        [chart.y_key as string]: yValue,
      };
    })
    .filter((row): row is Record<string, unknown> => row !== null);
}

function buildNamedValueRows(rows: Record<string, unknown>[], nameKey: string, valueKey: string) {
  return rows
    .map((row, index) => ({
      name: String(row[nameKey] ?? `Item ${index + 1}`),
      value: numericValue(row[valueKey]),
      fill: chartPalette[index % chartPalette.length],
    }))
    .filter((row) => row.value > 0);
}

function buildHistogramRows(rows: Record<string, unknown>[], valueKey: string) {
  const values = rows.map((row) => numericValue(row[valueKey])).filter((value) => Number.isFinite(value));
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return [{ bin: String(min), count: values.length }];
  }
  const binCount = Math.min(10, Math.max(4, Math.ceil(Math.sqrt(values.length))));
  const binSize = (max - min) / binCount;
  const bins = Array.from({ length: binCount }, (_, index) => {
    const start = min + index * binSize;
    const end = index === binCount - 1 ? max : start + binSize;
    return {
      bin: `${formatNumber(start)}-${formatNumber(end)}`,
      start,
      end,
      count: 0,
    };
  });
  values.forEach((value) => {
    const index = Math.min(Math.floor((value - min) / binSize), binCount - 1);
    bins[index].count += 1;
  });
  return bins.map(({ bin, count }) => ({ bin, count }));
}

function numericValue(value: unknown) {
  return finiteNumericValue(value) ?? 0;
}

function finiteNumericValue(value: unknown) {
  const numberValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
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
