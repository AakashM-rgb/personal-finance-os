/**
 * API client wrapper for persistent user merchant-categorization rules
 * (backend: app.api.v1.merchant_rules). The primary way a rule gets
 * created is the opt-in "Remember this category" checkbox on the
 * transaction edit form (see TransactionUpdateInput.remember_category_for_merchant
 * in lib/transactions.ts) - this module covers viewing and removing rules.
 */
import { apiRequest } from "@/lib/api-client";

export interface MerchantRule {
  id: string;
  merchant_key: string;
  category_id: string;
  category_name: string;
  category_icon: string;
  category_color: string;
  created_at: string;
  updated_at: string;
}

export async function listMerchantRules(accessToken: string): Promise<MerchantRule[]> {
  return apiRequest<MerchantRule[]>("/api/v1/merchant-rules", { accessToken });
}

export async function deleteMerchantRule(accessToken: string, ruleId: string): Promise<void> {
  await apiRequest(`/api/v1/merchant-rules/${ruleId}`, { method: "DELETE", accessToken });
}
