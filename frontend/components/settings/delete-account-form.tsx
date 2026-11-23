"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { useAuth } from "@/lib/auth-context";
import { toFormErrors } from "@/lib/form-errors";

/** What the user must type to confirm. Kept in one place so the label, the
 * check and the tests can't drift apart. */
export const DELETE_CONFIRMATION = "DELETE";

/** Backend field -> the inline error slot this form renders for it. */
const API_FIELD_SLOTS: Record<string, "password"> = { password: "password" };

export function DeleteAccountForm() {
  const { deleteAccount } = useAuth();
  const router = useRouter();

  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [confirmationError, setConfirmationError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const missingPassword = password ? null : "Enter your password to confirm.";
    const wrongConfirmation =
      confirmation === DELETE_CONFIRMATION ? null : `Type ${DELETE_CONFIRMATION} to confirm.`;
    setPasswordError(missingPassword);
    setConfirmationError(wrongConfirmation);
    if (missingPassword || wrongConfirmation) return;

    setIsSubmitting(true);
    try {
      await deleteAccount(password);
      // The signed-in shell's guard sends a cleared session to /login anyway;
      // going there directly avoids racing it (same as "log out everywhere").
      router.replace("/login");
    } catch (err) {
      const mapped = toFormErrors(err, API_FIELD_SLOTS);
      setPasswordError(
        mapped.fieldErrors.password ? "Your password is incorrect." : null
      );
      setFormError(mapped.formError);
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium text-red-700 dark:text-red-400">Delete account</h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          This permanently deletes your account and everything in it: accounts, transactions,
          budgets, goals, subscriptions, receipts and settings. It can&apos;t be undone.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="delete_account_password">Password</Label>
          <PasswordInput
            id="delete_account_password"
            visibilityLabel="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={passwordError ? true : undefined}
          />
          <FormError message={passwordError} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="delete_account_confirmation">
            Type {DELETE_CONFIRMATION} to confirm
          </Label>
          <Input
            id="delete_account_confirmation"
            autoComplete="off"
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            aria-invalid={confirmationError ? true : undefined}
          />
          <FormError message={confirmationError} />
        </div>
      </div>

      <FormError message={formError} />

      <div>
        <Button
          type="submit"
          className="bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-700"
          isLoading={isSubmitting}
        >
          Delete my account
        </Button>
      </div>
    </form>
  );
}
