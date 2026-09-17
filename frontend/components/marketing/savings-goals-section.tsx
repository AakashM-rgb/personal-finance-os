import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import { DEMO_CURRENCY, demoGoal } from "@/components/marketing/demo-data";

export function SavingsGoalsSection() {
  return (
    <section className="border-t border-zinc-100 dark:border-zinc-900">
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-12 px-6 py-20 sm:py-28 lg:grid-cols-2 lg:items-center lg:gap-16">
        <div
          aria-label="Illustrative savings goal preview with example data"
          className="order-2 flex flex-col gap-3 lg:order-1"
        >
          <div className="flex justify-end">
            <span className="rounded-full bg-zinc-200/70 px-2.5 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              Example data
            </span>
          </div>
          <Card className="flex flex-col gap-3">
            <div className="flex items-start justify-between">
              <span className="font-medium text-zinc-900 dark:text-zinc-50">{demoGoal.name}</span>
              <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-400">
                On track
              </span>
            </div>

            <div>
              <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                {formatMoney(demoGoal.currentAmountMinor, DEMO_CURRENCY)}
                <span className="text-sm font-normal text-zinc-500 dark:text-zinc-400">
                  {" "}
                  / {formatMoney(demoGoal.targetAmountMinor, DEMO_CURRENCY)}
                </span>
              </p>
              <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div
                  role="progressbar"
                  aria-valuenow={demoGoal.progressPercent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className="h-full rounded-full bg-blue-600"
                  style={{ width: `${demoGoal.progressPercent}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {demoGoal.progressPercent.toFixed(1)}% saved
              </p>
            </div>

            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Target date: <span className="font-medium">{demoGoal.targetDateLabel}</span>
            </p>

            <p className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
              Save {formatMoney(demoGoal.requiredMonthlyMinor, DEMO_CURRENCY)}/month to reach your
              target by {demoGoal.targetDateLabel}.
            </p>
          </Card>
        </div>

        <div className="order-1 lg:order-2">
          <p className="text-xs font-semibold tracking-[0.2em] text-zinc-500 uppercase dark:text-zinc-500">
            Savings goals
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl dark:text-zinc-50">
            Give every goal a plan.
          </h2>
          <p className="mt-4 text-base text-zinc-600 dark:text-zinc-400">
            Set a target amount and date, and see exactly how much to save each month or week to
            get there - recalculated automatically as you save.
          </p>
        </div>
      </div>
    </section>
  );
}
