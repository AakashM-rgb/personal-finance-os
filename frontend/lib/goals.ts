import { apiRequest } from "@/lib/api-client";

export interface SavingsGoal {
  id: string;
  name: string;
  target_amount_minor: number;
  current_amount_minor: number;
  currency: string;
  target_date: string;

  progress_percent: number;
  remaining_minor: number;
  is_completed: boolean;
  days_remaining: number;
  // null when the target date is today or already in the past and the
  // goal isn't yet complete - there's no future time window left to
  // spread the remaining amount over.
  required_monthly_savings_minor: number | null;
  required_weekly_savings_minor: number | null;

  created_at: string;
  updated_at: string;
}

export interface SavingsGoalCreateInput {
  name: string;
  target_amount_minor: number;
  current_amount_minor?: number;
  currency?: string;
  target_date: string;
}

export interface SavingsGoalUpdateInput {
  name?: string;
  target_amount_minor?: number;
  current_amount_minor?: number;
  currency?: string;
  target_date?: string;
}

export async function listGoals(accessToken: string): Promise<SavingsGoal[]> {
  return apiRequest<SavingsGoal[]>("/api/v1/goals", { accessToken });
}

export async function createGoal(
  accessToken: string,
  input: SavingsGoalCreateInput
): Promise<SavingsGoal> {
  return apiRequest<SavingsGoal>("/api/v1/goals", { method: "POST", accessToken, body: input });
}

export async function updateGoal(
  accessToken: string,
  goalId: string,
  input: SavingsGoalUpdateInput
): Promise<SavingsGoal> {
  return apiRequest<SavingsGoal>(`/api/v1/goals/${goalId}`, {
    method: "PUT",
    accessToken,
    body: input,
  });
}

export async function deleteGoal(accessToken: string, goalId: string): Promise<void> {
  await apiRequest(`/api/v1/goals/${goalId}`, { method: "DELETE", accessToken });
}

export type GoalStatus = "completed" | "overdue" | "due_today" | "on_track";

/**
 * Pure UI-status derivation from the goal's own server-computed fields
 * (is_completed, days_remaining) - no new calculation happens here, just a
 * label for how the card should look. Mirrors the deterministic status
 * classification pattern used for budgets.
 */
export function getGoalStatus(goal: SavingsGoal): GoalStatus {
  if (goal.is_completed) return "completed";
  if (goal.days_remaining < 0) return "overdue";
  if (goal.days_remaining === 0) return "due_today";
  return "on_track";
}
