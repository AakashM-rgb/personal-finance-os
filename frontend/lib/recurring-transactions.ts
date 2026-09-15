import { apiRequest } from "@/lib/api-client";
import type { Transaction } from "@/lib/transactions";

export const RECURRENCE_FREQUENCIES = [
  "daily",
  "weekly",
  "monthly",
  "quarterly",
  "yearly",
] as const;
export type RecurrenceFrequency = (typeof RECURRENCE_FREQUENCIES)[number];

export const FREQUENCY_LABELS: Record<RecurrenceFrequency, string> = {
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  quarterly: "Quarterly",
  yearly: "Yearly",
};

export interface RecurringTransaction {
  id: string;
  name: string;
  account_id: string;
  account_name: string;
  category_id: string | null;
  category_name: string | null;
  category_icon: string | null;
  category_color: string | null;
  type: "income" | "expense";
  amount_minor: number;
  currency: string;
  frequency: RecurrenceFrequency;
  start_date: string;
  next_occurrence_date: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RecurringTransactionCreateInput {
  name: string;
  account_id: string;
  category_id?: string | null;
  type: "income" | "expense";
  amount_minor: number;
  frequency: RecurrenceFrequency;
  start_date: string;
}

export interface RecurringTransactionUpdateInput {
  name?: string;
  account_id?: string;
  category_id?: string | null;
  clear_category?: boolean;
  type?: "income" | "expense";
  amount_minor?: number;
  frequency?: RecurrenceFrequency;
}

export async function listRecurringTransactions(
  accessToken: string
): Promise<RecurringTransaction[]> {
  return apiRequest<RecurringTransaction[]>("/api/v1/recurring-transactions", { accessToken });
}

export async function createRecurringTransaction(
  accessToken: string,
  input: RecurringTransactionCreateInput
): Promise<RecurringTransaction> {
  return apiRequest<RecurringTransaction>("/api/v1/recurring-transactions", {
    method: "POST",
    accessToken,
    body: input,
  });
}

export async function updateRecurringTransaction(
  accessToken: string,
  recurringId: string,
  input: RecurringTransactionUpdateInput
): Promise<RecurringTransaction> {
  return apiRequest<RecurringTransaction>(`/api/v1/recurring-transactions/${recurringId}`, {
    method: "PUT",
    accessToken,
    body: input,
  });
}

export async function deactivateRecurringTransaction(
  accessToken: string,
  recurringId: string
): Promise<void> {
  await apiRequest(`/api/v1/recurring-transactions/${recurringId}`, {
    method: "DELETE",
    accessToken,
  });
}

export async function generateRecurringTransactions(accessToken: string): Promise<Transaction[]> {
  return apiRequest<Transaction[]>("/api/v1/recurring-transactions/generate", {
    method: "POST",
    accessToken,
  });
}

/**
 * True when an active schedule's next occurrence date has already passed
 * without being generated yet (i.e. "Generate now" has something to catch
 * up on for it). ISO "YYYY-MM-DD" strings compare correctly with plain `<`,
 * so no Date parsing is needed. Pure UI-status derivation only - it never
 * decides whether generation actually runs.
 */
export function isOverdue(recurring: RecurringTransaction, todayIso: string): boolean {
  return recurring.is_active && recurring.next_occurrence_date < todayIso;
}
