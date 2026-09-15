import { Card } from "@/components/ui/card";
import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import type { ExpenseReport } from "@/lib/reports";

import { CategoryItemsList } from "./category-items-list";
import { StatTile, StatTileGrid } from "./stat-tile";
import { TimeSeriesChart } from "./time-series-chart";
import { TopTransactionsList } from "./top-transactions-list";

const EXPENSE_COLOR = "#dc2626"; // red-600

interface ExpenseReportViewProps {
  report: ExpenseReport;
  accounts: Account[];
  categories: Category[];
}

export function ExpenseReportView({ report, accounts, categories }: ExpenseReportViewProps) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Expense report</h2>
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
            <StatTile label="Transactions" value={String(report.transaction_count)} />
            <StatTile
              label="Recurring"
              value={formatMoney(report.recurring_expense_minor, report.currency)}
            />
            <StatTile
              label="Non-recurring"
              value={formatMoney(report.non_recurring_expense_minor, report.currency)}
            />
          </StatTileGrid>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Expenses over time</h2>
        <div className="mt-4">
          <TimeSeriesChart
            points={report.over_time}
            currency={report.currency}
            color={EXPENSE_COLOR}
            emptyMessage="No expenses recorded in this range yet."
          />
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">By category</h2>
        <div className="mt-4">
          <CategoryItemsList
            items={report.by_category}
            currency={report.currency}
            emptyMessage="No expenses recorded in this range yet."
          />
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
          Largest expense transactions
        </h2>
        <div className="mt-4">
          <TopTransactionsList
            transactions={report.largest_transactions}
            accounts={accounts}
            categories={categories}
            emptyMessage="No expenses recorded in this range yet."
          />
        </div>
      </Card>
    </div>
  );
}
