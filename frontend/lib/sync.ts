/**
 * API client wrapper for the automatic transaction sync feature
 * (backend: app.api.v1.sync). This connects to a MockSyncProvider only -
 * see app.sync.provider - never a real bank, Account Aggregator, or other
 * external financial provider. Every field here mirrors
 * backend/app/schemas/sync.py exactly; nothing here ever carries a PIN,
 * CVV, OTP, password, or provider credential of any kind - the backend
 * itself never returns one (see app.services.sync_service).
 */
import { apiRequest } from "@/lib/api-client";

export const SYNC_CONSENT_STATUSES = [
  "pending",
  "active",
  "paused",
  "revoked",
  "expired",
] as const;
export type SyncConsentStatus = (typeof SYNC_CONSENT_STATUSES)[number];

export const SYNC_RUN_STATUSES = ["success", "partial", "failed"] as const;
export type SyncRunStatus = (typeof SYNC_RUN_STATUSES)[number];

export interface LinkedAccount {
  id: string;
  account_id: string | null;
  provider: string;
  external_institution_name: string;
  fip_reference: string | null;
  consent_status: SyncConsentStatus;
  consent_expires_at: string | null;
  masked_account_ref: string | null;
  last_synced_at: string | null;
  last_sync_status: string | null;
  created_at: string;
  updated_at: string;
}

/** `consent_handle` is a short-lived, opaque token - never a credential -
 * that must be passed straight back to completeLink to finish the mock
 * connection flow. Callers must never store this beyond that. */
export interface LinkInitiation {
  provider: string;
  consent_handle: string;
  redirect_url: string;
  expires_at: string;
}

export interface SyncRun {
  id: string;
  linked_account_id: string;
  started_at: string;
  completed_at: string | null;
  status: SyncRunStatus;
  transactions_fetched: number;
  transactions_created: number;
  transactions_skipped_duplicate: number;
  error_message: string | null;
}

export async function initiateLink(accessToken: string): Promise<LinkInitiation> {
  return apiRequest<LinkInitiation>("/api/v1/sync/links", {
    method: "POST",
    accessToken,
    body: {},
  });
}

export async function completeLink(
  accessToken: string,
  consentHandle: string
): Promise<LinkedAccount[]> {
  return apiRequest<LinkedAccount[]>(
    `/api/v1/sync/links/${encodeURIComponent(consentHandle)}/callback`,
    { method: "POST", accessToken }
  );
}

export async function listLinkedAccounts(accessToken: string): Promise<LinkedAccount[]> {
  return apiRequest<LinkedAccount[]>("/api/v1/sync/links", { accessToken });
}

export async function revokeLink(
  accessToken: string,
  linkedAccountId: string
): Promise<LinkedAccount> {
  return apiRequest<LinkedAccount>(`/api/v1/sync/links/${linkedAccountId}`, {
    method: "DELETE",
    accessToken,
  });
}

export async function triggerSync(
  accessToken: string,
  linkedAccountId: string
): Promise<SyncRun> {
  return apiRequest<SyncRun>(`/api/v1/sync/links/${linkedAccountId}/sync`, {
    method: "POST",
    accessToken,
  });
}

export async function listSyncRuns(
  accessToken: string,
  linkedAccountId: string
): Promise<SyncRun[]> {
  return apiRequest<SyncRun[]>(`/api/v1/sync/links/${linkedAccountId}/runs`, { accessToken });
}
