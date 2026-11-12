"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import { useAuth } from "@/lib/auth-context";
import { toFormErrors } from "@/lib/form-errors";
import { checkPasswordRules, isPasswordValid, PASSWORD_MAX_LENGTH } from "@/lib/password-rules";

type FieldKey = "current" | "next" | "confirm";

/** Backend field -> the inline error slot this form renders for it. */
const API_FIELD_SLOTS: Record<string, FieldKey> = {
  current_password: "current",
  new_password: "next",
  confirm_password: "confirm",
};

function validate(current: string, next: string, confirm: string): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {};
  if (!current) errors.current = "Enter your current password.";
  if (!isPasswordValid(next)) {
    errors.next =
      next.length > PASSWORD_MAX_LENGTH
        ? `Must be ${PASSWORD_MAX_LENGTH} characters or fewer.`
        : "New password doesn't meet the requirements below.";
  } else if (next === current) {
    errors.next = "New password must be different from your current password.";
  }
  if (!confirm) errors.confirm = "Confirm your new password.";
  else if (confirm !== next) errors.confirm = "Passwords don't match.";
  return errors;
}

export function ChangePasswordForm() {
  const { changePassword } = useAuth();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [didSucceed, setDidSucceed] = useState(false);

  const rules = checkPasswordRules(next);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setDidSucceed(false);

    const clientErrors = validate(current, next, confirm);
    setFieldErrors(clientErrors);
    if (Object.keys(clientErrors).length > 0) return;

    setIsSubmitting(true);
    try {
      await changePassword({
        current_password: current,
        new_password: next,
        confirm_password: confirm,
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      setDidSucceed(true);
    } catch (err) {
      const mapped = toFormErrors(err, API_FIELD_SLOTS);
      setFieldErrors(mapped.fieldErrors as Partial<Record<FieldKey, string>>);
      setFormError(mapped.formError);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Change password</h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Changing your password signs out every other device. You&apos;ll stay signed in here.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="current_password">Current password</Label>
          <PasswordInput
            id="current_password"
            visibilityLabel="current password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            aria-invalid={fieldErrors.current ? true : undefined}
          />
          <FormError message={fieldErrors.current ?? null} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new_password">New password</Label>
          <PasswordInput
            id="new_password"
            visibilityLabel="new password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            aria-invalid={fieldErrors.next ? true : undefined}
            aria-describedby="new_password_rules"
          />
          <FormError message={fieldErrors.next ?? null} />
          <ul id="new_password_rules" className="flex flex-col gap-0.5 text-xs">
            {rules.map((rule) => (
              <li
                key={rule.label}
                className={
                  rule.isMet
                    ? "text-emerald-700 dark:text-emerald-400"
                    : "text-zinc-500 dark:text-zinc-400"
                }
              >
                <span aria-hidden="true">{rule.isMet ? "✓" : "•"}</span> {rule.label}
                <span className="sr-only">{rule.isMet ? " (met)" : " (not met)"}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="confirm_password">Confirm new password</Label>
          <PasswordInput
            id="confirm_password"
            visibilityLabel="password confirmation"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            aria-invalid={fieldErrors.confirm ? true : undefined}
          />
          <FormError message={fieldErrors.confirm ?? null} />
        </div>
      </div>

      <FormError message={formError} />
      {didSucceed && (
        <p role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
          Password changed. Other devices have been signed out.
        </p>
      )}

      <div>
        <Button type="submit" variant="secondary" isLoading={isSubmitting}>
          Change password
        </Button>
      </div>
    </form>
  );
}
