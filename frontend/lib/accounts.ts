import { apiRequest } from "@/lib/api-client";

export const ACCOUNT_TYPES = [
  "bank_account",
  "cash",
  "credit_card",
  "upi",
  "savings_account",
  "wallet",
] as const;

export type AccountType = (typeof ACCOUNT_TYPES)[number];

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  bank_account: "Bank Account",
  cash: "Cash",
  credit_card: "Credit Card",
  upi: "UPI",
  savings_account: "Savings Account",
  wallet: "Wallet",
};

export interface CreditCardFields {
  credit_limit_minor: number;
  statement_day: number;
  payment_due_day: number;
  minimum_payment_minor: number | null;
}

export interface CreditCardDetails extends CreditCardFields {
  available_credit_minor: number;
  utilization_percent: number;
}

export interface Account {
  id: string;
  name: string;
  type: AccountType;
  balance_minor: number;
  currency: string;
  institution_name: string | null;
  is_active: boolean;
  credit_card: CreditCardDetails | null;
  created_at: string;
  updated_at: string;
}

export interface AccountCreateInput {
  name: string;
  type: AccountType;
  balance_minor: number;
  currency: string;
  institution_name?: string | null;
  credit_card?: CreditCardFields | null;
}

export interface AccountUpdateInput {
  name?: string;
  balance_minor?: number;
  currency?: string;
  institution_name?: string | null;
  credit_card?: CreditCardFields | null;
}

export async function listAccounts(
  accessToken: string,
  options: { includeInactive?: boolean } = {}
): Promise<Account[]> {
  const query = options.includeInactive ? "?include_inactive=true" : "";
  return apiRequest<Account[]>(`/api/v1/accounts${query}`, { accessToken });
}

export async function createAccount(
  accessToken: string,
  input: AccountCreateInput
): Promise<Account> {
  return apiRequest<Account>("/api/v1/accounts", { method: "POST", accessToken, body: input });
}

export async function updateAccount(
  accessToken: string,
  accountId: string,
  input: AccountUpdateInput
): Promise<Account> {
  return apiRequest<Account>(`/api/v1/accounts/${accountId}`, {
    method: "PUT",
    accessToken,
    body: input,
  });
}

export async function archiveAccount(accessToken: string, accountId: string): Promise<void> {
  await apiRequest(`/api/v1/accounts/${accountId}`, { method: "DELETE", accessToken });
}
