import { Card } from "@/components/ui/card";
import type { CategoryBreakdown } from "@/lib/analytics";
import { formatMoney } from "@/lib/money";

interface CategoryBreakdownListProps {
  data: CategoryBreakdown;
  currency: string;
}

export function CategoryBreakdownList({ data, currency }: CategoryBreakdownListProps) {
  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Category breakdown</h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">Where is my money going?</p>

      {data.items.length === 0 ? (
        <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
          No expenses recorded in this range yet.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-3">
          {data.items.map((item) => (
            <li key={item.category_id ?? "uncategorized"}>
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
                  <span aria-hidden="true">{item.icon}</span>
                  {item.name}
                </span>
                <span className="text-zinc-500 dark:text-zinc-400">
                  {formatMoney(item.amount_minor, currency)} &middot; {item.percent.toFixed(1)}%
                </span>
              </div>
              <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.min(item.percent, 100)}%`, backgroundColor: item.color }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
