import { BudgetPerformanceList } from "@/components/analytics/budget-performance-list";
import { CategoryBreakdownList } from "@/components/analytics/category-breakdown-list";
import { RecurringExpenseBreakdownList } from "@/components/analytics/recurring-expense-breakdown-list";
import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { MonthlyReport } from "@/lib/reports";

import { StatTile, StatTileGrid } from "./stat-tile";

export function MonthlyReportView({ report }: { report: MonthlyReport }) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
          Monthly summary
        </h2>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {report.date_from} to {report.date_to}
        </p>
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
              hint={report.savings_rate === null ? "No income recorded this month" : undefined}
            />
          </StatTileGrid>
        </div>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        <CategoryBreakdownList data={report.category_breakdown} currency={report.currency} />
        <BudgetPerformanceList budgets={report.budget_performance} currency={report.currency} />
        <div className="sm:col-span-2">
          <RecurringExpenseBreakdownList
            data={report.recurring_expense_breakdown}
            currency={report.currency}
          />
        </div>
      </div>
    </div>
  );
}
