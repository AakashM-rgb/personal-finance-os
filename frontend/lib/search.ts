import { apiRequest } from "@/lib/api-client";
import type { Transaction as TransactionType } from "@/lib/transactions";

export const SEARCH_MAX_QUERY_LENGTH = 200;

export const SEARCH_EXAMPLES = [
  "food last month",
  "Amazon purchases above ₹1000",
  "transport expenses in August",
  "biggest expenses this year",
  "weekend spending",
  "subscriptions this month",
];

export type TransactionKind = TransactionType["type"];

/** A slimmed, search-result-safe projection of a transaction - matches
 * backend/app/ai/tools/schemas.py::TransactionSummary, reused as-is for
 * search results. */
export interface SearchResultTransaction {
  id: string;
  occurred_at: string;
  type: TransactionKind;
  amount_minor: number;
  currency: string;
  category_name: string | null;
  merchant: string | null;
  description: string | null;
}

export interface InterpretedCriteria {
  search_text: string | null;
  category_name: string | null;
  start_date: string | null;
  end_date: string | null;
  min_amount_minor: number | null;
  max_amount_minor: number | null;
  transaction_type: TransactionKind | null;
  is_weekend_only: boolean;
  subscriptions_only: boolean;
  sort: "date_desc" | "date_asc" | "amount_desc" | "amount_asc";
  limit: number;
  currency: string;
}

export interface CategoryCandidate {
  id: string;
  name: string;
  icon: string;
}

export interface SearchResponse {
  interpretation: InterpretedCriteria;
  requires_confirmation: boolean;
  ambiguity_reason: string | null;
  ambiguous_categories: CategoryCandidate[];
  results: SearchResultTransaction[];
  result_count: number;
  total_matching: number;
  limited: boolean;
  provider: string;
}

export async function searchFinancial(
  accessToken: string,
  query: string,
  options: { confirmed?: boolean; categoryOverrideId?: string } = {}
): Promise<SearchResponse> {
  return apiRequest<SearchResponse>("/api/v1/search/financial", {
    method: "POST",
    accessToken,
    body: {
      query,
      confirmed: options.confirmed ?? false,
      category_override_id: options.categoryOverrideId ?? null,
    },
  });
}
