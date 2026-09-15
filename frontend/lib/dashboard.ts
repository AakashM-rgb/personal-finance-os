import { apiRequest } from "@/lib/api-client";
import type { Transaction } from "@/lib/transactions";

export interface HealthScoreFactor {
  key: string;
  label: string;
  weight: number;
  score: number | null;
  detail: string;
  is_positive: boolean | null;
}

export interface HealthScore {
  score: number | null;
  label: string | null;
  factors: HealthScoreFactor[];
}

export interface CategoryBreakdownItem {
  category_id: string | null;
  name: string;
  icon: string;
  color: string;
  amount_minor: number;
  percent: number;
}

export interface MonthlySpending {
  current_month_expense_minor: number;
  previous_month_expense_minor: number;
  percent_change: number | null;
  daily_average_minor: number;
  projected_month_expense_minor: number;
  days_elapsed: number;
  days_in_month: number;
}

export interface UpcomingPayment {
  account_id: string;
  account_name: string;
  kind: string;
  due_date: string;
  amount_minor: number;
  description: string;
}

export interface Dashboard {
  currency: string;
  generated_at: string;
  total_balance_minor: number;
  net_worth_minor: number;
  total_income_minor: number;
  total_expense_minor: number;
  savings_minor: number;
  savings_rate: number | null;
  monthly_spending: MonthlySpending;
  category_breakdown: CategoryBreakdownItem[];
  recent_transactions: Transaction[];
  upcoming_payments: UpcomingPayment[];
  health_score: HealthScore;
  excluded_other_currency_accounts: number;
}

export async function getDashboard(accessToken: string): Promise<Dashboard> {
  return apiRequest<Dashboard>("/api/v1/dashboard", { accessToken });
}
