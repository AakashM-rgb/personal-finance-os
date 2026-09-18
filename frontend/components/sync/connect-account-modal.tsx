"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Modal } from "@/components/ui/modal";
import { ApiError } from "@/lib/api-client";
import { completeLink, initiateLink, type LinkedAccount } from "@/lib/sync";

interface ConnectAccountModalProps {
  accessToken: string;
  onConnected: (linkedAccounts: LinkedAccount[]) => void;
  onCancel: () => void;
}

/**
 * A development-safe mock connection flow - this app has no real bank,
 * Account Aggregator, or payment provider integration (see
 * app.sync.provider.mock.MockSyncProvider). `consent_handle` only ever
 * lives in this function's own local variable for the moment it takes to
 * call completeLink; it is never put in component state, storage, a URL,
 * or rendered anywhere.
 */
export function ConnectAccountModal({ accessToken, onConnected, onCancel }: ConnectAccountModalProps) {
  const [isConnecting, setIsConnecting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleConnect() {
    setIsConnecting(true);
    setErrorMessage(null);
    try {
      const initiation = await initiateLink(accessToken);
      const linkedAccounts = await completeLink(accessToken, initiation.consent_handle);
      onConnected(linkedAccounts);
    } catch (err) {
      setErrorMessage(
        err instanceof ApiError ? err.message : "Failed to connect. Please try again."
      );
      setIsConnecting(false);
    }
  }

  return (
    <Modal title="Connect financial account" onClose={onCancel}>
      <div className="flex flex-col gap-4">
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
          This is a development/demo connection to a simulated institution (&quot;Mock
          Bank&quot;). No real bank, UPI app, or payment provider is ever contacted.
        </div>

        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          🔒 Connecting grants <strong>read-only</strong> access to transaction history only. This
          app can never make payments, transfers, or withdrawals, and will never ask for a UPI
          PIN, card PIN, CVV, OTP, or banking password.
        </p>

        <FormError message={errorMessage} />

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={isConnecting}>
            Cancel
          </Button>
          <Button variant="primary" isLoading={isConnecting} onClick={() => void handleConnect()}>
            Connect Mock Bank
          </Button>
        </div>
      </div>
    </Modal>
  );
}
