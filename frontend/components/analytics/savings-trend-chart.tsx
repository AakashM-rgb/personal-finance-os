"use client";

import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/card";
import type { SavingsTrend } from "@/lib/analytics";
import { formatMoney } from "@/lib/money";

import { TrendBadge } from "./trend-badge";

const SURPLUS_COLOR = "#059669"; // emerald-600
const DEFICIT_COLOR = "#dc2626"; // red-600

function formatMonthLabel(period: string): string {
  return new Date(`${period}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
}

interface SavingsTrendChartProps {
  data: SavingsTrend;
  currency: string;
}

export function SavingsTrendChart({ data, currency }: SavingsTrendChartProps) {
  const chartData = data.points.map((p) => ({
    label: formatMonthLabel(p.period),
    savings: p.savings_minor,
  }));
  const hasAnyData = chartData.some((d) => d.savings !== 0);

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Savings trend</h2>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Is my savings position improving?
          </p>
        </div>
        <TrendBadge trend={data.trend} increasingIsGood={true} />
      </div>

      {chartData.length < 2 ? (
        <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
          Select a longer range to see a savings trend across multiple months.
        </p>
      ) : !hasAnyData ? (
        <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
          No income or expenses recorded in this range yet.
        </p>
      ) : (
        <div className="mt-4 h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11 }}
                stroke="currentColor"
                className="text-zinc-500 dark:text-zinc-400"
                minTickGap={20}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                stroke="currentColor"
                className="text-zinc-500 dark:text-zinc-400"
                width={56}
                tickFormatter={(value: number) => formatMoney(value, currency).replace(/\.00$/, "")}
              />
              <ReferenceLine y={0} stroke="currentColor" className="text-zinc-400 dark:text-zinc-600" />
              <Tooltip
                formatter={(value) => formatMoney(Number(value ?? 0), currency)}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Bar dataKey="savings" radius={3} maxBarSize={28}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.label}
                    fill={entry.savings >= 0 ? SURPLUS_COLOR : DEFICIT_COLOR}
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
