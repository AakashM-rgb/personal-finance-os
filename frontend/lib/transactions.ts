import { apiRequest, apiRequestWithMeta } from "@/lib/api-client";

export const TRANSACTION_TYPES = ["income", "expense", "transfer"] as const;
export type TransactionType = (typeof TRANSACTION_TYPES)[number];

export interface Transaction {
  id: string;
  account_id: string;
  transfer_account_id: string | null;
  category_id: string | null;
  type: TransactionType;
  amount_minor: number;
  currency: string;
  merchant: string | null;
  description: string | null;
  notes: string | null;
  payment_method: string | null;
  tags: string[];
  occurred_at: string;
  is_recurring: boolean;
  recurring_transaction_id: string | null;
  /** Set only for a transaction imported by the automatic sync feature
   * (see lib/sync.ts) - null for every manual, recurring-generated, or
   * receipt-derived transaction. */
  linked_account_id: string | null;
  /** True only for a low-confidence synced transaction awaiting user
   * review - see backend app.models.transaction. Always false otherwise. */
  needs_review: boolean;
  created_at: string;
  updated_at: string;
}

export interface TransactionInput {
  account_id: string;
  type: TransactionType;
  amount_minor: number;
  transfer_account_id?: string | null;
  category_id?: string | null;
  merchant?: string | null;
  description?: string | null;
  notes?: string | null;
  payment_method?: string | null;
  tags?: string[];
  occurred_at?: string;
  is_recurring?: boolean;
}

export type TransactionUpdateInput = Partial<TransactionInput> & {
  clear_category?: boolean;
  /** Opt-in only - persists the transaction's (merchant, category) pair as
   * a reusable rule (see lib/merchant-rules.ts) applied to future synced
   * transactions from the same merchant. Never set unless the user
   * explicitly asked to remember it on this specific edit. */
  remember_category_for_merchant?: boolean;
};

export interface TransactionFilters {
  q?: string;
  category_id?: string;
  account_id?: string;
  type?: TransactionType;
  date_from?: string;
  date_to?: string;
  amount_min?: number;
  amount_max?: number;
  is_recurring?: boolean;
  tags?: string[];
  sort_by?: "occurred_at" | "amount_minor" | "created_at";
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface TransactionListResult {
  transactions: Transaction[];
  total: number;
}

export interface QuickAddParseResult {
  raw_text: string;
  amount_minor: number | null;
  category_id: string | null;
  category_name: string | null;
  description: string | null;
  occurred_at: string;
  confidence: "high" | "medium" | "low";
  error: string | null;
}

function buildQuery(filters: TransactionFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      value.forEach((v) => params.append(key, String(v)));
    } else {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function listTransactions(
  accessToken: string,
  filters: TransactionFilters = {}
): Promise<TransactionListResult> {
  const { data, meta } = await apiRequestWithMeta<Transaction[]>(
    `/api/v1/transactions${buildQuery(filters)}`,
    { accessToken }
  );
  return { transactions: data, total: (meta?.count as number) ?? data.length };
}

export async function createTransaction(
  accessToken: string,
  input: TransactionInput,
  idempotencyKey?: string
): Promise<Transaction> {
  return apiRequest<Transaction>("/api/v1/transactions", {
    method: "POST",
    accessToken,
    body: input,
    idempotencyKey,
  });
}

export async function updateTransaction(
  accessToken: string,
  transactionId: string,
  input: TransactionUpdateInput
): Promise<Transaction> {
  return apiRequest<Transaction>(`/api/v1/transactions/${transactionId}`, {
    method: "PUT",
    accessToken,
    body: input,
  });
}

export async function deleteTransaction(accessToken: string, transactionId: string): Promise<void> {
  await apiRequest(`/api/v1/transactions/${transactionId}`, { method: "DELETE", accessToken });
}

export async function duplicateTransaction(
  accessToken: string,
  transactionId: string
): Promise<Transaction> {
  return apiRequest<Transaction>(`/api/v1/transactions/${transactionId}/duplicate`, {
    method: "POST",
    accessToken,
  });
}

export async function parseQuickAdd(
  accessToken: string,
  text: string
): Promise<QuickAddParseResult> {
  return apiRequest<QuickAddParseResult>("/api/v1/transactions/quick-add/parse", {
    method: "POST",
    accessToken,
    body: { text },
  });
}
