import { Card } from "@/components/ui/card";
import type { MonthlySpending } from "@/lib/dashboard";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

export function MonthlySpendingCard({
  spending,
  currency,
}: {
  spending: MonthlySpending;
  currency: string;
}) {
  const { percent_change: percentChange } = spending;

  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Monthly spending</h2>

      <div className="mt-3 flex items-end gap-3">
        <span className="text-2xl font-semibold text-zinc-900 [font-variant-numeric:proportional-nums] dark:text-zinc-50">
          {formatMoney(spending.current_month_expense_minor, currency)}
        </span>
        {percentChange !== null && (
          <span
            className={cn(
              "text-sm font-medium",
              // For spending, an increase is unfavorable and a decrease is favorable.
              percentChange > 0
                ? "text-red-600 dark:text-red-400"
                : "text-emerald-600 dark:text-emerald-400"
            )}
          >
            {percentChange > 0 ? "+" : ""}
            {percentChange.toFixed(1)}%
          </span>
        )}
      </div>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        {percentChange === null
          ? "No spending recorded last month to compare against."
          : `vs ${formatMoney(spending.previous_month_expense_minor, currency)} last month`}
      </p>

      <div className="mt-4 grid grid-cols-2 gap-4 border-t border-zinc-100 pt-4 dark:border-zinc-800">
        <div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Daily average</p>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
            {formatMoney(spending.daily_average_minor, currency)}
          </p>
        </div>
        <div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Projected this month <span title="An estimate based on your average daily spending so far - not a guarantee.">(estimate)</span>
          </p>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
            {formatMoney(spending.projected_month_expense_minor, currency)}
          </p>
        </div>
      </div>
    </Card>
  );
}
