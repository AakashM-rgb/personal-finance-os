"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { NetWorthTrendPoint } from "@/lib/reports";

const LINE_COLOR = "#2563eb"; // blue-600

function formatMonthLabel(month: string): string {
  return new Date(`${month}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
}

interface NetWorthTrendChartProps {
  trend: NetWorthTrendPoint[];
  currency: string;
}

export function NetWorthTrendChart({ trend, currency }: NetWorthTrendChartProps) {
  const chartData = trend.map((p) => ({ label: formatMonthLabel(p.month), amount: p.net_worth_minor }));

  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Net worth trend</h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Reconstructed from your transaction history over the last 12 months.
      </p>

      {chartData.length < 2 ? (
        <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
          Not enough history yet to show a trend.
        </p>
      ) : (
        <div className="mt-4 h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="currentColor"
                className="text-zinc-200 dark:text-zinc-800"
                vertical={false}
              />
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
              <Line type="monotone" dataKey="amount" stroke={LINE_COLOR} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
