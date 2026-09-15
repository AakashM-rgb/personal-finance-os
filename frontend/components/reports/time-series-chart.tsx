"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatMoney } from "@/lib/money";
import type { TimeSeriesPoint } from "@/lib/reports";

function formatPeriodLabel(period: string): string {
  const parsed = new Date(`${period}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return period;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

interface TimeSeriesChartProps {
  points: TimeSeriesPoint[];
  currency: string;
  color: string;
  emptyMessage: string;
}

export function TimeSeriesChart({ points, currency, color, emptyMessage }: TimeSeriesChartProps) {
  const chartData = points.map((p) => ({ label: formatPeriodLabel(p.period), amount: p.amount_minor }));
  const hasAnyData = chartData.some((d) => d.amount !== 0);

  if (!hasAnyData) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">{emptyMessage}</p>;
  }

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10 }}
            stroke="currentColor"
            className="text-zinc-500 dark:text-zinc-400"
            minTickGap={16}
          />
          <YAxis
            tick={{ fontSize: 11 }}
            stroke="currentColor"
            className="text-zinc-500 dark:text-zinc-400"
            width={56}
            tickFormatter={(value: number) => formatMoney(value, currency).replace(/\.00$/, "")}
          />
          <Tooltip
            formatter={(value) => formatMoney(Number(value ?? 0), currency)}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Bar dataKey="amount" fill={color} radius={2} maxBarSize={18} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
