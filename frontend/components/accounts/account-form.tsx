"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-error";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  ACCOUNT_TYPE_LABELS,
  ACCOUNT_TYPES,
  type Account,
  type AccountCreateInput,
  type AccountType,
  type AccountUpdateInput,
} from "@/lib/accounts";
import { ApiError } from "@/lib/api-client";
import { CURRENCIES, minorUnitsToInputValue, parseMoneyToMinorUnits } from "@/lib/money";

interface AccountFormProps {
  account?: Account;
  onSubmit: (input: AccountCreateInput | AccountUpdateInput) => Promise<void>;
  onCancel: () => void;
}

export function AccountForm({ account, onSubmit, onCancel }: AccountFormProps) {
  const isEditing = account !== undefined;
  const [name, setName] = useState(account?.name ?? "");
  const [type, setType] = useState<AccountType>(account?.type ?? "bank_account");
  const [currency, setCurrency] = useState(account?.currency ?? "INR");
  const [balanceInput, setBalanceInput] = useState(
    account ? minorUnitsToInputValue(account.balance_minor, account.currency) : "0"
  );
  const [institutionName, setInstitutionName] = useState(account?.institution_name ?? "");

  const [creditLimitInput, setCreditLimitInput] = useState(
    account?.credit_card ? minorUnitsToInputValue(account.credit_card.credit_limit_minor, currency) : ""
  );
  const [statementDay, setStatementDay] = useState(
    String(account?.credit_card?.statement_day ?? 1)
  );
  const [paymentDueDay, setPaymentDueDay] = useState(
    String(account?.credit_card?.payment_due_day ?? 15)
  );
  const [minPaymentInput, setMinPaymentInput] = useState(
    account?.credit_card?.minimum_payment_minor != null
      ? minorUnitsToInputValue(account.credit_card.minimum_payment_minor, currency)
      : ""
  );

  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isCreditCard = type === "credit_card";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    const balanceMinor = parseMoneyToMinorUnits(balanceInput, currency);
    if (balanceMinor === null) {
      setFieldErrors({ balance: "Enter a valid amount." });
      return;
    }

    let creditCard = null;
    if (isCreditCard) {
      const creditLimitMinor = parseMoneyToMinorUnits(creditLimitInput, currency);
      if (creditLimitMinor === null || creditLimitMinor <= 0) {
        setFieldErrors({ credit_limit: "Enter a valid credit limit." });
        return;
      }
      const minimumPaymentMinor =
        minPaymentInput.trim() === "" ? null : parseMoneyToMinorUnits(minPaymentInput, currency);
      creditCard = {
        credit_limit_minor: creditLimitMinor,
        statement_day: Number(statementDay),
        payment_due_day: Number(paymentDueDay),
        minimum_payment_minor: minimumPaymentMinor,
      };
    }

    setIsSubmitting(true);
    try {
      if (isEditing) {
        await onSubmit({
          name,
          balance_minor: balanceMinor,
          currency,
          institution_name: institutionName || null,
          credit_card: creditCard,
        });
      } else {
        await onSubmit({
          name,
          type,
          balance_minor: balanceMinor,
          currency,
          institution_name: institutionName || null,
          credit_card: creditCard,
        });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors ?? {});
        if (!err.fieldErrors) setError(err.message);
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="account-name">Name</Label>
        <Input id="account-name" required value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      {isEditing ? (
        <div className="flex flex-col gap-1.5">
          <Label>Type</Label>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {ACCOUNT_TYPE_LABELS[type]} (cannot be changed)
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="account-type">Type</Label>
          <Select
            id="account-type"
            value={type}
            onChange={(e) => setType(e.target.value as AccountType)}
          >
            {ACCOUNT_TYPES.map((accountType) => (
              <option key={accountType} value={accountType}>
                {ACCOUNT_TYPE_LABELS[accountType]}
              </option>
            ))}
          </Select>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="account-balance">
            {isCreditCard ? "Current usage" : "Current balance"}
          </Label>
          <Input
            id="account-balance"
            inputMode="decimal"
            value={balanceInput}
            onChange={(e) => setBalanceInput(e.target.value)}
          />
          <FormError message={fieldErrors.balance ?? null} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="account-currency">Currency</Label>
          <Select
            id="account-currency"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {CURRENCIES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="account-institution">Institution name (optional)</Label>
        <Input
          id="account-institution"
          value={institutionName}
          onChange={(e) => setInstitutionName(e.target.value)}
        />
      </div>

      {isCreditCard && (
        <div className="flex flex-col gap-4 rounded-md border border-zinc-200 p-4 dark:border-zinc-800">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="account-credit-limit">Credit limit</Label>
            <Input
              id="account-credit-limit"
              inputMode="decimal"
              value={creditLimitInput}
              onChange={(e) => setCreditLimitInput(e.target.value)}
            />
            <FormError message={fieldErrors.credit_limit ?? null} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="account-statement-day">Statement day</Label>
              <Input
                id="account-statement-day"
                type="number"
                min={1}
                max={31}
                value={statementDay}
                onChange={(e) => setStatementDay(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="account-due-day">Payment due day</Label>
              <Input
                id="account-due-day"
                type="number"
                min={1}
                max={31}
                value={paymentDueDay}
                onChange={(e) => setPaymentDueDay(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="account-min-payment">Minimum payment (optional)</Label>
            <Input
              id="account-min-payment"
              inputMode="decimal"
              value={minPaymentInput}
              onChange={(e) => setMinPaymentInput(e.target.value)}
            />
          </div>
        </div>
      )}

      <FormError message={error} />

      <div className="mt-2 flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isSubmitting}>
          {isEditing ? "Save changes" : "Add account"}
        </Button>
      </div>
    </form>
  );
}
