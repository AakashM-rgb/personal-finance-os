import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import { DEMO_CURRENCY, demoBudgets, type DemoBudget } from "@/components/marketing/demo-data";

const STATUS_STYLES: Record<DemoBudget["status"], { bar: string; badge: string; label: string }> = {
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

/** Mirrors the real BudgetCard's visual language (components/budgets/
 * budget-card.tsx) - same status colors/progress bar - but read-only, no
 * edit/delete affordances, since this is a marketing preview a logged-out
 * visitor can't actually interact with. */
function BudgetPreviewCard({ budget }: { budget: DemoBudget }) {
  const style = STATUS_STYLES[budget.status];
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-xl" aria-hidden="true">
            {budget.categoryIcon}
          </span>
          <span className="font-medium text-zinc-900 dark:text-zinc-50">{budget.categoryName}</span>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${style.badge}`}>
          {style.label}
        </span>
      </div>

      <div>
        <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          {formatMoney(budget.spentMinor, DEMO_CURRENCY)}
          <span className="text-sm font-normal text-zinc-500 dark:text-zinc-400">
            {" "}
            / {formatMoney(budget.amountMinor, DEMO_CURRENCY)}
          </span>
        </p>
        <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
          <div
            role="progressbar"
            aria-valuenow={Math.min(budget.percentUsed, 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            className={`h-full rounded-full ${style.bar}`}
            style={{ width: `${Math.min(budget.percentUsed, 100)}%` }}
          />
        </div>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          {budget.percentUsed.toFixed(1)}% used · projected{" "}
          {formatMoney(budget.projectedMonthMinor, DEMO_CURRENCY)} this month
        </p>
      </div>
    </Card>
  );
}

export function BudgetSection() {
  return (
    <section className="border-t border-zinc-100 dark:border-zinc-900">
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-12 px-6 py-20 sm:py-28 lg:grid-cols-2 lg:items-center lg:gap-16">
        <div>
          <p className="text-xs font-semibold tracking-[0.2em] text-zinc-500 uppercase dark:text-zinc-500">
            Budgeting
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl dark:text-zinc-50">
            Know your limits before you cross them.
          </h2>
          <p className="mt-4 text-base text-zinc-600 dark:text-zinc-400">
            Set a monthly limit per category and see exactly where you stand - based on your
            actual recorded spending, with a projection of where you&apos;ll land by month&apos;s
            end.
          </p>
          <ul className="mt-6 flex flex-col gap-2 text-sm text-zinc-700 dark:text-zinc-300">
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-600 dark:bg-emerald-500" aria-hidden="true" />
              Healthy - comfortably within budget
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-orange-500" aria-hidden="true" />
              Near limit - approaching your cap
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-red-600" aria-hidden="true" />
              Exceeded - over budget for the month
            </li>
          </ul>
        </div>

        <div
          aria-label="Illustrative budget preview with example data"
          className="flex flex-col gap-3"
        >
          <div className="flex justify-end">
            <span className="rounded-full bg-zinc-200/70 px-2.5 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              Example data
            </span>
          </div>
          <div className="flex flex-col gap-4">
            {demoBudgets.map((budget) => (
              <BudgetPreviewCard key={budget.categoryName} budget={budget} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
