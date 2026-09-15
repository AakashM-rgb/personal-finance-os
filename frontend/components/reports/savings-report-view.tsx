import { SavingsTrendChart } from "@/components/analytics/savings-trend-chart";
import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { SavingsReport } from "@/lib/reports";

import { ReportGoalList } from "./report-goal-list";
import { StatTile, StatTileGrid } from "./stat-tile";

export function SavingsReportView({ report }: { report: SavingsReport }) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Savings report</h2>
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
              label="Savings"
              value={formatMoney(report.savings_minor, report.currency)}
              tone={report.savings_minor >= 0 ? "positive" : "negative"}
              hint="Income − Expenses"
            />
            <StatTile
              label="Savings rate"
              value={report.savings_rate !== null ? `${report.savings_rate.toFixed(1)}%` : "N/A"}
              hint={report.savings_rate === null ? "No income recorded in this range" : undefined}
            />
          </StatTileGrid>
        </div>
      </Card>

      <SavingsTrendChart
        data={{ points: report.trend, trend: report.trend_direction }}
        currency={report.currency}
      />

      <ReportGoalList goals={report.goals} />
    </div>
  );
}
