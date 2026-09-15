"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/card";
import type { SpendingOverTime } from "@/lib/analytics";
import { formatMoney } from "@/lib/money";

import { TrendBadge } from "./trend-badge";

const LINE_COLOR = "#2563eb"; // blue-600

function formatPeriodLabel(period: string, granularity: "day" | "month"): string {
  const parsed = new Date(`${period}T00:00:00`);
  return parsed.toLocaleDateString(undefined, {
    day: granularity === "day" ? "numeric" : undefined,
    month: "short",
    year: granularity === "month" ? "numeric" : undefined,
  });
}

interface SpendingOverTimeChartProps {
  data: SpendingOverTime;
  currency: string;
}

export function SpendingOverTimeChart({ data, currency }: SpendingOverTimeChartProps) {
  const chartData = data.points.map((p) => ({
    period: p.period,
    label: formatPeriodLabel(p.period, data.granularity),
    amount: p.amount_minor,
  }));

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
            Spending over time
          </h2>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Is my spending increasing or decreasing?
          </p>
        </div>
        <TrendBadge trend={data.trend} increasingIsGood={false} />
      </div>

      {chartData.every((d) => d.amount === 0) ? (
        <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
          No expenses recorded in this range yet.
        </p>
      ) : (
        <div className="mt-4 h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-zinc-200 dark:text-zinc-800" vertical={false} />
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
              <Tooltip
                formatter={(value) => formatMoney(Number(value ?? 0), currency)}
                labelStyle={{ color: "#0b0b0b" }}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Line
                type="monotone"
                dataKey="amount"
                stroke={LINE_COLOR}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
