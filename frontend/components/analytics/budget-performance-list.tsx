import { Card } from "@/components/ui/card";
import type { Budget, BudgetStatus } from "@/lib/budgets";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<BudgetStatus, { bar: string; badge: string; label: string }> = {
  healthy: {
    bar: "bg-emerald-600",
    badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
    label: "Healthy",
  },
  warning: {
    bar: "bg-amber-500",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
    label: "Warning",
  },
  near_limit: {
    bar: "bg-orange-500",
    badge: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400",
    label: "Near limit",
  },
  exceeded: {
    bar: "bg-red-600",
    badge: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
    label: "Exceeded",
  },
};

interface BudgetPerformanceListProps {
  budgets: Budget[];
  currency: string;
}

export function BudgetPerformanceList({ budgets, currency }: BudgetPerformanceListProps) {
  const atRisk = budgets.filter((b) => b.status !== "healthy").length;

  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Budget performance</h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Which budgets are at risk of being exceeded? (always reflects the current month)
      </p>

      {budgets.length === 0 ? (
        <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
          You haven&apos;t set any budgets yet.
        </p>
      ) : (
        <>
          {atRisk > 0 && (
            <p className="mt-2 text-xs font-medium text-amber-600 dark:text-amber-400">
              {atRisk} budget{atRisk === 1 ? "" : "s"} at risk this month
            </p>
          )}
          <ul className="mt-4 flex flex-col gap-3">
            {[...budgets]
              .sort((a, b) => b.percent_used - a.percent_used)
              .map((budget) => {
                const style = STATUS_STYLES[budget.status];
                return (
                  <li key={budget.id}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
                        <span aria-hidden="true">{budget.category_icon}</span>
                        {budget.category_name}
                      </span>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          style.badge
                        )}
                      >
                        {style.label}
                      </span>
                    </div>
                    <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                      <div
                        className={cn("h-full rounded-full", style.bar)}
                        style={{ width: `${Math.min(budget.percent_used, 100)}%` }}
                      />
                    </div>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {formatMoney(budget.spent_minor, currency)} of{" "}
                      {formatMoney(budget.amount_minor, currency)} &middot;{" "}
                      {budget.percent_used.toFixed(1)}%
                    </p>
                  </li>
                );
              })}
          </ul>
        </>
      )}
    </Card>
  );
}
