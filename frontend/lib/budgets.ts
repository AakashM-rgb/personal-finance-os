import { apiRequest } from "@/lib/api-client";

export type BudgetStatus = "healthy" | "warning" | "near_limit" | "exceeded";

export interface Budget {
  id: string;
  category_id: string;
  category_name: string;
  category_icon: string;
  category_color: string;
  currency: string;
  amount_minor: number;
  spent_minor: number;
  remaining_minor: number;
  percent_used: number;
  status: BudgetStatus;
  warning_message: string | null;
  projected_month_minor: number;
  days_elapsed: number;
  days_in_month: number;
  created_at: string;
  updated_at: string;
}

export interface BudgetCreateInput {
  category_id: string;
  amount_minor: number;
}

export interface BudgetUpdateInput {
  amount_minor: number;
}

export interface BudgetSuggestion {
  category_id: string;
  category_name: string;
  category_icon: string;
  category_color: string;
  suggested_amount_minor: number;
  based_on: string;
}

export async function listBudgets(accessToken: string): Promise<Budget[]> {
  return apiRequest<Budget[]>("/api/v1/budgets", { accessToken });
}

export async function listBudgetSuggestions(accessToken: string): Promise<BudgetSuggestion[]> {
  return apiRequest<BudgetSuggestion[]>("/api/v1/budgets/suggestions", { accessToken });
}

export async function createBudget(
  accessToken: string,
  input: BudgetCreateInput
): Promise<Budget> {
  return apiRequest<Budget>("/api/v1/budgets", { method: "POST", accessToken, body: input });
}

export async function updateBudget(
  accessToken: string,
  budgetId: string,
  input: BudgetUpdateInput
): Promise<Budget> {
  return apiRequest<Budget>(`/api/v1/budgets/${budgetId}`, {
    method: "PUT",
    accessToken,
    body: input,
  });
}

export async function deleteBudget(accessToken: string, budgetId: string): Promise<void> {
  await apiRequest(`/api/v1/budgets/${budgetId}`, { method: "DELETE", accessToken });
}
