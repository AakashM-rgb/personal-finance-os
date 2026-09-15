import { apiRequest } from "@/lib/api-client";
import type { Budget } from "@/lib/budgets";
import type { RecurrenceFrequency } from "@/lib/recurring-transactions";

export const ANALYTICS_RANGES = [
  "current_month",
  "previous_month",
  "last_3_months",
  "last_6_months",
  "last_12_months",
  "custom",
] as const;
export type AnalyticsRange = (typeof ANALYTICS_RANGES)[number];

export const ANALYTICS_RANGE_LABELS: Record<AnalyticsRange, string> = {
  current_month: "Current month",
  previous_month: "Previous month",
  last_3_months: "Last 3 months",
  last_6_months: "Last 6 months",
  last_12_months: "Last 12 months",
  custom: "Custom range",
};

export type Granularity = "day" | "month";
export type TrendDirection = "increasing" | "decreasing" | "flat";

export interface TrendInfo {
  direction: TrendDirection | null;
  percent_change: number | null;
}

export interface SpendingOverTimePoint {
  period: string;
  amount_minor: number;
}

export interface SpendingOverTime {
  granularity: Granularity;
  points: SpendingOverTimePoint[];
  trend: TrendInfo;
}

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

export interface IncomeVsExpense {
  total_income_minor: number;
  total_expense_minor: number;
  net_minor: number;
  is_spending_more_than_earning: boolean;
}

export interface SavingsTrendPoint {
  period: string;
  income_minor: number;
  expense_minor: number;
  savings_minor: number;
  savings_rate: number | null;
}

export interface SavingsTrend {
  points: SavingsTrendPoint[];
  trend: TrendInfo;
}

export interface DailySpendingPoint {
  day: string;
  amount_minor: number;
}

export interface DailySpending {
  points: DailySpendingPoint[];
  highest_day: string | null;
  highest_amount_minor: number;
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

export interface Analytics {
  currency: string;
  range: AnalyticsRange;
  date_from: string;
  date_to: string;

  spending_over_time: SpendingOverTime;
  category_breakdown: CategoryBreakdown;
  income_vs_expense: IncomeVsExpense;
  savings_trend: SavingsTrend;
  budget_performance: Budget[];
  daily_spending: DailySpending;
  recurring_expense_breakdown: RecurringExpenseBreakdown;
}

export interface AnalyticsQuery {
  range: AnalyticsRange;
  custom_from?: string;
  custom_to?: string;
}

function buildQuery(query: AnalyticsQuery): string {
  const params = new URLSearchParams();
  params.set("range", query.range);
  if (query.custom_from) params.set("custom_from", query.custom_from);
  if (query.custom_to) params.set("custom_to", query.custom_to);
  return `?${params.toString()}`;
}

export async function getAnalytics(accessToken: string, query: AnalyticsQuery): Promise<Analytics> {
  return apiRequest<Analytics>(`/api/v1/analytics${buildQuery(query)}`, { accessToken });
}

export type TrendTone = "positive" | "negative" | "neutral" | "unknown";

/**
 * Maps a raw trend direction to a display tone, given whether "increasing"
 * is good news for this particular chart (spending increasing is bad news;
 * savings increasing is good news) - pure UI-labeling logic, no new
 * calculation happens here, the direction itself always comes from the
 * server's real trend calculation.
 */
export function resolveTrendTone(
  direction: TrendDirection | null,
  increasingIsGood: boolean
): TrendTone {
  if (direction === null) return "unknown";
  if (direction === "flat") return "neutral";
  const isIncreasing = direction === "increasing";
  const isGoodNews = isIncreasing === increasingIsGood;
  return isGoodNews ? "positive" : "negative";
}
