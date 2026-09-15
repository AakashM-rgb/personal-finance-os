import { apiRequest } from "@/lib/api-client";
import type { Budget } from "@/lib/budgets";
import type { AnalyticsRange, TrendInfo } from "@/lib/analytics";
import type { SavingsGoal } from "@/lib/goals";
import type { RecurrenceFrequency } from "@/lib/recurring-transactions";
import type { Transaction } from "@/lib/transactions";

export const REPORT_TYPES = [
  "monthly",
  "yearly",
  "category",
  "income",
  "expense",
  "budget",
  "savings",
  "net-worth",
] as const;
export type ReportType = (typeof REPORT_TYPES)[number];

export const REPORT_LABELS: Record<ReportType, string> = {
  monthly: "Monthly Report",
  yearly: "Yearly Report",
  category: "Category Report",
  income: "Income Report",
  expense: "Expense Report",
  budget: "Budget Report",
  savings: "Savings Report",
  "net-worth": "Net Worth Report",
};

export interface CategoryBreakdownItem {
  category_id: string | null;
  name: string;
  icon: string;
  color: string;
  amount_minor: number;
  percent: number;
}

export interface CategoryBreakdown {
  items: CategoryBreakdownItem[];
  total_expense_minor: number;
}

export interface RecurringExpenseBreakdownItem {
  recurring_transaction_id: string;
  name: string;
  frequency: RecurrenceFrequency;
  amount_minor: number;
  currency: string;
  is_active: boolean;
  is_subscription: boolean;
  scheduled_monthly_cost_minor: number;
  actual_paid_minor: number;
}

export interface RecurringExpenseBreakdown {
  items: RecurringExpenseBreakdownItem[];
  total_scheduled_monthly_minor: number;
  total_actual_paid_minor: number;
  recurring_share_of_expense_percent: number | null;
}

export interface MonthlyReport {
  year: number;
  month: number;
  currency: string;
  date_from: string;
  date_to: string;
  total_income_minor: number;
  total_expense_minor: number;
  net_cash_flow_minor: number;
  savings_minor: number;
  savings_rate: number | null;
  category_breakdown: CategoryBreakdown;
  budget_performance: Budget[];
  recurring_expense_breakdown: RecurringExpenseBreakdown;
}

export interface MonthlyAmount {
  month: string;
  amount_minor: number;
}

export interface YearlyReport {
  year: number;
  currency: string;
  total_income_minor: number;
  total_expense_minor: number;
  net_cash_flow_minor: number;
  savings_minor: number;
  savings_rate: number | null;
  monthly_income_trend: MonthlyAmount[];
  monthly_expense_trend: MonthlyAmount[];
  monthly_savings_trend: MonthlyAmount[];
  category_totals: CategoryBreakdown;
}

export interface CategoryReportItem {
  category_id: string | null;
  name: string;
  icon: string;
  color: string;
  amount_minor: number;
  percent: number;
  transaction_count: number;
}

export interface CategoryReport {
  currency: string;
  date_from: string;
  date_to: string;
  total_expense_minor: number;
  items: CategoryReportItem[];
}

export interface TimeSeriesPoint {
  period: string;
  amount_minor: number;
}

export interface IncomeReport {
  currency: string;
  date_from: string;
  date_to: string;
  total_income_minor: number;
  transaction_count: number;
  by_source: CategoryReportItem[];
  over_time: TimeSeriesPoint[];
  largest_transactions: Transaction[];
}

export interface ExpenseReport {
  currency: string;
  date_from: string;
  date_to: string;
  total_expense_minor: number;
  transaction_count: number;
  by_category: CategoryReportItem[];
  over_time: TimeSeriesPoint[];
  largest_transactions: Transaction[];
  recurring_expense_minor: number;
  non_recurring_expense_minor: number;
}

export interface BudgetReport {
  currency: string;
  items: Budget[];
  total_budgeted_minor: number;
  total_spent_minor: number;
  at_risk_count: number;
  exceeded_count: number;
}

export interface SavingsTrendPoint {
  period: string;
  income_minor: number;
  expense_minor: number;
  savings_minor: number;
  savings_rate: number | null;
}

export interface SavingsReport {
  currency: string;
  date_from: string;
  date_to: string;
  total_income_minor: number;
  total_expense_minor: number;
  savings_minor: number;
  savings_rate: number | null;
  trend: SavingsTrendPoint[];
  trend_direction: TrendInfo;
  goals: SavingsGoal[];
}

export interface NetWorthAccountItem {
  account_id: string;
  name: string;
  type: string;
  balance_minor: number;
  currency: string;
  is_liability: boolean;
}

export interface NetWorthTrendPoint {
  month: string;
  net_worth_minor: number;
}

export interface NetWorthReport {
  currency: string;
  total_assets_minor: number;
  total_liabilities_minor: number;
  net_worth_minor: number;
  accounts: NetWorthAccountItem[];
  trend: NetWorthTrendPoint[];
}

export interface ReportRangeQuery {
  range: AnalyticsRange;
  custom_from?: string;
  custom_to?: string;
}

export function rangeQueryParams(query: ReportRangeQuery): URLSearchParams {
  const params = new URLSearchParams();
  params.set("range", query.range);
  if (query.custom_from) params.set("custom_from", query.custom_from);
  if (query.custom_to) params.set("custom_to", query.custom_to);
  return params;
}

function rangeQuery(query: ReportRangeQuery): string {
  return rangeQueryParams(query).toString();
}

export async function getMonthlyReport(
  accessToken: string,
  year: number,
  month: number
): Promise<MonthlyReport> {
  return apiRequest<MonthlyReport>(`/api/v1/reports/monthly?year=${year}&month=${month}`, {
    accessToken,
  });
}

export async function getYearlyReport(accessToken: string, year: number): Promise<YearlyReport> {
  return apiRequest<YearlyReport>(`/api/v1/reports/yearly?year=${year}`, { accessToken });
}

export async function getCategoryReport(
  accessToken: string,
  query: ReportRangeQuery
): Promise<CategoryReport> {
  return apiRequest<CategoryReport>(`/api/v1/reports/category?${rangeQuery(query)}`, {
    accessToken,
  });
}

export async function getIncomeReport(
  accessToken: string,
  query: ReportRangeQuery
): Promise<IncomeReport> {
  return apiRequest<IncomeReport>(`/api/v1/reports/income?${rangeQuery(query)}`, { accessToken });
}

export async function getExpenseReport(
  accessToken: string,
  query: ReportRangeQuery
): Promise<ExpenseReport> {
  return apiRequest<ExpenseReport>(`/api/v1/reports/expense?${rangeQuery(query)}`, {
    accessToken,
  });
}

export async function getBudgetReport(accessToken: string): Promise<BudgetReport> {
  return apiRequest<BudgetReport>("/api/v1/reports/budget", { accessToken });
}

export async function getSavingsReport(
  accessToken: string,
  query: ReportRangeQuery
): Promise<SavingsReport> {
  return apiRequest<SavingsReport>(`/api/v1/reports/savings?${rangeQuery(query)}`, {
    accessToken,
  });
}

export async function getNetWorthReport(accessToken: string): Promise<NetWorthReport> {
  return apiRequest<NetWorthReport>("/api/v1/reports/net-worth", { accessToken });
}

export type ExportFormat = "csv" | "xlsx" | "pdf";

/**
 * Downloads a report export by fetching it with the caller's auth token
 * (export endpoints require the same Authorization header as every other
 * API call) and saving the resulting file client-side - a plain <a href>
 * link can't carry the auth header, so the fetch happens here instead.
 */
export async function downloadReportExport(
  accessToken: string,
  path: string,
  format: ExportFormat,
  filenameBase: string
): Promise<void> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) {
    throw new Error("Failed to generate the export.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${filenameBase}.${format}`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
