import { Card } from "@/components/ui/card";
import type { CategoryBreakdownItem } from "@/lib/dashboard";
import { formatMoney } from "@/lib/money";

interface CategoryBreakdownProps {
  items: CategoryBreakdownItem[];
  currency: string;
}

export function CategoryBreakdown({ items, currency }: CategoryBreakdownProps) {
  return (
    <Card>
      <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
        Where your money went this month
      </h2>

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
          No expenses recorded yet this month.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-3">
          {items.map((item) => (
            <li key={item.category_id ?? "uncategorized"}>
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
                  <span aria-hidden="true">{item.icon}</span>
                  {item.name}
                </span>
                <span className="text-zinc-500 dark:text-zinc-400">
                  {formatMoney(item.amount_minor, currency)} · {item.percent.toFixed(1)}%
                </span>
              </div>
              <div className="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${item.percent}%`, backgroundColor: item.color }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
