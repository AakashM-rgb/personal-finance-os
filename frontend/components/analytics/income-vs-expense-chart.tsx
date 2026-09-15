"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import type { IncomeVsExpense } from "@/lib/analytics";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const INCOME_COLOR = "#059669"; // emerald-600
const EXPENSE_COLOR = "#2563eb"; // blue-600

interface IncomeVsExpenseChartProps {
  data: IncomeVsExpense;
  currency: string;
}

export function IncomeVsExpenseChart({ data, currency }: IncomeVsExpenseChartProps) {
  const chartData = [
    { label: "Income", amount: data.total_income_minor, color: INCOME_COLOR },
    { label: "Expense", amount: data.total_expense_minor, color: EXPENSE_COLOR },
  ];
  const hasAnyData = data.total_income_minor > 0 || data.total_expense_minor > 0;

  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Income vs expenses</h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">Am I spending more than I earn?</p>

      <div className="mt-3 flex items-baseline gap-2">
        <span
          className={cn(
            "text-2xl font-semibold",
            data.net_minor >= 0
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-red-600 dark:text-red-400"
          )}
        >
          {formatMoney(data.net_minor, currency)}
        </span>
        <span className="text-sm text-zinc-500 dark:text-zinc-400">
          {data.is_spending_more_than_earning ? "net deficit" : "net surplus"}
        </span>
      </div>

      {!hasAnyData ? (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          No income or expenses recorded in this range yet.
        </p>
      ) : (
        <div className="mt-4 h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
              <XAxis
                type="number"
                tick={{ fontSize: 11 }}
                stroke="currentColor"
                className="text-zinc-500 dark:text-zinc-400"
                tickFormatter={(value: number) => formatMoney(value, currency).replace(/\.00$/, "")}
              />
              <YAxis
                type="category"
                dataKey="label"
                tick={{ fontSize: 12 }}
                stroke="currentColor"
                className="text-zinc-700 dark:text-zinc-300"
                width={64}
              />
              <Tooltip
                formatter={(value) => formatMoney(Number(value ?? 0), currency)}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Bar dataKey="amount" radius={4} maxBarSize={36}>
                {chartData.map((entry) => (
                  <Cell key={entry.label} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
