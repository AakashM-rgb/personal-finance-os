import { BudgetPerformanceList } from "@/components/analytics/budget-performance-list";
import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { BudgetReport } from "@/lib/reports";

import { StatTile, StatTileGrid } from "./stat-tile";

export function BudgetReportView({ report }: { report: BudgetReport }) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Budget report</h2>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">Current month</p>
        <div className="mt-4">
          <StatTileGrid>
            <StatTile
              label="Budgeted"
              value={formatMoney(report.total_budgeted_minor, report.currency)}
            />
            <StatTile
              label="Spent"
              value={formatMoney(report.total_spent_minor, report.currency)}
              tone={report.total_spent_minor > report.total_budgeted_minor ? "negative" : "default"}
            />
            <StatTile
              label="At risk"
              value={String(report.at_risk_count)}
              tone={report.at_risk_count > 0 ? "negative" : "default"}
            />
            <StatTile
              label="Exceeded"
              value={String(report.exceeded_count)}
              tone={report.exceeded_count > 0 ? "negative" : "default"}
            />
          </StatTileGrid>
        </div>
      </Card>

      <BudgetPerformanceList budgets={report.items} currency={report.currency} />
    </div>
  );
}
