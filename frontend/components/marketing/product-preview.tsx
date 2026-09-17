import { CategoryBreakdown } from "@/components/dashboard/category-breakdown";
import { HealthScoreMeter } from "@/components/dashboard/health-score-meter";
import { MonthlySpendingCard } from "@/components/dashboard/monthly-spending-card";
import { StatCard } from "@/components/dashboard/stat-card";
import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import {
  DEMO_CURRENCY,
  demoCategoryBreakdown,
  demoHealthScore,
  demoMonthlySpending,
  demoRecentTransactions,
  demoSavingsRatePercentRounded,
  demoStats,
} from "@/components/marketing/demo-data";

const TYPE_COLOR: Record<string, string> = {
  income: "text-emerald-600 dark:text-emerald-400",
  expense: "text-red-600 dark:text-red-400",
  transfer: "text-zinc-600 dark:text-zinc-400",
};
const TYPE_SIGN: Record<string, string> = { income: "+", expense: "-", transfer: "" };

function RecentTransactionsPreview() {
  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Recent transactions</h2>
      <ul className="mt-3 flex flex-col">
        {demoRecentTransactions.map((txn) => (
          <li
            key={txn.id}
            className="flex items-center justify-between gap-3 border-b border-zinc-100 py-2.5 last:border-0 dark:border-zinc-800"
          >
            <div className="flex min-w-0 items-center gap-2.5">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm"
                style={{ backgroundColor: `${txn.categoryColor}22` }}
                aria-hidden="true"
              >
                {txn.categoryIcon}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
                  {txn.description}
                </p>
                <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                  {txn.accountName}
                </p>
              </div>
            </div>
            <span className={`shrink-0 text-sm font-medium ${TYPE_COLOR[txn.type]}`}>
              {TYPE_SIGN[txn.type]}
              {formatMoney(txn.amountMinor, DEMO_CURRENCY)}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/**
 * The hero's product visual - a real, working composition of the app's
 * ACTUAL dashboard components (StatCard, MonthlySpendingCard,
 * HealthScoreMeter, CategoryBreakdown), fed hand-written illustrative
 * numbers instead of a live API response. This is deliberately a real
 * screenshot-equivalent of the product's own UI, not a separate mockup -
 * see components/marketing/demo-data.ts for why the numbers are safe to
 * use here and clearly not real customer data.
 */
export function ProductPreview() {
  return (
    <div
      aria-label="Illustrative product preview with example data"
      className="rounded-2xl border border-zinc-200 bg-zinc-50/60 p-3 shadow-[0_1px_2px_rgba(0,0,0,0.04),0_16px_40px_-24px_rgba(0,0,0,0.25)] sm:p-4 dark:border-zinc-800 dark:bg-zinc-900/40"
    >
      <div className="flex items-center justify-between px-2 pb-3">
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <span className="h-2.5 w-2.5 rounded-full bg-zinc-300 dark:bg-zinc-700" />
          <span className="h-2.5 w-2.5 rounded-full bg-zinc-300 dark:bg-zinc-700" />
          <span className="h-2.5 w-2.5 rounded-full bg-zinc-300 dark:bg-zinc-700" />
        </div>
        <span className="rounded-full bg-zinc-200/70 px-2.5 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          Example data
        </span>
      </div>

      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Total balance" value={formatMoney(demoStats.totalBalanceMinor, DEMO_CURRENCY)} />
          <StatCard label="Net worth" value={formatMoney(demoStats.netWorthMinor, DEMO_CURRENCY)} />
          <StatCard
            label="Income"
            value={formatMoney(demoStats.incomeMinor, DEMO_CURRENCY)}
            sublabel="This month"
          />
          <StatCard
            label="Savings rate"
            value={`${demoSavingsRatePercentRounded}%`}
            sublabel="This month"
          />
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <MonthlySpendingCard spending={demoMonthlySpending} currency={DEMO_CURRENCY} />
          <HealthScoreMeter healthScore={demoHealthScore} />
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <CategoryBreakdown items={demoCategoryBreakdown} currency={DEMO_CURRENCY} />
          <RecentTransactionsPreview />
        </div>
      </div>
    </div>
  );
}
