"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import type { DailySpending } from "@/lib/analytics";
import { formatMoney } from "@/lib/money";

const BAR_COLOR = "#2563eb"; // blue-600
const HIGHLIGHT_COLOR = "#f97316"; // orange-500

function formatDayLabel(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

interface DailySpendingChartProps {
  data: DailySpending;
  currency: string;
}

export function DailySpendingChart({ data, currency }: DailySpendingChartProps) {
  const chartData = data.points.map((p) => ({
    day: p.day,
    label: formatDayLabel(p.day),
    amount: p.amount_minor,
  }));
  const hasAnyData = data.highest_amount_minor > 0;

  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Daily spending</h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">Which days am I spending the most?</p>

      {hasAnyData && data.highest_day && (
        <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
          Highest:{" "}
          <span className="font-medium text-orange-600 dark:text-orange-400">
            {formatDayLabel(data.highest_day)} &middot;{" "}
            {formatMoney(data.highest_amount_minor, currency)}
          </span>
        </p>
      )}

      {!hasAnyData ? (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          No expenses recorded in this range yet.
        </p>
      ) : (
        <div className="mt-4 h-56 w-full">
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
              <Bar dataKey="amount" radius={2} maxBarSize={18}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.day}
                    fill={entry.day === data.highest_day ? HIGHLIGHT_COLOR : BAR_COLOR}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
