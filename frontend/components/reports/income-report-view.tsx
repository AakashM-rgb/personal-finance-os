import { Card } from "@/components/ui/card";
import type { Account } from "@/lib/accounts";
import type { Category } from "@/lib/categories";
import { formatMoney } from "@/lib/money";
import type { IncomeReport } from "@/lib/reports";

import { CategoryItemsList } from "./category-items-list";
import { StatTile, StatTileGrid } from "./stat-tile";
import { TimeSeriesChart } from "./time-series-chart";
import { TopTransactionsList } from "./top-transactions-list";

const INCOME_COLOR = "#059669"; // emerald-600

interface IncomeReportViewProps {
  report: IncomeReport;
  accounts: Account[];
  categories: Category[];
}

export function IncomeReportView({ report, accounts, categories }: IncomeReportViewProps) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Income report</h2>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {report.date_from} to {report.date_to}
        </p>
        <div className="mt-4">
          <StatTileGrid>
            <StatTile
              label="Total income"
              value={formatMoney(report.total_income_minor, report.currency)}
              tone="positive"
            />
            <StatTile label="Transactions" value={String(report.transaction_count)} />
          </StatTileGrid>
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Income over time</h2>
        <div className="mt-4">
          <TimeSeriesChart
            points={report.over_time}
            currency={report.currency}
            color={INCOME_COLOR}
            emptyMessage="No income recorded in this range yet."
          />
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">By source</h2>
        <div className="mt-4">
          <CategoryItemsList
            items={report.by_source}
            currency={report.currency}
            emptyMessage="No income recorded in this range yet."
          />
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
          Largest income transactions
        </h2>
        <div className="mt-4">
          <TopTransactionsList
            transactions={report.largest_transactions}
            accounts={accounts}
            categories={categories}
            emptyMessage="No income recorded in this range yet."
          />
        </div>
      </Card>
    </div>
  );
}
