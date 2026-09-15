import { Card } from "@/components/ui/card";
import { formatMoney } from "@/lib/money";
import type { NetWorthReport } from "@/lib/reports";
import { cn } from "@/lib/utils";

import { NetWorthTrendChart } from "./net-worth-trend-chart";
import { StatTile, StatTileGrid } from "./stat-tile";

export function NetWorthReportView({ report }: { report: NetWorthReport }) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Net worth report</h2>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">As of today</p>
        <div className="mt-4">
          <StatTileGrid>
            <StatTile
              label="Net worth"
              value={formatMoney(report.net_worth_minor, report.currency)}
              tone={report.net_worth_minor >= 0 ? "positive" : "negative"}
            />
            <StatTile
              label="Assets"
              value={formatMoney(report.total_assets_minor, report.currency)}
              tone="positive"
            />
            <StatTile
              label="Liabilities"
              value={formatMoney(report.total_liabilities_minor, report.currency)}
              tone={report.total_liabilities_minor > 0 ? "negative" : "default"}
            />
          </StatTileGrid>
        </div>
      </Card>

      <NetWorthTrendChart trend={report.trend} currency={report.currency} />

      <Card>
        <h2 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Accounts</h2>
        {report.accounts.length === 0 ? (
          <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
            You haven&apos;t added any accounts yet.
          </p>
        ) : (
          <ul className="mt-4 flex flex-col gap-2">
            {report.accounts.map((account) => (
              <li
                key={account.account_id}
                className="flex items-center justify-between rounded-md border border-zinc-200 p-2.5 text-sm dark:border-zinc-800"
              >
                <div className="flex items-center gap-2">
                  <span className="text-zinc-900 dark:text-zinc-50">{account.name}</span>
                  {account.is_liability && (
                    <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-medium text-red-700 dark:bg-red-950 dark:text-red-400">
                      Liability
                    </span>
                  )}
                </div>
                <span
                  className={cn(
                    "font-medium",
                    account.is_liability
                      ? "text-red-600 dark:text-red-400"
                      : "text-zinc-900 dark:text-zinc-50"
                  )}
                >
                  {formatMoney(account.balance_minor, account.currency)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
