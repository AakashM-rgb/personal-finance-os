import { Card } from "@/components/ui/card";

interface Feature {
  icon: string;
  title: string;
  description: string;
}

const FEATURES: Feature[] = [
  {
    icon: "🏠",
    title: "Unified dashboard",
    description: "Balances, net worth, income, expenses, and a financial health score - computed from your real ledger, not a guess.",
  },
  {
    icon: "💳",
    title: "Transaction management",
    description: "Record income, expenses, and transfers across accounts, with categories, tags, and fast quick-add entry.",
  },
  {
    icon: "🔁",
    title: "Recurring & subscriptions",
    description: "Set up bills and income that repeat on a schedule, and track what your subscriptions really cost you.",
  },
  {
    icon: "📅",
    title: "Financial calendar",
    description: "See upcoming bills, income, and scheduled payments laid out day by day.",
  },
  {
    icon: "🧾",
    title: "Reports & exports",
    description: "Monthly, yearly, category, income, and expense reports - exportable as PDF, CSV, or Excel.",
  },
  {
    icon: "🔍",
    title: "Natural-language search",
    description: "Ask for “food last month” or “Amazon purchases above ₹1,000” and get a validated, filtered result - never free-form SQL.",
  },
  {
    icon: "📷",
    title: "Receipt management",
    description: "Scan a receipt, review what was extracted, and turn it into a transaction only once you confirm the details.",
  },
  {
    icon: "📡",
    title: "Offline-safe expense entry",
    description: "Add an expense with no signal - it's saved on your device and syncs automatically, safely, once you're back online.",
  },
];

export function FeatureGrid() {
  return (
    <section id="features" className="mx-auto max-w-6xl px-6 py-20 sm:py-28">
      <div className="mx-auto max-w-2xl text-center">
        <p className="text-xs font-semibold tracking-[0.2em] text-zinc-500 uppercase dark:text-zinc-500">
          Features
        </p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl dark:text-zinc-50">
          Everything your money needs. In one place.
        </h2>
        <p className="mt-4 text-base text-zinc-600 dark:text-zinc-400">
          A single, connected system instead of a spreadsheet, a budgeting app, and a folder of
          receipts.
        </p>
      </div>

      <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((feature) => (
          <Card
            key={feature.title}
            className="flex flex-col gap-3 transition-shadow hover:shadow-md"
          >
            <span
              className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-100 text-xl dark:bg-zinc-900"
              aria-hidden="true"
            >
              {feature.icon}
            </span>
            <h3 className="font-medium text-zinc-900 dark:text-zinc-50">{feature.title}</h3>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">{feature.description}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
