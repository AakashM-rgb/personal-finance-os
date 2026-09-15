"use client";

import {
  CartesianGrid,
  Legend,
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
import type { MonthlyAmount } from "@/lib/reports";

const INCOME_COLOR = "#059669"; // emerald-600
const EXPENSE_COLOR = "#dc2626"; // red-600
const SAVINGS_COLOR = "#2563eb"; // blue-600

function formatMonthLabel(month: string): string {
  return new Date(`${month}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
}

interface YearlyTrendChartProps {
  incomeTrend: MonthlyAmount[];
  expenseTrend: MonthlyAmount[];
  savingsTrend: MonthlyAmount[];
  currency: string;
}

export function YearlyTrendChart({
  incomeTrend,
  expenseTrend,
  savingsTrend,
  currency,
}: YearlyTrendChartProps) {
  const chartData = incomeTrend.map((point, i) => ({
    label: formatMonthLabel(point.month),
    income: point.amount_minor,
    expense: expenseTrend[i]?.amount_minor ?? 0,
    savings: savingsTrend[i]?.amount_minor ?? 0,
  }));
  const hasAnyData = chartData.some((d) => d.income !== 0 || d.expense !== 0 || d.savings !== 0);

  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Monthly trends</h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Income, expenses, and savings across the year.
      </p>

      {!hasAnyData ? (
        <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
          No transactions recorded in this year yet.
        </p>
      ) : (
        <div className="mt-4 h-64 w-full">
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
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="income" name="Income" stroke={INCOME_COLOR} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="expense" name="Expenses" stroke={EXPENSE_COLOR} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="savings" name="Savings" stroke={SAVINGS_COLOR} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
