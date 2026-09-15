import { CategoryBreakdownList } from "@/components/analytics/category-breakdown-list";
import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { YearlyReport } from "@/lib/reports";

import { StatTile, StatTileGrid } from "./stat-tile";
import { YearlyTrendChart } from "./yearly-trend-chart";

export function YearlyReportView({ report }: { report: YearlyReport }) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Yearly summary</h2>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">{report.year}</p>
        <div className="mt-4">
          <StatTileGrid>
            <StatTile
              label="Income"
              value={formatMoney(report.total_income_minor, report.currency)}
              tone="positive"
            />
            <StatTile
              label="Expenses"
              value={formatMoney(report.total_expense_minor, report.currency)}
              tone="negative"
            />
            <StatTile
              label="Net cash flow"
              value={formatMoney(report.net_cash_flow_minor, report.currency)}
              tone={report.net_cash_flow_minor >= 0 ? "positive" : "negative"}
            />
            <StatTile
              label="Savings rate"
              value={report.savings_rate !== null ? `${report.savings_rate.toFixed(1)}%` : "N/A"}
              hint={report.savings_rate === null ? "No income recorded this year" : undefined}
            />
          </StatTileGrid>
        </div>
      </Card>

      <YearlyTrendChart
        incomeTrend={report.monthly_income_trend}
        expenseTrend={report.monthly_expense_trend}
        savingsTrend={report.monthly_savings_trend}
        currency={report.currency}
      />

      <CategoryBreakdownList data={report.category_totals} currency={report.currency} />
    </div>
  );
}
