import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { CategoryReport } from "@/lib/reports";

import { CategoryItemsList } from "./category-items-list";
import { StatTile, StatTileGrid } from "./stat-tile";

export function CategoryReportView({ report }: { report: CategoryReport }) {
  const uncategorized = report.items.find((item) => item.category_id === null);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Category report</h2>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {report.date_from} to {report.date_to}
        </p>
        <div className="mt-4">
          <StatTileGrid>
            <StatTile
              label="Total expenses"
              value={formatMoney(report.total_expense_minor, report.currency)}
              tone="negative"
            />
            <StatTile
              label="Categories"
              value={String(report.items.length)}
            />
            {uncategorized && (
              <StatTile
                label="Uncategorized"
                value={formatMoney(uncategorized.amount_minor, report.currency)}
                hint={`${uncategorized.percent.toFixed(1)}% of expenses`}
              />
            )}
          </StatTileGrid>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">By category</h2>
        <div className="mt-4">
          <CategoryItemsList
            items={report.items}
            currency={report.currency}
            emptyMessage="No expenses recorded in this range yet."
          />
        </div>
      </Card>
    </div>
  );
}
