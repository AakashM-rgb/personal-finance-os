"use client";

import dynamic from "next/dynamic";

import { CategoryBreakdown } from "@/components/dashboard/category-breakdown";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DEMO_CURRENCY,
  demoCategoryBreakdown,
  demoSpendingOverTime,
} from "@/components/marketing/demo-data";

// Recharts is only needed for this below-the-fold chart - loaded on demand
// rather than in the main landing-page bundle.
const SpendingOverTimeChart = dynamic(
  () =>
    import("@/components/analytics/spending-over-time-chart").then(
      (mod) => mod.SpendingOverTimeChart
    ),
  { ssr: false, loading: () => <Skeleton className="h-72 w-full rounded-xl" /> }
);

export function AnalyticsSection() {
  return (
    <section id="analytics" className="border-t border-zinc-100 dark:border-zinc-900">
      <div className="mx-auto max-w-6xl px-6 py-20 sm:py-28">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold tracking-[0.2em] text-zinc-500 uppercase dark:text-zinc-500">
            Analytics
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl dark:text-zinc-50">
            See where your money actually goes.
          </h2>
          <p className="mt-4 text-base text-zinc-600 dark:text-zinc-400">
            Turn transaction history into patterns you can understand - spending trends, category
            breakdowns, and income vs. expenses, computed from your real ledger.
          </p>
        </div>

        <div
          aria-label="Illustrative analytics preview with example data"
          className="mt-12 flex flex-col gap-3"
        >
          <div className="flex justify-end">
            <span className="rounded-full bg-zinc-200/70 px-2.5 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              Example data
            </span>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <SpendingOverTimeChart data={demoSpendingOverTime} currency={DEMO_CURRENCY} />
            <CategoryBreakdown items={demoCategoryBreakdown} currency={DEMO_CURRENCY} />
          </div>
        </div>
      </div>
    </section>
  );
}
