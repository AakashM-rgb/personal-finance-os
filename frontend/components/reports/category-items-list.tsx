import type { CategoryReportItem } from "@/lib/reports";
import { formatMoney } from "@/lib/money";

interface CategoryItemsListProps {
  items: CategoryReportItem[];
  currency: string;
  emptyMessage: string;
}

export function CategoryItemsList({ items, currency, emptyMessage }: CategoryItemsListProps) {
  if (items.length === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">{emptyMessage}</p>;
  }

  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.category_id ?? "uncategorized"}>
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
              <span aria-hidden="true">{item.icon}</span>
              {item.name}
            </span>
            <span className="text-zinc-500 dark:text-zinc-400">
              {formatMoney(item.amount_minor, currency)} &middot; {item.percent.toFixed(1)}% &middot;{" "}
              {item.transaction_count} txn{item.transaction_count === 1 ? "" : "s"}
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
  );
}
