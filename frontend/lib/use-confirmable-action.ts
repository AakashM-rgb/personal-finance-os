"use client";

import { useState } from "react";

import { getErrorMessage } from "@/lib/api-client";

/**
 * State for a one-shot async action (duplicate, generate…) whose failure must
 * be shown to the user rather than swallowed as an unhandled rejection.
 * `run` resolves to whether the action succeeded and never rejects.
 */
export function useAsyncAction(action: () => Promise<void>, fallbackError: string) {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(): Promise<boolean> {
    setIsPending(true);
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      setError(getErrorMessage(err, fallbackError));
      return false;
    } finally {
      setIsPending(false);
    }
  }

  return { isPending, error, run, clearError: () => setError(null) };
}

/**
 * A "click, then confirm" action (delete, archive, deactivate). On failure the
 * confirmation stays open showing the error, so the user can retry or cancel;
 * on success it closes (the item usually disappears from its list right after).
 */
export function useConfirmableAction(action: () => Promise<void>, fallbackError: string) {
  const [isConfirming, setIsConfirming] = useState(false);
  const { isPending, error, run, clearError } = useAsyncAction(action, fallbackError);

  return {
    isConfirming,
    isPending,
    error,
    start: () => {
      clearError();
      setIsConfirming(true);
    },
    cancel: () => {
      clearError();
      setIsConfirming(false);
    },
    confirm: async () => {
      if (await run()) setIsConfirming(false);
    },
  };
}
