import { apiRequest } from "@/lib/api-client";
import type { RecurrenceFrequency } from "@/lib/recurring-transactions";

export interface Subscription {
  id: string;
  recurring_transaction_id: string;
  name: string;
  account_id: string;
  account_name: string;
  category_id: string | null;
  category_name: string | null;
  category_icon: string | null;
  category_color: string | null;
  amount_minor: number;
  currency: string;
  frequency: RecurrenceFrequency;

  monthly_cost_minor: number;
  yearly_cost_minor: number;
  next_renewal_date: string;

  is_active: boolean;

  // null = insufficient evidence, no claim made. true/false = an
  // evidence-based claim either way. unused_reason always explains which.
  is_possibly_unused: boolean | null;
  unused_reason: string;

  created_at: string;
  updated_at: string;
}

export interface SubscriptionCreateInput {
  name: string;
  account_id: string;
  category_id?: string | null;
  amount_minor: number;
  frequency: RecurrenceFrequency;
  start_date: string;
}

export interface SubscriptionUpdateInput {
  name?: string;
  account_id?: string;
  category_id?: string | null;
  clear_category?: boolean;
  amount_minor?: number;
  frequency?: RecurrenceFrequency;
}

export async function listSubscriptions(accessToken: string): Promise<Subscription[]> {
  return apiRequest<Subscription[]>("/api/v1/subscriptions", { accessToken });
}

export async function createSubscription(
  accessToken: string,
  input: SubscriptionCreateInput
): Promise<Subscription> {
  return apiRequest<Subscription>("/api/v1/subscriptions", {
    method: "POST",
    accessToken,
    body: input,
  });
}

export async function updateSubscription(
  accessToken: string,
  subscriptionId: string,
  input: SubscriptionUpdateInput
): Promise<Subscription> {
  return apiRequest<Subscription>(`/api/v1/subscriptions/${subscriptionId}`, {
    method: "PUT",
    accessToken,
    body: input,
  });
}

export async function deactivateSubscription(
  accessToken: string,
  subscriptionId: string
): Promise<void> {
  await apiRequest(`/api/v1/subscriptions/${subscriptionId}`, {
    method: "DELETE",
    accessToken,
  });
}

/**
 * Total monthly/yearly cost across only the ACTIVE subscriptions - a
 * deactivated subscription no longer costs anything going forward, so it
 * never contributes to either total. Pure aggregation of server-computed
 * per-subscription figures; no new cost math happens here.
 */
export function calculateActiveTotals(subscriptions: Subscription[]): {
  monthlyTotal: number;
  yearlyTotal: number;
} {
  const active = subscriptions.filter((s) => s.is_active);
  return {
    monthlyTotal: active.reduce((sum, s) => sum + s.monthly_cost_minor, 0),
    yearlyTotal: active.reduce((sum, s) => sum + s.yearly_cost_minor, 0),
  };
}
