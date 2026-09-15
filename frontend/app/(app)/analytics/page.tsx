"use client";

import { useEffect, useState } from "react";

import { BudgetPerformanceList } from "@/components/analytics/budget-performance-list";
import { CategoryBreakdownList } from "@/components/analytics/category-breakdown-list";
import { DailySpendingChart } from "@/components/analytics/daily-spending-chart";
import { DateRangeSelector } from "@/components/analytics/date-range-selector";
import { IncomeVsExpenseChart } from "@/components/analytics/income-vs-expense-chart";
import { RecurringExpenseBreakdownList } from "@/components/analytics/recurring-expense-breakdown-list";
import { SavingsTrendChart } from "@/components/analytics/savings-trend-chart";
import { SpendingOverTimeChart } from "@/components/analytics/spending-over-time-chart";
import { Skeleton } from "@/components/ui/skeleton";
import { getAnalytics, type Analytics, type AnalyticsRange } from "@/lib/analytics";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function AnalyticsPage() {
  const { accessToken } = useAuth();

  const [range, setRange] = useState<AnalyticsRange>("current_month");
  const [customFrom, setCustomFrom] = useState(todayIso());
  const [customTo, setCustomTo] = useState(todayIso());
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const isCustomIncomplete = range === "custom" && (!customFrom || !customTo);

  useEffect(() => {
    if (!accessToken || isCustomIncomplete) return;
    let isMounted = true;

    void getAnalytics(accessToken, { range, custom_from: customFrom, custom_to: customTo })
      .then((result) => {
        if (isMounted) {
          setData(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setData(null);
          setError(err instanceof ApiError ? err.message : "Failed to load analytics.");
        }
      });

    return () => {
      isMounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, range, customFrom, customTo, reloadToken]);

  const isLoading = data === null && !error && !isCustomIncomplete;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Analytics</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Real answers about your money, from your own transaction history.
        </p>
      </div>

      <DateRangeSelector
        range={range}
        customFrom={customFrom}
        customTo={customTo}
        onRangeChange={setRange}
        onCustomFromChange={setCustomFrom}
        onCustomToChange={setCustomTo}
      />

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button
            type="button"
            onClick={() => setReloadToken((n) => n + 1)}
            className="font-medium underline"
          >
            Try again
          </button>
        </div>
      )}

      {isCustomIncomplete && !error && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Choose both a start and end date for a custom range.
          </p>
        </div>
      )}

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      )}

      {data && !error && (
        <div className="grid gap-4 sm:grid-cols-2">
          <SpendingOverTimeChart data={data.spending_over_time} currency={data.currency} />
          <CategoryBreakdownList data={data.category_breakdown} currency={data.currency} />
          <IncomeVsExpenseChart data={data.income_vs_expense} currency={data.currency} />
          <SavingsTrendChart data={data.savings_trend} currency={data.currency} />
          <DailySpendingChart data={data.daily_spending} currency={data.currency} />
          <BudgetPerformanceList budgets={data.budget_performance} currency={data.currency} />
          <div className="sm:col-span-2">
            <RecurringExpenseBreakdownList
              data={data.recurring_expense_breakdown}
              currency={data.currency}
            />
          </div>
        </div>
      )}
    </div>
  );
}
