"use client";

import { useEffect, useState } from "react";

import { BudgetReportView } from "@/components/reports/budget-report-view";
import { CategoryReportView } from "@/components/reports/category-report-view";
import { ExpenseReportView } from "@/components/reports/expense-report-view";
import { ExportButtons } from "@/components/reports/export-buttons";
import { IncomeReportView } from "@/components/reports/income-report-view";
import { MonthlyReportView } from "@/components/reports/monthly-report-view";
import { NetWorthReportView } from "@/components/reports/net-worth-report-view";
import { ReportControls } from "@/components/reports/report-controls";
import { ReportTypeTabs } from "@/components/reports/report-type-tabs";
import { SavingsReportView } from "@/components/reports/savings-report-view";
import { YearlyReportView } from "@/components/reports/yearly-report-view";
import { Skeleton } from "@/components/ui/skeleton";
import { listAccounts, type Account } from "@/lib/accounts";
import type { AnalyticsRange } from "@/lib/analytics";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { listCategories, type Category } from "@/lib/categories";
import {
  downloadReportExport,
  getBudgetReport,
  getCategoryReport,
  getExpenseReport,
  getIncomeReport,
  getMonthlyReport,
  getNetWorthReport,
  getSavingsReport,
  getYearlyReport,
  rangeQueryParams,
  type BudgetReport,
  type CategoryReport,
  type ExportFormat,
  type ExpenseReport,
  type IncomeReport,
  type MonthlyReport,
  type NetWorthReport,
  type ReportType,
  type SavingsReport,
  type YearlyReport,
} from "@/lib/reports";

type ReportData =
  | { type: "monthly"; report: MonthlyReport }
  | { type: "yearly"; report: YearlyReport }
  | { type: "category"; report: CategoryReport }
  | { type: "income"; report: IncomeReport }
  | { type: "expense"; report: ExpenseReport }
  | { type: "budget"; report: BudgetReport }
  | { type: "savings"; report: SavingsReport }
  | { type: "net-worth"; report: NetWorthReport };

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ReportsPage() {
  const { accessToken } = useAuth();
  const now = new Date();

  const [reportType, setReportType] = useState<ReportType>("monthly");
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [range, setRange] = useState<AnalyticsRange>("current_month");
  const [customFrom, setCustomFrom] = useState(todayIso());
  const [customTo, setCustomTo] = useState(todayIso());

  const [data, setData] = useState<ReportData | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const isCustomIncomplete =
    range === "custom" &&
    (!customFrom || !customTo) &&
    ["category", "income", "expense", "savings"].includes(reportType);

  useEffect(() => {
    if (!accessToken) return;
    let isMounted = true;
    void Promise.all([listAccounts(accessToken), listCategories(accessToken)]).then(
      ([accountsData, categoriesData]) => {
        if (isMounted) {
          setAccounts(accountsData);
          setCategories(categoriesData);
        }
      }
    );
    return () => {
      isMounted = false;
    };
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken || isCustomIncomplete) return;
    let isMounted = true;

    const rangeQuery = { range, custom_from: customFrom, custom_to: customTo };

    const fetchReport: Promise<ReportData> =
      reportType === "monthly"
        ? getMonthlyReport(accessToken, year, month).then((report) => ({ type: "monthly", report }))
        : reportType === "yearly"
          ? getYearlyReport(accessToken, year).then((report) => ({ type: "yearly", report }))
          : reportType === "category"
            ? getCategoryReport(accessToken, rangeQuery).then((report) => ({ type: "category", report }))
            : reportType === "income"
              ? getIncomeReport(accessToken, rangeQuery).then((report) => ({ type: "income", report }))
              : reportType === "expense"
                ? getExpenseReport(accessToken, rangeQuery).then((report) => ({
                    type: "expense",
                    report,
                  }))
                : reportType === "budget"
                  ? getBudgetReport(accessToken).then((report) => ({ type: "budget", report }))
                  : reportType === "savings"
                    ? getSavingsReport(accessToken, rangeQuery).then((report) => ({
                        type: "savings",
                        report,
                      }))
                    : getNetWorthReport(accessToken).then((report) => ({ type: "net-worth", report }));

    void fetchReport
      .then((result) => {
        if (isMounted) {
          setData(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setData(null);
          setError(err instanceof ApiError ? err.message : "Failed to load this report.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [accessToken, reportType, year, month, range, customFrom, customTo, isCustomIncomplete, reloadToken]);

  async function handleExport(format: ExportFormat) {
    if (!accessToken) return;
    const params = rangeQueryParams({ range, custom_from: customFrom, custom_to: customTo });
    params.set("format", format);

    if (reportType === "monthly") {
      params.set("year", String(year));
      params.set("month", String(month));
    } else if (reportType === "yearly") {
      params.set("year", String(year));
    }

    await downloadReportExport(
      accessToken,
      `/api/v1/reports/${reportType}/export?${params.toString()}`,
      format,
      `${reportType}-report`
    );
  }

  const isLoading = data === null && !error && !isCustomIncomplete;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Reports</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Detailed answers about your money, exportable as CSV, Excel, or PDF.
        </p>
      </div>

      <ReportTypeTabs value={reportType} onChange={setReportType} />

      <div className="flex flex-wrap items-end justify-between gap-4">
        <ReportControls
          reportType={reportType}
          year={year}
          month={month}
          onYearChange={setYear}
          onMonthChange={setMonth}
          range={range}
          customFrom={customFrom}
          customTo={customTo}
          onRangeChange={setRange}
          onCustomFromChange={setCustomFrom}
          onCustomToChange={setCustomTo}
        />
        {data && !error && <ExportButtons onExport={handleExport} />}
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-400">
          {error}{" "}
          <button
            type="button"
            onClick={() => setReloadToken((n) => n + 1)}
            className="font-medium underline"
          >
            Try again
          </button>
        </div>
      )}

      {isCustomIncomplete && !error && (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Choose both a start and end date for a custom range.
          </p>
        </div>
      )}

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      )}

      {data && !error && (
        <>
          {data.type === "monthly" && <MonthlyReportView report={data.report} />}
          {data.type === "yearly" && <YearlyReportView report={data.report} />}
          {data.type === "category" && <CategoryReportView report={data.report} />}
          {data.type === "income" && (
            <IncomeReportView report={data.report} accounts={accounts} categories={categories} />
          )}
          {data.type === "expense" && (
            <ExpenseReportView report={data.report} accounts={accounts} categories={categories} />
          )}
          {data.type === "budget" && <BudgetReportView report={data.report} />}
          {data.type === "savings" && <SavingsReportView report={data.report} />}
          {data.type === "net-worth" && <NetWorthReportView report={data.report} />}
        </>
      )}
    </div>
  );
}
